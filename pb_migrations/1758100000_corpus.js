/// <reference path="../pb_data/types.d.ts" />
//
// The corpus, in the spine.
//
//   documents  one row per source file: path, hash, Bates range if numbered
//   chunks     the text in pieces, each with its embedding
//
// Both locked: no API rules, superuser and server routes only. The spine
// is the record of truth for the embeddings, so they are backed up with
// everything else and can be rebuilt by anyone with the files and the
// same model. Search is done by workers/search.py; PocketBase has no
// vector search and this design does not pretend it does.
//
migrate((app) => {
  const documents = new Collection({
    name: "documents",
    type: "base",
    fields: [
      { name: "path", type: "text", required: true, max: 1000 },
      { name: "sha256", type: "text", required: true, min: 64, max: 64 },
      { name: "title", type: "text", max: 500 },
      { name: "chars", type: "number", min: 0 },
      { name: "chunks", type: "number", min: 0 },
      { name: "bates_start", type: "text", max: 40 },
      { name: "bates_end", type: "text", max: 40 },
      { name: "language", type: "text", max: 10 },
      { name: "created", type: "autodate", onCreate: true, onUpdate: false },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_documents_sha ON documents (sha256)"],
    listRule: null, viewRule: null, createRule: null, updateRule: null, deleteRule: null,
  });
  app.save(documents);

  const chunks = new Collection({
    name: "chunks",
    type: "base",
    fields: [
      { name: "document", type: "relation", collectionId: documents.id, required: true, maxSelect: 1, cascadeDelete: true },
      { name: "ordinal", type: "number", min: 0 }, // not "required": PocketBase treats 0 as blank
      { name: "text", type: "text", required: true, max: 8000 },
      { name: "embedding", type: "json", maxSize: 200000 },
      { name: "model", type: "text", max: 100 },
      { name: "dim", type: "number", min: 0 },
      { name: "created", type: "autodate", onCreate: true, onUpdate: false },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ],
    indexes: ["CREATE UNIQUE INDEX idx_chunks_doc_ordinal ON chunks (document, ordinal)"],
    listRule: null, viewRule: null, createRule: null, updateRule: null, deleteRule: null,
  });
  app.save(chunks);
}, (app) => {
  app.delete(app.findCollectionByNameOrId("chunks"));
  app.delete(app.findCollectionByNameOrId("documents"));
});
