/// <reference path="../pb_data/types.d.ts" />
//
// The Desk: one screen behind the chat, for the person who runs the spine.
//
//   GET /api/cxi/desk              who is waiting on a reply, the latest
//                                  documents in, the seats, the counts
//   GET /api/cxi/desk/search?q=    word search over the corpus text
//
// Both read collections that are otherwise locked (the register, the
// corpus), so they are gated. Set
//
//     CXI_DESK_OWNERS=you@example.com            (comma-separated for more)
//
// before starting the spine. Only a signed-in person whose email is on that
// list gets an answer; everyone else gets 403 and a sentence saying why.
// Unset, the Desk is closed for everyone. Rules live here, not on the page.
//
// Each handler runs in its own scope, so helpers are declared inside them.

routerAdd("GET", "/api/cxi/desk", (e) => {
  const owners = String($os.getenv("CXI_DESK_OWNERS") || "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
  const mine = String(e.auth.email() || "").toLowerCase();
  if (!owners.length) throw new ForbiddenError("The Desk is closed on this spine. Start it with CXI_DESK_OWNERS=you@example.com");
  if (!owners.includes(mine)) throw new ForbiddenError("The Desk belongs to the person who runs this spine.");

  const plain = (r, fields) => {
    const o = {};
    for (const f of fields) o[f] = r.get(f);
    return o;
  };
  const str = (v) => (v ? String(v) : "");

  // Who owes a reply: every open thread, most recently written first.
  const waiting = e.app.findRecordsByFilter("threads", "status = 'OPEN'", "-last_sent", 30, 0)
    .map((r) => ({
      organisation: r.get("organisation"), source: r.get("source"), subject: r.get("subject") || "",
      messages_sent: r.get("messages_sent") || 0, human_replies: r.get("human_replies") || 0,
      first_sent: str(r.get("first_sent")), last_sent: str(r.get("last_sent")),
    }));

  const contacts = e.app.findAllRecords("contacts");
  const orgs = new Set(), answered = new Set();
  let openThreads = 0;
  for (const r of contacts) {
    orgs.add(r.get("organisation"));
    if (r.get("answered_by_person")) answered.add(r.get("organisation"));
    openThreads += r.get("open_threads") || 0;
  }
  const register = {
    organisations_written_to: orgs.size,
    answered_by_a_person: answered.size,
    never_answered_by_a_person: orgs.size - answered.size,
    open_threads: openThreads,
    dead_addresses: e.app.findAllRecords("dead_addresses").length,
  };

  // The latest documents in, newest first.
  const documents = e.app.findRecordsByFilter("documents", "id != ''", "-created", 12, 0)
    .map((r) => plain(r, ["id", "title", "path", "bates_start", "bates_end", "chars", "chunks", "language", "created"]));
  const documentCount = e.app.findRecordsByFilter("documents", "id != ''", "", 0, 0).length;

  // The seats: does the account exist, and what was the last thing it said.
  const seats = [];
  for (const seat of [["Homei", "CXI_HOMEI_EMAIL", "homei@cxi.local"], ["Handi", "CXI_HANDI_EMAIL", "handi@cxi.local"]]) {
    const email = String($os.getenv(seat[1]) || seat[2]);
    let present = false, lastSpoke = "", room = "";
    try {
      const u = e.app.findAuthRecordByEmail("users", email);
      present = true;
      const last = e.app.findRecordsByFilter("messages", "author = {:id}", "-created", 1, 0, { id: u.id });
      if (last.length) {
        lastSpoke = str(last[0].get("created"));
        try { room = e.app.findRecordById("rooms", last[0].get("room")).get("name"); } catch (_) {}
      }
    } catch (_) {}
    seats.push({ name: seat[0], present, last_spoke: lastSpoke, room });
  }

  const rooms = e.app.findRecordsByFilter("rooms", "created_by = {:id} || members.id ?= {:id} || private = false", "", 0, 0, { id: e.auth.id }).length;

  return e.json(200, {
    person: { id: e.auth.id, name: e.auth.get("name") },
    waiting, register, documents, seats,
    counts: { documents: documentCount, waiting: waiting.length, rooms },
  });
}, $apis.requireAuth("users"));

routerAdd("GET", "/api/cxi/desk/search", (e) => {
  const owners = String($os.getenv("CXI_DESK_OWNERS") || "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
  const mine = String(e.auth.email() || "").toLowerCase();
  if (!owners.length) throw new ForbiddenError("The Desk is closed on this spine. Start it with CXI_DESK_OWNERS=you@example.com");
  if (!owners.includes(mine)) throw new ForbiddenError("The Desk belongs to the person who runs this spine.");

  const q = String(e.requestInfo().query.q || "").trim();
  if (q.length < 2) return e.json(200, { q, results: [] });

  // Word search over the chunk text. Not the embedding search (that is
  // workers/search.py and needs the model); this one needs nothing and
  // answers "where does this phrase occur".
  const rows = e.app.findRecordsByFilter("chunks", "text ~ {:q}", "-created", 200, 0, { q });
  const snippetOf = (text) => {
    const at = text.toLowerCase().indexOf(q.toLowerCase());
    const start = Math.max(0, at - 90), end = Math.min(text.length, at + q.length + 110);
    return (start > 0 ? "…" : "") + text.slice(start, end).replace(/\s+/g, " ") + (end < text.length ? "…" : "");
  };
  const byDoc = {}, seen = new Set(), order = [];
  for (const r of rows) {
    const key = r.get("document") + "#" + r.get("ordinal");  // the same text under two models counts once
    if (seen.has(key)) continue;
    seen.add(key);
    const id = r.get("document");
    let d = byDoc[id];
    if (!d) {
      let doc;
      try { doc = e.app.findRecordById("documents", id); } catch (_) { continue; }
      d = byDoc[id] = { id, title: doc.get("title") || "", path: doc.get("path"), bates_start: doc.get("bates_start") || "", bates_end: doc.get("bates_end") || "", hits: 0, snippets: [] };
      order.push(id);
    }
    d.hits += 1;
    if (d.snippets.length < 3) d.snippets.push({ ordinal: r.get("ordinal"), text: snippetOf(r.get("text")) });
  }
  const results = order.map((id) => byDoc[id]).sort((a, b) => b.hits - a.hits).slice(0, 12);
  return e.json(200, { q, results, documents_matched: order.length });
}, $apis.requireAuth("users"));
