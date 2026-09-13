/// <reference path="../pb_data/types.d.ts" />
//
// POST /api/cxi/invite   { room: "<room id>", email: "<person's email>" }
//
// Adds a person to a private room by email. Only the room's owner may call
// it. The email lookup happens here, on the server, and the response carries
// only the person's id and name, so emails are never searchable from the
// page. Returns 404 if no account has that email.
//
routerAdd("POST", "/api/cxi/invite", (e) => {
  const body = e.requestInfo().body || {};
  const roomId = String(body.room || "").trim();
  const email = String(body.email || "").trim().toLowerCase();
  if (!roomId || !email) throw new BadRequestError("room and email are required");

  let room;
  try {
    room = e.app.findRecordById("rooms", roomId);
  } catch (_) {
    throw new NotFoundError("No such room");
  }
  if (room.get("created_by") !== e.auth.id) {
    throw new ForbiddenError("Only the room's owner can invite people");
  }

  let person;
  try {
    person = e.app.findAuthRecordByEmail("users", email);
  } catch (_) {
    throw new NotFoundError("No account with that email");
  }

  const members = room.get("members") || [];
  if (!members.includes(person.id)) {
    members.push(person.id);
    room.set("members", members);
    e.app.save(room);
  }
  return e.json(200, { id: person.id, name: person.get("name") });
}, $apis.requireAuth("users"));

// POST /api/cxi/uninvite   { room, user }   — owner removes a member (never themselves).
routerAdd("POST", "/api/cxi/uninvite", (e) => {
  const body = e.requestInfo().body || {};
  const roomId = String(body.room || "").trim();
  const userId = String(body.user || "").trim();
  if (!roomId || !userId) throw new BadRequestError("room and user are required");
  let room;
  try {
    room = e.app.findRecordById("rooms", roomId);
  } catch (_) {
    throw new NotFoundError("No such room");
  }
  if (room.get("created_by") !== e.auth.id) throw new ForbiddenError("Only the room's owner can remove people");
  if (userId === e.auth.id) throw new BadRequestError("The owner cannot leave their own room");
  room.set("members", (room.get("members") || []).filter((id) => id !== userId));
  e.app.save(room);
  return e.json(200, { ok: true });
}, $apis.requireAuth("users"));
