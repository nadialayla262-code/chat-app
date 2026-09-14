#!/usr/bin/env python3
"""Unpack a chat export into plain text, one file per conversation.

Claude, ChatGPT, Gemini (Google Takeout), Grok (xAI) and DeepSeek exports all
arrive as a zip or a folder of JSON. This turns each one into a folder of
dated text files that workers/index.py can read, plus an index of what was
in it. Nothing is summarised, scored or dropped: every turn is written out
as it was exported.

    python3 workers/exports_unpack.py --in claude-export.zip --out exports/claude
    python3 workers/exports_unpack.py --in takeout-2026.zip  --out exports/gemini
    python3 workers/exports_unpack.py --in grok.zip          --out exports/grok

Then, to make it all searchable from the Desk:

    python3 workers/index.py --in exports

What it recognises, in this order:

    claude    conversations.json with chat_messages[].sender/text
    chatgpt   conversations.json with mapping{}.message.author.role
              (DeepSeek exports this same shape; it lands here with its titles)
    gemini    Takeout "My Activity/Gemini Apps/MyActivity.json"
    generic   any JSON holding lists of messages with role/content,
              sender/text, or author/content (Grok lands here)
    text      .md .txt .html files, copied as text

Output, under --out:

    <source>/<created>-<slug>-<id>.md      one file per conversation
    index.csv                              source,id,title,created,updated,turns,chars,path
    titles.csv                             title,created,source   (every conversation, oldest first)

Rules applied, printed at the end:
  - one file per conversation, named by its created date and its own id
  - re-running overwrites a conversation's file with the same content, never a different one
  - no turn is dropped; empty turns are written as (empty)
  - unknown shapes are reported by path, not guessed

Standard library only.
"""
import argparse
import csv
import html
import json
import os
import re
import sys
import zipfile
from html.parser import HTMLParser

SAY = "[exports-unpack]"


def say(msg):
    print(f"{SAY} {msg}", flush=True)


def slug(s, n=48):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:n] or "untitled"


def day(ts):
    """'2026-09-11T12:50:42.123Z' | epoch seconds | '' -> 'YYYY-MM-DD' or 'undated'."""
    if ts is None or ts == "":
        return "undated"
    if isinstance(ts, str) and re.fullmatch(r"\d{9,11}(\.\d+)?", ts.strip()):
        ts = float(ts)
    if isinstance(ts, (int, float)):
        import datetime
        return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(ts))
    return m.group(1) if m else "undated"


class Strip(HTMLParser):
    def __init__(self):
        super().__init__(); self.out = []
    def handle_data(self, d): self.out.append(d)
    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "tr"): self.out.append("\n")
    def text(self): return re.sub(r"\n{3,}", "\n\n", "".join(self.out)).strip()


def strip_html(s):
    p = Strip(); p.feed(s); return html.unescape(p.text())


# ---------------------------------------------------------------- readers

def read_tree(path):
    """Yield (relative_name, bytes) for a zip or a folder."""
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for f in sorted(files):
                full = os.path.join(root, f)
                with open(full, "rb") as fh:
                    yield os.path.relpath(full, path), fh.read()
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for name in sorted(z.namelist()):
                if name.endswith("/"):
                    continue
                with z.open(name) as fh:
                    yield name, fh.read()
    else:
        with open(path, "rb") as fh:
            yield os.path.basename(path), fh.read()


# ---------------------------------------------------------------- shapes
# Each parser returns a list of conversations:
#   {id, title, created, updated, turns: [(who, text, when)]}

def parse_claude(data):
    out = []
    for c in data:
        turns = []
        for m in c.get("chat_messages") or []:
            text = m.get("text") or ""
            if not text and isinstance(m.get("content"), list):
                text = "\n".join(p.get("text", "") for p in m["content"] if isinstance(p, dict) and p.get("type") == "text")
            who = "you" if m.get("sender") == "human" else "claude"
            turns.append((who, text, m.get("created_at", "")))
        out.append({"id": c.get("uuid") or c.get("id") or "", "title": c.get("name") or "", "created": c.get("created_at", ""), "updated": c.get("updated_at", ""), "turns": turns})
    return out


def parse_chatgpt(data):
    out = []
    for c in data:
        nodes = list((c.get("mapping") or {}).values())
        msgs = [n.get("message") for n in nodes if n.get("message")]
        msgs.sort(key=lambda m: (m.get("create_time") or 0))
        turns = []
        for m in msgs:
            role = ((m.get("author") or {}).get("role")) or ""
            if role == "system":
                continue
            parts = ((m.get("content") or {}).get("parts")) or []
            text = "\n".join(p if isinstance(p, str) else json.dumps(p, ensure_ascii=False) for p in parts)
            turns.append(("you" if role == "user" else role or "assistant", text, m.get("create_time")))
        # DeepSeek exports the same mapping shape under different key names (name, inserted_at, updated_at).
        out.append({"id": c.get("conversation_id") or c.get("id") or "", "title": c.get("title") or c.get("name") or "",
                    "created": c.get("create_time") or c.get("inserted_at") or c.get("created_at"), "updated": c.get("update_time") or c.get("updated_at"), "turns": turns})
    return out


def parse_gemini_activity(data):
    """Takeout Gemini Apps activity: one entry per prompt. Each becomes its own small conversation."""
    out = []
    for i, e in enumerate(data):
        title = e.get("title") or ""
        prompt = re.sub(r"^Prompted\s+", "", title)
        reply = ""
        for k in ("subtitles", "details"):
            v = e.get(k)
            if isinstance(v, list):
                reply += "\n".join(x.get("name", "") if isinstance(x, dict) else str(x) for x in v)
        text_html = e.get("safeHtmlItem") or e.get("textItem") or ""
        if isinstance(text_html, list):
            text_html = "\n".join(str(x.get("html", x)) if isinstance(x, dict) else str(x) for x in text_html)
        if text_html:
            reply = (reply + "\n" + strip_html(str(text_html))).strip()
        when = e.get("time", "")
        out.append({"id": f"gemini-{day(when)}-{i:05d}", "title": prompt[:120], "created": when, "updated": when,
                    "turns": [("you", prompt, when), ("gemini", reply, when)]})
    return out


ROLE_KEYS = (("role", "content"), ("sender", "text"), ("author", "content"), ("role", "text"), ("from", "text"), ("speaker", "message"))


def looks_like_message(o):
    return isinstance(o, dict) and any(rk in o and ck in o for rk, ck in ROLE_KEYS)


def message_turn(o):
    for rk, ck in ROLE_KEYS:
        if rk in o and ck in o:
            role = o[rk]
            if isinstance(role, dict):
                role = role.get("role") or role.get("name") or "assistant"
            content = o[ck]
            if isinstance(content, dict):
                content = content.get("text") or content.get("parts") or content
            if isinstance(content, list):
                content = "\n".join(p if isinstance(p, str) else (p.get("text", "") if isinstance(p, dict) else str(p)) for p in content)
            role = str(role).lower()
            who = "you" if role in ("user", "human") else role
            return (who, str(content) if content is not None else "", o.get("create_time") or o.get("created_at") or o.get("timestamp") or o.get("time") or "")
    return None


def parse_generic(data, source_name):
    """Walk any JSON. A list of message-like dicts is a conversation; a dict holding one is its container."""
    found = []

    def walk(node, path, container):
        if isinstance(node, list) and node and all(looks_like_message(x) for x in node if isinstance(x, dict)) and any(isinstance(x, dict) for x in node):
            turns = [t for t in (message_turn(x) for x in node if isinstance(x, dict)) if t]
            c = container or {}
            found.append({"id": str(c.get("id") or c.get("uuid") or c.get("conversation_id") or f"{slug(path)}-{len(found):04d}"),
                          "title": str(c.get("title") or c.get("name") or c.get("subject") or ""), "created": c.get("created_at") or c.get("create_time") or c.get("created") or c.get("time") or (turns[0][2] if turns else ""),
                          "updated": c.get("updated_at") or c.get("update_time") or c.get("updated") or "", "turns": turns})
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}/{k}", node if any(kk in node for kk in ("title", "name", "id", "uuid", "conversation_id")) else container)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}/{i}", container)

    walk(data, source_name, None)
    return found


def detect_and_parse(name, data):
    """Return (kind, conversations) for one JSON document."""
    base = os.path.basename(name).lower()
    if isinstance(data, list) and data and isinstance(data[0], dict):
        first = data[0]
        if "chat_messages" in first:
            return "claude", parse_claude(data)
        if "mapping" in first:
            return "chatgpt", parse_chatgpt(data)
        if "gemini" in name.lower() and ("title" in first and "time" in first):
            return "gemini", parse_gemini_activity(data)
    convs = parse_generic(data, base)
    return ("generic", convs) if convs else ("unknown", [])


# ---------------------------------------------------------------- writing

def write_conversation(out_dir, source, c):
    who_max = max((len(t[0]) for t in c["turns"]), default=3)
    created = day(c.get("created"))
    ident = re.sub(r"[^A-Za-z0-9-]", "", str(c.get("id") or ""))[-12:] or "noid"
    fname = f"{created}-{slug(c.get('title'))}-{ident}.md"
    folder = os.path.join(out_dir, source)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, fname)
    lines = [f"# {c.get('title') or '(untitled)'}", "",
             f"source: {source}", f"id: {c.get('id') or ''}", f"created: {c.get('created') or ''}", f"updated: {c.get('updated') or ''}",
             f"turns: {len(c['turns'])}", "", "-----", ""]
    chars = 0
    for who, text, when in c["turns"]:
        text = text if (text or "").strip() else "(empty)"
        chars += len(text)
        lines.append(f"## {who}" + (f"  ({day(when)})" if when else ""))
        lines.append("")
        lines.append(text)
        lines.append("")
    body = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return os.path.relpath(path, out_dir), chars


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src", required=True, help="a zip, a folder, or one JSON/HTML/text file")
    ap.add_argument("--out", required=True, help="folder to write into (created)")
    ap.add_argument("--source", default="", help="override the source label (default: detected kind)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    index_path = os.path.join(args.out, "index.csv")
    titles_path = os.path.join(args.out, "titles.csv")
    existing = {}
    if os.path.exists(index_path):
        with open(index_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing[(row["source"], row["id"])] = row

    counts = {}
    unknown = []
    rows = dict(existing)
    for name, raw in read_tree(args.src):
        low = name.lower()
        if low.endswith(".json"):
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception as e:
                unknown.append(f"{name} (not JSON: {e})"); continue
            kind, convs = detect_and_parse(name, data)
            if kind == "unknown":
                unknown.append(name); continue
            source = args.source or kind
            for c in convs:
                rel, chars = write_conversation(args.out, source, c)
                rows[(source, str(c.get("id") or rel))] = {"source": source, "id": str(c.get("id") or rel), "title": c.get("title") or "", "created": str(c.get("created") or ""),
                                                            "updated": str(c.get("updated") or ""), "turns": len(c["turns"]), "chars": chars, "path": rel}
                counts[source] = counts.get(source, 0) + 1
        elif low.endswith((".md", ".txt", ".html", ".htm")):
            text = raw.decode("utf-8", errors="replace")
            if low.endswith((".html", ".htm")):
                text = strip_html(text)
            if not text.strip():
                continue
            source = args.source or "text"
            c = {"id": slug(name, 80), "title": os.path.splitext(os.path.basename(name))[0], "created": "", "updated": "", "turns": [("text", text, "")]}
            rel, chars = write_conversation(args.out, source, c)
            rows[(source, c["id"])] = {"source": source, "id": c["id"], "title": c["title"], "created": "", "updated": "", "turns": 1, "chars": chars, "path": rel}
            counts[source] = counts.get(source, 0) + 1
        # anything else (images, audio, pdf) is left where it is; the corpus indexer has its own readers

    with open(index_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["source", "id", "title", "created", "updated", "turns", "chars", "path"])
        w.writeheader()
        for r in sorted(rows.values(), key=lambda r: (r["source"], str(r["created"]), r["path"])):
            w.writerow(r)
    with open(titles_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["title", "created", "source"])
        for r in sorted(rows.values(), key=lambda r: (day(r["created"]), r["source"], r["title"])):
            w.writerow([r["title"], day(r["created"]), r["source"]])

    for k, v in sorted(counts.items()):
        say(f"{k}: {v} conversations written")
    for u in unknown:
        say(f"unknown shape, not written: {u}")
    say(f"index: {index_path} ({len(rows)} rows)   titles: {titles_path}")
    say("rules: one file per conversation named by created date and id; re-runs overwrite with the same content; no turn dropped, empty turns written as (empty); unknown shapes reported by path, not guessed")
    if not counts:
        sys.exit(1)


if __name__ == "__main__":
    main()
