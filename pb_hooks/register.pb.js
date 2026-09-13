/// <reference path="../pb_data/types.d.ts" />
//
// Public, read-only views of the register. Counts only. No addresses, no
// subjects, no names beyond the organisation you chose to publish.
//
//   GET /api/cxi/register/summary   totals across everything loaded
//   GET /api/cxi/register/board     one row per organisation flagged `published`
//
// Rate the State reads these. Everything else in the register is locked.
//
// Each handler runs in its own scope, so helpers are declared inside them.

routerAdd("GET", "/api/cxi/register/summary", (e) => {
  const dateMax = (a, b) => (!a ? (b || "") : !b ? a : a > b ? a : b);
  const rows = e.app.findAllRecords("contacts");
  const orgs = new Set();
  let sent = 0, answered = new Set(), updated = "";
  for (const r of rows) {
    orgs.add(r.get("organisation"));
    sent += r.get("messages_sent") || 0;
    if (r.get("answered_by_person")) answered.add(r.get("organisation"));
    updated = dateMax(updated, String(r.get("updated")));
  }
  const dead = e.app.findAllRecords("dead_addresses").length;
  return e.json(200, {
    organisations_written_to: orgs.size,
    messages_sent: sent,
    answered_by_a_person: answered.size,
    never_answered_by_a_person: orgs.size - answered.size,
    dead_addresses: dead,
    updated: updated,
  });
});

routerAdd("GET", "/api/cxi/register/board", (e) => {
  const dateMax = (a, b) => (!a ? (b || "") : !b ? a : a > b ? a : b);
  const dateMin = (a, b) => (!a ? (b || "") : !b ? a : a < b ? a : b);
  const rows = e.app.findAllRecords("contacts");
  const byOrg = {};
  for (const r of rows) {
    if (!r.get("published")) continue;
    const org = r.get("organisation");
    const row = byOrg[org] || (byOrg[org] = {
      organisation: org,
      display_name: "",
      times_written: 0,
      threads: 0,
      first_written: "",
      last_written: "",
      human_replies: 0,
      auto_replies: 0,
      last_human_reply: "",
      open_threads: 0,
      answered_by_a_person: false,
    });
    row.display_name = row.display_name || r.get("display_name") || "";
    row.times_written += r.get("messages_sent") || 0;
    row.threads += r.get("threads") || 0;
    row.first_written = dateMin(row.first_written, String(r.get("first_sent") || ""));
    row.last_written = dateMax(row.last_written, String(r.get("last_sent") || ""));
    row.human_replies += r.get("human_replies") || 0;
    row.auto_replies += r.get("auto_replies") || 0;
    row.last_human_reply = dateMax(row.last_human_reply, String(r.get("last_human_reply") || ""));
    row.open_threads += r.get("open_threads") || 0;
    row.answered_by_a_person = row.answered_by_a_person || !!r.get("answered_by_person");
  }
  const board = Object.values(byOrg).sort((a, b) => b.times_written - a.times_written);
  return e.json(200, { organisations: board });
});
