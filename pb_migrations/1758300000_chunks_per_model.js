/// <reference path="../pb_data/types.d.ts" />
//
// A chunk is identified by (document, model, ordinal), not (document, ordinal).
// Two embedding models can index the same corpus side by side; neither
// overwrites the other. Documents also record how they were chunked, so a
// change of chunk size is noticed instead of interleaving old and new text.
//
migrate((app) => {
  const chunks = app.findCollectionByNameOrId("chunks");
  chunks.indexes = ["CREATE UNIQUE INDEX idx_chunks_doc_model_ordinal ON chunks (document, model, ordinal)"];
  app.save(chunks);

  const documents = app.findCollectionByNameOrId("documents");
  documents.fields.add(new TextField({ name: "chunking", max: 40 }));
  app.save(documents);
}, (app) => {
  const documents = app.findCollectionByNameOrId("documents");
  documents.fields.removeByName("chunking");
  app.save(documents);
  const chunks = app.findCollectionByNameOrId("chunks");
  chunks.indexes = ["CREATE UNIQUE INDEX idx_chunks_doc_ordinal ON chunks (document, ordinal)"];
  app.save(chunks);
});
