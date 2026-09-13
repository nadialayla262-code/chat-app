"""Index three documents into the spine through the stand-in embedder, search them, re-index, and check the locks."""
import json, os, shutil, subprocess, sys, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); TMP = os.path.join(HERE, ".tmp")
BASE = os.environ.get("CXI_TEST_URL", "http://127.0.0.1:8099")
fails = 0
def check(label, ok, detail=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'} {label}  {detail}"); fails += (not ok)
env = dict(os.environ, CXI_PB_URL=BASE, CXI_SUPERUSER_EMAIL="test@cxi.local", CXI_SUPERUSER_PASSWORD="test-superuser-pass",
           CXI_OLLAMA_HOST="http://127.0.0.1:11435", CXI_EMBED_MODEL="fake-embed", CXI_CHUNK_CHARS="300", CXI_CHUNK_OVERLAP="40")
src = os.path.join(TMP, "corpus"); shutil.rmtree(src, ignore_errors=True); os.makedirs(src)
shutil.rmtree(os.path.join(TMP, "workers", ".vectors"), ignore_errors=True)
open(os.path.join(src, "a-court-order.txt"), "w").write(
    "Court order. The hearing was held without the person present.\n\nThe order authorises detention for three weeks.\n\n" +
    "Signed by the judge on the stated date. " * 12)
open(os.path.join(src, "b-medical-note.txt"), "w").write(
    "Nursing note. Patient refused medication.\n\nThe signature block appears to have been added later, in different ink.\n\n" +
    "Routine observations recorded. " * 15)
open(os.path.join(src, "c-letter.md"), "w").write("# Letter to the inspectorate\n\nWe request the complete file under article fifteen.\n")
open(os.path.join(src, "ignored.pdf"), "wb").write(b"%PDF")

wd = os.path.join(TMP, "workers")
def run(script, *a):
    return subprocess.run([sys.executable, os.path.join(wd, script), *a], env=env, cwd=wd, capture_output=True, text=True)
r1 = run("index.py", "--in", src)
check("index three documents", r1.returncode == 0 and "3 new documents" in r1.stdout, (r1.stdout + r1.stderr).strip().splitlines()[-1:])
r2 = run("index.py", "--in", src)
check("re-index skips unchanged", "3 unchanged" in r2.stdout and "0 chunks embedded" in r2.stdout, r2.stdout.strip().splitlines()[-1:])
s1 = run("search.py", "--json", "signature added later different ink")
res = json.loads(s1.stdout[s1.stdout.index("["):]) if s1.returncode == 0 else []
check("search finds the medical note first", bool(res) and res[0]["document"] == "b-medical-note", res[0]["document"] if res else s1.stderr[-300:])
check("result carries text and path", bool(res) and "different ink" in res[0]["text"] and res[0]["path"].endswith("b-medical-note.txt"))
s2 = run("search.py", "--json", "hearing detention judge")
res2 = json.loads(s2.stdout[s2.stdout.index("["):])
check("search finds the court order first", res2[0]["document"] == "a-court-order", res2[0]["document"])
s3 = run("search.py", "--json", "article fifteen file")
res3 = json.loads(s3.stdout[s3.stdout.index("["):])
check("search finds the letter first", res3[0]["document"] == "c-letter", res3[0]["document"])
check("vector cache written", os.path.exists(os.path.join(wd, ".vectors", "fake-embed.bin")))
open(os.path.join(src, "d-new.txt"), "w").write("A new document about the financial administrator and the bank account.\n")
r3 = run("index.py", "--in", src)
s4 = run("search.py", "--json", "financial administrator bank")
res4 = json.loads(s4.stdout[s4.stdout.index("["):])
check("new document indexed and found after cache refresh", "1 new documents" in r3.stdout and res4[0]["document"] == "d-new", res4[0]["document"])
# a second model indexes alongside the first; nothing overwritten
env2 = dict(env, CXI_EMBED_MODEL="fake-embed-2")
r5 = subprocess.run([sys.executable, os.path.join(wd, "index.py"), "--in", src], env=env2, cwd=wd, capture_output=True, text=True)
import urllib.request as _u, json as _j
def count_model(m):
    tok = _j.load(_u.urlopen(_u.Request(f"{BASE}/api/collections/_superusers/auth-with-password", data=_j.dumps({"identity":"test@cxi.local","password":"test-superuser-pass"}).encode(), headers={"Content-Type":"application/json"})))["token"]
    from urllib.parse import quote
    filt = quote('model = "' + m + '"')
    return _j.load(_u.urlopen(_u.Request(f"{BASE}/api/collections/chunks/records?perPage=1&filter={filt}", headers={"Authorization": tok})))["totalItems"]
c1, c2 = count_model("fake-embed"), count_model("fake-embed-2")
check("second model indexed alongside, first intact", r5.returncode == 0 and c1 > 0 and c2 == c1, f"{c1} vs {c2}")
# a changed chunk size is refused for indexed files unless --rechunk
env3 = dict(env, CXI_CHUNK_CHARS="200", CXI_CHUNK_OVERLAP="20")
r6 = subprocess.run([sys.executable, os.path.join(wd, "index.py"), "--in", src], env=env3, cwd=wd, capture_output=True, text=True)
check("changed chunk size refused without --rechunk", "skipped. Run with --rechunk" in r6.stdout and "0 chunks embedded" in r6.stdout)
r7 = subprocess.run([sys.executable, os.path.join(wd, "index.py"), "--in", src, "--rechunk"], env=env3, cwd=wd, capture_output=True, text=True)
check("--rechunk redoes this model only", "re-chunking" in r7.stdout and count_model("fake-embed-2") == c2, f"model2 still {count_model('fake-embed-2')}")
for col in ("documents", "chunks"):
    code = urllib.request.urlopen(urllib.request.Request(f"{BASE}/api/collections/{col}/records")).getcode() if False else None
    try:
        urllib.request.urlopen(f"{BASE}/api/collections/{col}/records"); check(f"{col} locked", False, "(readable)")
    except urllib.error.HTTPError as e:
        check(f"{col} locked", e.code == 403, str(e.code))
print("corpus: all passed" if not fails else f"corpus: {fails} FAILED"); sys.exit(1 if fails else 0)
