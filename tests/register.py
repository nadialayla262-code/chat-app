"""Handi on mail: a synthetic mailbox through workers/handi_mail.py, then loaded into the spine and read back."""
import csv, email.utils, json, mailbox, os, subprocess, sys, urllib.request
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TMP = os.path.join(HERE, ".tmp")
BASE = os.environ.get("CXI_TEST_URL", "http://127.0.0.1:8099")
fails = 0
def check(label, ok, detail=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'} {label}  {detail}"); fails += (not ok)

os.makedirs(TMP, exist_ok=True)
mbox_path = os.path.join(TMP, "test.mbox")
if os.path.exists(mbox_path): os.remove(mbox_path)
mb = mailbox.mbox(mbox_path)
base = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc); n = [0]
def add(frm, to, subj, body, days, refs=None, **hdr):
    n[0] += 1
    m = EmailMessage(); m["From"] = frm; m["To"] = to; m["Subject"] = subj
    m["Date"] = email.utils.format_datetime(base + timedelta(days=days)); m["Message-ID"] = f"<m{n[0]}@test>"
    if refs: m["In-Reply-To"] = refs; m["References"] = refs
    for k, v in hdr.items(): m[k.replace("_", "-")] = v
    m.set_content(body); mb.add(m); return m["Message-ID"]
me = "layna@example.test"
a1 = add(me, "klacht@igj.example", "Complaint about detention", "...", 0)
add("noreply@igj.example", me, "Ontvangstbevestiging: uw bericht", "Wij hebben uw bericht ontvangen.", 0, refs=a1)
add(me, "klacht@igj.example", "Complaint about detention", "follow up", 20, refs=a1)
add(me, "klacht@igj.example", "Second complaint", "...", 40)
add("info@igj.example", me, "Automatic reply: Second complaint", "out of office", 40, refs="<m4@test>", Auto_Submitted="auto-replied")
b1 = add(me, "jan@lawfirm.example", "Representation", "...", 1)
add("jan@lawfirm.example", me, "Re: Representation", "Yes, send the file.", 3, refs=b1)
add(me, "jan@lawfirm.example", "Re: Representation", "sent, any news?", 30, refs=b1)
c1 = add(me, "old.address@gemeente.example", "Woo request", "...", 5)
bounce = EmailMessage(); bounce["From"] = "mailer-daemon@googlemail.com"; bounce["To"] = me
bounce["Subject"] = "Delivery Status Notification (Failure)"; bounce["Date"] = email.utils.format_datetime(base + timedelta(days=5))
bounce["Message-ID"] = "<b1@test>"; bounce["In-Reply-To"] = c1
bounce.set_content("Your message wasn't delivered to old.address@gemeente.example because the address couldn't be found."); mb.add(bounce)
add(me, "woo@gemeente.example", "Woo request", "resent", 6)
add("anna@gemeente.example", me, "Re: Woo request", "We will respond within 4 weeks.", 8, refs="<m11@test>")
add("news@shop.example", me, "Sale!", "...", 2)
mb.flush()

out = os.path.join(TMP, "register")
subprocess.run([sys.executable, os.path.join(ROOT, "workers", "handi_mail.py"), "--mbox", mbox_path, "--out", out], check=True, capture_output=True)
contacts = {r["organisation"]: r for r in csv.DictReader(open(os.path.join(out, "contacts.csv")))}
threads = list(csv.DictReader(open(os.path.join(out, "threads.csv"))))
check("three organisations, newsletter excluded", set(contacts) == {"igj.example", "lawfirm.example", "gemeente.example"}, str(set(contacts)))
check("inspectorate never answered by a person", contacts["igj.example"]["ever_answered_by_a_person"] == "NO" and contacts["igj.example"]["auto_replies"] == "2")
check("lawyer answered, thread open again", contacts["lawfirm.example"]["ever_answered_by_a_person"] == "yes" and contacts["lawfirm.example"]["open_threads"] == "1")
check("council: bounce caught, resend answered", contacts["gemeente.example"]["bounces"] == "1" and contacts["gemeente.example"]["human_replies"] == "1")
check("dead address listed", open(os.path.join(out, "bounced.txt")).read().strip() == "old.address@gemeente.example")
check("thread statuses", sorted(t["status"] for t in threads) == ["OPEN", "OPEN", "OPEN", "answered"])

# The same mailbox over IMAP, through a stand-in server, must give the same register.
imap_port = 14300 + os.getpid() % 200
srv = subprocess.Popen([sys.executable, os.path.join(HERE, "fake_imap.py"), str(imap_port), mbox_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    import time as _t; _t.sleep(0.6)
    out_imap = os.path.join(TMP, "register-imap")
    ienv = dict(os.environ, CXI_IMAP_HOST="127.0.0.1", CXI_IMAP_PORT=str(imap_port), CXI_IMAP_SSL="0",
                CXI_IMAP_USER="layna@example.test", CXI_IMAP_PASSWORD="app-password", CXI_IMAP_FOLDER="INBOX", CXI_MY_EMAILS=me)
    ri = subprocess.run([sys.executable, os.path.join(ROOT, "workers", "handi_mail.py"), "--imap", "--out", out_imap], env=ienv, capture_output=True, text=True)
    same = ri.returncode == 0 and open(os.path.join(out_imap, "contacts.csv")).read() == open(os.path.join(out, "contacts.csv")).read() \
        and open(os.path.join(out_imap, "threads.csv")).read() == open(os.path.join(out, "threads.csv")).read()
    check("IMAP path gives the identical register", same, (ri.stdout + ri.stderr).strip().splitlines()[-1:] if not same else "")
finally:
    srv.terminate(); srv.wait(timeout=5)

env = dict(os.environ, CXI_PB_URL=BASE, CXI_SUPERUSER_EMAIL="test@cxi.local", CXI_SUPERUSER_PASSWORD="test-superuser-pass")
r1 = subprocess.run([sys.executable, os.path.join(ROOT, "workers", "register_load.py"), "--source", "test", "--dir", out], env=env, capture_output=True, text=True)
check("load into spine", r1.returncode == 0 and "contacts: 3 new" in r1.stdout, r1.stdout.strip().splitlines()[0] if r1.stdout else r1.stderr[-200:])
r2 = subprocess.run([sys.executable, os.path.join(ROOT, "workers", "register_load.py"), "--source", "test", "--dir", out], env=env, capture_output=True, text=True)
check("re-load updates in place", "contacts: 0 new, 3 updated" in r2.stdout)
summary = json.load(urllib.request.urlopen(f"{BASE}/api/cxi/register/summary"))
check("public summary counts", summary["organisations_written_to"] == 3 and summary["answered_by_a_person"] == 2 and summary["dead_addresses"] == 1, json.dumps(summary))
board = json.load(urllib.request.urlopen(f"{BASE}/api/cxi/register/board"))
check("board empty until published", board["organisations"] == [])
r3 = subprocess.run([sys.executable, os.path.join(ROOT, "workers", "register_load.py"), "--source", "test", "--dir", out, "--publish"], env=env, capture_output=True, text=True)
board = json.load(urllib.request.urlopen(f"{BASE}/api/cxi/register/board"))
check("board after publish, counts only", len(board["organisations"]) == 3 and all("addresses" not in o and "subject" not in o for o in board["organisations"]))
print("register: all passed" if not fails else f"register: {fails} FAILED"); sys.exit(1 if fails else 0)
