# Connecting Lovable to the spine

Your build notes call this the highest ratio of effort to unblocking in the
whole build: about an hour, never done, and the reason you cannot yet see
anything. This is that hour, written down so it only has to be done once.

The ending first: Lovable never touches the database. It talks to
PocketBase over HTTPS through a tunnel from the Mac, using the same thin
layer this repo already has. Swap the back end later, change one file,
the Lovable app never knows.

## 1. Make the spine reachable

PocketBase runs on the Mac. Lovable runs on the web. A Cloudflare Tunnel
joins them without opening a port on your router and without a server in
the Netherlands.

```sh
brew install cloudflared
cloudflared tunnel login                 # opens a browser, pick your domain
cloudflared tunnel create cxi-spine
cloudflared tunnel route dns cxi-spine spine.<your-domain>
```

Then a config file at `~/.cloudflared/config.yml`:

```yaml
tunnel: cxi-spine
credentials-file: /Users/<you>/.cloudflared/<tunnel-id>.json
ingress:
  - hostname: spine.<your-domain>
    service: http://127.0.0.1:8090
  - service: http_status:404
```

Start it next to the app:

```sh
./scripts/dev.sh                      # terminal 1
cloudflared tunnel run cxi-spine      # terminal 2
```

Check from anywhere: `https://spine.<your-domain>/api/health` returns
`API is healthy`. Nothing else is exposed: the collection rules in
`pb_migrations/` decide what a signed-in person can see, exactly as they do
on localhost.

Protect the admin panel before the tunnel goes up: in Cloudflare Zero Trust,
add an Access policy for `spine.<your-domain>/_/*` that only your email can
pass. The app itself needs no such policy; its own sign-in is the gate.

## 2. Tell PocketBase where the front end lives

In the admin panel, Settings → Application, set the application URL to
`https://spine.<your-domain>`. In the `users` collection, no change: the
rules already require sign-in. CORS is open by default in PocketBase; leave
it, the rules are the security, not the origin.

## 3. The Lovable side

Lovable projects want Supabase by reflex. Do not connect one. Give the
project this, verbatim, as its first message:

> Build a chat app front end that talks to an existing PocketBase server at
> `https://spine.<your-domain>`. Use the `pocketbase` npm package. Do not
> add Supabase or any other backend. Keep every PocketBase call in one file,
> `src/lib/cxi.ts`, exposing `auth`, `rooms` and `messages` with these
> shapes and rules:
>
> - `auth.signUp({name,email,password})`, `auth.signIn`, `auth.me()`, `auth.signOut()` on the `users` collection.
> - `rooms.list()` sorted by name with `expand: "members"`; `rooms.create({name, private})` sets `created_by` to the current user and, when private, `members: [me]`; `rooms.watch(fn)` subscribes to the `rooms` collection.
> - `rooms.invite(roomId, email)` POSTs to `/api/cxi/invite`, `rooms.leave(roomId)` to `/api/cxi/leave`, `rooms.uninvite(roomId,userId)` to `/api/cxi/uninvite`.
> - `messages.history(roomId)` last 100 sorted by created, `expand: "author"`; `messages.send(roomId, body)` sets `author` to the current user; `messages.watch(roomId, fn)` subscribes with a filter on `room`.
>
> No component may import PocketBase directly; only `cxi.ts` does. Phone
> first, large tap targets, one restrained ink colour, dark mode, no icons
> library. Sign-in screen, room list with a lock on private rooms, message
> pane with live updates, composer that keeps an unsent draft per room in
> localStorage.

That prompt is the same contract as `public/cxi.js` in this repo, so the
two front ends are interchangeable and either can be thrown away.

## 4. Homei and Handi

They run on the Mac next to the spine and never need the tunnel: they talk
to `http://127.0.0.1:8090` and the model on the same machine. The Lovable
front end sees their messages like anyone else's, because they are just
accounts.

## What this costs

Cloudflare Tunnel is free. Lovable is what you already pay. Nothing new.

## When the spine moves to Iceland

Point the tunnel hostname, or the DNS record, at the new host. The Lovable
app has one URL in one file. Change it. Done.
