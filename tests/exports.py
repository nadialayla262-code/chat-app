"""Unpack five export shapes (Claude, ChatGPT, Gemini Takeout, a generic messages JSON, loose text) from a zip and a folder; check files, index, titles, re-run stability and unknown-shape reporting."""
import csv, json, os, shutil, subprocess, sys, zipfile
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); TMP = os.path.join(HERE, ".tmp", "exports")
fails = 0
def check(label, ok, detail=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'} {label}  {detail}"); fails += (not ok)

shutil.rmtree(TMP, ignore_errors=True); os.makedirs(TMP)
claude = [{"uuid": "c1-aaaa-bbbb", "name": "Bates numbering plan", "created_at": "2026-09-01T10:00:00Z", "updated_at": "2026-09-01T11:00:00Z",
           "chat_messages": [{"sender": "human", "text": "Number every page.", "created_at": "2026-09-01T10:00:00Z"},
                             {"sender": "assistant", "text": "", "content": [{"type": "text", "text": "Permanent numbers, append-only ledger."}], "created_at": "2026-09-01T10:01:00Z"},
                             {"sender": "human", "text": "", "created_at": "2026-09-01T10:02:00Z"}]}]
chatgpt = [{"title": "One Tribe naming", "create_time": 1756720000, "update_time": 1756723600, "conversation_id": "g1",
            "mapping": {"a": {"message": {"author": {"role": "system"}, "content": {"parts": ["sys"]}, "create_time": 1756720000}},
                        "b": {"message": {"author": {"role": "user"}, "content": {"parts": ["Names: 111, One Tribe, Rate the State"]}, "create_time": 1756720001}},
                        "c": {"message": {"author": {"role": "assistant"}, "content": {"parts": ["Rate the State names the product."]}, "create_time": 1756720002}}}}]
gemini = [{"header": "Gemini Apps", "title": "Prompted Draft the Woo request", "time": "2026-08-20T09:00:00.000Z", "safeHtmlItem": [{"html": "<p>Here is the <b>request</b>.</p>"}]},
          {"header": "Gemini Apps", "title": "Prompted Second prompt", "time": "2026-08-21T09:00:00.000Z"}]
grokish = {"conversations": [{"id": "x9", "title": "Grok on FlokiNET", "created_at": "2026-09-05T08:00:00Z",
                              "messages": [{"role": "user", "content": "Is Iceland outside the Netherlands?"}, {"role": "assistant", "content": "Yes."}]}]}
deepseekish = [{"name": "DeepSeek stack", "inserted_at": "2026-07-23T23:00:00Z", "mapping": {"n1": {"message": {"author": {"role": "user"}, "content": {"parts": ["Stack?"]}}}, "n2": {"message": {"author": {"role": "assistant"}, "content": {"parts": ["PocketBase spine."]}}}}}]
z = os.path.join(TMP, "claude.zip")
with zipfile.ZipFile(z, "w") as zf:
    zf.writestr("conversations.json", json.dumps(claude)); zf.writestr("users.json", json.dumps([{"uuid": "u", "full_name": "X"}])); zf.writestr("memories.json", json.dumps({"note": "no messages"}))
folder = os.path.join(TMP, "mixed"); os.makedirs(os.path.join(folder, "Takeout", "My Activity", "Gemini Apps"))
json.dump(chatgpt, open(os.path.join(folder, "conversations.json"), "w"))
json.dump(gemini, open(os.path.join(folder, "Takeout", "My Activity", "Gemini Apps", "MyActivity.json"), "w"))
json.dump(grokish, open(os.path.join(folder, "grok-export.json"), "w"))
json.dump(deepseekish, open(os.path.join(folder, "deepseek.json"), "w"))
open(os.path.join(folder, "note.md"), "w").write("# A loose note\n\nKept as text.\n")
open(os.path.join(folder, "page.html"), "w").write("<html><body><h1>Title</h1><p>Body &amp; more.</p></body></html>")
open(os.path.join(folder, "photo.jpg"), "wb").write(b"\xff\xd8")

out = os.path.join(TMP, "out")
def run(*a):
    return subprocess.run([sys.executable, os.path.join(ROOT, "workers", "exports_unpack.py"), *a], capture_output=True, text=True)
r1 = run("--in", z, "--out", out)
check("claude zip unpacks", r1.returncode == 0 and "claude: 1 conversations written" in r1.stdout, r1.stdout.strip().splitlines()[:2] + r1.stderr.strip().splitlines()[-2:])
check("files without messages are reported, not guessed", "unknown shape, not written: users.json" in r1.stdout and "memories.json" in r1.stdout)
cfile = [f for f in os.listdir(os.path.join(out, "claude"))][0]
body = open(os.path.join(out, "claude", cfile), encoding="utf-8").read()
check("claude file named by date, slug, id", cfile.startswith("2026-09-01-bates-numbering-plan-") and cfile.endswith("aaaa-bbbb.md"), cfile)
check("claude turns kept, content[] text used, empty turn written as (empty)", "## you" in body and "Permanent numbers, append-only ledger." in body and body.count("(empty)") == 1)
r2 = run("--in", folder, "--out", out)
check("mixed folder unpacks four kinds", all(f"{k}:" in r2.stdout for k in ("chatgpt", "gemini", "generic", "text")), r2.stdout.strip().splitlines()[:6])
rows = list(csv.DictReader(open(os.path.join(out, "index.csv"), encoding="utf-8")))
kinds = sorted(set(r["source"] for r in rows))
check("index carries every source incl. the earlier claude run", kinds == ["chatgpt", "claude", "gemini", "generic", "text"], kinds)
check("chatgpt: system turn dropped, user and assistant kept, epoch date parsed", any(r["source"] == "chatgpt" and r["turns"] == "2" and r["path"].startswith("chatgpt/2025-09-01") for r in rows), [r for r in rows if r["source"] == "chatgpt"])
check("gemini: two prompts, html stripped", sum(1 for r in rows if r["source"] == "gemini") == 2 and "Here is the request." in open(os.path.join(out, next(r["path"] for r in rows if r["source"] == "gemini")), encoding="utf-8").read())
gen = [r for r in rows if r["source"] == "generic"]
check("generic: grok-like found with its title", [r["title"] for r in gen] == ["Grok on FlokiNET"], [r["title"] for r in gen])
check("deepseek-like (ChatGPT shape, other key names) keeps its title and date", any(r["source"] == "chatgpt" and r["title"] == "DeepSeek stack" and r["path"].startswith("chatgpt/2026-07-23") for r in rows))
check("text: md and html copied, jpg ignored", sorted(r["title"] for r in rows if r["source"] == "text") == ["note", "page"])
titles = list(csv.DictReader(open(os.path.join(out, "titles.csv"), encoding="utf-8")))
check("titles.csv oldest first, epoch dates included", [t["title"] for t in titles][:2] == ["One Tribe naming", "DeepSeek stack"], [t["title"] for t in titles][:3])
before = open(os.path.join(out, "claude", cfile), encoding="utf-8").read()
r3 = run("--in", z, "--out", out)
check("re-run rewrites the same content and keeps the index whole", open(os.path.join(out, "claude", cfile), encoding="utf-8").read() == before and len(list(csv.DictReader(open(os.path.join(out, "index.csv"), encoding="utf-8")))) == len(rows))
r4 = run("--in", os.path.join(folder, "photo.jpg"), "--out", os.path.join(TMP, "none"))
check("nothing recognised exits 1", r4.returncode == 1)
check("rules printed", "rules: one file per conversation" in r1.stdout)
print("exports: all passed" if not fails else f"exports: {fails} FAILED"); sys.exit(1 if fails else 0)
