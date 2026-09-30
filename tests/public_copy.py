"""Public copies: identifiers blanked, line keys intact, originals untouched, same output twice, never overwritten."""
import hashlib, json, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); TMP = os.path.join(HERE, ".tmp", "public_copy")
fails = 0
def check(label, ok, detail=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'} {label}  {detail}"); fails += (not ok)
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()

shutil.rmtree(TMP, ignore_errors=True)
src, out, log = os.path.join(TMP, "in"), os.path.join(TMP, "out"), os.path.join(TMP, "log.jsonl")
os.makedirs(os.path.join(src, "sub"))
# Every value below is made up.
SAMPLE = """# TST — test file

code: TST
bates: not yet assigned

[TST/p1/L01]
NL: Verzekeringsnummer: 123456789
EN: Insurance number: 123456789

[TST/p1/L02]
NL: Geb. datum
EN: Date of birth

[TST/p1/L03]
NL: 01-02-1980
EN: 01-02-1980

[TST/p1/L04]
NL: Tel. 0612345678 of +31 6 12345678 of 020-1234567
EN: Phone 0612345678

[TST/p1/L05]
NL: Teststraat 1, 1234AB Teststad
EN: Teststraat 1, 1234AB Teststad

[TST/p1/L06]
NL: Rekening NL91ABNA0417164300 en kenmerk ZD173722340 en zaak C/13/746912 van 21-05-2025
EN: Account NL91ABNA0417164300

[FAM-01/L07]
NL: Mail naar iemand@example.test over het verzoek
EN: Mail to iemand@example.test
"""
open(os.path.join(src, "TST.md"), "w", encoding="utf-8").write(SAMPLE)
open(os.path.join(src, "sub", "Other.txt"), "w", encoding="utf-8").write("[OTH/p1/L01]\nNL: Bel 0687654321\n")
open(os.path.join(src, "skip.pdf"), "wb").write(b"%PDF not text")
terms = os.path.join(TMP, "terms.txt")
open(terms, "w", encoding="utf-8").write("Teststraat 1\n1234AB Teststad\nxx\n")

env = dict(os.environ, CXI_PUBLIC_LOG=log, CXI_REDACT_TERMS=terms)
def run(extra_env=None, a=None, b=None):
    e = dict(env, **(extra_env or {}))
    return subprocess.run([sys.executable, os.path.join(ROOT, "workers", "public_copy.py"), "--in", a or src, "--out", b or out],
                          env=e, capture_output=True, text=True)

before = {p: sha(os.path.join(src, p)) for p in ("TST.md", os.path.join("sub", "Other.txt"))}
r = run()
pub = open(os.path.join(out, "TST.md"), encoding="utf-8").read()
check("runs and prints the rules it applied", r.returncode == 0 and "rules applied:" in r.stdout and "5  exact strings" in r.stdout, r.stderr.strip()[-200:])
check("labelled insurance number removed, both languages", "123456789" not in pub and pub.count("Insurance number: [removed]") == 1 and "Verzekeringsnummer: [removed]" in pub)
check("date of birth on the lines after the label removed", "01-02-1980" not in pub and pub.count("[removed]") >= 4)
check("phone numbers removed in three forms", "0612345678" not in pub and "+31 6 12345678" not in pub and "020-1234567" not in pub)
check("address removed through the terms file", "Teststraat" not in pub and "1234AB" not in pub)
check("IBAN removed", "NL91ABNA0417164300" not in pub)
check("document numbers, case numbers and other dates survive", "ZD173722340" in pub and "C/13/746912" in pub and "21-05-2025" in pub)
check("every line key is unchanged", all(k in pub for k in ("[TST/p1/L01]", "[TST/p1/L02]", "[TST/p1/L03]", "[TST/p1/L04]", "[TST/p1/L05]", "[TST/p1/L06]", "[FAM-01/L07]")))
check("header lines survive", "bates: not yet assigned" in pub and "code: TST" in pub)
check("email addresses are left and counted, not claimed clean", "iemand@example.test" in pub and "email=2" in r.stdout.split("TST.md:")[1].splitlines()[0])
check("notice line names the count", "[public copy: " in pub and "The original is unaltered.]" in pub)
check("subfolders followed, non-text files skipped", os.path.exists(os.path.join(out, "sub", "Other.txt")) and not os.path.exists(os.path.join(out, "skip.pdf")) and "0687654321" not in open(os.path.join(out, "sub", "Other.txt")).read())
check("originals untouched", all(sha(os.path.join(src, p)) == h for p, h in before.items()))

first = open(os.path.join(out, "TST.md"), "rb").read()
r2 = run()
check("second run changes nothing and says so", r2.returncode == 0 and "unchanged" in r2.stdout and open(os.path.join(out, "TST.md"), "rb").read() == first)
lines = [json.loads(l) for l in open(log, encoding="utf-8")]
check("log is append only: two runs, four lines", len(lines) == 4 and lines[0]["original_sha256"] == before["TST.md"] and lines[0]["public_sha256"] == lines[2]["public_sha256"])
check("log counts what was removed", lines[0]["removed"]["phone"] == 4 and lines[0]["removed"]["labelled_number"] == 2 and lines[0]["removed"]["dob"] == 2 and lines[0]["removed"]["iban"] == 2, str(lines[0]["removed"]))

os.remove(terms); open(terms, "w", encoding="utf-8").write("Teststraat 1\n")
r3 = run()
names = sorted(os.listdir(out))
check("changed rules never overwrite: the new copy sits beside the old", any(n.startswith("TST.") and n != "TST.md" for n in names) and open(os.path.join(out, "TST.md"), "rb").read() == first, str(names))

r4 = run(a=src, b=os.path.join(src, "inside"))
check("refuses an output folder inside the input", r4.returncode == 2 and "refused" in r4.stdout and not os.path.exists(os.path.join(src, "inside")))
r5 = subprocess.run([sys.executable, os.path.join(ROOT, "workers", "public_copy.py"), "--in", src, "--out", os.path.join(TMP, "out2")],
                    env={k: v for k, v in env.items() if k != "CXI_REDACT_TERMS"}, capture_output=True, text=True)
check("without a terms file it says so and still runs rules 1 to 4", "no terms file set" in r5.stdout and "Teststraat" in open(os.path.join(TMP, "out2", "TST.md")).read())
sys.exit(1 if fails else 0)
