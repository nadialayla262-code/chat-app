#!/usr/bin/env python3
"""Handi — holds the thread when you can't.

Say "@handi" in a room and Handi posts the register for that room:

    Last word: Bram.  Waiting on: Ada.
    Open questions: Ada asked "did the letter go?" — no reply yet.
    Open promises: Bram said "I'll send the scan tonight".

Say "@handi all" and it posts the register for every room it can see.
Deterministic first: the register is computed from the messages, not
imagined. If a model is reachable, Handi adds three lines saying where the
thread stands. If not, the register stands alone.

    python3 workers/handi.py

Settings, environment variables only:

    CXI_PB_URL          http://127.0.0.1:8090
    CXI_OLLAMA_HOST     http://127.0.0.1:11434
    CXI_CHAT_MODEL      qwen3:4b
    CXI_HANDI_EMAIL     handi@cxi.local
    CXI_HANDI_PASSWORD  (generated once, kept in workers/.handi-password)
    CXI_HANDI_HISTORY   100     how many messages per room it reads back
    CXI_HANDI_POLL      2
    CXI_HANDI_MODEL     1       set to 0 to never call the model

Back ends live in cxi_spine.py. This file knows neither.
"""
import os
import re
import sys
import time

from cxi_spine import Model, Spine, author_name, load_password, log_append, now_iso, say as _say

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(HERE, "log", "handi.jsonl")
SYSTEM_FILE = os.path.join(HERE, "handi.system.md")
PASSWORD_FILE = os.path.join(HERE, ".handi-password")

MODEL = os.environ.get("CXI_CHAT_MODEL", "qwen3:4b")
EMAIL = os.environ.get("CXI_HANDI_EMAIL", "handi@cxi.local")
NAME = "Handi"
HISTORY = int(os.environ.get("CXI_HANDI_HISTORY", "100"))
POLL = float(os.environ.get("CXI_HANDI_POLL", "2"))
USE_MODEL = os.environ.get("CXI_HANDI_MODEL", "1") != "0"

ADDRESSED = re.compile(r"(^|\W)@?handi(\W|$)", re.I)
WANTS_ALL = re.compile(r"\bhandi\b\W*\ball\b", re.I)
PROMISE = re.compile(
    r"\b(i'?ll|i will|i'?m going to|i shall|will (?:send|do|call|write|check|ask|post|book|file|chase)|let me|leave it with me|on it)\b",
    re.I,
)
WORKER_IDS = set()                 # Handi's own id, filled in at sign-in
WORKER_NAMES = {"Handi", "Homei"}  # AI seats: their lines never create obligations


def is_worker(m):
    return m["author"] in WORKER_IDS or author_name(m) in WORKER_NAMES


def say(msg):
    _say("handi", msg)


def short(text, n=90):
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def register(history, my_id):
    """The thread's state, from the messages alone."""
    # Handi's own posts and the lines that summon it are not the thread.
    lines = [m for m in history if m["author"] != my_id and not ADDRESSED.search(m["body"])]
    humans = [m for m in lines if not is_worker(m)]
    if not lines:
        return {"empty": True}
    people = {}
    for m in lines:
        people[m["author"]] = author_name(m)
    last = lines[-1]
    last_author = last["author"]
    waiting_on = [n for uid, n in people.items() if uid != last_author and n not in WORKER_NAMES]

    open_questions = []
    open_promises = []
    for i, m in enumerate(lines):
        answered = any(x["author"] != m["author"] for x in lines[i + 1:])
        body = m["body"]
        if "?" in body and not answered and not is_worker(m):
            open_questions.append((author_name(m), short(body)))
        if not is_worker(m) and PROMISE.search(body):
            # A promise stays open unless the same person spoke again after it
            # with something that reads as done.
            later_same = [x["body"] for x in lines[i + 1:] if x["author"] == m["author"]]
            done = any(re.search(r"\b(done|sent|did it|finished|posted|filed|booked|sorted)\b", x, re.I) for x in later_same)
            if not done:
                open_promises.append((author_name(m), short(body)))

    return {
        "empty": False,
        "lines": len(lines),
        "people": sorted(people.values()),
        "last_word": author_name(last),
        "waiting_on": waiting_on,
        "open_questions": open_questions[-5:],
        "open_promises": open_promises[-5:],
    }


def render(room_name, reg):
    if reg["empty"]:
        return f"{room_name}: nothing said yet."
    out = [f"{room_name} — {reg['lines']} lines, {', '.join(reg['people'])}."]
    out.append(f"Last word: {reg['last_word']}. Waiting on: {', '.join(reg['waiting_on']) or 'nobody'}.")
    if reg["open_questions"]:
        out.append("Open questions:")
        out += [f"  · {who} asked \"{q}\" — no reply yet." for who, q in reg["open_questions"]]
    else:
        out.append("Open questions: none.")
    if reg["open_promises"]:
        out.append("Open promises:")
        out += [f"  · {who}: \"{p}\"" for who, p in reg["open_promises"]]
    else:
        out.append("Open promises: none.")
    return "\n".join(out)


def main():
    with open(SYSTEM_FILE, encoding="utf-8") as f:
        system = f.read().strip()
    spine = Spine()
    model = Model(MODEL)
    spine.sign_in_or_up(NAME, EMAIL, load_password("CXI_HANDI_PASSWORD", PASSWORD_FILE), who="handi")
    my_id = spine.me["id"]
    WORKER_IDS.add(my_id)
    say(f"signed in as {spine.me.get('name')} ({EMAIL}) on {spine.base}")
    say("say '@handi' in a room for its register, '@handi all' for every room")

    cursor = now_iso()
    rooms = {}

    def room_name(rid):
        if rid not in rooms:
            try:
                rooms[rid] = spine.room(rid)
            except Exception:
                rooms[rid] = {}
        return rooms[rid].get("name", rid)

    while True:
        try:
            fresh = spine.messages_since(cursor)
        except Exception as e:
            say(f"cannot reach the spine: {e}")
            time.sleep(max(POLL, 5))
            continue

        asks = {}
        for msg in fresh:
            cursor = max(cursor, msg["created"])
            if msg["author"] == my_id or not ADDRESSED.search(msg["body"]):
                continue
            asks[msg["room"]] = (msg, bool(WANTS_ALL.search(msg["body"])))

        for rid, (msg, want_all) in asks.items():
            started = time.time()
            targets = [r["id"] for r in spine.rooms()] if want_all else [rid]
            parts = []
            for tid in targets:
                hist = spine.history(tid, HISTORY)
                parts.append(render(room_name(tid), register(hist, my_id)))
            text = "\n\n".join(parts)

            summary = ""
            if USE_MODEL and not want_all:
                try:
                    summary = model.ask(system, [{"role": "user", "content": text}], temperature=0.2)
                except Exception as e:
                    say(f"model unavailable, register only: {e}")
            body = text + (("\n\n" + summary) if summary else "")
            posted = spine.send(rid, body)
            cursor = max(cursor, posted["created"])
            log_append(LOG_FILE, {
                "at": now_iso(), "room": room_name(rid), "room_id": rid, "all": want_all,
                "trigger_message": msg["id"], "reply_message": posted["id"],
                "rooms_covered": len(targets), "model": MODEL if summary else None,
                "seconds": round(time.time() - started, 2),
            })
            say(f"register for {len(targets)} room(s) posted in '{room_name(rid)}' for {author_name(msg)}")

        time.sleep(POLL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("stopped")
        sys.exit(0)
