#!/usr/bin/env python3
"""Homei — an AI seat in the room.

Watches the chat's `messages` collection and answers through a local model.
Python 3, standard library only. Nothing leaves the machine.

    python3 workers/homei.py

Homei answers when a message says its name, or in any room whose name starts
with "homei". The room history is its memory; the spine keeps it.

Settings are environment variables, never edits to this file:

    CXI_PB_URL          http://127.0.0.1:8090     the spine (PocketBase)
    CXI_OLLAMA_HOST     http://127.0.0.1:11434    the model server
    CXI_CHAT_MODEL      qwen3:4b                  which model
    CXI_HOMEI_EMAIL     homei@cxi.local           Homei's own account
    CXI_HOMEI_PASSWORD  (generated once, kept in workers/.homei-password)
    CXI_HOMEI_HISTORY   30                        how many messages it reads back
    CXI_HOMEI_POLL      2                         seconds between checks

Two sections below know about a back end: `Spine` (PocketBase) and `Model`
(Ollama). Everything else talks to those two. Swap either one, change one
class. That is the swap rule.
"""
import hashlib
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(HERE, "log")
SYSTEM_FILE = os.path.join(HERE, "homei.system.md")
PASSWORD_FILE = os.path.join(HERE, ".homei-password")

PB_URL = os.environ.get("CXI_PB_URL", "http://127.0.0.1:8090").rstrip("/")
OLLAMA = os.environ.get("CXI_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.environ.get("CXI_CHAT_MODEL", "qwen3:4b")
EMAIL = os.environ.get("CXI_HOMEI_EMAIL", "homei@cxi.local")
NAME = "Homei"
HISTORY = int(os.environ.get("CXI_HOMEI_HISTORY", "30"))
POLL = float(os.environ.get("CXI_HOMEI_POLL", "2"))
PROMPT_VERSION = "1"


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000Z")


def say(msg):
    print(f"[homei] {msg}", flush=True)


def http(method, url, body=None, headers=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


# ---------------------------------------------------------------------------
# Spine — the only class that knows the back end is PocketBase.
# ---------------------------------------------------------------------------
class Spine:
    def __init__(self, base):
        self.base = base
        self.token = None
        self.me = None

    def _h(self):
        return {"Authorization": self.token} if self.token else {}

    def sign_in(self, email, password):
        r = http("POST", f"{self.base}/api/collections/users/auth-with-password",
                 {"identity": email, "password": password})
        self.token, self.me = r["token"], r["record"]
        return self.me

    def sign_up(self, name, email, password):
        http("POST", f"{self.base}/api/collections/users/records",
             {"name": name, "email": email, "password": password, "passwordConfirm": password})

    def messages_since(self, cursor_iso):
        q = urllib.parse.urlencode({
            "filter": f'created > "{cursor_iso}"',
            "sort": "created",
            "expand": "author",
            "perPage": 50,
        })
        return http("GET", f"{self.base}/api/collections/messages/records?{q}", headers=self._h())["items"]

    def history(self, room_id, limit):
        q = urllib.parse.urlencode({
            "filter": f'room = "{room_id}"',
            "sort": "-created",
            "expand": "author",
            "perPage": limit,
        })
        items = http("GET", f"{self.base}/api/collections/messages/records?{q}", headers=self._h())["items"]
        return list(reversed(items))

    def room(self, room_id):
        return http("GET", f"{self.base}/api/collections/rooms/records/{room_id}", headers=self._h())

    def send(self, room_id, body):
        return http("POST", f"{self.base}/api/collections/messages/records",
                    {"room": room_id, "author": self.me["id"], "body": body}, headers=self._h())


# ---------------------------------------------------------------------------
# Model — the only class that knows the model server is Ollama.
# ---------------------------------------------------------------------------
class Model:
    def __init__(self, host, name):
        self.host, self.name = host, name

    def ask(self, system, turns):
        """turns: list of {"role": "user"|"assistant", "content": str}. Returns text."""
        r = http("POST", f"{self.host}/api/chat", {
            "model": self.name,
            "messages": [{"role": "system", "content": system}] + turns,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.7},
        }, timeout=300)
        text = (r.get("message") or {}).get("content", "")
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


# ---------------------------------------------------------------------------
# Homei
# ---------------------------------------------------------------------------
def load_password():
    pw = os.environ.get("CXI_HOMEI_PASSWORD")
    if pw:
        return pw
    if os.path.exists(PASSWORD_FILE):
        return open(PASSWORD_FILE).read().strip()
    pw = secrets.token_urlsafe(24)
    with open(PASSWORD_FILE, "w") as f:
        f.write(pw)
    os.chmod(PASSWORD_FILE, 0o600)
    return pw


def load_system():
    with open(SYSTEM_FILE, encoding="utf-8") as f:
        return f.read().strip()


def log_exchange(record):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, "homei.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


ADDRESSED = re.compile(r"(^|\W)@?homei(\W|$)", re.I)


def is_for_me(msg, room, my_id):
    if msg["author"] == my_id:
        return False
    if room and room.get("name", "").lower().startswith("homei"):
        return True
    return bool(ADDRESSED.search(msg["body"]))


def author_name(m):
    a = (m.get("expand") or {}).get("author") or {}
    return a.get("name") or "someone"


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
    system = load_system()
    system_sha = hashlib.sha256(system.encode()).hexdigest()[:12]
    spine = Spine(PB_URL)
    model = Model(OLLAMA, MODEL)
    password = load_password()

    try:
        spine.sign_in(EMAIL, password)
    except urllib.error.HTTPError:
        say(f"no account for {EMAIL} yet, creating one")
        spine.sign_up(NAME, EMAIL, password)
        spine.sign_in(EMAIL, password)
    my_id = spine.me["id"]
    say(f"signed in as {spine.me.get('name')} ({EMAIL}) on {PB_URL}")
    say(f"model {MODEL} at {OLLAMA}; answering when named, or in rooms starting with 'homei'")

    cursor = now_iso()          # only answer what arrives from now on
    rooms = {}                  # small cache of room records
    model_down = False

    while True:
        try:
            fresh = spine.messages_since(cursor)
        except Exception as e:  # spine unreachable: report, wait, retry
            say(f"cannot reach the spine: {e}")
            time.sleep(max(POLL, 5))
            continue

        # One answer per room per pass: if several lines arrived together
        # (or a backlog appeared because Homei was just invited), reply once,
        # to the thread as it stands, not once per line.
        pending = {}
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
            history = spine.history(rid, HISTORY)
            if history and history[-1]["author"] == my_id:
                continue  # the last word in the room is already Homei's
            turns = build_turns(history, my_id)
            started = time.time()
            try:
                reply = model.ask(system, turns)
                if model_down:
                    say("model is back")
                    model_down = False
            except Exception as e:
                say(f"model failed: {e}")
                if not model_down:
                    spine.send(rid, "I can't reach my model right now. I'll answer as soon as it's back.")
                    model_down = True
                continue
            if not reply:
                continue

            posted = spine.send(rid, reply)
            cursor = max(cursor, posted["created"])
            log_exchange({
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
