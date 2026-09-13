// Homei and Handi against a stand-in model server (tests/fake_embed.py).
const { sleep, person, check, done } = require("./lib");
const from = async (pb, roomId, name) =>
  (await pb.collection("messages").getList(1, 30, { filter: `room = "${roomId}"`, sort: "created", expand: "author" })).items
    .filter((m) => m.expand?.author?.name === name);
const waitFor = async (pb, roomId, name, ms = 8000) => {
  const end = Date.now() + ms;
  while (Date.now() < end) { const r = await from(pb, roomId, name); if (r.length) return r; await sleep(300); }
  return [];
};
(async () => {
  const me = await person("Inayah");
  const t = Date.now();

  console.log("homei");
  const r1 = await me.pb.collection("rooms").create({ name: `general-${t}`, created_by: me.id });
  await me.pb.collection("messages").create({ room: r1.id, author: me.id, body: "humans only here" });
  await sleep(2500);
  check("silent when not addressed", (await from(me.pb, r1.id, "Homei")).length === 0);
  await me.pb.collection("messages").create({ room: r1.id, author: me.id, body: "hey @homei, you there?" });
  const rep = await waitFor(me.pb, r1.id, "Homei");
  check("answers when named", rep.length === 1, JSON.stringify(rep[0]?.body));
  check("thinking tags stripped", rep.length && !rep[0].body.includes("<think>"));
  const r2 = await me.pb.collection("rooms").create({ name: `homei-${t}`, created_by: me.id });
  await me.pb.collection("messages").create({ room: r2.id, author: me.id, body: "first" });
  await waitFor(me.pb, r2.id, "Homei");
  await me.pb.collection("messages").create({ room: r2.id, author: me.id, body: "second" });
  await sleep(2500);
  const h = await from(me.pb, r2.id, "Homei");
  check("answers every line in a homei room", h.length === 2);
  check("carries the thread (more turns second time)", h.length === 2 && /\|4 msgs\]/.test(h[1].body), h[1]?.body);
  const p = await me.pb.collection("rooms").create({ name: `homei-private-${t}`, private: true, created_by: me.id, members: [me.id] });
  await me.pb.collection("messages").create({ room: p.id, author: me.id, body: "homei, here?" });
  await sleep(2500);
  check("blind to a private room until invited", (await from(me.pb, p.id, "Homei")).length === 0);
  await me.pb.send("/api/cxi/invite", { method: "POST", body: { room: p.id, email: "homei@cxi.local" } });
  await me.pb.collection("messages").create({ room: p.id, author: me.id, body: "now?" });
  const pr = await waitFor(me.pb, p.id, "Homei");
  check("answers once after invite, not once per backlog line", pr.length === 1);

  console.log("handi");
  const other = await person("Bram");
  const r3 = await me.pb.collection("rooms").create({ name: `thread-${t}`, created_by: me.id });
  const post = async (who, body) => { await who.pb.collection("messages").create({ room: r3.id, author: who.id, body }); await sleep(150); };
  await post(me, "Did the letter go out?");
  await post(other, "Not yet. I'll send the scan tonight.");
  await post(me, "Which address did you use?");
  await post(me, "@handi where are we");
  const reg = await waitFor(me.pb, r3.id, "Handi");
  check("posts a register", reg.length === 1);
  const body = reg[0]?.body || "";
  check("answered question dropped", !body.includes("Did the letter go out"));
  check("open question kept", body.includes("Which address did you use?"));
  check("promise kept", body.includes("I'll send the scan tonight"));
  check("waiting on the right person", body.includes("Waiting on: Bram"));
  check("summon line not counted", body.includes("3 lines"), body.split("\n")[0]);
  await post(me, "@handi all");
  await sleep(3000);
  const all = (await from(me.pb, r3.id, "Handi")).pop().body;
  check("'all' covers this room", all.includes(`thread-${t}`));
  check("'all' skips a private room it is not in", !all.includes(`homei-private-${t}`) || false);

  console.log("handi find");
  await post(me, "@handi find signature added later different ink");
  await sleep(2500);
  const open = (await from(me.pb, r3.id, "Handi")).pop().body;
  check("refuses to search in an open room", open.includes("only search the corpus in a private room"));
  const v = await me.pb.collection("rooms").create({ name: `vault-${t}`, private: true, created_by: me.id, members: [me.id] });
  await me.pb.send("/api/cxi/invite", { method: "POST", body: { room: v.id, email: "handi@cxi.local" } });
  await me.pb.collection("messages").create({ room: v.id, author: me.id, body: "@handi find signature added later different ink" });
  const found = await waitFor(me.pb, v.id, "Handi", 10000);
  const fb = found[0]?.body || "";
  if (fb.includes("Nothing indexed")) console.log("  skip  corpus not indexed in this run (run the full suite for the search check)");
  else check("finds the passage in a private room, with document name", fb.includes("b-medical-note") && fb.includes("different ink"), fb.split("\n")[1]);
  done("workers");
})().catch((e) => { console.error("ERR", e.response || e); process.exit(1); });
