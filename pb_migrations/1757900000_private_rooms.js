/// <reference path="../pb_data/types.d.ts" />
//
// Private rooms.
//
// A room is either open (every signed-in person sees it) or private (only
// its members see it, and only its members can write in it). The owner
// decides who is a member. Everything else, including realtime delivery,
// follows from the rules below: if you cannot list a room, you do not get
// its events either.
//
// Inviting is done by email through a server-side route (pb_hooks/invite.pb.js),
// so nobody can search other people's emails: the lookup happens on the
// server, only for the room's owner, and returns only a name.
//
// Homei is an ordinary account, so it sits in a private room only when the
// owner invites it.
//
migrate((app) => {
  const users = app.findCollectionByNameOrId("users");
  const rooms = app.findCollectionByNameOrId("rooms");
  rooms.fields.add(new BoolField({ name: "private" }));
  rooms.fields.add(new RelationField({
    name: "members",
    collectionId: users.id,
    maxSelect: 999,
    cascadeDelete: false,
  }));
  const canSeeRoom = '@request.auth.id != "" && (private = false || members.id ?= @request.auth.id)';
  rooms.listRule = canSeeRoom;
  rooms.viewRule = canSeeRoom;
  // The owner must be a member of their own private room, or they lock themselves out.
  rooms.createRule = '@request.auth.id != "" && created_by = @request.auth.id && (private = false || members.id ?= @request.auth.id)';
  // Membership and privacy change only through the invite route (pb_hooks),
  // never by direct update, so an owner can never lock themselves out.
  rooms.updateRule = 'created_by = @request.auth.id && @request.body.members:isset = false && @request.body.private:isset = false';
  rooms.deleteRule = "created_by = @request.auth.id";
  app.save(rooms);

  const messages = app.findCollectionByNameOrId("messages");
  const canSeeMessage = '@request.auth.id != "" && (room.private = false || room.members.id ?= @request.auth.id)';
  messages.listRule = canSeeMessage;
  messages.viewRule = canSeeMessage;
  messages.createRule = '@request.auth.id != "" && author = @request.auth.id && (room.private = false || room.members.id ?= @request.auth.id)';
  app.save(messages);
}, (app) => {
  const messages = app.findCollectionByNameOrId("messages");
  messages.listRule = '@request.auth.id != ""';
  messages.viewRule = '@request.auth.id != ""';
  messages.createRule = '@request.auth.id != "" && author = @request.auth.id';
  app.save(messages);

  const rooms = app.findCollectionByNameOrId("rooms");
  rooms.listRule = '@request.auth.id != ""';
  rooms.viewRule = '@request.auth.id != ""';
  rooms.createRule = '@request.auth.id != "" && created_by = @request.auth.id';
  rooms.updateRule = "created_by = @request.auth.id";
  rooms.fields.removeByName("members");
  rooms.fields.removeByName("private");
  app.save(rooms);
});
