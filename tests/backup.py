"""Back up the test spine into two folders, verify the restore, check hashes and the log."""
import json, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); TMP = os.path.join(HERE, ".tmp")
BASE = os.environ.get("CXI_TEST_URL", "http://127.0.0.1:8099")
fails = 0
def check(label, ok, detail=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'} {label}  {detail}"); fails += (not ok)
d1, d2 = os.path.join(TMP, "copy-a"), os.path.join(TMP, "copy-b")
shutil.rmtree(d1, ignore_errors=True); shutil.rmtree(d2, ignore_errors=True)
# Put something in the spine so the counts mean something.
import json as _json, urllib.request, time as _t
def post(path, data, token=""):
    req = urllib.request.Request(f"{BASE}{path}", data=_json.dumps(data).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", token)
    return _json.load(urllib.request.urlopen(req))
em = f"bk{int(_t.time())}@test.local"
post("/api/collections/users/records", {"name": "Bk", "email": em, "password": "correct-horse-battery", "passwordConfirm": "correct-horse-battery"})
auth = post("/api/collections/users/auth-with-password", {"identity": em, "password": "correct-horse-battery"})
room = post("/api/collections/rooms/records", {"name": f"backup-{em}", "created_by": auth["record"]["id"]}, auth["token"])
post("/api/collections/messages/records", {"room": room["id"], "author": auth["record"]["id"], "body": "worth keeping"}, auth["token"])

env = dict(os.environ, CXI_PB_URL=BASE, CXI_SUPERUSER_EMAIL="test@cxi.local", CXI_SUPERUSER_PASSWORD="test-superuser-pass",
           CXI_PB_DATA=os.path.join(TMP, "pb_data"), CXI_PB_BIN=os.path.join(ROOT, "bin", "pocketbase"))
r = subprocess.run([sys.executable, os.path.join(ROOT, "workers", "backup.py"), d1, d2], env=env, capture_output=True, text=True)
out = r.stdout + r.stderr
check("backup runs", r.returncode == 0, out.strip().splitlines()[-1:] if out else "")
check("restore verified with counts", "RESTORE VERIFIED" in out and "rooms" in out and "messages" in out)
files1 = [f for f in os.listdir(d1) if f.endswith(".zip")] if os.path.isdir(d1) else []
files2 = [f for f in os.listdir(d2) if f.endswith(".zip")] if os.path.isdir(d2) else []
check("zip in both destinations", len(files1) == 1 and files1 == files2)
log = [json.loads(l) for l in open(os.path.join(d1, "backups.log"))] if os.path.exists(os.path.join(d1, "backups.log")) else []
check("append-only log with hash and verified counts", len(log) == 1 and len(log[0]["sha256"]) == 64 and log[0]["verified"].get("rooms", 0) >= 1 and log[0]["verified"].get("messages", 0) >= 1, str(log[0]["verified"]) if log else "")
import time; time.sleep(1.1)  # names carry seconds; two runs must not share one
r2 = subprocess.run([sys.executable, os.path.join(ROOT, "workers", "backup.py"), d1], env=env, capture_output=True, text=True)
log = [json.loads(l) for l in open(os.path.join(d1, "backups.log"))] if os.path.exists(os.path.join(d1, "backups.log")) else []
check("second run appends, never overwrites", r2.returncode == 0 and len(log) == 2 and log[0]["file"] != log[1]["file"])
print("backup: all passed" if not fails else f"backup: {fails} FAILED"); sys.exit(1 if fails else 0)
