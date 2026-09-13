# HANDOVER — the state of things, in plain words

The ending first: **everything in this repo works and has been tested, on
built data, not on yours yet.** Three terminals on the Mac bring it all
up. Nothing here needs Claude Code to run.

## What exists

| Thing | What it does for you | Status |
| --- | --- | --- |
| **The chat** | Your server, your data. Rooms, live messages, drafts that survive interruption. Phone first. | Working, tested in two browsers |
| **Private rooms** | Invitation only. Non-members see nothing, get nothing, can't write. You invite by email, members can leave, you can never lock yourself out. | Working, tested |
| **Homei** | Your chatbot, in the room, on your machine, through Ollama. The room history is its memory. Its rules are a text file. | Logic tested against a stand-in model. Not yet run with the real `qwen3:4b` |
| **Handi in the room** | Say `@handi` and it posts who is waiting on whom, what is unanswered, what was promised. Counted, not imagined. | Working, tested |
| **Handi on your mail** | Reads a Takeout export or your mailbox over IMAP and writes the register: organisations written to, times, who ever answered with a human word, which addresses bounced. | Working on a built mailbox. Not yet run on your real mail |
| **The register in the spine** | Loads that register into your database, locked to you. Two public routes give counts only, and only for organisations you flag published. | Working, tested |
| **Bates numbering** | Every page of every exhibit gets a permanent number. Ledger is append-only. Duplicates are named. Originals never touched. | Working, tested. Needs `pip3 install pypdf reportlab pillow` |
| **The corpus in the spine** | `index.py` chunks and embeds your text files into locked collections; `search.py` finds the passage and names the exhibit. | Working, tested with a stand-in embedder. Not yet run on the real corpus or the real embedding model |
| **The Lovable recipe** | `docs/LOVABLE.md`: tunnel from the Mac, a paste-ready first message for Lovable. | Written, not yet fired: needs the tunnel up first |

## Bring it up

```sh
./scripts/dev.sh                 # terminal 1: the spine, http://127.0.0.1:8090
python3 workers/homei.py         # terminal 2: Homei (needs Ollama running with qwen3:4b)
python3 workers/handi.py         # terminal 3: Handi
```

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
and runs every suite: rules, workers, mail register, Bates, browser. Ends
with `ALL GREEN` or says what failed. Your real database is never touched.

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

## Back up

`pb_data/` is the whole state of the chat and the register. It goes on the
same schedule as everything else: working copy on the Mac, T7 weekly,
secondary cloud. `register/` and `~/CXI/exhibits/` likewise. The repo
itself carries no data.

## What is not done

- Homei on the real model has not been heard yet.
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
