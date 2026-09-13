/// <reference path="../pb_data/types.d.ts" />
//
// GET /api/cxi/export  — everything the spine holds about the signed-in person.
//
// Your data is yours. One call returns it all as JSON: profile, the rooms
// you own or belong to, every message you wrote, every memory a seat keeps
// about you. Nothing about anyone else. No superuser needed.
//
routerAdd("GET", "/api/cxi/export", (e) => {
  const me = e.auth;
  const id = me.id;
  const plain = (r, fields) => {
    const o = {};
    for (const f of fields) o[f] = r.get(f);
    return o;
  };
  const rooms = e.app.findRecordsByFilter("rooms", "created_by = {:id} || members.id ?= {:id}", "name", 0, 0, { id })
    .map((r) => plain(r, ["id", "name", "topic", "private", "created_by", "members", "created"]));
  const messages = e.app.findRecordsByFilter("messages", "author = {:id}", "created", 0, 0, { id })
    .map((r) => plain(r, ["id", "room", "body", "created", "updated"]));
  const memories = e.app.findRecordsByFilter("memories", "person = {:id}", "created", 0, 0, { id })
    .map((r) => plain(r, ["id", "author", "text", "created"]));
  return e.json(200, {
    exported_by: "cxi-chat",
    person: { id, name: me.get("name"), email: me.email(), created: me.get("created") },
    rooms, messages, memories,
    counts: { rooms: rooms.length, messages: messages.length, memories: memories.length },
  });
}, $apis.requireAuth("users"));
