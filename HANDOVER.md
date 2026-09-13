# HANDOVER — the state of things, in plain words

The ending first: **everything in this repo works and has been tested, on
built data, not on yours yet.** One command on the Mac brings it all
up. Nothing here needs Claude Code to run.

## What exists

| Thing | What it does for you | Status |
| --- | --- | --- |
| **The chat** | Your server, your data. Rooms, live messages, drafts that survive interruption. Phone first. | Working, tested in two browsers |
| **Export my data** | One click in the room list downloads everything the spine holds about the signed-in person. | Working, tested |
| **Private rooms** | Invitation only. Non-members see nothing, get nothing, can't write. You invite by email, members can leave, you can never lock yourself out. | Working, tested |
| **Homei** | Your chatbot, in the room, on your machine, through Ollama. The room history is its memory, and "homei, remember …" carries facts across rooms. Its rules are a text file. | Logic tested against a stand-in model. Not yet run with the real `qwen3:4b` |
| **Handi in the room** | Say `@handi` and it posts who is waiting on whom, what is unanswered, what was promised. Counted, not imagined. `@handi find …` in a private room searches the corpus. | Working, tested |
| **Handi on your mail** | Reads a Takeout export or your mailbox over IMAP and writes the register: organisations written to, times, who ever answered with a human word, which addresses bounced. | Both paths working on a built mailbox. Not yet run on your real mail |
| **The register in the spine** | Loads that register into your database, locked to you. Two public routes give counts only, and only for organisations you flag published. | Working, tested |
| **Bates numbering** | Every page of every exhibit gets a permanent number. Ledger is append-only. Duplicates are named. Originals never touched. | Working, tested. Needs `pip3 install pypdf reportlab pillow` |
| **The corpus in the spine** | `index.py` chunks and embeds your text files into locked collections; `search.py` finds the passage and names the exhibit. | Working, tested with a stand-in embedder. Not yet run on the real corpus or the real embedding model |
| **Backup with a tested restore** | Snapshot, copy, hash-check, restore into a throwaway spine, count, log. | Working, tested |
| **The Lovable recipe** | `docs/LOVABLE.md`: tunnel from the Mac, a paste-ready first message for Lovable. | Written, not yet fired: needs the tunnel up first |

## Bring it up

```sh
./scripts/start.sh               # spine + Homei + Handi, in the background; logs in workers/log/
./scripts/stop.sh                # all of it
```

Set `CXI_SUPERUSER_EMAIL` and `CXI_SUPERUSER_PASSWORD` in that shell first
if you want `@handi find`. Homei needs Ollama running with `qwen3:4b`.
One terminal, two commands. The three-terminal way still works:
`./scripts/dev.sh`, `python3 workers/homei.py`, `python3 workers/handi.py`.

First time: open http://127.0.0.1:8090/_/ and create the superuser. That
is you. Then open http://127.0.0.1:8090, create an account, make a room.
Homei and Handi make their own accounts the first time they run
(`homei@cxi.local`, `handi@cxi.local`). Invite them into private rooms by
those addresses.

## Prove it works, without trusting anyone

```sh
./tests/run.sh
```

Starts a throwaway spine on another port, a stand-in model, both workers,
and runs nine suites: rules, mail register, corpus, workers, backup,
Bates, browser, start and stop, sign-up code. Ends with `ALL GREEN` or
says what failed. Your real database is never touched.

## Run it on your real data, in this order

1. **Bates first.** `python3 workers/bates.py --in ~/CXI/evidence --out ~/CXI/exhibits`.
   Read `INDEX.md`. Anything flagged NOT STAMPED: convert to PDF, run again.
2. **The mail register.** One Takeout per account, or IMAP with an app
   password. `python3 workers/handi_mail.py --mbox <file>`. Read
   `register/REGISTER.md`. Check `bounced.txt` and stop using those addresses.
3. **Load it.** `CXI_SUPERUSER_EMAIL=... CXI_SUPERUSER_PASSWORD=... python3 workers/register_load.py --source <account-label>`.
   Repeat per account with a different label.
4. **Publish what you have verified.** In the admin panel, `contacts`
   collection, tick `published` on an organisation. Only then does it
   appear on `/api/cxi/register/board`.
5. **Index the corpus.** `CXI_BATES_LEDGER=~/CXI/exhibits/ledger.csv python3 workers/index.py --in ~/CXI/extracted`
   with the superuser variables set. Then `python3 workers/search.py "what you are looking for"`.
6. **Homei with the real model.** `ollama list` should show `qwen3:4b`.
   Start the worker, say its name in a room. Adjust
   `workers/homei.system.md` until it sounds right. Restart the worker.

## The repository

`main` is the branch to review into; work arrives by pull request. The
licence is AGPL-3.0: open, and it stays open. One click is still yours:
on GitHub, Settings → General → Default branch, choose `main`. The proxy
this was built through is not allowed to change repository settings.

## Before the tunnel

Set `CXI_SIGNUP_CODE` in the shell that starts the spine. Sign-up then
needs the code. Do this before `cloudflared` runs, not after.

## Back up

`pb_data/` is the whole state: chat, register, memories, corpus. One
command snapshots it, copies it to the T7 and the secondary, and proves
the copy restores before it says so:

```sh
CXI_SUPERUSER_EMAIL=... CXI_SUPERUSER_PASSWORD=... \
  python3 workers/backup.py /Volumes/T7/cxi-backups "~/Google Drive/cxi-backups"
```

Weekly, or after anything you would mind losing. `register/` and
`~/CXI/exhibits/` are plain folders; copy them the same way. The repo
itself carries no data.

## What is not done

- Homei on the real model has not been heard yet.
- The backup has not yet run against your real `pb_data/`. The first run
  is the one that matters; read the RESTORE VERIFIED line.
- Handi on mail has not seen a real mailbox. Expect the auto-reply and
  bounce patterns to need one or two additions after the first real run.
  They are two regular expressions at the top of `workers/handi_mail.py`.
- The Lovable front end is a recipe, not a build.
- Rate the State is deliberately not in this repo. It reads the board
  route from its own, separate, codebase.
- The corpus indexer has not seen the real corpus or the real embedding
  model. First run: `ollama pull qwen3-embedding:0.6b`, then
  `python3 workers/index.py --in ~/CXI/extracted` with the superuser
  variables set, and go and do something else; embedding thousands of
  documents on a laptop takes a while. Then `search.py` anything.

## If something breaks

Every worker prints the moment it fails and keeps going. Logs are in
`workers/log/` (append-only) and, for the test run, `tests/.tmp/`. The
spine's own log is in the admin panel under Logs. Nothing in this repo
deletes anything, ever, so the way back is always the last backup of
`pb_data/`.
