"""Load a board CSV into the spine for one person, twice; check upsert, refusals, and that only the owner can see it."""
import json, os, subprocess, sys, urllib.request, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); TMP = os.path.join(HERE, ".tmp")
BASE = os.environ.get("CXI_TEST_URL", "http://127.0.0.1:8099")
fails = 0
def check(label, ok, detail=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'} {label}  {detail}"); fails += (not ok)

def post(path, body, token=""):
    req = urllib.request.Request(f"{BASE}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **({"Authorization": token} if token else {})})
    return json.load(urllib.request.urlopen(req))
def get(path, token):
    return json.load(urllib.request.urlopen(urllib.request.Request(f"{BASE}{path}", headers={"Authorization": token})))

import time
t = int(time.time())
me, other = f"board{t}@test.local", f"other{t}@test.local"
pw = "correct-horse-battery"
for email in (me, other):
    post("/api/collections/users/records", {"name": email.split("@")[0], "email": email, "password": pw, "passwordConfirm": pw})
tok_me = post("/api/collections/users/auth-with-password", {"identity": me, "password": pw})["token"]
tok_other = post("/api/collections/users/auth-with-password", {"identity": other, "password": pw})["token"]

os.makedirs(TMP, exist_ok=True)
csv1 = os.path.join(TMP, "board.csv")
open(csv1, "w", encoding="utf-8").write(
    "title,stage,priority,area,link,source,notes\n"
    "Rate the State site,working,1,Rate the State,https://example.test/rts,Lovable,brand pass queued\n"
    "Patchi gate,idea,2,CXI,,,identities then the gate\n"
    "Ollama on the Mac,idea,,CXI Chat,,,\n"
    "Bad stage row,someday,1,,,,\n"
    "Bad priority row,idea,7,,,,\n"
    ",idea,1,,,,no title\n")
env = dict(os.environ, CXI_PB_URL=BASE, CXI_SUPERUSER_EMAIL="test@cxi.local", CXI_SUPERUSER_PASSWORD="test-superuser-pass")
def load(csv_path, owner=me):
    return subprocess.run([sys.executable, os.path.join(ROOT, "workers", "board_load.py"), "--csv", csv_path, "--owner", owner, "--source", "test-load"], env=env, capture_output=True, text=True)
r1 = load(csv1)
check("first load: 3 new, 3 refused", r1.returncode == 0 and "3 new, 0 updated, 3 refused" in r1.stdout, (r1.stdout + r1.stderr).strip().splitlines()[-2:])
check("refusals are named, not guessed", "stage 'someday'" in r1.stdout and "priority '7'" in r1.stdout and "no title" in r1.stdout)
check("rules printed", "rules: upsert by (owner, title)" in r1.stdout)
rows = get("/api/collections/projects/records?perPage=50", tok_me)["items"]
check("owner sees exactly 3 rows", len(rows) == 3, len(rows))
rts = next(r for r in rows if r["title"] == "Rate the State site")
check("fields land as given", rts["stage"] == "working" and rts["priority"] == 1 and rts["area"] == "Rate the State" and rts["link"] == "https://example.test/rts" and rts["source"] == "Lovable")
oll = next(r for r in rows if r["title"] == "Ollama on the Mac")
check("blank priority stays blank; blank source takes --source", not oll.get("priority") and oll["source"] == "test-load")
check("the other person sees none of it", get("/api/collections/projects/records?perPage=50", tok_other)["items"] == [])

csv2 = os.path.join(TMP, "board2.csv")
open(csv2, "w", encoding="utf-8").write("title,stage,priority\nPatchi gate,working,1\nNew idea,idea,3\n")
r2 = load(csv2)
check("second load updates in place, adds the new one", "1 new, 1 updated, 0 refused" in r2.stdout, r2.stdout.strip().splitlines()[-2:])
rows = get("/api/collections/projects/records?perPage=50", tok_me)["items"]
check("no duplicates; Patchi moved to working", len(rows) == 4 and next(r for r in rows if r["title"] == "Patchi gate")["stage"] == "working")
r3 = load(csv2, owner=f"nobody{t}@test.local")
check("unknown owner refused with a sentence", r3.returncode == 2 and "no account with email" in r3.stdout)
print("board: all passed" if not fails else f"board: {fails} FAILED"); sys.exit(1 if fails else 0)
