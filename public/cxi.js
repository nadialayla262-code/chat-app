/* cxi.js — the thin layer.
 *
 * This is the only file in the frontend that knows the back end is PocketBase.
 * app.js talks to `cxi`. If the spine ever changes, this file changes and
 * nothing else does. That is the swap rule.
 *
 * Shape of a record as the app sees it:
 *   user     { id, name, email? }
 *   room     { id, name, topic, created_by, created }
 *   message  { id, room, author, author_name, body, created }
 */
(function (global) {
  "use strict";

  const pb = new PocketBase(global.location.origin);
  pb.autoCancellation(false);

  const asMessage = (r) => ({
    id: r.id,
    room: r.room,
    author: r.author,
    author_name: (r.expand && r.expand.author && r.expand.author.name) || "",
    body: r.body,
    created: r.created,
  });
  const asRoom = (r) => ({
    id: r.id, name: r.name, topic: r.topic || "", created_by: r.created_by, created: r.created,
  });
  const asUser = (u) => (u ? { id: u.id, name: u.name || "", email: u.email || "" } : null);

  /** Turn a back-end error into one plain sentence. */
  const explain = (err) => {
    if (err && err.response && err.response.data && Object.keys(err.response.data).length) {
      return Object.entries(err.response.data)
        .map(([k, v]) => `${k}: ${v.message}`)
        .join(" ");
    }
    if (err && err.response && err.response.message) return err.response.message;
    if (err && err.message) return err.message;
    return "Something went wrong.";
  };

  const cxi = {
    explain,

    auth: {
      /** Current user or null. */
      me: () => asUser(pb.authStore.record),
      isSignedIn: () => pb.authStore.isValid,
      async signUp({ name, email, password }) {
        await pb.collection("users").create({ name, email, password, passwordConfirm: password });
        return cxi.auth.signIn({ email, password });
      },
      async signIn({ email, password }) {
        await pb.collection("users").authWithPassword(email, password);
        return cxi.auth.me();
      },
      /** Re-validate a stored session. Returns the user, or null if it is stale. */
      async resume() {
        if (!pb.authStore.isValid) return null;
        try {
          await pb.collection("users").authRefresh();
          return cxi.auth.me();
        } catch (_) {
          pb.authStore.clear();
          return null;
        }
      },
      signOut() { pb.authStore.clear(); },
      /** Called whenever the session becomes invalid (e.g. expired). */
      onSignedOut(fn) {
        pb.authStore.onChange(() => { if (!pb.authStore.isValid) fn(); });
      },
    },

    rooms: {
      async list() {
        const rows = await pb.collection("rooms").getFullList({ sort: "name" });
        return rows.map(asRoom);
      },
      async create({ name, topic = "" }) {
        const r = await pb.collection("rooms").create({ name, topic, created_by: pb.authStore.record.id });
        return asRoom(r);
      },
      /** fn({ action: "create"|"update"|"delete", room }) — returns an unsubscribe function. */
      async watch(fn) {
        return pb.collection("rooms").subscribe("*", (e) => fn({ action: e.action, room: asRoom(e.record) }));
      },
    },

    messages: {
      /** Oldest first, most recent `limit`. */
      async history(roomId, limit = 100) {
        const page = await pb.collection("messages").getList(1, limit, {
          filter: pb.filter("room = {:room}", { room: roomId }),
          sort: "-created",
          expand: "author",
        });
        return page.items.reverse().map(asMessage);
      },
      async send(roomId, body) {
        const r = await pb.collection("messages").create(
          { room: roomId, author: pb.authStore.record.id, body },
          { expand: "author" },
        );
        return asMessage(r);
      },
      async remove(id) { await pb.collection("messages").delete(id); },
      /** fn({ action, message }) for one room — returns an unsubscribe function. */
      async watch(roomId, fn) {
        return pb.collection("messages").subscribe("*", (e) => {
          if (e.record.room !== roomId) return;
          fn({ action: e.action, message: asMessage(e.record) });
        }, { filter: pb.filter("room = {:room}", { room: roomId }), expand: "author" });
      },
    },
  };

  global.cxi = cxi;
})(window);
