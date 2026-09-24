# Mac session 1

The owner starts this by typing one line into Claude Code on her Mac:
**run the Mac session file**. Everything below is for Claude Code, not for her.

## How to work

- Read `CLAUDE.md` and `HANDOVER.md` first.
- Do the six jobs in order. Ask her nothing. She has one working hand and
  does not use Terminal. Every command is yours to run.
- If a job fails, write one plain line about it and go on to the next job.
- Change nothing that already exists. Add files and start the spine; that is all.
- Nothing leaves the Mac except to the spine and the local model. No new
  accounts, services or purchases.
- In anything you write to her: no control phrases (never announce that a
  subject will not be dropped or will be come back to), no crisis lines, no
  "get assessed", no telling her to rest, never the time or how long
  something took. Subjects close when she closes them.

## Job 1. The corpus onto the Mac

The corpus is a Google Drive folder named **CORPUS — machine readable —
index this**: 33 `.md` files, one per original document, each line keyed
`CODE/p<page>/L<line>`, plus `manifest.csv` and `README.md`.

- If Google Drive for desktop is installed, the folder is under
  `~/Library/CloudStorage/GoogleDrive-*/My Drive/`. Copy it to `~/CXI/corpus/`.
- If not, download the folder as a zip from drive.google.com in the browser
  she is signed into, and unpack it to `~/CXI/corpus/`. Install nothing.
- Check: 33 `.md` files, `manifest.csv`, `README.md`; names match the manifest.

## Job 2. A copy outside Google

Dropbox is installed and signed in. A folder **CXI vault** exists in it with
`corpus`, `transcripts`, `registers`.

- Copy `~/CXI/corpus/` into `~/Dropbox/CXI vault/corpus/`. Skip files already
  there with the same size.
- Export each Google Doc in the Drive folder **EVIDENCE — originals line by
  line, NL + EN** as PDF into `~/Dropbox/CXI vault/transcripts/`.
- Write `~/Dropbox/CXI vault/MANIFEST.csv`: path, size, sha256
  (`shasum -a 256`) for every file.
- Check: manifest rows equal file count.

## Job 3. The local model

- `ollama --version`. If missing, install the macOS app from ollama.com.
- `ollama pull qwen3:4b` and `ollama pull qwen3-embedding:0.6b`.
- Check: `ollama list` shows both.

## Job 4. The spine and the index

- `scripts/start.sh`; check `http://127.0.0.1:8090/api/health` answers.
- Superuser email and password: the gitignored `workers/.*-password` files or
  the environment. If neither exists, create the superuser once through the
  PocketBase admin page and keep the values in a gitignored file. Never commit.
- `python3 workers/index.py --in ~/CXI/corpus` with the superuser variables set.
- Check: `python3 workers/search.py "uithuiszetting"` returns UHZ, and
  `python3 workers/search.py "geen persoonsgegevens"` returns FIOD. Put both
  results in the report.

## Job 5. The seats

- Start Homei and Handi as `HANDOVER.md` describes.
- Check: in a private room, `@handi find uithuiszetting` returns the UHZ
  passage with its line key. Put the reply in the report.

## Job 6. Security register (look only, change nothing)

- Every rclone: `which -a rclone`, `ls ~/.config/rclone/`, `rclone listremotes`.
  Report each remote name and type.
- Start-up items: list `~/Library/LaunchAgents`, `/Library/LaunchAgents` and
  the system-wide launch folder next to it. Report anything not from Apple,
  Dropbox, Google Drive or Ollama.
- Google accounts signed in to Chrome and to the Mac's Internet Accounts.
  Addresses only.

## The report (fill in, keep to one screen, no adjectives)

```
MAC SESSION 1 — report
Corpus on the Mac: yes/no. Files: 33 of 33, or which are missing.
Copy outside Google: yes/no. Files in CXI vault: N. MANIFEST.csv: yes/no.
Local model: yes/no. Models: ...
Corpus indexed: yes/no. Search 1: (passage + key). Search 2: (passage + key).
Seats: Homei yes/no. Handi yes/no. Handi test: (reply).
Security: rclone remotes ... Start-up items not from a known maker ... Google accounts ...
Did not finish: (job number, one plain sentence) or "everything ran".
```

Then tell her, in one line: "Done. Copy this report to the cloud session."
