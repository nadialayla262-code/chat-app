# CXI Chat

A chat app that runs on your own machine, on your own data, with nothing
phoning home. One binary, one folder, one page. Open source, built by a
citizen for all citizens.

Part of the **CXI** civic-technology ecosystem. PocketBase is the spine;
this is one of the surfaces on it.

## Run it

```sh
./scripts/dev.sh
```

Then open <http://127.0.0.1:8090>. The first run downloads PocketBase into
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
| `pb_hooks/` | Server-side routes, as code. Today: inviting people to private rooms. |
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
| `docs/LOVABLE.md` | How to point a Lovable front end at this spine through a tunnel. |
| `scripts/dev.sh` | Downloads PocketBase and serves everything. |
| `pb_data/` | Your database. Gitignored. Never commit it. |
| `bin/` | The PocketBase binary. Gitignored. |

There is no build step, no package manager, no framework. You can read every
line of the app in one sitting, and you can change it with any text editor.

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
python3 workers/homei.py      # in a second terminal, next to dev.sh
```

Homei creates its own account the first time it runs. It answers when a
message says its name, and answers everything in any room whose name starts
with `homei`. Say nothing to it, it says nothing to you.

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

```sh
python3 workers/handi.py
```

Same settings pattern as Homei, prefixed `CXI_HANDI_`. Set
`CXI_HANDI_MODEL=0` to keep it purely deterministic.

### Handi on your mail

The same register, over your mailbox. Every organisation you wrote to,
how many times, whether a person ever answered, which addresses bounced.
Non-response is the data point.

```sh
# from a Google Takeout export (Mail -> .mbox), nothing leaves the Mac
python3 workers/handi_mail.py --mbox ~/Downloads/Takeout/Mail/"All mail Including Spam and Trash.mbox"

# or straight from the mailbox over IMAP, with an app password
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

## The method

This is the part that matters more than the code.

**One file knows the back end.** In the page it is `public/cxi.js`. In the
worker it is the `Spine` class. Everything else talks to those. Swap the
back end, change one file. Never depend on a layer that can be taken away.

**The schema is versioned, not clicked.** Collections and access rules live in
`pb_migrations/1757800000_init_chat.js`. Anyone can read exactly who may do
what, and reproduce the setup from nothing. No admin panel archaeology.

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

**Realtime is a subscription, not polling.** The page subscribes to the
`messages` collection filtered to the open room. New messages, edits and
deletes arrive as events over a single long-lived connection.

**Drafts survive interruption.** What you typed and did not send is kept in
the browser per room. Close the tab, come back, it is still there.

**Accessible by default.** Large tap targets, high contrast, one ink colour,
phone first, keyboard works everywhere, respects reduced-motion and dark mode.

## Data model

```
users     (built in)   id, name, avatar, email (hidden from others)
rooms                  id, name (unique), topic, private, created_by -> users, members -> users[]
messages               id, room -> rooms, author -> users, body, created
```

## Where this goes next

- **Patchi / Gar Shield** becomes the sign-in. Today it is PocketBase's own
  email and password auth; the collection rules do not change when the
  identity layer does.
- **The mail register into the spine**, so Rate the State reads it live.
- **A Lovable front end** on this spine. The recipe is in `docs/LOVABLE.md`.
- **Homei on DeepSeek**, self-hosted, once that is the driver model.

## Licence

MIT. See `LICENSE`. The vendored PocketBase SDK carries its own MIT licence
in `public/vendor/`.
