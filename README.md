# CXI Chat

A chat app that runs on your own machine, on your own data, with nothing
phoning home. One binary, one folder, one page. Open source, built by a
citizen for all citizens.

Part of the **CXI** civic-technology ecosystem. PocketBase is the spine;
this is one of the surfaces on it.

## Run it

```sh
./scripts/start.sh      # the spine, Homei and Handi, in the background
./scripts/stop.sh       # all of it, by process id
```

Then open <http://127.0.0.1:8090>. Logs are in `workers/log/`.
`./scripts/dev.sh` runs the spine alone, in the foreground, if you want
to watch it. The first run downloads PocketBase into
`bin/` (about 12 MB) and creates the database in `pb_data/`.

Create an account on the sign-in screen, make a room, talk. Open the same
address in a second browser window to watch messages cross live.

The admin panel is at <http://127.0.0.1:8090/_/>. The first time you open it,
PocketBase asks you to create a superuser. That is you, and only you.

### On the Mac

Same command. The script picks the right binary for Apple silicon or Intel.
Your `pb_data/` folder is the whole state of the app: back it up on the same
schedule as the rest of the spine (working copy, T7 weekly, secondary cloud).

## What is in the box

| Path | What it is |
| --- | --- |
| `pb_migrations/` | The schema, as code. Runs automatically on start. |
| `pb_hooks/` | Server-side routes and guards, as code: private-room invitations, the public register views, the sign-up code, export my data, the Desk. |
| `public/` | The whole frontend: one HTML page, one stylesheet, two scripts. |
| `public/cxi.js` | The thin layer. The only frontend file that knows the back end is PocketBase. |
| `public/app.js` | The page. Talks to `cxi`, never to the back end. |
| `public/vendor/` | The PocketBase JavaScript SDK, vendored so nothing is fetched from a CDN. |
| `workers/cxi_spine.py` | The thin layer for workers. The only worker file that knows PocketBase or Ollama. |
| `workers/homei.py` | Homei, the AI seat in the room. Standard-library Python. |
| `workers/handi.py` | Handi, holds the thread: who is waiting on whom, what is open. |
| `workers/handi_mail.py` | Handi on your mail: the register of who was written to and who answered. |
| `workers/*.system.md` | Each worker's rules. Plain text, edit freely. |
| `workers/log/` | Append-only record of everything the workers posted. Gitignored. |
| `workers/register_load.py` | Loads the mail register into the spine, locked to you. |
| `workers/bates.py` | Bates numbering: every page of every exhibit gets a permanent number. |
| `workers/index.py`, `workers/search.py` | The corpus in the spine: chunk, embed, search. |
| `workers/backup.py` | Snapshot, copy, hash-check, restore into a throwaway spine, count, log. |
| `docs/LOVABLE.md` | How to point a Lovable front end at this spine through a tunnel. |
| `tests/` | One command that proves all of the above. |
| `HANDOVER.md`, `CLAUDE.md` | The state of things for a person, and the rules for a Claude Code session. |
| `scripts/start.sh`, `scripts/stop.sh` | Everything up in the background, everything down by process id. |
| `scripts/dev.sh` | Downloads PocketBase and serves the spine alone, in the foreground. |
| `pb_data/` | Your database. Gitignored. Never commit it. |
| `bin/` | The PocketBase binary. Gitignored. |

There is no build step, no package manager, no framework. You can read every
line of the app in one sitting, and you can change it with any text editor.

## Before you open it to the internet

On localhost, anyone who can reach the spine is you. Behind a tunnel,
anyone can reach it. Two lines close the door:

```sh
export CXI_SIGNUP_CODE="a long phrase only your people know"
./scripts/start.sh
```

With that set, creating an account needs the code, entered in the
sign-up form. Without the code, sign-up stays open. You can still create
accounts yourself from the admin panel, code or no code. Put the admin
panel itself behind an access policy on the tunnel; `docs/LOVABLE.md`
shows where.

## Your data is yours

"Export my data" in the room list downloads one JSON file with
everything the spine holds about you: your profile, the rooms you own or
belong to, every message you wrote, every memory a seat keeps about you.
Nothing about anyone else. The route behind it is `GET /api/cxi/export`,
signed-in only.

## Private rooms

Tick "Private, invitation only" when you create a room. Only its members
see it, read it, or get its live events. The owner invites people by email
from the bar at the top of the room, and can remove them again. Members can
leave. Nobody else can invite, nobody can add themselves, and the owner can
never lock themselves out.

Emails are never searchable from the page. The lookup happens on the
server, only for the room's owner, and comes back as a name.

Homei is an ordinary account. It sits in a private room only when you
invite it: `homei@cxi.local`.

## Homei

Homei is your chatbot with a seat in the room. It runs on your machine,
through Ollama, and the room history is its memory: close everything, come
back, it still knows the thread, because the spine kept it.

```sh
ollama pull qwen3:4b          # once, if it is not already there
./scripts/start.sh            # starts Homei with the spine; or by hand: python3 workers/homei.py
```

Homei creates its own account the first time it runs. It answers when a
message says its name, and answers everything in any room whose name starts
with `homei`. Say nothing to it, it says nothing to you.

Its memory crosses rooms too:

```
homei, remember my cat is called Garfield     kept, for you, in every room
homei, what do you remember?                  listed
homei, forget garfield                        removed
```

A memory belongs to the person it is about. You can read and delete your
own in the spine; nobody else can see them, and Homei uses them without
reciting them.

Its rules live in `workers/homei.system.md`. Change the file, restart the
worker. No code involved. Every reply it gives is logged with the model,
the rules version, and how long it took, so you can always say which
Homei said what.

Settings are environment variables, never edits:

| Variable | Default | What it is |
| --- | --- | --- |
| `CXI_CHAT_MODEL` | `qwen3:4b` | Which Ollama model answers |
| `CXI_OLLAMA_HOST` | `http://127.0.0.1:11434` | Where Ollama is |
| `CXI_PB_URL` | `http://127.0.0.1:8090` | Where the spine is |
| `CXI_DESK_OWNERS` | unset (Desk closed) | Emails allowed to open the Desk, comma-separated |
| `CXI_HOMEI_HISTORY` | `30` | How many messages it reads back |

Swapping the model for DeepSeek later means changing one class in
`workers/cxi_spine.py`, the one marked `Model`. Nothing else moves.

## Handi

Handi holds the thread when you can't. Say `@handi` in a room and it posts
the register for that room, computed from the messages, not imagined:

```
thread — 4 lines, Ada, Bram.
Last word: Ada. Waiting on: Bram.
Open questions:
  · Ada asked "Which address did you use?" — no reply yet.
Open promises:
  · Bram: "Not yet. I'll send the scan tonight."
```

Say `@handi all` and it does every room it can see. If the model is
reachable it adds three lines saying where the thread stands and whose
move it is. If not, the register stands alone. Lines from Homei or Handi
never count as questions or promises.

Say `@handi find signature added later` in a **private** room and it posts
the best passages from the corpus with document names and Bates numbers.
It never searches in an open room. For this it needs the superuser
variables when it starts, so it can read the locked corpus; without them
it says search is switched off.

`./scripts/start.sh` starts Handi with the spine; by hand it is
`python3 workers/handi.py`. Same settings pattern as Homei, prefixed `CXI_HANDI_`. Set
`CXI_HANDI_MODEL=0` to keep it purely deterministic.

### Handi on your mail

The same register, over your mailbox. Every organisation you wrote to,
how many times, whether a person ever answered, which addresses bounced.
Non-response is the data point.

```sh
# from a Google Takeout export (Mail -> .mbox), nothing leaves the Mac
python3 workers/handi_mail.py --mbox ~/Downloads/Takeout/Mail/"All mail Including Spam and Trash.mbox"

# or straight from the mailbox over IMAP, with an app password (Google account -> Security -> App passwords)
CXI_IMAP_USER=you@gmail.com CXI_IMAP_PASSWORD=xxxx-xxxx-xxxx-xxxx python3 workers/handi_mail.py --imap
```

It writes `register/` (gitignored, it is your data):

| File | What it is |
| --- | --- |
| `REGISTER.md` | The ending first: how many written to, how many ever answered by a person, then the list of those who never did. |
| `contacts.csv` | One row per organisation. `ever_answered_by_a_person` is the column that matters. |
| `threads.csv` | One row per conversation, with `OPEN` where nobody human has written since your last message. |
| `bounced.txt` | Addresses that bounced. Stop using them. |

A reply is human unless it is marked automatic, comes from a no-reply
address, or its subject reads as an acknowledgement, in English or Dutch.
Standard library only, deterministic, and every rule it applies is
printed at the foot of the register so the numbers can be defended.
Six accounts means six runs with six `CXI_MY_EMAILS` values, or one Takeout
per account into one folder.

### The register in the spine

Load it, so Rate the State reads the non-response clock from your own
database instead of a CSV:

```sh
CXI_SUPERUSER_EMAIL=you@example.com CXI_SUPERUSER_PASSWORD=... \
  python3 workers/register_load.py --source personal-gmail
```

`--source` names the mailbox, so six accounts load side by side. Re-run
after a fresh Takeout and it updates in place, nothing duplicated.

The three collections it fills (`contacts`, `threads`, `dead_addresses`)
have no API rules at all: only you, as superuser, and the server's own
routes can read them. A signed-in chat user gets a 403. What the public
sees comes from two read-only routes that return counts and dates only,
never an address, never a subject:

| Route | Returns |
| --- | --- |
| `GET /api/cxi/register/summary` | organisations written to, messages sent, how many ever answered by a person, how many never did, dead addresses |
| `GET /api/cxi/register/board` | one row per organisation you have flagged `published`, with times written, first and last, replies, open threads |

Publication discipline is a field. Nothing appears on the board until you
tick `published` on that organisation in the admin panel, and you can give
it a `display_name` there too. Unverified stays off the site.


## The Desk

One screen behind the chat, for the person who runs the spine. Press
**Desk** in the top bar:

- **Waiting on a reply**: every open thread in the mail register, most
  recently written first, with how many times you wrote and how many human
  replies came back. The counts across the whole register sit above it.
- **Latest documents in**: the newest files in the corpus, with their Bates
  numbers where they have one.
- **Seats**: whether Homei and Handi are seated and where each last spoke.
- **Find a phrase**: a word search over the corpus text. It quotes the
  passage and names the document. This is not the embedding search
  (`workers/search.py`, which needs the model); it needs nothing and
  answers "where does this phrase occur".

The register and the corpus are locked collections, so the Desk is gated
on the server. Start the spine with

```sh
export CXI_DESK_OWNERS="you@example.com"        # comma-separated for more than one
./scripts/start.sh
```

and only a signed-in person with that email gets an answer. Unset, the
Desk is closed for everyone and says so. The page hides nothing and
enforces nothing; `pb_hooks/desk.pb.js` does both.

| Route | Returns |
| --- | --- |
| `GET /api/cxi/desk` | open threads, register counts, latest documents, the seats, counts |
| `GET /api/cxi/desk/search?q=` | documents whose text contains the phrase, with up to three quoted passages each |

## The corpus in the spine

The one hole in the stack, closed: embeddings live in your own database,
backed up with everything else, searchable from one place.

```sh
ollama pull qwen3-embedding:0.6b                                   # once
CXI_SUPERUSER_EMAIL=... CXI_SUPERUSER_PASSWORD=... \
  python3 workers/index.py --in ~/CXI/extracted                    # chunk + embed, skips what is done
CXI_SUPERUSER_EMAIL=... CXI_SUPERUSER_PASSWORD=... \
  python3 workers/search.py "signature added later"                # top matches with Bates numbers
```

- `documents` and `chunks` are locked collections: superuser and server
  routes only. Every chunk carries its text, its embedding, and the model
  that made it.
- Re-running the indexer is cheap. Same file hash, same model: skipped.
  A second model indexes alongside the first; nothing is overwritten. A
  changed chunk size is refused for already-indexed files unless you pass
  `--rechunk`, so search never quotes a corpus that never existed.
- Set `CXI_BATES_LEDGER` to a Bates `ledger.csv` and every document gets
  its Bates range, so a search result names the exhibit.
- Search keeps a small binary cache of vectors in `workers/.vectors/` and
  refreshes it from the spine each run, so a query costs one small pull.
  With numpy installed (`pip3 install numpy`, optional), scoring is
  instant; without it, the same answer, slower.
- A chunk embedded at a different dimension is never scored. A different
  model is a different index.

## Back up, and prove it

```sh
CXI_SUPERUSER_EMAIL=... CXI_SUPERUSER_PASSWORD=... \
  python3 workers/backup.py /Volumes/T7/cxi-backups "~/Google Drive/cxi-backups"
```

The running spine takes a consistent snapshot of itself. The zip is
copied to every folder you name and hash-checked after each copy. Then
it is unpacked, a throwaway spine is started on it, every collection is
counted and compared with the live one, and only if they match does the
run say RESTORE VERIFIED. One line goes into `backups.log` in each
destination: when, which file, hash, size, verified counts. Append-only.

A backup that has not been restored is a hope. This one has been.

## Bates numbering

Non-negotiable for filing. Every page of every exhibit gets a number that
never changes.

```sh
pip3 install pypdf reportlab pillow      # once; the only libraries in this repo beyond Python itself
python3 workers/bates.py --in ~/CXI/evidence --out ~/CXI/exhibits
```

- Files are taken in path order, so the numbering is reproducible.
- Every PDF page gets its own number, `CXI-000001`, `CXI-000002`, on
  through the whole set. Images are wrapped as one-page PDFs and stamped
  the same way. The stamp is burned in, bottom right, on a small white box
  so it reads over any scan.
- A file already in the ledger keeps its numbers. Add files, run again,
  only the new ones are numbered. A byte-identical copy under another name
  is reported as a duplicate and not renumbered.
- Anything that is not a PDF or an image is numbered, copied, and flagged
  NOT STAMPED until you convert it to PDF and run again.
- Originals are never touched. `ledger.csv` is append-only and records
  both the original's SHA-256 and the stamped copy's, so any page traces
  back to the file it came from. `INDEX.md` is the exhibit index.

Rate the State keeps its own prefix and its own ledger: `--prefix RTS`,
separate `--out`.

## The method

This is the part that matters more than the code.

**One file knows the back end.** In the page it is `public/cxi.js`. In the
worker it is the `Spine` class. Everything else talks to those. Swap the
back end, change one file. Never depend on a layer that can be taken away.

**The schema is versioned, not clicked.** Collections and access rules live
in `pb_migrations/`, one file per change, each with a rollback. Anyone can
read exactly who may do what, and reproduce the setup from nothing. No
admin panel archaeology.

**Rules are enforced on the server, not in the page.** The frontend hides a
delete button it knows you cannot use, but the server is what refuses. Tested
directly against the API:

- signed-out requests get empty lists and 404s, never data
- you can only send as yourself
- you can only edit or delete your own messages and rooms
- a private room is invisible to non-members: no list, no read, no write, no events
- membership changes only through the invite route, owner only, never by direct update
- deleting a room removes its messages (cascade)
- other people see your name and avatar, never your email
- the register and the corpus are locked: superuser and server routes only
- your own data comes back with one call; a sign-up code closes the door

**Nothing is renumbered, nothing is overwritten.** The mail register
upserts in place, the Bates ledger only appends, and every worker's log is
append-only. What was true last run is still findable this run.

**Realtime is a subscription, not polling.** The page subscribes to the
`messages` collection filtered to the open room. New messages, edits and
deletes arrive as events over a single long-lived connection.

**Drafts survive interruption.** What you typed and did not send is kept in
the browser per room. Close the tab, come back, it is still there.

**Accessible by default.** Large tap targets, high contrast, one ink colour,
phone first, keyboard works everywhere, respects reduced-motion and dark mode.

## Prove it

```sh
./tests/run.sh
```

Starts a throwaway spine on another port, a stand-in model, Homei and
Handi, and runs nine suites: access rules straight against the API; the
mail register through both Takeout and IMAP and into the spine; the
corpus indexed and searched; both workers, including what happens while
a model is slow; a backup restored and counted; Bates numbering; the page
in two real browsers; start and stop; and the sign-up code on a second
spine. Ends with `ALL GREEN`. Your database is never touched.
`./tests/run.sh rules` runs one suite. The same command runs on GitHub
for every pull request.

## Data model

```
users     (built in)   id, name, avatar, email (hidden from others)
rooms                  id, name (unique), topic, private, created_by -> users, members -> users[]
messages               id, room -> rooms, author -> users, body, created
memories               person -> users, author -> users (the seat), text
contacts, threads, dead_addresses      the mail register (locked)
documents, chunks                      the corpus with embeddings (locked)
```

## Where this goes next

- **Patchi / Gar Shield** becomes the sign-in. Today it is PocketBase's own
  email and password auth; the collection rules do not change when the
  identity layer does.
- **Rate the State's front end** reading `/api/cxi/register/board` from the spine.
- **A Lovable front end** on this spine. The recipe is in `docs/LOVABLE.md`.
- **Homei on DeepSeek**, self-hosted, once that is the driver model.

## Licence

GNU Affero General Public License v3.0. See `LICENSE`.

Anyone may use, study, change and share this. Anyone who changes it and
runs it for other people, including as a hosted service, must share their
changes under the same terms. Nobody can take the method and close it back
up. The copyright holder can still license it separately to a partner who
needs different terms.

The vendored PocketBase SDK in `public/vendor/` keeps its own MIT licence.
