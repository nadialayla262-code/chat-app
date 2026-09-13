#!/usr/bin/env python3
"""Bates numbering — every page of every exhibit gets a number that never changes.

    python3 workers/bates.py --in ~/CXI/evidence --out ~/CXI/exhibits

What it does, per file in --in (sorted by path, so the order is reproducible):

  1. SHA-256 of the original. If that hash is already in the ledger, the
     file keeps the numbers it was given last time. Nothing is ever
     renumbered. Add files, run again, only the new ones get numbers.
  2. PDFs: every page is stamped bottom-right with its own number,
     CXI-000001, CXI-000002, ... continuing across files. Images (jpg, png,
     tif) are wrapped as one-page PDFs and stamped the same way.
  3. Anything else (docx, eml, xlsx ...) is numbered in the ledger, copied
     with its number in the filename, and flagged NOT STAMPED so you convert
     it to PDF and run again.
  4. The stamped copy goes to --out as  CXI-000001__original-name.pdf.
     The original is never touched.
  5. ledger.csv in --out is append-only: number range, pages, original
     path, original SHA-256, stamped path, stamped SHA-256, run id.
     INDEX.md is rewritten from the ledger each run.

The thing that makes a document set survive contact with a lawyer is not
that it is perfect. It is that it is traceable. The ledger is the trace.

Needs three libraries, once:

    pip3 install pypdf reportlab pillow

Settings:

    --prefix   CXI        (Rate the State keeps its own prefix and its own ledger)
    --digits   6
    --start    1          first number, only used when the ledger is empty
"""
import argparse
import csv
import hashlib
import io
import os
import shutil
import sys
from datetime import datetime, timezone

try:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from PIL import Image
except BaseException as e:  # ImportError, or a broken native package refusing to load
    print(f"[bates] PDF libraries unavailable ({type(e).__name__}: {e}). Run:  pip3 install pypdf reportlab pillow", file=sys.stderr)
    sys.exit(2)

TOOL_VERSION = "1"
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
LEDGER_FIELDS = ["bates_start", "bates_end", "pages", "original_path", "original_sha256",
                 "stamped_path", "stamped_sha256", "stamped", "run_id", "stamped_at_utc", "tool_version"]


def say(msg):
    print(f"[bates] {msg}", flush=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def label(prefix, n, digits):
    return f"{prefix}-{n:0{digits}d}"


def stamp_pdf(src_reader, out_path, prefix, first, digits):
    """Write src pages to out_path, each stamped with its own number. Returns page count."""
    writer = PdfWriter()
    n = first
    for page in src_reader.pages:
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        c.setFont("Helvetica-Bold", 9)
        text = label(prefix, n, digits)
        tw = c.stringWidth(text, "Helvetica-Bold", 9)
        # Small white box behind the number so it reads over any scan.
        c.setFillColorRGB(1, 1, 1)
        c.rect(w - tw - 30, 14, tw + 12, 16, stroke=0, fill=1)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(w - tw - 24, 18, text)
        c.save()
        buf.seek(0)
        overlay = PdfReader(buf).pages[0]
        page.merge_page(overlay)
        writer.add_page(page)
        n += 1
    with open(out_path, "wb") as f:
        writer.write(f)
    return n - first


def image_to_pdf_reader(path):
    """Every frame becomes a page: a six-page TIFF fax is six numbered pages, not one."""
    from PIL import ImageSequence
    img = Image.open(path)
    frames = []
    for frame in ImageSequence.Iterator(img):
        f = frame.convert("RGB") if frame.mode not in ("RGB", "L") else frame.copy()
        frames.append(f)
    buf = io.BytesIO()
    dpi = img.info.get("dpi", (150, 150))[0] or 150
    frames[0].save(buf, format="PDF", resolution=dpi, save_all=True, append_images=frames[1:])
    buf.seek(0)
    return PdfReader(buf)


def read_ledger(path):
    rows = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    return rows


def append_ledger(path, rows):
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_FIELDS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def write_index(out_dir, ledger, prefix):
    rows = sorted(ledger, key=lambda r: int(r["bates_start"].rsplit("-", 1)[1]))
    total_pages = sum(int(r["pages"]) for r in rows)
    lines = [f"# Exhibit index — {prefix}", "",
             f"{len(rows)} exhibits, {total_pages} numbered pages. Numbers are permanent; the ledger is append-only.", "",
             "| Bates range | pages | original | stamped | SHA-256 (original, first 12) |", "|---|---|---|---|---|"]
    for r in rows:
        rng = r["bates_start"] if r["bates_start"] == r["bates_end"] else f"{r['bates_start']} – {r['bates_end']}"
        flag = "" if r["stamped"] == "yes" else " **NOT STAMPED — convert to PDF**"
        lines.append(f"| {rng} | {r['pages']} | {os.path.basename(r['original_path'])} | {os.path.basename(r['stamped_path'])}{flag} | `{r['original_sha256'][:12]}` |")
    lines += ["", "## Method", "",
              "- Files are processed in path order. Each file's SHA-256 is checked against the ledger first; a file already numbered keeps its numbers.",
              "- Every PDF page and every image gets one number, continuing across files. Non-PDF documents receive a placeholder number and are flagged until converted.",
              "- The stamp is burned into the page at bottom right on a white box. Originals are never modified.",
              "- Both the original and the stamped copy are hashed and recorded, so any page can be traced back to the file it came from."]
    with open(os.path.join(out_dir, "INDEX.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src", required=True, help="folder of originals (searched recursively)")
    ap.add_argument("--out", required=True, help="folder for stamped copies, ledger.csv and INDEX.md")
    ap.add_argument("--prefix", default="CXI")
    ap.add_argument("--digits", type=int, default=6)
    ap.add_argument("--start", type=int, default=1)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    ledger_path = os.path.join(args.out, "ledger.csv")
    ledger = read_ledger(ledger_path)
    known = {r["original_sha256"]: r for r in ledger}
    next_n = args.start
    if ledger:
        next_n = max(int(r["bates_end"].rsplit("-", 1)[1]) for r in ledger) + 1
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    files = []
    for root, _, names in os.walk(args.src):
        for n in names:
            if n.startswith(".") or n in ("ledger.csv", "INDEX.md"):
                continue
            files.append(os.path.join(root, n))
    files.sort()
    say(f"{len(files)} files in {args.src}; ledger has {len(ledger)} exhibits; next number {label(args.prefix, next_n, args.digits)}")

    new_rows = []
    skipped = 0
    for path in files:
        digest = sha256(path)
        if digest in known:
            skipped += 1
            prior = known[digest]
            if os.path.abspath(path) != prior["original_path"]:
                say(f"duplicate: {os.path.basename(path)} is byte-identical to {os.path.basename(prior['original_path'])} "
                    f"({prior['bates_start']}); same numbers, not renumbered")
            continue
        ext = os.path.splitext(path)[1].lower()
        base = os.path.splitext(os.path.basename(path))[0]
        first = next_n
        stamped = "yes"
        try:
            if ext == ".pdf":
                reader = PdfReader(path)
                if reader.is_encrypted:
                    reader.decrypt("")
                out_path = os.path.join(args.out, f"{label(args.prefix, first, args.digits)}__{base}.pdf")
                pages = stamp_pdf(reader, out_path, args.prefix, first, args.digits)
            elif ext in IMAGE_EXT:
                out_path = os.path.join(args.out, f"{label(args.prefix, first, args.digits)}__{base}.pdf")
                pages = stamp_pdf(image_to_pdf_reader(path), out_path, args.prefix, first, args.digits)
            else:
                out_path = os.path.join(args.out, f"{label(args.prefix, first, args.digits)}__{os.path.basename(path)}")
                shutil.copy2(path, out_path)
                pages = 1
                stamped = "no"
        except Exception as e:
            say(f"FAILED {path}: {e}  (not numbered; fix the file and run again)")
            continue
        row = {
            "bates_start": label(args.prefix, first, args.digits),
            "bates_end": label(args.prefix, first + pages - 1, args.digits),
            "pages": pages,
            "original_path": os.path.abspath(path),
            "original_sha256": digest,
            "stamped_path": os.path.abspath(out_path),
            "stamped_sha256": sha256(out_path),
            "stamped": stamped,
            "run_id": run_id,
            "stamped_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "tool_version": TOOL_VERSION,
        }
        new_rows.append(row)
        known[digest] = row
        next_n = first + pages
        say(f"{row['bates_start']}–{row['bates_end']}  {os.path.basename(path)}" + ("" if stamped == "yes" else "  NOT STAMPED"))

    if new_rows:
        append_ledger(ledger_path, new_rows)
    write_index(args.out, ledger + new_rows, args.prefix)
    say(f"{len(new_rows)} new exhibits numbered, {skipped} already in the ledger, "
        f"next free number {label(args.prefix, next_n, args.digits)}. Index: {os.path.join(args.out, 'INDEX.md')}")


if __name__ == "__main__":
    main()
