"""Bates numbering on built evidence: first run, no-op re-run, duplicate, addition, stamps on every page."""
import os, shutil, subprocess, sys, csv
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); TMP = os.path.join(HERE, ".tmp")
try:
    from pypdf import PdfReader
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4, landscape
    from PIL import Image
except BaseException as e:  # ImportError, or a broken native package refusing to load
    print(f"bates: skipped (PDF libraries unavailable: {type(e).__name__}; pip3 install pypdf reportlab pillow)"); sys.exit(0)
fails = 0
def check(label, ok, detail=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'} {label}  {detail}"); fails += (not ok)
ev = os.path.join(TMP, "evidence"); ex = os.path.join(TMP, "exhibits")
shutil.rmtree(ev, ignore_errors=True); shutil.rmtree(ex, ignore_errors=True); os.makedirs(os.path.join(ev, "sub"))
c = canvas.Canvas(os.path.join(ev, "b-record.pdf"), pagesize=A4)
for i in range(3): c.drawString(72, 800, f"record page {i+1}"); c.showPage()
c.save()
c = canvas.Canvas(os.path.join(ev, "sub", "c-order.pdf"), pagesize=landscape(A4))
for i in range(2): c.drawString(72, 500, f"order page {i+1}"); c.showPage()
c.save()
Image.new("RGB", (1200, 1600), "white").save(os.path.join(ev, "a-scan.jpg"))
f1, f2 = Image.new("L", (800, 1000), 255), Image.new("L", (800, 1000), 200)
f1.save(os.path.join(ev, "d-fax.tif"), save_all=True, append_images=[f2])
open(os.path.join(ev, "e-notes.docx"), "wb").write(b"PK fake")
run = lambda: subprocess.run([sys.executable, os.path.join(ROOT, "workers", "bates.py"), "--in", ev, "--out", ex], capture_output=True, text=True).stdout
o1 = run()
ledger = list(csv.DictReader(open(os.path.join(ex, "ledger.csv"))))
check("five exhibits numbered", len(ledger) == 5, o1.strip().splitlines()[-1])
fax = next(r for r in ledger if "d-fax" in r["original_path"])
check("two-frame TIFF is two numbered pages", fax["pages"] == "2" and fax["bates_start"] != fax["bates_end"], f"{fax['bates_start']}-{fax['bates_end']}")
check("path order: scan first, record second", ledger[0]["bates_start"] == "CXI-000001" and ledger[1]["bates_start"] == "CXI-000002" and ledger[1]["bates_end"] == "CXI-000004")
check("docx flagged not stamped", any(r["stamped"] == "no" for r in ledger))
o2 = run(); check("re-run numbers nothing", "0 new exhibits" in o2)
shutil.copy(os.path.join(ev, "sub", "c-order.pdf"), os.path.join(ev, "f-copy.pdf"))
c = canvas.Canvas(os.path.join(ev, "g-new.pdf"), pagesize=A4); c.drawString(72, 800, "new"); c.showPage(); c.save()
o3 = run()
check("duplicate reported, not renumbered", "duplicate: f-copy.pdf" in o3 and "1 new exhibits" in o3)
ledger = list(csv.DictReader(open(os.path.join(ex, "ledger.csv"))))
check("ledger append-only, six rows, new file takes next free number", len(ledger) == 6 and ledger[-1]["bates_start"] == "CXI-000010")
for r in ledger:
    if r["stamped"] != "yes": continue
    pages = PdfReader(r["stamped_path"]).pages
    start = int(r["bates_start"].rsplit("-", 1)[1])
    ok = all(f"CXI-{start+i:06d}" in (p.extract_text() or "") for i, p in enumerate(pages))
    check(f"every page stamped: {os.path.basename(r['original_path'])}", ok and len(pages) == int(r["pages"]))
print("bates: all passed" if not fails else f"bates: {fails} FAILED"); sys.exit(1 if fails else 0)
