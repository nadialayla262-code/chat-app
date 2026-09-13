#!/usr/bin/env python3
"""Load the mail register into the spine.

Reads register/ (from workers/handi_mail.py) and upserts it into the
`contacts`, `threads` and `dead_addresses` collections. Those collections
are locked to superusers, so this signs in as you:

    CXI_SUPERUSER_EMAIL=you@example.com CXI_SUPERUSER_PASSWORD=... \
      python3 workers/register_load.py --source personal-gmail

`--source` names the mailbox the register came from, so six accounts load
side by side without overwriting each other. Re-running with the same
source updates in place; nothing is duplicated.

    --dir      register folder (default ./register)
    --publish  flag every loaded organisation as published (default: leave as is)

Standard library only. The back end lives in cxi_spine.py.
"""
import argparse
import csv
import hashlib
import os
import sys
import urllib.error
import urllib.parse

from cxi_spine import Spine, http, say as _say

HERE = os.path.dirname(os.path.abspath(__file__))


def say(msg):
    _say("register-load", msg)


class Superuser(Spine):
    """Same spine, signed in as a superuser. Locked collections open up."""

    def sign_in(self, email, password):
        r = http("POST", f"{self.base}/api/collections/_superusers/auth-with-password",
                 {"identity": email, "password": password})
        self.token, self.me = r["token"], r["record"]
        return self.me

    def find(self, collection, filt):
        q = urllib.parse.urlencode({"filter": filt, "perPage": 1})
        items = http("GET", f"{self.base}/api/collections/{collection}/records?{q}", headers=self._h())["items"]
        return items[0] if items else None

    def upsert(self, collection, filt, data):
        existing = self.find(collection, filt)
        if existing:
            return http("PATCH", f"{self.base}/api/collections/{collection}/records/{existing['id']}", data, headers=self._h()), False
        return http("POST", f"{self.base}/api/collections/{collection}/records", data, headers=self._h()), True


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def date(s):
    return f"{s} 00:00:00.000Z" if s else ""


def num(s):
    return int(s or 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="a label for the mailbox this register came from")
    ap.add_argument("--dir", default=os.path.join(os.path.dirname(HERE), "register"))
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()

    email = os.environ.get("CXI_SUPERUSER_EMAIL")
    password = os.environ.get("CXI_SUPERUSER_PASSWORD")
    if not email or not password:
        say("set CXI_SUPERUSER_EMAIL and CXI_SUPERUSER_PASSWORD (your PocketBase superuser)")
        sys.exit(2)
    spine = Superuser()
    try:
        spine.sign_in(email, password)
    except urllib.error.HTTPError as e:
        say(f"superuser sign-in failed: {e}")
        sys.exit(2)

    created = updated = 0
    with open(os.path.join(args.dir, "contacts.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            data = {
                "organisation": row["organisation"], "source": args.source,
                "addresses": row["addresses"].split(";") if row["addresses"] else [],
                "threads": num(row["threads"]), "messages_sent": num(row["messages_sent"]),
                "first_sent": date(row["first_sent"]), "last_sent": date(row["last_sent"]),
                "human_replies": num(row["human_replies"]), "auto_replies": num(row["auto_replies"]),
                "bounces": num(row["bounces"]), "last_human_reply": date(row["last_human_reply"]),
                "open_threads": num(row["open_threads"]),
                "answered_by_person": row["ever_answered_by_a_person"].lower() == "yes",
            }
            if args.publish:
                data["published"] = True
            _, new = spine.upsert("contacts", f"organisation = {q(row['organisation'])} && source = {q(args.source)}", data)
            created += new; updated += (not new)
    say(f"contacts: {created} new, {updated} updated")

    created = updated = 0
    with open(os.path.join(args.dir, "threads.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = hashlib.sha256("|".join([args.source, row["organisation"], row["subject"], row["first_sent"]]).encode()).hexdigest()[:40]
            data = {
                "key": key, "organisation": row["organisation"], "source": args.source, "subject": row["subject"],
                "to": row["to"].split(";") if row["to"] else [],
                "messages_sent": num(row["messages_sent"]), "first_sent": date(row["first_sent"]), "last_sent": date(row["last_sent"]),
                "human_replies": num(row["human_replies"]), "auto_replies": num(row["auto_replies"]), "bounces": num(row["bounces"]),
                "last_human_reply": date(row["last_human_reply"]), "status": row["status"],
            }
            _, new = spine.upsert("threads", f"key = {q(key)}", data)
            created += new; updated += (not new)
    say(f"threads: {created} new, {updated} updated")

    created = 0
    path = os.path.join(args.dir, "bounced.txt")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            addr = line.strip().lower()
            if not addr:
                continue
            _, new = spine.upsert("dead_addresses", f"address = {q(addr)}", {"address": addr, "source": args.source})
            created += new
    say(f"dead addresses: {created} new")
    say("done. counts: GET /api/cxi/register/summary  board: GET /api/cxi/register/board")


if __name__ == "__main__":
    main()
