#!/usr/bin/env python3
"""Index the corpus into the spine.

Walks a folder of text files, cuts each into chunks, embeds every chunk
through the local model, and stores documents and chunks in the spine.
Re-running is cheap: a file whose hash is already in `documents` is
skipped; a chunk already embedded with the same model is skipped. A second
model indexes alongside the first; nothing is overwritten. A changed chunk
size is refused for already-indexed files unless you pass --rechunk.

    CXI_SUPERUSER_EMAIL=... CXI_SUPERUSER_PASSWORD=... \\
      python3 workers/index.py --in ~/CXI/extracted

Settings, environment variables only:

    CXI_PB_URL          http://127.0.0.1:8090
    CXI_OLLAMA_HOST     http://127.0.0.1:11434
    CXI_EMBED_MODEL     qwen3-embedding:0.6b
    CXI_CHUNK_CHARS     1200        target chunk size
    CXI_CHUNK_OVERLAP   150
    CXI_BATES_LEDGER    path to a Bates ledger.csv; if set, documents get their Bates range

Reads .txt, .md, .en.txt, .vl.md. Standard library only; the back ends
live in cxi_spine.py.
"""
import argparse
import csv
import hashlib
import os
import sys
import time

from cxi_spine import Model, Superuser, q, say as _say

EMBED_MODEL = os.environ.get("CXI_EMBED_MODEL", "qwen3-embedding:0.6b")
CHUNK = int(os.environ.get("CXI_CHUNK_CHARS", "1200"))
OVERLAP = int(os.environ.get("CXI_CHUNK_OVERLAP", "150"))
TEXT_EXT = {".txt", ".md"}


def say(msg):
    _say("index", msg)


def chunk_text(text, size=CHUNK, overlap=OVERLAP):
    """Deterministic chunks: paragraphs packed to ~size chars, with overlap carried forward."""
    paras = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n")]
    paras = [p for p in paras if p]
    out, cur = [], ""
    for p in paras:
        if len(p) > size:                       # a wall of text: hard-split it
            for i in range(0, len(p), size - overlap):
                piece = p[i:i + size]
                if cur:
                    out.append(cur); cur = ""
                out.append(piece)
            continue
        if len(cur) + len(p) + 2 > size and cur:
            out.append(cur)
            cur = cur[-overlap:] + "\n\n" + p if overlap else p
        else:
            cur = (cur + "\n\n" + p) if cur else p
    if cur:
        out.append(cur)
    return [c.strip() for c in out if c.strip()]


def read_bates(path):
    """original_path -> (start, end) from a Bates ledger, keyed by sha too."""
    by_sha = {}
    if not path or not os.path.exists(path):
        return by_sha
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            by_sha[r["original_sha256"]] = (r["bates_start"], r["bates_end"])
    return by_sha


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--batch", type=int, default=16, help="chunks per embedding call")
    ap.add_argument("--rechunk", action="store_true",
                    help="if the chunk size changed since a document was indexed, throw away its chunks for this model and redo them")
    args = ap.parse_args()
    chunking = f"{CHUNK}/{OVERLAP}"

    spine = Superuser(); spine.sign_in()
    model = Model(EMBED_MODEL)
    bates = read_bates(os.environ.get("CXI_BATES_LEDGER"))

    files = []
    for root, _, names in os.walk(args.src):
        for n in names:
            if n.startswith("."):
                continue
            if os.path.splitext(n)[1].lower() in TEXT_EXT:
                files.append(os.path.join(root, n))
    files.sort()
    say(f"{len(files)} text files in {args.src}; model {EMBED_MODEL}")

    new_docs = skipped = new_chunks = 0
    for path in files:
        digest = sha256_file(path)
        doc = spine.find("documents", f"sha256 = {q(digest)}")
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        pieces = chunk_text(text)
        if not pieces:
            continue
        data = {
            "path": os.path.abspath(path), "sha256": digest,
            "title": os.path.splitext(os.path.basename(path))[0], "chars": len(text), "chunks": len(pieces),
            "chunking": chunking,
        }
        if digest in bates:
            data["bates_start"], data["bates_end"] = bates[digest]
        if doc:
            mine = f"document = {q(doc['id'])} && model = {q(EMBED_MODEL)}"
            if doc.get("chunking") and doc["chunking"] != chunking:
                # The text was cut differently last time. Mixing old and new pieces
                # would make search quote a corpus that never existed. Refuse, or redo on request.
                if not args.rechunk:
                    say(f"  {os.path.basename(path)}: indexed with chunking {doc['chunking']}, now {chunking}; "
                        f"skipped. Run with --rechunk to redo it, or set CXI_CHUNK_CHARS/OVERLAP back.")
                    skipped += 1
                    continue
                old = list(spine.list_all("chunks", mine, fields="id"))
                for c in old:
                    spine.delete("chunks", c["id"])
                say(f"  {os.path.basename(path)}: re-chunking ({doc['chunking']} -> {chunking}), {len(old)} old chunks removed for {EMBED_MODEL}")
            # only embed the chunks this model does not have yet
            have = {c["ordinal"] for c in spine.list_all("chunks", mine, fields="id,ordinal")}
            if len(have) == len(pieces):
                skipped += 1
                continue
            spine.update("documents", doc["id"], data)
        else:
            doc = spine.create("documents", data)
            new_docs += 1
            have = set()

        todo = [(i, p) for i, p in enumerate(pieces) if i not in have]
        for b in range(0, len(todo), args.batch):
            batch = todo[b:b + args.batch]
            started = time.time()
            vectors = model.embed([p for _, p in batch])
            for (i, p), v in zip(batch, vectors):
                spine.upsert("chunks", f"document = {q(doc['id'])} && model = {q(EMBED_MODEL)} && ordinal = {i}",
                             {"document": doc["id"], "ordinal": i, "text": p, "embedding": v, "model": EMBED_MODEL, "dim": len(v)})
                new_chunks += 1
            say(f"  {os.path.basename(path)}: chunks {batch[0][0]}–{batch[-1][0]} embedded ({time.time() - started:.1f}s)")
    say(f"done: {new_docs} new documents, {skipped} unchanged, {new_chunks} chunks embedded with {EMBED_MODEL}")


if __name__ == "__main__":
    main()
