/// <reference path="../pb_data/types.d.ts" />
//
// Projects: the board. What a person has done, is working on, has as an
// idea, at what stage, at what priority. One row per thing, owned by the
// person it belongs to. Nobody else sees it.
//
//   projects   owner -> users, title, stage, priority, area, link, source, notes
//
// stage      idea | working | built | live | done | parked
// priority   1 now, 2 next, 3 later (no "required": PocketBase treats 0 as blank)
//
// Append only in spirit: rows are never deleted through the API, they are
// parked. The owner cannot be changed once set. (owner, title) is unique
// so a loader can upsert by title without duplicating.
//
migrate((app) => {
  const users = app.findCollectionByNameOrId("users");
  const projects = new Collection({
    name: "projects",
    type: "base",
    fields: [
      { name: "owner", type: "relation", collectionId: users.id, required: true, maxSelect: 1, cascadeDelete: true },
      { name: "title", type: "text", required: true, min: 1, max: 200 },
      { name: "stage", type: "select", values: ["idea", "working", "built", "live", "done", "parked"], maxSelect: 1, required: true },
      { name: "priority", type: "number", min: 1, max: 3 },
      { name: "area", type: "text", max: 80 },
      { name: "link", type: "url", max: 1000 },
      { name: "source", type: "text", max: 200 },
      { name: "notes", type: "text", max: 4000 },
      { name: "created", type: "autodate", onCreate: true, onUpdate: false },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    indexes: [
      "CREATE UNIQUE INDEX idx_projects_owner_title ON projects (owner, title)",
      "CREATE INDEX idx_projects_owner_stage ON projects (owner, stage, priority)",
    ],
    listRule: "owner = @request.auth.id",
    viewRule: "owner = @request.auth.id",
    createRule: '@request.auth.id != "" && owner = @request.auth.id',
    updateRule: "owner = @request.auth.id && @request.body.owner:isset = false",
    deleteRule: null,
  });
  app.save(projects);
}, (app) => {
  app.delete(app.findCollectionByNameOrId("projects"));
});
