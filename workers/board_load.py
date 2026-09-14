#!/usr/bin/env python3
"""Load a board (a list of things: done, working on, ideas) into the spine.

Reads a CSV and upserts one `projects` row per line for one person, so a
list kept anywhere else (a spreadsheet, an export, a note) lands on their
Desk without anyone retyping it.

    CXI_SUPERUSER_EMAIL=you@example.com CXI_SUPERUSER_PASSWORD=... \
      python3 workers/board_load.py --csv board.csv --owner you@example.com

CSV columns (header row required; extra columns are ignored):

    title      required. The key: re-running with the same title updates in place.
    stage      idea | working | built | live | done | parked   (default idea)
    priority   1 now, 2 next, 3 later, or blank
    area       a short grouping, e.g. "Rate the State", "CXI Chat", "Case"
    link       a URL, or blank
    source     where this line came from, e.g. "Claude export 12 Sep 2026"
    notes      free text

Rules applied, printed at the end so the load can be defended:
  - upsert by (owner, title); nothing is duplicated, nothing is deleted
  - an unknown stage is refused, not guessed
  - a priority outside 1..3 is refused, not clamped
  - blank fields are left blank; nothing is inferred

Standard library only. The back end lives in cxi_spine.py.
"""
import argparse
import csv
import os
import sys
import urllib.error

from cxi_spine import Superuser, q, say as _say

STAGES = ("idea", "working", "built", "live", "done", "parked")


def say(msg):
    _say("board-load", msg)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--owner", required=True, help="email of the person whose board this is")
    ap.add_argument("--source", default="", help="a label written into `source` where the CSV leaves it blank")
    args = ap.parse_args()

    spine = Superuser()
    try:
        spine.sign_in()
    except urllib.error.HTTPError as e:
        say(f"superuser sign-in failed: {e}")
        sys.exit(2)

    owner = spine.find("users", f"email = {q(args.owner.strip().lower())}")
    if not owner:
        say(f"no account with email {args.owner}; create it on the sign-in screen first")
        sys.exit(2)

    created = updated = refused = 0
    with open(args.csv, newline="", encoding="utf-8-sig") as f:
        for n, row in enumerate(csv.DictReader(f), start=2):
            title = (row.get("title") or "").strip()
            if not title:
                refused += 1; say(f"line {n}: no title, refused"); continue
            stage = (row.get("stage") or "idea").strip().lower()
            if stage not in STAGES:
                refused += 1; say(f"line {n}: stage {stage!r} is not one of {', '.join(STAGES)}, refused"); continue
            pr = (row.get("priority") or "").strip()
            data = {
                "owner": owner["id"], "title": title[:200], "stage": stage,
                "area": (row.get("area") or "").strip()[:80],
                "link": (row.get("link") or "").strip()[:1000],
                "source": ((row.get("source") or "").strip() or args.source)[:200],
                "notes": (row.get("notes") or "").strip()[:4000],
            }
            if pr:
                if pr not in ("1", "2", "3"):
                    refused += 1; say(f"line {n}: priority {pr!r} is not 1, 2 or 3, refused"); continue
                data["priority"] = int(pr)
            try:
                _, new = spine.upsert("projects", f"owner = {q(owner['id'])} && title = {q(title)}", data)
            except urllib.error.HTTPError as e:
                refused += 1; say(f"line {n}: {e.read().decode(errors='replace')[:200]}"); continue
            created += new; updated += (not new)

    say(f"board for {args.owner}: {created} new, {updated} updated, {refused} refused")
    say("rules: upsert by (owner, title); unknown stage refused; priority outside 1..3 refused; blanks stay blank; nothing deleted")


if __name__ == "__main__":
    main()
