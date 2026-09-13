#!/usr/bin/env python3
"""Handi on mail — the register of who was written to, and who answered.

Reads your mail and writes the register: every organisation you wrote to,
how many times, whether a person ever answered, which addresses bounced.
Non-response is the data point.

Input, one of:

    python3 workers/handi_mail.py --mbox ~/Downloads/Takeout/Mail/"All mail Including Spam and Trash.mbox"
    python3 workers/handi_mail.py --imap            # reads CXI_IMAP_* from the environment

Output, in ./register/ (gitignored):

    REGISTER.md      the ending first: counts, then who never answered
    contacts.csv     one row per organisation (counterparty domain)
    threads.csv      one row per conversation
    bounced.txt      addresses that bounced — stop using these

Settings, environment variables only:

    CXI_MY_EMAILS     comma-separated addresses that are you (else inferred: the most frequent sender)
    CXI_IMAP_HOST     imap.gmail.com
    CXI_IMAP_PORT     993
    CXI_IMAP_SSL      1            set 0 only for a local test server
    CXI_IMAP_USER     you@gmail.com
    CXI_IMAP_PASSWORD an app password, never your real one
    CXI_IMAP_FOLDER   "[Gmail]/All Mail"
    CXI_REGISTER_DIR  ./register

Standard library only. Deterministic: run it twice, get the same register.
"""
import argparse
import csv
import email
import email.utils
import imaplib
import mailbox
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from email.header import decode_header, make_header

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get("CXI_REGISTER_DIR", os.path.join(os.path.dirname(HERE), "register"))

AUTO_SUBJECT = re.compile(
    r"\b(automatic reply|auto-?reply|out of office|autoreply|we have received your|"
    r"ontvangstbevestiging|automatisch(e)? (antwoord|bericht)|afwezig|"
    r"your (request|message|email) has been received|ticket .*(created|received)|"
    r"do not reply|no-?reply)\b",
    re.I,
)
BOUNCE_SUBJECT = re.compile(
    r"(delivery status notification|undeliverable|mail delivery failed|delivery failure|"
    r"returned mail|could not be delivered|niet bezorgd|onbestelbaar)",
    re.I,
)
NOREPLY_LOCAL = re.compile(r"^(no-?reply|noreply|donotreply|do-not-reply|mailer-daemon|postmaster|bounce)", re.I)
RE_PREFIX = re.compile(r"^\s*((re|fwd?|aw|wg|antw|tr|betr)\s*:\s*)+", re.I)
PERSONAL_DOMAINS = {"gmail.com", "googlemail.com", "hotmail.com", "outlook.com", "live.com", "live.nl",
                    "yahoo.com", "icloud.com", "me.com", "proton.me", "protonmail.com", "ziggo.nl", "kpnmail.nl"}


def say(msg):
    print(f"[handi-mail] {msg}", flush=True)


def clean_header(v):
    if not v:
        return ""
    try:
        return str(make_header(decode_header(v)))
    except Exception:
        return str(v)


def addresses(msg, *fields):
    out = []
    for f in fields:
        for _, addr in email.utils.getaddresses([clean_header(msg.get(f, ""))]):
            addr = addr.strip().lower()
            if "@" in addr:
                out.append(addr)
    return out


def domain(addr):
    return addr.rsplit("@", 1)[-1] if "@" in addr else ""


def parse_date(msg):
    try:
        d = email.utils.parsedate_to_datetime(msg.get("Date", ""))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return None


def norm_subject(s):
    return RE_PREFIX.sub("", clean_header(s)).strip().lower()


def is_auto(msg, from_addr):
    if (msg.get("Auto-Submitted", "no").lower() != "no"):
        return True
    if msg.get("X-Autoreply") or msg.get("X-Autorespond"):
        return True
    if msg.get("Precedence", "").lower() in ("bulk", "auto_reply", "junk"):
        return True
    if NOREPLY_LOCAL.match(from_addr.split("@")[0]):
        return True
    return bool(AUTO_SUBJECT.search(clean_header(msg.get("Subject", ""))))


def is_bounce(msg, from_addr):
    if from_addr.startswith("mailer-daemon") or from_addr.startswith("postmaster"):
        return True
    if msg.get_content_type() == "multipart/report":
        return True
    return bool(BOUNCE_SUBJECT.search(clean_header(msg.get("Subject", ""))))


def bounced_addresses(msg):
    """Addresses named in a bounce: Final-Recipient / Original-Recipient headers, else any address in the text."""
    found = set()
    for part in msg.walk():
        for h in ("Final-Recipient", "Original-Recipient"):
            v = part.get(h, "")
            m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", v)
            if m:
                found.add(m.group(0).lower())
        if part.get_content_type() == "text/plain" and not found:
            try:
                text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
            except Exception:
                continue
            for m in re.finditer(r"[\w.+-]+@[\w.-]+\.\w+", text[:4000]):
                a = m.group(0).lower()
                if not NOREPLY_LOCAL.match(a.split("@")[0]):
                    found.add(a)
    return found


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
def read_mbox(path):
    say(f"reading {path}")
    for msg in mailbox.mbox(path):
        yield msg


def read_imap():
    host = os.environ.get("CXI_IMAP_HOST", "imap.gmail.com")
    port = int(os.environ.get("CXI_IMAP_PORT", "993" if os.environ.get("CXI_IMAP_SSL", "1") != "0" else "143"))
    user = os.environ["CXI_IMAP_USER"]
    pw = os.environ["CXI_IMAP_PASSWORD"]
    folder = os.environ.get("CXI_IMAP_FOLDER", "[Gmail]/All Mail")
    say(f"connecting to {host}:{port} as {user}, folder {folder}")
    box = imaplib.IMAP4_SSL(host, port) if os.environ.get("CXI_IMAP_SSL", "1") != "0" else imaplib.IMAP4(host, port)
    box.login(user, pw)
    box.select(f'"{folder}"', readonly=True)
    _, data = box.search(None, "ALL")
    ids = data[0].split()
    say(f"{len(ids)} messages")
    for i, uid in enumerate(ids, 1):
        _, parts = box.fetch(uid, "(BODY.PEEK[])")
        for p in parts:
            if isinstance(p, tuple):
                yield email.message_from_bytes(p[1])
        if i % 500 == 0:
            say(f"  {i}/{len(ids)}")
    box.logout()


# ---------------------------------------------------------------------------
# The register
# ---------------------------------------------------------------------------
def build(messages, my_emails):
    rows = []
    sender_count = defaultdict(int)
    for msg in messages:
        froms = addresses(msg, "From")
        if not froms:
            continue
        frm = froms[0]
        sender_count[frm] += 1
        rows.append({
            "msg": msg,
            "id": (msg.get("Message-ID") or "").strip(),
            "from": frm,
            "to": addresses(msg, "To", "Cc"),
            "date": parse_date(msg),
            "subject": clean_header(msg.get("Subject", "")),
            "nsubject": norm_subject(msg.get("Subject", "")),
            "refs": set(re.findall(r"<[^>]+>", (msg.get("References", "") + " " + msg.get("In-Reply-To", "")))),
        })
    if not my_emails:
        if not sender_count:
            return None
        me = max(sender_count.items(), key=lambda kv: kv[1])[0]
        my_emails = {me}
        say(f"assuming you are {me} (set CXI_MY_EMAILS to override)")
    my_emails = {m.lower() for m in my_emails}
    my_domains = {domain(m) for m in my_emails}

    # Thread key: walk References; else normalised subject + counterparty domain.
    id_to_key = {}
    threads = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["date"] or datetime.min.replace(tzinfo=timezone.utc)):
        key = None
        for ref in r["refs"]:
            if ref in id_to_key:
                key = id_to_key[ref]
                break
        if key is None:
            others = [a for a in ([r["from"]] + r["to"]) if a not in my_emails]
            cp = domain(others[0]) if others else "unknown"
            key = f"{r['nsubject']}|{cp}"
        if r["id"]:
            id_to_key[r["id"]] = key
        threads[key].append(r)

    thread_rows = []
    contacts = defaultdict(lambda: {
        "organisation": "", "addresses": set(), "threads": 0, "sent": 0, "first_sent": None, "last_sent": None,
        "human_replies": 0, "auto_replies": 0, "bounces": 0, "last_human_reply": None, "open_threads": 0,
    })
    dead = set()

    for key, msgs in threads.items():
        sent = [m for m in msgs if m["from"] in my_emails]
        if not sent:
            continue  # only threads you started or took part in as sender
        counterparties = sorted({a for m in sent for a in m["to"] if a not in my_emails})
        if not counterparties:
            continue
        cp_domain = domain(counterparties[0])
        org = cp_domain
        human, auto, bounce = [], [], []
        for m in msgs:
            if m["from"] in my_emails:
                continue
            if is_bounce(m["msg"], m["from"]):
                bounce.append(m)
                dead |= bounced_addresses(m["msg"]) & set(counterparties)
            elif is_auto(m["msg"], m["from"]):
                auto.append(m)
            else:
                human.append(m)
        last_sent = max((m["date"] for m in sent if m["date"]), default=None)
        last_human = max((m["date"] for m in human if m["date"]), default=None)
        is_open = last_human is None or (last_sent and last_human < last_sent)
        thread_rows.append({
            "organisation": org,
            "subject": sent[0]["subject"],
            "to": ";".join(counterparties),
            "sent": len(sent),
            "first_sent": min((m["date"] for m in sent if m["date"]), default=None),
            "last_sent": last_sent,
            "human_replies": len(human),
            "auto_replies": len(auto),
            "bounces": len(bounce),
            "last_human_reply": last_human,
            "status": "OPEN" if is_open else "answered",
        })
        c = contacts[org]
        c["organisation"] = org
        c["addresses"] |= set(counterparties)
        c["threads"] += 1
        c["sent"] += len(sent)
        c["human_replies"] += len(human)
        c["auto_replies"] += len(auto)
        c["bounces"] += len(bounce)
        c["open_threads"] += 1 if is_open else 0
        for m in sent:
            if m["date"]:
                c["first_sent"] = min(c["first_sent"] or m["date"], m["date"])
                c["last_sent"] = max(c["last_sent"] or m["date"], m["date"])
        if last_human:
            c["last_human_reply"] = max(c["last_human_reply"] or last_human, last_human)

    return {"threads": thread_rows, "contacts": list(contacts.values()), "dead": sorted(dead), "me": sorted(my_emails)}


def fmt(d):
    return d.strftime("%Y-%m-%d") if d else ""


def write(reg, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    contacts = sorted(reg["contacts"], key=lambda c: (-c["sent"], c["organisation"]))
    threads = sorted(reg["threads"], key=lambda t: (t["organisation"], t["first_sent"] or datetime.min.replace(tzinfo=timezone.utc)))

    with open(os.path.join(out_dir, "contacts.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["organisation", "addresses", "threads", "messages_sent", "first_sent", "last_sent",
                    "human_replies", "auto_replies", "bounces", "last_human_reply", "open_threads", "ever_answered_by_a_person"])
        for c in contacts:
            w.writerow([c["organisation"], ";".join(sorted(c["addresses"])), c["threads"], c["sent"], fmt(c["first_sent"]),
                        fmt(c["last_sent"]), c["human_replies"], c["auto_replies"], c["bounces"],
                        fmt(c["last_human_reply"]), c["open_threads"], "yes" if c["human_replies"] else "NO"])

    with open(os.path.join(out_dir, "threads.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["organisation", "subject", "to", "messages_sent", "first_sent", "last_sent",
                    "human_replies", "auto_replies", "bounces", "last_human_reply", "status"])
        for t in threads:
            w.writerow([t["organisation"], t["subject"], t["to"], t["sent"], fmt(t["first_sent"]), fmt(t["last_sent"]),
                        t["human_replies"], t["auto_replies"], t["bounces"], fmt(t["last_human_reply"]), t["status"]])

    with open(os.path.join(out_dir, "bounced.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(reg["dead"]) + ("\n" if reg["dead"] else ""))

    orgs = len(contacts)
    sent = sum(c["sent"] for c in contacts)
    answered = [c for c in contacts if c["human_replies"]]
    silent = [c for c in contacts if not c["human_replies"]]
    auto_only = [c for c in silent if c["auto_replies"]]
    lines = [
        "# The register", "",
        f"Written from: {', '.join(reg['me'])}", "",
        f"**{orgs} organisations written to, {sent} times. {len(answered)} ever answered with something a person wrote.**", "",
        f"- {len(silent)} never answered with a human word.",
        f"- {len(auto_only)} of those sent only an automatic acknowledgement.",
        (f"- {len(reg['dead'])} address{'es' if len(reg['dead']) != 1 else ''} bounced. "
         + ("They are" if len(reg['dead']) != 1 else "It is") + " in `bounced.txt`. Stop using "
         + ("them." if len(reg['dead']) != 1 else "it.")),
        "",
        "## Never answered by a person", "",
        "| organisation | times written | first | last | auto-replies | bounces |", "|---|---|---|---|---|---|",
    ]
    for c in sorted(silent, key=lambda c: -c["sent"]):
        lines.append(f"| {c['organisation']} | {c['sent']} | {fmt(c['first_sent'])} | {fmt(c['last_sent'])} | {c['auto_replies']} | {c['bounces']} |")
    lines += ["", "## Answered, but a thread is open again", "",
              "| organisation | open threads | last written | last human reply |", "|---|---|---|---|"]
    for c in sorted([c for c in answered if c["open_threads"]], key=lambda c: -c["open_threads"]):
        lines.append(f"| {c['organisation']} | {c['open_threads']} | {fmt(c['last_sent'])} | {fmt(c['last_human_reply'])} |")
    lines += ["", "## Method", "",
              "- A thread is every message sharing a References chain, else the same subject to the same domain.",
              "- A reply is human unless it is marked Auto-Submitted, comes from a no-reply address, or its subject reads as an automatic acknowledgement.",
              "- A bounce is a delivery report or a mailer-daemon message; the address it names goes to `bounced.txt`.",
              "- A thread is OPEN when nobody human has written since your last message.",
              "- Nothing here is judged. It is counted."]
    with open(os.path.join(out_dir, "REGISTER.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    say(f"{orgs} organisations, {sent} messages sent, {len(answered)} answered by a person, {len(reg['dead'])} dead addresses")
    say(f"written to {out_dir}/")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--mbox", help="path to an .mbox file (Google Takeout)")
    src.add_argument("--imap", action="store_true", help="read the mailbox over IMAP using CXI_IMAP_* variables")
    ap.add_argument("--out", default=OUT_DIR, help="output folder")
    args = ap.parse_args()

    my = {m.strip() for m in os.environ.get("CXI_MY_EMAILS", "").split(",") if m.strip()}
    messages = read_mbox(args.mbox) if args.mbox else read_imap()
    reg = build(messages, my)
    if reg is None:
        say("no messages found")
        sys.exit(1)
    write(reg, args.out)


if __name__ == "__main__":
    main()
