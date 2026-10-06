#!/usr/bin/env python3
"""Make public copies of corpus text files.

Reads every .md and .txt file under --in and writes a copy under --out with
personal identifiers blanked. The originals are never opened for writing.
Line keys such as [UHZ/p1/L12] are never altered. The same input and the same
rules give the same output, byte for byte.

    python3 workers/public_copy.py --in ~/CXI/corpus --out ~/CXI/public

Rules applied, printed at every run:

    1  a nine-digit number after a label: BSN, citizen service number,
       insurance number, verzekeringsnummer
    2  a date after a date-of-birth label, on the same line or on the next
       two lines
    3  Dutch phone numbers: 06..., 020..., +31...
    4  IBAN
    5  every exact string listed in the file named by CXI_REDACT_TERMS,
       one per line, matched without regard to case

Rule 5 is where your own address and date of birth go. Keep that file outside
the repository. Without it only rules 1 to 4 run, and the worker says so.

After the rules the worker counts what still looks like an identifier:
nine-digit numbers, long digit runs and email addresses. It prints the count
per file. Read that line before anything is published. Nothing here proves a
file is clean.

An existing public copy is never overwritten. If the rules changed and the
output differs, the new copy is written beside the old one with the first
eight characters of its sha256 in the name.

Settings, environment variables only:

    CXI_REDACT_TERMS    path to a text file, one exact string per line
    CXI_PUBLIC_LOG      log path, default workers/log/public_copy.jsonl
                        (append only: file, sha256 of original and copy,
                        counts removed, counts left)

Standard library only. It reads and writes files and touches no back end.
"""
import argparse
import hashlib
import os
import re
import sys

from cxi_spine import log_append, say as _say

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.environ.get("CXI_PUBLIC_LOG", os.path.join(HERE, "log", "public_copy.jsonl"))
TEXT_EXT = {".md", ".txt"}
REMOVED = "[removed]"

RULES = [
    "1  nine-digit number after a BSN or insurance label",
    "2  date after a date-of-birth label, same line or next two lines",
    "3  Dutch phone numbers",
    "4  IBAN",
    "5  exact strings in CXI_REDACT_TERMS",
]

KEY = re.compile(r"^\[[A-Za-z0-9]+(?:[/-][A-Za-z0-9]+)*\]$")
DATE = r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}"
DOB_WORDS = r"(?:geb\.?\s*datum|gebdatum|geboortedatum|date of birth)"
DOB_LABEL = re.compile(r"(?i)\b" + DOB_WORDS + r"\b")
DOB_SAME = re.compile(r"(?i)(\b" + DOB_WORDS + r"\b[^0-9\n]{0,20}?)(" + DATE + r")")
DATE_ANY = re.compile(DATE)
LABELLED_NUMBER = re.compile(
    r"(?i)(\b(?:bsn|burgerservicenummer|citizen service number|verzekeringsnummer|insurance number)\b[^0-9\n]{0,40}?)(\d{9})(?!\d)")
PHONE = re.compile(r"(?<![\w/])(?:\+31|0031|0)[\s-]?(?:\(0\))?[1-9](?:[\s-]?\d){8}(?!\d)")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")
RESIDUAL = {
    "nine_digit": re.compile(r"(?<!\d)\d{9}(?!\d)"),
    "long_digits": re.compile(r"(?<!\d)\d{10,}(?!\d)"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
}


def say(msg):
    _say("public_copy", msg)


def read_terms(path):
    if not path:
        return []
    with open(path, encoding="utf-8") as f:
        terms = [t.strip() for t in f.read().splitlines() if len(t.strip()) >= 3]
    return [(t, re.compile(re.escape(t), re.I)) for t in terms]


def redact(text, terms):
    """-> (public text, counts removed per rule). Line keys and blank lines pass through."""
    counts = {"terms": 0, "labelled_number": 0, "dob": 0, "phone": 0, "iban": 0}
    out, pending = [], 0
    for line in text.split("\n"):
        if not line.strip() or KEY.match(line.strip()):
            out.append(line)
            continue
        for _, rx in terms:
            line, n = rx.subn(REMOVED, line)
            counts["terms"] += n
        line, n = LABELLED_NUMBER.subn(lambda m: m.group(1) + REMOVED, line)
        counts["labelled_number"] += n
        has_label = bool(DOB_LABEL.search(line))
        line, n = DOB_SAME.subn(lambda m: m.group(1) + REMOVED, line)
        counts["dob"] += n
        if has_label and n == 0:
            pending = 2
        elif pending > 0:
            line, n2 = DATE_ANY.subn(REMOVED, line)
            counts["dob"] += n2
            pending -= 1
        line, n = PHONE.subn(REMOVED, line)
        counts["phone"] += n
        line, n = IBAN.subn(REMOVED, line)
        counts["iban"] += n
        out.append(line)
    return "\n".join(out), counts


def residual(text):
    return {name: len(rx.findall(text)) for name, rx in RESIDUAL.items()}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inside(child, parent):
    child, parent = os.path.realpath(child), os.path.realpath(parent)
    return os.path.commonpath([child, parent]) == parent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    args = ap.parse_args()
    if inside(args.dst, args.src) or inside(args.src, args.dst):
        say("refused: --in and --out must be separate folders, neither inside the other")
        return 2

    terms = read_terms(os.environ.get("CXI_REDACT_TERMS"))
    say("rules applied:")
    for r in RULES:
        say("  " + r)
    if not terms:
        say("no terms file set: your own address and date of birth are removed only where a label names them")
    else:
        say(f"terms file: {len(terms)} strings")

    files = []
    for root, _, names in os.walk(args.src):
        for n in sorted(names):
            if not n.startswith(".") and os.path.splitext(n)[1].lower() in TEXT_EXT:
                files.append(os.path.join(root, n))
    files.sort()
    say(f"{len(files)} files in {args.src}")

    total = {"terms": 0, "labelled_number": 0, "dob": 0, "phone": 0, "iban": 0}
    left_total = {"nine_digit": 0, "long_digits": 0, "email": 0}
    written = unchanged = beside = 0
    for path in files:
        rel = os.path.relpath(path, args.src)
        try:
            with open(path, "rb") as f:
                original = f.read()
            public, counts = redact(original.decode("utf-8"), terms)
            n_removed = sum(counts.values())
            public = public.rstrip("\n") + f"\n\n[public copy: {n_removed} identifiers removed. The original is unaltered.]\n"
            data = public.encode("utf-8")
            target = os.path.join(args.dst, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if os.path.exists(target):
                with open(target, "rb") as f:
                    existing = f.read()
                if existing == data:
                    unchanged += 1
                    status = "unchanged"
                else:
                    stem, ext = os.path.splitext(target)
                    target = f"{stem}.{sha(data)[:8]}{ext}"
                    with open(target, "wb") as f:
                        f.write(data)
                    beside += 1
                    status = "rules changed, written beside the old copy"
            else:
                with open(target, "wb") as f:
                    f.write(data)
                written += 1
                status = "written"
            left = residual(public)
            for k, v in counts.items():
                total[k] += v
            for k, v in left.items():
                left_total[k] += v
            log_append(LOG, {"file": rel, "original_sha256": sha(original), "public_sha256": sha(data),
                             "removed": counts, "left": left, "status": status})
            say(f"{rel}: {status}; removed {n_removed}; left nine_digit={left['nine_digit']} long_digits={left['long_digits']} email={left['email']}")
        except Exception as e:  # one file failing must not stop the rest
            say(f"{rel}: failed: {e}")
    say(f"done: {written} written, {unchanged} unchanged, {beside} beside; removed {sum(total.values())} "
        f"(terms {total['terms']}, labelled numbers {total['labelled_number']}, dates of birth {total['dob']}, "
        f"phones {total['phone']}, iban {total['iban']}); left "
        f"nine_digit={left_total['nine_digit']} long_digits={left_total['long_digits']} email={left_total['email']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
