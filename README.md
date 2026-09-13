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
| `public/` | The whole frontend: one HTML page, one stylesheet, two scripts. |
| `public/cxi.js` | The thin layer. The only frontend file that knows the back end is PocketBase. |
| `public/app.js` | The page. Talks to `cxi`, never to the back end. |
| `public/vendor/` | The PocketBase JavaScript SDK, vendored so nothing is fetched from a CDN. |
| `workers/homei.py` | Homei, the AI seat in the room. Standard-library Python, talks to Ollama. |
| `workers/homei.system.md` | Homei's rules. Plain text, edit it freely. |
| `workers/log/` | Append-only record of every answer Homei gave. Gitignored. |
| `scripts/dev.sh` | Downloads PocketBase and serves everything. |
| `pb_data/` | Your database. Gitignored. Never commit it. |
| `bin/` | The PocketBase binary. Gitignored. |

There is no build step, no package manager, no framework. You can read every
line of the app in one sitting, and you can change it with any text editor.

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
`workers/homei.py`, the one marked `Model`. Nothing else moves.

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
rooms                  id, name (unique), topic, created_by -> users
messages               id, room -> rooms, author -> users, body, created
```

## Where this goes next

- **Patchi / Gar Shield** becomes the sign-in. Today it is PocketBase's own
  email and password auth; the collection rules do not change when the
  identity layer does.
- **Handi** can read the same `messages` collection to hold the thread.
- **Homei on DeepSeek**, self-hosted, once that is the driver model.
- Private rooms and invitations: one more relation and two more rules.
- A Lovable surface pointed at this PocketBase, if you want to steer it
  visually.

## Licence

MIT. See `LICENSE`. The vendored PocketBase SDK carries its own MIT licence
in `public/vendor/`.
