# CLAUDE.md — how to work in this repo

Read this before touching anything. It is short on purpose.

## What this is

CXI Chat: a self-hosted chat on a PocketBase spine, with AI seats in the
room (Homei, Handi), a mail register, and Bates numbering for exhibits.
Open source, built by a citizen for all citizens. `README.md` explains the
product; `HANDOVER.md` explains the state of things in plain words. Read
both before your first change.

## The rules that govern every decision

1. **The swap rule.** Apps talk to a thin layer; the thin layer talks to
   the back end. Exactly one file per side knows what the back end is:
   `public/cxi.js` for the page, `workers/cxi_spine.py` for the workers.
   Never import PocketBase or call Ollama anywhere else.
2. **Rules live on the server, as code.** Who may do what is decided by
   collection rules in `pb_migrations/` and routes in `pb_hooks/`. The page
   may hide a button; it never enforces anything. New schema = new
   migration file with a working rollback. Never edit an applied migration.
3. **Method as product.** Every worker prints the rules it applied. Every
   output is reproducible from its inputs. A number nobody can regenerate
   is a claim, not a finding.
4. **Append only. Never renumber. Never overwrite.** The Bates ledger
   appends. The register upserts by key. Worker logs append. If something
   was true last run it must still be findable this run.
5. **No build step, no framework, no CDN.** The page is one HTML file, one
   stylesheet, two scripts, and a vendored SDK. Workers are standard-library
   Python; `workers/bates.py` is the one exception and says so.
6. **Settings are environment variables, never edits.** Prefix `CXI_`.
7. **Nothing leaves the machine.** No telemetry, no external calls from the
   page or the workers except to the spine and the local model.
8. **No servers in the Netherlands.** Design choice, not a preference.

## Language

- AI systems are not "tools". Homei and Handi are seats, workers, or by name.
- Processes: start / stop, main / worker. Never kill, spawn, child, parent,
  orphan, daemon, in code comments, commit messages, or output.
- Workers never state the time, the date, or how long something took in
  anything they post to a room. Registers carry dates as data, not as
  remarks about now.
- "Divergent", never "disabled".
- Maximum force, zero adjectives, in anything a worker writes.

## Before you push

```sh
./tests/run.sh          # all suites, throwaway spine on :8099, never touches ./pb_data
```

Green or it does not ship. The same command runs in GitHub Actions on
every pull request (`.github/workflows/tests.yml`). Browser and Bates suites skip themselves if
Playwright or the PDF libraries are missing; say so in the commit if they
were skipped. The Homei and Handi suites run against `tests/fake_embed.py`,
so worker logic is tested; the real model is not. A last message containing
"slow" makes the stand-in wait 3 seconds, for testing what happens while a model thinks.

When you change the page, run `tests/browser.js`. When you change a rule,
run `tests/rules.js`. When you add a worker, add a test for it.

## Where things are

| Path | What |
| --- | --- |
| `pb_migrations/` | Schema and rules, in order, each with a rollback |
| `pb_hooks/` | Server routes and guards: invite / uninvite / leave, register summary and board, sign-up code, export |
| `public/` | The page. `cxi.js` is the thin layer; `app.js` never touches the back end |
| `workers/` | Homei, Handi, Handi on mail, register loader, corpus index and search, backup, Bates. `cxi_spine.py` is their thin layer |
| `tests/` | `run.sh` and one script per suite |
| `docs/LOVABLE.md` | Pointing a Lovable front end at this spine |
| `scripts/start.sh`, `stop.sh`, `dev.sh` | Background start/stop by pid file; foreground spine |

Gitignored and never committed: `pb_data/` (the database), `bin/`,
`register/`, `workers/log/`, `workers/.vectors/`, `workers/.*-password`, `.run/`, `tests/.tmp/`.

## Things that bit us once

- PocketBase runs each `routerAdd` handler in its own scope. Helpers
  declared at file top level are not visible inside a handler. Declare
  them inside.
- PocketBase will not filter on `email` for auth records unless the
  record's email is public. Look people up server-side in a hook instead.
- Collection rules on `update` are evaluated against the stored record,
  not the incoming body. To forbid a field change, use
  `@request.body.field:isset = false`.
- The realtime feed must be subscribed before history is loaded, or a
  message sent in between is lost. The page does this; keep it that way.
- `pkill -f` with a pattern that appears in your own shell command kills
  the shell. Stop processes by id.
- `( cd dir && cmd & echo $! > file )` backgrounds the whole list, cd
  included; the pid file lands in the wrong folder. Use `;` after the cd.
- Never advance a worker's poll cursor to its own reply's timestamp:
  everything written while the model was thinking sits between the trigger
  and the reply and would be skipped forever. Advance only past what was read.
- A worker token expires (7 days by default) and the worker silently becomes
  a guest that sees nothing. `Spine.keep_alive()` refreshes hourly; call it
  in every long loop.
- Wrap the per-item body of a worker loop in try/except. One failed call
  must not stop the seat.
- PocketBase backup names must match `[a-z0-9_-]+\.zip`; no uppercase.
- A required number field rejects 0 ("cannot be blank"). Leave `required`
  off and let a unique index enforce presence.
- Worker log lines start with `[name]`. In `--json` mode print nothing
  else, or the caller's JSON parse grabs the log line.

## Branches

`main` is the branch to review into. Work happens on a branch and arrives
in `main` by pull request. Never push to `main` directly.

## Commits

Small, one concern each, message says what changed and what was verified.
Never commit data, secrets, or anything under the gitignored paths.
