#!/usr/bin/env python3
"""Homei — an AI seat in the room.

Watches the chat's `messages` collection and answers through a local model.
Python 3, standard library only. Nothing leaves the machine.

    python3 workers/homei.py

Homei answers when a message says its name, or in any room whose name starts
with "homei". The room history is its memory within a room; the spine keeps
it. Across rooms:

    @homei remember my cat is called Garfield      kept, for you, in every room
    @homei forget Garfield                         removed
    @homei what do you remember?                   listed

Memories belong to the person they are about. You can see and delete your
own in the spine; nobody else can.

Settings are environment variables, never edits to this file:

    CXI_PB_URL          http://127.0.0.1:8090     the spine (PocketBase)
    CXI_OLLAMA_HOST     http://127.0.0.1:11434    the model server
    CXI_CHAT_MODEL      qwen3:4b                  which model
    CXI_HOMEI_EMAIL     homei@cxi.local           Homei's own account
    CXI_HOMEI_PASSWORD  (generated once, kept in workers/.homei-password)
    CXI_HOMEI_HISTORY   30                        how many messages it reads back
    CXI_HOMEI_POLL      2                         seconds between checks

The back ends live in cxi_spine.py (Spine = PocketBase, Model = Ollama).
This file knows neither. That is the swap rule.
"""
import hashlib
import os
import re
import sys
import time

from cxi_spine import Model, Spine, author_name, load_password, log_append, now_iso, q, say as _say

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(HERE, "log", "homei.jsonl")
SYSTEM_FILE = os.path.join(HERE, "homei.system.md")
PASSWORD_FILE = os.path.join(HERE, ".homei-password")

MODEL = os.environ.get("CXI_CHAT_MODEL", "qwen3:4b")
EMAIL = os.environ.get("CXI_HOMEI_EMAIL", "homei@cxi.local")
NAME = "Homei"
HISTORY = int(os.environ.get("CXI_HOMEI_HISTORY", "30"))
POLL = float(os.environ.get("CXI_HOMEI_POLL", "2"))
PROMPT_VERSION = "1"

ADDRESSED = re.compile(r"(^|\W)@?homei(\W|$)", re.I)
REMEMBER = re.compile(r"\bhomei\b[,:]?\s*(?:please\s+)?remember(?:\s+that)?\s+(.+)$", re.I | re.S)
FORGET = re.compile(r"\bhomei\b[,:]?\s*(?:please\s+)?forget(?:\s+about)?\s+(.+)$", re.I | re.S)
RECALL = re.compile(r"\bhomei\b[,:]?\s*what do you remember", re.I)


def say(msg):
    _say("homei", msg)


def is_for_me(msg, room, my_id):
    if msg["author"] == my_id:
        return False
    if room and room.get("name", "").lower().startswith("homei"):
        return True
    return bool(ADDRESSED.search(msg["body"]))


def memories_for(spine, person_ids):
    """{person_id: [text, ...]} for the people in the room, from the spine."""
    out = {}
    for pid in person_ids:
        rows = spine.list_all("memories", f"person = {q(pid)}", fields="id,text", sort="created")
        out[pid] = [r["text"] for r in rows]
    return out


def memory_block(history, mem):
    """The remembered facts about the people in this thread, for the system prompt."""
    names = {}
    for m in history:
        names[m["author"]] = author_name(m)
    lines = []
    for pid, facts in mem.items():
        if facts:
            lines.append(f"About {names.get(pid, 'someone')}:")
            lines += [f"- {f}" for f in facts]
    if not lines:
        return ""
    return "\n\nWhat you remember (told to you earlier; use it, never recite it unasked):\n" + "\n".join(lines)


def handle_memory(spine, msg, my_id):
    """remember / forget / recall. Returns a reply, or None if the message is none of those."""
    body, pid = msg["body"], msg["author"]
    m = REMEMBER.search(body)
    if m:
        text = m.group(1).strip().rstrip(".")
        spine.create("memories", {"person": pid, "author": my_id, "text": text})
        return f"Kept: {text}"
    m = FORGET.search(body)
    if m:
        needle = m.group(1).strip().rstrip(".").lower()
        gone = []
        for r in list(spine.list_all("memories", f"person = {q(pid)}", fields="id,text")):
            if needle in r["text"].lower():
                spine.delete("memories", r["id"]); gone.append(r["text"])
        return ("Forgotten: " + "; ".join(gone)) if gone else f"I had nothing about \"{needle}\"."
    if RECALL.search(body):
        facts = [r["text"] for r in spine.list_all("memories", f"person = {q(pid)}", fields="text", sort="created")]
        return ("What I remember about you:\n" + "\n".join(f"- {f}" for f in facts)) if facts else "Nothing yet. Tell me: homei, remember …"
    return None


def build_turns(history, my_id):
    """Room history as alternating turns. Other people's lines carry their name."""
    turns = []
    for m in history:
        if m["author"] == my_id:
            turns.append({"role": "assistant", "content": m["body"]})
        else:
            turns.append({"role": "user", "content": f"{author_name(m)}: {m['body']}"})
    return turns


def main():
    with open(SYSTEM_FILE, encoding="utf-8") as f:
        system = f.read().strip()
    system_sha = hashlib.sha256(system.encode()).hexdigest()[:12]
    spine = Spine()
    model = Model(MODEL)
    spine.sign_in_or_up(NAME, EMAIL, load_password("CXI_HOMEI_PASSWORD", PASSWORD_FILE), who="homei")
    my_id = spine.me["id"]
    say(f"signed in as {spine.me.get('name')} ({EMAIL}) on {spine.base}")
    say(f"model {MODEL} at {model.host}; answering when named, or in rooms starting with 'homei'")

    cursor = now_iso()          # only answer what arrives from now on
    rooms = {}                  # small cache of room records
    model_down = False
    retry = {}                  # rooms still owed an answer after a model outage
    last_fail = 0.0

    while True:
        spine.keep_alive()
        try:
            fresh = spine.messages_since(cursor)
        except Exception as e:  # spine unreachable: report, wait, retry
            say(f"cannot reach the spine: {e}")
            time.sleep(max(POLL, 5))
            continue

        # One answer per room per pass: if several lines arrived together
        # (or a backlog appeared because Homei was just invited), reply once,
        # to the thread as it stands, not once per line. Rooms owed an answer
        # from an outage come first, tried again no more than every 30s.
        pending = dict(retry) if (retry and time.time() - last_fail > 30) else {}
        for msg in fresh:
            cursor = max(cursor, msg["created"])
            rid = msg["room"]
            if rid not in rooms:
                try:
                    rooms[rid] = spine.room(rid)
                except Exception:
                    rooms[rid] = {}
            if is_for_me(msg, rooms[rid], my_id):
                pending[rid] = msg

        for rid, msg in pending.items():
            started = time.time()
            try:
                direct = handle_memory(spine, msg, my_id)
                if direct is not None:
                    spine.send(rid, direct)
                    retry.pop(rid, None)
                    say(f"memory: {direct.splitlines()[0][:60]}")
                    continue
                history = spine.history(rid, HISTORY)
                if history and history[-1]["author"] == my_id:
                    retry.pop(rid, None)
                    continue  # the last word in the room is already Homei's
                turns = build_turns(history, my_id)
                people = {m["author"] for m in history if m["author"] != my_id}
                prompt = system + memory_block(history, memories_for(spine, people))
            except Exception as e:  # the spine hiccuped mid-room: say so, keep the room owed, carry on
                say(f"spine error in '{rooms.get(rid, {}).get('name', rid)}': {e}")
                retry[rid] = msg
                continue
            try:
                reply = model.ask(prompt, turns)
                if model_down:
                    say("model is back")
                    model_down = False
            except Exception as e:
                say(f"model failed: {e}")
                retry[rid] = msg          # owed; answered when the model returns
                last_fail = time.time()
                if not model_down:
                    try:
                        spine.send(rid, "I can't reach my model right now. I'll answer as soon as it's back.")
                    except Exception:
                        pass
                    model_down = True
                continue
            retry.pop(rid, None)
            if not reply:
                continue

            try:
                posted = spine.send(rid, reply)
            except Exception as e:
                say(f"could not post in '{rooms.get(rid, {}).get('name', rid)}': {e}")
                retry[rid] = msg
                continue
            # The cursor is not advanced to the reply: anything written while the
            # model was thinking is still newer than the cursor and gets read next pass.
            log_append(LOG_FILE, {
                "at": now_iso(),
                "room": rooms[rid].get("name", rid),
                "room_id": rid,
                "trigger_message": msg["id"],
                "reply_message": posted["id"],
                "model": MODEL,
                "prompt_version": PROMPT_VERSION,
                "system_sha256_12": system_sha,
                "history_turns": len(turns),
                "seconds": round(time.time() - started, 2),
            })
            say(f"answered {author_name(msg)} in '{rooms[rid].get('name', rid)}' ({len(reply)} chars)")

        time.sleep(POLL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("stopped")
        sys.exit(0)
