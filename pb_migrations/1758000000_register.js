/// <reference path="../pb_data/types.d.ts" />
//
// The register, in the spine.
//
// Three collections holding what workers/handi_mail.py counts:
//
//   contacts        one row per organisation per mailbox
//   threads         one row per conversation
//   dead_addresses  addresses that bounced
//
// All three are locked: no API rule at all, so only a superuser (you) and
// server-side routes can touch them. Rate the State reads them through
// pb_hooks/register.pb.js, which publishes counts only, and only for
// organisations you have flagged `published`. Publication discipline is a
// field, not a promise.
//
migrate((app) => {
  const contacts = new Collection({
    name: "contacts",
    type: "base",
    fields: [
      { name: "organisation", type: "text", required: true, max: 200 },
      { name: "source", type: "text", required: true, max: 200 },
      { name: "addresses", type: "json", maxSize: 20000 },
      { name: "threads", type: "number", min: 0 },
      { name: "messages_sent", type: "number", min: 0 },
      { name: "first_sent", type: "date" },
      { name: "last_sent", type: "date" },
      { name: "human_replies", type: "number", min: 0 },
      { name: "auto_replies", type: "number", min: 0 },
      { name: "bounces", type: "number", min: 0 },
      { name: "last_human_reply", type: "date" },
      { name: "open_threads", type: "number", min: 0 },
      { name: "answered_by_person", type: "bool" },
      { name: "published", type: "bool" },
      { name: "display_name", type: "text", max: 200 },
      { name: "created", type: "autodate", onCreate: true, onUpdate: false },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_contacts_org_source ON contacts (organisation, source)"],
    listRule: null, viewRule: null, createRule: null, updateRule: null, deleteRule: null,
  });
  app.save(contacts);

  const threads = new Collection({
    name: "threads",
    type: "base",
    fields: [
      { name: "key", type: "text", required: true, max: 64 },
      { name: "organisation", type: "text", required: true, max: 200 },
      { name: "source", type: "text", required: true, max: 200 },
      { name: "subject", type: "text", max: 1000 },
      { name: "to", type: "json", maxSize: 20000 },
      { name: "messages_sent", type: "number", min: 0 },
      { name: "first_sent", type: "date" },
      { name: "last_sent", type: "date" },
      { name: "human_replies", type: "number", min: 0 },
      { name: "auto_replies", type: "number", min: 0 },
      { name: "bounces", type: "number", min: 0 },
      { name: "last_human_reply", type: "date" },
      { name: "status", type: "select", values: ["OPEN", "answered"], maxSelect: 1 },
      { name: "created", type: "autodate", onCreate: true, onUpdate: false },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_threads_key ON threads (key)"],
    listRule: null, viewRule: null, createRule: null, updateRule: null, deleteRule: null,
  });
  app.save(threads);

  const dead = new Collection({
    name: "dead_addresses",
    type: "base",
    fields: [
      { name: "address", type: "text", required: true, max: 320 },
      { name: "source", type: "text", max: 200 },
      { name: "created", type: "autodate", onCreate: true, onUpdate: false },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_dead_address ON dead_addresses (address)"],
    listRule: null, viewRule: null, createRule: null, updateRule: null, deleteRule: null,
  });
  app.save(dead);
}, (app) => {
  app.delete(app.findCollectionByNameOrId("dead_addresses"));
  app.delete(app.findCollectionByNameOrId("threads"));
  app.delete(app.findCollectionByNameOrId("contacts"));
});
