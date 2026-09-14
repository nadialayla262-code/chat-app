// Access rules, straight against the API: open rooms, private rooms, invitations, the register.
const { BASE, PocketBase, sleep, person, personWithEmail, superuser, check, blocked, done } = require("./lib");
(async () => {
  const anon = new PocketBase(BASE);
  const a = await person("A"), b = await person("B"), c = await person("C");
  const t = Date.now();

  console.log("open rooms");
  check("anon list rooms is empty", (await anon.collection("rooms").getFullList()).length === 0);
  const room = await a.pb.collection("rooms").create({ name: `r${t}`, created_by: a.id });
  await blocked("B creates room as A", () => b.pb.collection("rooms").create({ name: `r2${t}`, created_by: a.id }));
  await blocked("B renames A's room", () => b.pb.collection("rooms").update(room.id, { name: "x" }));
  const msg = await a.pb.collection("messages").create({ room: room.id, author: a.id, body: "hi" });
  await blocked("B sends as A", () => b.pb.collection("messages").create({ room: room.id, author: a.id, body: "forged" }));
  await blocked("B edits A's message", () => b.pb.collection("messages").update(msg.id, { body: "x" }));
  await blocked("B deletes A's message", () => b.pb.collection("messages").delete(msg.id));
  await blocked("empty message", () => a.pb.collection("messages").create({ room: room.id, author: a.id, body: "" }));
  const seen = await b.pb.collection("messages").getList(1, 5, { filter: `room="${room.id}"`, expand: "author" });
  check("B sees A's name, not email", seen.items[0].expand.author.name === "A" && !seen.items[0].expand.author.email);
  await a.pb.collection("rooms").delete(room.id);
  await blocked("message gone after room delete (cascade)", () => a.pb.collection("messages").getOne(msg.id));

  console.log("private rooms");
  await blocked("private room without self as member", () => a.pb.collection("rooms").create({ name: `p0${t}`, private: true, created_by: a.id, members: [] }));
  const priv = await a.pb.collection("rooms").create({ name: `p${t}`, private: true, created_by: a.id, members: [a.id] });
  const secret = await a.pb.collection("messages").create({ room: priv.id, author: a.id, body: "secret" });
  check("B does not list private room", !(await b.pb.collection("rooms").getFullList()).some((r) => r.id === priv.id));
  await blocked("B views private room by id", () => b.pb.collection("rooms").getOne(priv.id));
  await blocked("B reads private message by id", () => b.pb.collection("messages").getOne(secret.id));
  await blocked("B posts into private room", () => b.pb.collection("messages").create({ room: priv.id, author: b.id, body: "x" }));
  await blocked("B adds self to members", () => b.pb.collection("rooms").update(priv.id, { "members+": b.id }));
  await blocked("A removes self from members directly", () => a.pb.collection("rooms").update(priv.id, { members: [] }));
  await blocked("A flips private off directly", () => a.pb.collection("rooms").update(priv.id, { private: false }));
  await a.pb.collection("rooms").update(priv.id, { topic: "fine" });
  check("A edits topic", true);
  await blocked("B (stranger) invites via route", () => b.pb.send("/api/cxi/invite", { method: "POST", body: { room: priv.id, email: c.email } }));
  await blocked("anon invites via route", () => anon.send("/api/cxi/invite", { method: "POST", body: { room: priv.id, email: b.email } }));
  await blocked("A invites unknown email", () => a.pb.send("/api/cxi/invite", { method: "POST", body: { room: priv.id, email: `nobody${t}@test.local` } }));
  await blocked("B searches users by email", () => b.pb.collection("users").getFirstListItem(`email = "${a.email}"`));
  const inv = await a.pb.send("/api/cxi/invite", { method: "POST", body: { room: priv.id, email: b.email.toUpperCase() } });
  check("invite returns name only", inv.name === "B" && !inv.email);
  check("B now lists private room", (await b.pb.collection("rooms").getFullList()).some((r) => r.id === priv.id));
  check("B reads history", (await b.pb.collection("messages").getList(1, 5, { filter: `room="${priv.id}"` })).totalItems === 1);
  await b.pb.collection("messages").create({ room: priv.id, author: b.id, body: "invited" });
  check("B posts", true);
  await blocked("B (member) invites C", () => b.pb.send("/api/cxi/invite", { method: "POST", body: { room: priv.id, email: c.email } }));
  await blocked("C still blocked", () => c.pb.collection("messages").create({ room: priv.id, author: c.id, body: "x" }));
  await blocked("owner leaves own room", () => a.pb.send("/api/cxi/leave", { method: "POST", body: { room: priv.id } }));
  await b.pb.send("/api/cxi/leave", { method: "POST", body: { room: priv.id } });
  check("B gone after leave", !(await b.pb.collection("rooms").getFullList()).some((r) => r.id === priv.id));
  await blocked("B leaves twice", () => b.pb.send("/api/cxi/leave", { method: "POST", body: { room: priv.id } }));
  await a.pb.send("/api/cxi/invite", { method: "POST", body: { room: priv.id, email: b.email } });
  await blocked("A uninvites self", () => a.pb.send("/api/cxi/uninvite", { method: "POST", body: { room: priv.id, user: a.id } }));
  await a.pb.send("/api/cxi/uninvite", { method: "POST", body: { room: priv.id, user: b.id } });
  check("B gone after uninvite", !(await b.pb.collection("rooms").getFullList()).some((r) => r.id === priv.id));

  console.log("export");
  const ex = await a.pb.send("/api/cxi/export", { method: "GET" });
  check("export names me", ex.person.id === a.id && ex.person.email === a.email);
  check("export has my rooms and messages", ex.rooms.some((r) => r.id === priv.id) && ex.messages.some((m) => m.body === "secret"));
  check("export has nobody else's messages", ex.messages.every((m) => !["invited", "x"].includes(m.body)));
  const exb = await b.pb.send("/api/cxi/export", { method: "GET" });
  check("B's export does not carry A's private room", !exb.rooms.some((r) => r.id === priv.id));
  await blocked("anon export", () => anon.send("/api/cxi/export", { method: "GET" }));

  console.log("register is locked");
  for (const col of ["contacts", "threads", "dead_addresses"]) {
    await blocked(`anon reads ${col}`, () => anon.collection(col).getList(1, 1));
    await blocked(`signed-in user reads ${col}`, () => a.pb.collection(col).getList(1, 1));
  }
  const summary = await anon.send("/api/cxi/register/summary", { method: "GET" });
  check("public summary answers", typeof summary.organisations_written_to === "number");

  console.log("the desk");
  await blocked("anon opens the desk", () => anon.send("/api/cxi/desk", { method: "GET" }));
  try { await a.pb.send("/api/cxi/desk", { method: "GET" }); check("stranger opens the desk", false, "(was allowed)"); }
  catch (e) { check("stranger is refused with a sentence", e.status === 403 && /belongs to the person/.test(e.response.message), e.response.message); }
  await blocked("stranger searches the desk", () => a.pb.send("/api/cxi/desk/search", { method: "GET", query: { q: "secret" } }));
  const owner = await personWithEmail("Owner", "desk@test.local");
  const desk = await owner.pb.send("/api/cxi/desk", { method: "GET" });
  check("owner opens the desk", desk.person.id === owner.id && Array.isArray(desk.waiting) && Array.isArray(desk.documents) && desk.seats.length === 2);
  check("desk carries the register counts", typeof desk.register.open_threads === "number" && typeof desk.counts.documents === "number");
  const second = await personWithEmail("Second", "second.owner@test.local");
  check("second owner, listed with other casing, opens the desk", (await second.pb.send("/api/cxi/desk", { method: "GET" })).person.id === second.id);
  const su = await superuser();
  const doc = await su.collection("documents").create({ path: `desk/${t}.txt`, sha256: String(t).padStart(64, "a"), title: `Desk doc ${t}`, chars: 40, chunks: 1, bates_start: "CXI-000123" });
  await su.collection("chunks").create({ document: doc.id, ordinal: 0, text: `The signature block was added later, in different ink. ${t}`, model: "desk-test", dim: 4, embedding: [0, 0, 0, 0] });
  await su.collection("chunks").create({ document: doc.id, ordinal: 0, text: `The signature block was added later, in different ink. ${t}`, model: "desk-test-2", dim: 4, embedding: [0, 0, 0, 0] });
  const found = await owner.pb.send("/api/cxi/desk/search", { method: "GET", query: { q: "different ink" } });
  const hit = found.results.find((r) => r.id === doc.id);
  check("owner search finds the seeded document once, not once per model", !!hit && hit.hits === 1 && hit.bates_start === "CXI-000123" && /different ink/.test(hit.snippets[0].text), JSON.stringify(hit));
  check("one-letter search answers empty, not with everything", (await owner.pb.send("/api/cxi/desk/search", { method: "GET", query: { q: "i" } })).results.length === 0);
  check("desk lists the seeded document among the latest", (await owner.pb.send("/api/cxi/desk", { method: "GET" })).documents.some((d) => d.id === doc.id));
  await blocked("owner still cannot read the corpus directly", () => owner.pb.collection("chunks").getList(1, 1));
  done("rules");
})().catch((e) => { console.error("ERR", e.response || e); process.exit(1); });
