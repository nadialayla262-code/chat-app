/// <reference path="../pb_data/types.d.ts" />
//
// CXI chat — initial schema.
//
// Two collections on top of PocketBase's built-in `users` auth collection:
//
//   rooms     — a named conversation. Anyone signed in can see every room.
//   messages  — one line of text, in one room, by one author.
//
// Rules (who can do what) are written here, in code, so they are versioned
// and reviewable. Nobody has to click through an admin panel to reproduce
// this setup. That is the method: the schema is the product.
//
migrate((app) => {
  // Let signed-in users see each other's public profile (name, avatar) so a
  // message can show who wrote it. Email stays hidden unless the user opts in.
  const users = app.findCollectionByNameOrId("users");
  users.viewRule = '@request.auth.id != ""';
  app.save(users);

  const rooms = new Collection({
    name: "rooms",
    type: "base",
    fields: [
      { name: "name", type: "text", required: true, min: 1, max: 80 },
      { name: "topic", type: "text", max: 280 },
      {
        name: "created_by",
        type: "relation",
        collectionId: users.id,
        required: true,
        maxSelect: 1,
        cascadeDelete: false,
      },
      { name: "created", type: "autodate", onCreate: true, onUpdate: false },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_rooms_name ON rooms (name)"],
    listRule: '@request.auth.id != ""',
    viewRule: '@request.auth.id != ""',
    createRule: '@request.auth.id != "" && created_by = @request.auth.id',
    updateRule: "created_by = @request.auth.id",
    deleteRule: "created_by = @request.auth.id",
  });
  app.save(rooms);

  const messages = new Collection({
    name: "messages",
    type: "base",
    fields: [
      {
        name: "room",
        type: "relation",
        collectionId: rooms.id,
        required: true,
        maxSelect: 1,
        cascadeDelete: true,
      },
      {
        name: "author",
        type: "relation",
        collectionId: users.id,
        required: true,
        maxSelect: 1,
        cascadeDelete: false,
      },
      { name: "body", type: "text", required: true, min: 1, max: 4000 },
      { name: "created", type: "autodate", onCreate: true, onUpdate: false },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    indexes: ["CREATE INDEX idx_messages_room_created ON messages (room, created)"],
    listRule: '@request.auth.id != ""',
    viewRule: '@request.auth.id != ""',
    createRule: '@request.auth.id != "" && author = @request.auth.id',
    updateRule: "author = @request.auth.id",
    deleteRule: "author = @request.auth.id",
  });
  app.save(messages);
}, (app) => {
  // Rollback: drop in reverse dependency order, then restore the users rule.
  app.delete(app.findCollectionByNameOrId("messages"));
  app.delete(app.findCollectionByNameOrId("rooms"));
  const users = app.findCollectionByNameOrId("users");
  users.viewRule = "id = @request.auth.id";
  app.save(users);
});
