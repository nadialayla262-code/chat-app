# Migration path: Drive today, FlokiNET and Lovable tomorrow

The ending first: your findings live in Google Drive only because it is the one
place the cloud session can write today. The spine on FlokiNET is the home. Lovable
is the face. Drive is retired at the end.

## Where things are now

| Thing | Where it is | Who can reach it |
| --- | --- | --- |
| Scans (PDF) | Google Drive | cloud session reads their text layer |
| Keyed findings (dates, demands, absences, flags) | Drive sheets, folder "CUSTODI" | anyone with the link |
| FlokiNET server | bought, empty | nobody, until the spine is installed |
| Lovable | her paid project | she drives it; no session messages it |

## The path, in order

1. **Install the spine on FlokiNET, once.** `deploy/install.sh <domain> <email>`
   on the server. One run. It needs the server login, so it is done once by a
   person at a working computer. Nothing else in this list can start before it.
2. **Point the spine at its domain** with HTTPS. `deploy/README.md` covers it.
3. **Load the findings.** Each Drive sheet exports as CSV. A small loader
   (not written yet; it follows `workers/register_load.py`) upserts rows by key,
   so a row is never duplicated and never renumbered.
4. **Load the scans.** Originals copy from Drive to the server once. Image-only
   batches get real OCR there (OCRmyPDF, Tesseract, Dutch plus English), then
   Sorti numbers the pages as `CODE/pN/LNN`.
5. **Lovable reads the spine** over HTTPS through its one thin-layer file,
   per `docs/LOVABLE.md`. She drives Lovable. No session messages it.
6. **Retire Drive.** Keep the sheets as a dated copy; stop writing to them.

## Rules that do not change

- Append only. Never renumber. Never overwrite.
- A row without a key that resolves to a line and an exact quote is not written.
- Identifiers (citizen service numbers, birth dates, phone numbers, IBANs, email
  addresses, home addresses) are replaced by markers before anything is stored.
- Nothing is deleted from her Mac or Drive without her saying so.

## What is missing

- The findings loader (step 3).
- Anyone to run step 1. The cloud session cannot log in to the server.
- OCR for image-only batches (step 4), which needs the server.
