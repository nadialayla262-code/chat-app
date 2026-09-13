"""cxi_spine.py — the thin layer for workers.

Two classes know a back end: `Spine` (PocketBase) and `Model` (Ollama).
Every worker imports these and talks to nothing else. Swap either back end,
change this file, and no worker moves. Standard library only.
"""
import json
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

PB_URL = os.environ.get("CXI_PB_URL", "http://127.0.0.1:8090").rstrip("/")
OLLAMA = os.environ.get("CXI_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000Z")


def say(who, msg):
    print(f"[{who}] {msg}", flush=True)


def http(method, url, body=None, headers=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def load_password(env_name, path):
    """A worker's own password: from the environment, else generated once and kept in `path`."""
    pw = os.environ.get(env_name)
    if pw:
        return pw
    if os.path.exists(path):
        return open(path).read().strip()
    pw = secrets.token_urlsafe(24)
    with open(path, "w") as f:
        f.write(pw)
    os.chmod(path, 0o600)
    return pw


def author_name(m):
    a = (m.get("expand") or {}).get("author") or {}
    return a.get("name") or "someone"


def log_append(path, record):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Spine — the only class that knows the back end is PocketBase.
# ---------------------------------------------------------------------------
class Spine:
    def __init__(self, base=PB_URL):
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

    def sign_in_or_up(self, name, email, password, who="worker"):
        try:
            self.sign_in(email, password)
        except urllib.error.HTTPError:
            say(who, f"no account for {email} yet, creating one")
            self.sign_up(name, email, password)
            self.sign_in(email, password)
        return self.me

    def messages_since(self, cursor_iso):
        q = urllib.parse.urlencode({
            "filter": f'created > "{cursor_iso}"', "sort": "created", "expand": "author", "perPage": 50,
        })
        return http("GET", f"{self.base}/api/collections/messages/records?{q}", headers=self._h())["items"]

    def history(self, room_id, limit):
        q = urllib.parse.urlencode({
            "filter": f'room = "{room_id}"', "sort": "-created", "expand": "author", "perPage": limit,
        })
        items = http("GET", f"{self.base}/api/collections/messages/records?{q}", headers=self._h())["items"]
        return list(reversed(items))

    def rooms(self):
        q = urllib.parse.urlencode({"sort": "name", "perPage": 200})
        return http("GET", f"{self.base}/api/collections/rooms/records?{q}", headers=self._h())["items"]

    def room(self, room_id):
        return http("GET", f"{self.base}/api/collections/rooms/records/{room_id}", headers=self._h())

    def send(self, room_id, body):
        return http("POST", f"{self.base}/api/collections/messages/records",
                    {"room": room_id, "author": self.me["id"], "body": body}, headers=self._h())


# ---------------------------------------------------------------------------
# Model — the only class that knows the model server is Ollama.
# ---------------------------------------------------------------------------
class Model:
    def __init__(self, name, host=OLLAMA):
        self.host, self.name = host, name

    def ask(self, system, turns, temperature=0.7):
        """turns: list of {"role": "user"|"assistant", "content": str}. Returns text."""
        r = http("POST", f"{self.host}/api/chat", {
            "model": self.name,
            "messages": [{"role": "system", "content": system}] + turns,
            "stream": False,
            "think": False,
            "options": {"temperature": temperature},
        }, timeout=300)
        text = (r.get("message") or {}).get("content", "")
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
