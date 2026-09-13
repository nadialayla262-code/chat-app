#!/usr/bin/env python3
"""Search the corpus in the spine.

    CXI_SUPERUSER_EMAIL=... CXI_SUPERUSER_PASSWORD=... \\
      python3 workers/search.py "signature added later"
    python3 workers/search.py --top 10 --json "consent"

Embeds the query with the same model as the index, scores it against every
chunk, prints the best with their document and Bates range. Vectors are
cached in workers/.vectors/<model>.bin and refreshed from the spine on each
run, so a search after indexing costs one small pull, not the whole corpus.

Standard library only. If numpy is installed it is used for the scoring
and a 200,000-chunk corpus answers in well under a second; without it the
same search runs in pure Python and takes longer. Either way the answer is
the same.
"""
import argparse
import array
import json
import math
import os
import struct
import sys

from cxi_spine import Model, Superuser, q, say as _say

EMBED_MODEL = os.environ.get("CXI_EMBED_MODEL", "qwen3-embedding:0.6b")
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, ".vectors")


def say(msg):
    _say("search", msg)


def cache_path(model):
    return os.path.join(CACHE_DIR, model.replace("/", "_").replace(":", "_") + ".bin")


def load_cache(model):
    """-> (dim, ids[], vectors array('f'), updated_iso)"""
    p = cache_path(model)
    if not os.path.exists(p):
        return 0, [], array.array("f"), ""
    with open(p, "rb") as f:
        dim, n, ulen = struct.unpack("<III", f.read(12))
        updated = f.read(ulen).decode()
        ids = [f.read(15).decode().strip() for _ in range(n)]
        vecs = array.array("f"); vecs.frombytes(f.read(4 * dim * n))
    return dim, ids, vecs, updated


def save_cache(model, dim, ids, vecs, updated):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_path(model), "wb") as f:
        f.write(struct.pack("<III", dim, len(ids), len(updated.encode())))
        f.write(updated.encode())
        for i in ids:
            f.write(i.ljust(15).encode())
        f.write(vecs.tobytes())


def refresh(spine, model, quiet=False):
    """Pull chunks newer than the cache and append them. Returns (dim, ids, vecs)."""
    dim, ids, vecs, updated = load_cache(model)
    known = set(ids)
    filt = f"model = {q(model)}" + (f' && updated > {q(updated)}' if updated else "")
    added = 0
    newest = updated
    for c in spine.list_all("chunks", filt, fields="id,embedding,dim,updated", sort="updated"):
        if c["id"] in known:
            continue
        v = c["embedding"] or []
        if not v:
            continue
        if dim == 0:
            dim = len(v)
        if len(v) != dim:
            continue  # a different dimension is a different model; never score it wrong
        ids.append(c["id"]); vecs.extend(v); known.add(c["id"]); added += 1
        newest = max(newest, c["updated"])
    if added:
        save_cache(model, dim, ids, vecs, newest)
        if not quiet:
            say(f"cache: +{added} chunks, {len(ids)} total")
    return dim, ids, vecs


def scores(query, dim, vecs):
    n = len(vecs) // dim if dim else 0
    try:
        import numpy as np
        m = np.frombuffer(vecs, dtype=np.float32).reshape(n, dim)
        qv = np.asarray(query, dtype=np.float32)
        norms = np.linalg.norm(m, axis=1) * (np.linalg.norm(qv) or 1.0)
        norms[norms == 0] = 1.0
        return (m @ qv / norms).tolist()
    except ImportError:
        qn = math.sqrt(sum(x * x for x in query)) or 1.0
        out = []
        for r in range(n):
            row = vecs[r * dim:(r + 1) * dim]
            dot = sum(a * b for a, b in zip(row, query))
            rn = math.sqrt(sum(a * a for a in row)) or 1.0
            out.append(dot / (rn * qn))
        return out


def search(spine, model, text, top=5, quiet=False):
    dim, ids, vecs = refresh(spine, model.name, quiet)
    if not ids:
        return []
    qv = model.embed([text])[0]
    sc = scores(qv, dim, vecs)
    best = sorted(range(len(sc)), key=lambda i: -sc[i])[:top]
    results = []
    for i in best:
        c = spine.find("chunks", f"id = {q(ids[i])}")
        d = spine.find("documents", f"id = {q(c['document'])}") if c else None
        results.append({
            "score": round(sc[i], 4), "chunk": ids[i], "ordinal": c["ordinal"] if c else None,
            "document": d["title"] if d else "", "path": d["path"] if d else "",
            "bates": (f"{d['bates_start']}–{d['bates_end']}" if d and d.get("bates_start") else ""),
            "text": c["text"] if c else "",
        })
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="+")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    spine = Superuser(); spine.sign_in()
    model = Model(EMBED_MODEL)
    results = search(spine, model, " ".join(args.query), args.top, quiet=args.json)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2)); return
    if not results:
        say("nothing indexed yet for this model; run workers/index.py first"); return
    for r in results:
        head = f"{r['score']:.3f}  {r['document']}" + (f"  [{r['bates']}]" if r["bates"] else "") + f"  #{r['ordinal']}"
        print(head); print("   " + " ".join(r["text"].split())[:300]); print()


if __name__ == "__main__":
    main()
