/// <reference path="../pb_data/types.d.ts" />
//
// Memories: what an AI seat has been asked to remember about a person.
//
//   memories   person -> users, author -> users (the seat), text
//
// The seat writes them; the person can read, edit and delete their own.
// Nobody else sees them. A memory belongs to the person it is about, not
// to the seat that wrote it.
//
migrate((app) => {
  const users = app.findCollectionByNameOrId("users");
  const memories = new Collection({
    name: "memories",
    type: "base",
    fields: [
      { name: "person", type: "relation", collectionId: users.id, required: true, maxSelect: 1, cascadeDelete: true },
      { name: "author", type: "relation", collectionId: users.id, required: true, maxSelect: 1, cascadeDelete: false },
      { name: "text", type: "text", required: true, min: 1, max: 1000 },
      { name: "created", type: "autodate", onCreate: true, onUpdate: false },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    indexes: ["CREATE INDEX idx_memories_person ON memories (person, created)"],
    listRule: "person = @request.auth.id || author = @request.auth.id",
    viewRule: "person = @request.auth.id || author = @request.auth.id",
    createRule: '@request.auth.id != "" && author = @request.auth.id',
    updateRule: "person = @request.auth.id || author = @request.auth.id",
    deleteRule: "person = @request.auth.id || author = @request.auth.id",
  });
  app.save(memories);
}, (app) => {
  app.delete(app.findCollectionByNameOrId("memories"));
});
