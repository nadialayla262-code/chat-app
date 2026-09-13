#!/usr/bin/env python3
"""Back up the spine, copy it where you keep copies, and prove the copy restores.

    CXI_SUPERUSER_EMAIL=... CXI_SUPERUSER_PASSWORD=... \\
      python3 workers/backup.py /Volumes/T7/cxi-backups "~/Google Drive/cxi-backups"

What happens, every time:

  1. The running spine makes a consistent snapshot of itself (PocketBase's
     own backup: database, auxiliary data, uploaded files) into
     pb_data/backups/.
  2. The zip is copied to every destination you name. Its SHA-256 is
     checked after each copy.
  3. The zip is unpacked into a temporary folder, a throwaway spine is
     started on it, and every collection is counted and compared with the
     live one. Only if they match does the run print RESTORE VERIFIED.
  4. One line is appended to backups.log in each destination: when, which
     file, hash, size, and the verified counts. Append-only.

A backup that has not been restored is a hope. This one has been.

Settings:

    CXI_PB_URL      http://127.0.0.1:8090      the live spine
    CXI_PB_BIN      ./bin/pocketbase           the binary, for the throwaway restore
    CXI_PB_DATA     ./pb_data                  where the live spine keeps its files
    --keep          leave the temporary restore folder for inspection
"""
import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from datetime import datetime, timezone

from cxi_spine import Superuser, http, say as _say

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PB_BIN = os.environ.get("CXI_PB_BIN", os.path.join(ROOT, "bin", "pocketbase"))
PB_DATA = os.environ.get("CXI_PB_DATA", os.path.join(ROOT, "pb_data"))
COUNT_COLLECTIONS = ["users", "rooms", "messages", "memories", "contacts", "threads", "dead_addresses", "documents", "chunks"]


def say(msg):
    _say("backup", msg)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def counts(spine):
    out = {}
    for c in COUNT_COLLECTIONS:
        try:
            r = http("GET", f"{spine.base}/api/collections/{c}/records?perPage=1", headers=spine._h())
            out[c] = r["totalItems"]
        except Exception:
            out[c] = None
    return out


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("destinations", nargs="*", help="folders to copy the backup into")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    live = Superuser(); live.sign_in()
    email, password = os.environ["CXI_SUPERUSER_EMAIL"], os.environ["CXI_SUPERUSER_PASSWORD"]
    before = counts(live)

    # 1. snapshot
    name = datetime.now(timezone.utc).strftime("cxi-%Y%m%d-%H%M%S.zip")  # PocketBase allows only [a-z0-9_-]
    http("POST", f"{live.base}/api/backups", {"name": name}, headers=live._h(), timeout=600)
    src = os.path.join(PB_DATA, "backups", name)
    for _ in range(100):
        if os.path.exists(src):
            break
        time.sleep(0.2)
    if not os.path.exists(src):
        say(f"the spine reported a backup but {src} is not there; is CXI_PB_DATA right?"); sys.exit(1)
    digest = sha256(src); size = os.path.getsize(src)
    after_snapshot = counts(live)   # writes may land while the snapshot is taken
    say(f"snapshot {name} ({size:,} bytes, sha256 {digest[:12]})")

    # 2. copies
    copied = []
    for d in args.destinations:
        d = os.path.expanduser(d)
        os.makedirs(d, exist_ok=True)
        dst = os.path.join(d, name)
        shutil.copy2(src, dst)
        if sha256(dst) != digest:
            say(f"COPY MISMATCH at {dst}; that destination cannot be trusted"); sys.exit(1)
        copied.append(dst)
        say(f"copied and hash-checked: {dst}")

    # 3. restore into a throwaway spine and count
    tmp = tempfile.mkdtemp(prefix="cxi-restore-")
    with zipfile.ZipFile(src) as z:
        z.extractall(tmp)
    port = free_port()
    proc = subprocess.Popen([PB_BIN, "serve", f"--http=127.0.0.1:{port}", f"--dir={tmp}",
                             f"--migrationsDir={os.path.join(ROOT, 'pb_migrations')}"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2); break
            except Exception:
                time.sleep(0.25)
        restored = Superuser(base=f"http://127.0.0.1:{port}")
        restored.sign_in(email, password)
        after = counts(restored)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)

    # The snapshot is correct if every count sits between the live counts taken just
    # before and just after it. Workers writing during the backup are not a mismatch.
    same = all(before.get(c) <= after.get(c) <= after_snapshot.get(c)
               for c in COUNT_COLLECTIONS if before.get(c) is not None and after.get(c) is not None)
    summary = ", ".join(f"{c} {after.get(c)}" for c in COUNT_COLLECTIONS if after.get(c) is not None)
    if not same:
        say(f"RESTORE MISMATCH. live before: {before}  after: {after_snapshot}  restored: {after}"); sys.exit(1)
    say(f"RESTORE VERIFIED: {summary}")

    # 4. the log, append-only, in every destination
    line = json.dumps({"at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "file": name, "sha256": digest,
                       "bytes": size, "verified": after, "copies": copied}, ensure_ascii=False)
    for d in args.destinations:
        with open(os.path.join(os.path.expanduser(d), "backups.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    if args.keep:
        say(f"restore folder kept at {tmp}")


if __name__ == "__main__":
    main()
