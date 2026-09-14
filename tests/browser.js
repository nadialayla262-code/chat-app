// The page, in two real browsers: sign-up, live rooms and messages, drafts, private rooms, invite, leave, phone drawer, the Desk.
const { BASE, PW, playwright, sleep, check, done, superuser } = require("./lib");
const chromium = playwright()?.chromium;
if (!chromium) { console.log("browser: skipped (Playwright not installed: npm i -g playwright && npx playwright install chromium)"); process.exit(0); }
(async () => {
  const browser = await chromium.launch();
  const errors = [];
  const t = Date.now();
  const mk = async (width = 1100) => {
    const page = await (await browser.newContext({ viewport: { width, height: 800 } })).newPage();
    page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
    return page;
  };
  const signup = async (page, name) => {
    await page.goto(BASE); await page.click("#auth-toggle");
    await page.fill("#auth-name", name); await page.fill("#auth-email", `${name.toLowerCase()}${t}@test.local`); await page.fill("#auth-password", PW);
    await page.click("#auth-submit"); await page.waitForSelector("#chat:not([hidden])");
  };
  const A = await mk(), B = await mk();
  await signup(A, "Ada"); await signup(B, "Bram");
  check("two people signed up", (await A.textContent("#you")).includes("Ada") && (await B.textContent("#you")).includes("Bram"));

  await A.fill("#room-name", `Room ${t}`); await A.click("#room-form button[type=submit]"); await A.waitForSelector("#composer:not([hidden])");
  await B.waitForSelector(`#room-list button:has-text("Room ${t}")`, { timeout: 8000 });
  check("new room appears live on B", true);
  await B.click(`#room-list button:has-text("Room ${t}")`); await B.waitForSelector("#composer:not([hidden])");
  await A.fill("#body", "Hello from Ada"); await A.press("#body", "Enter");
  await B.waitForSelector('.msg:has-text("Hello from Ada")', { timeout: 8000 });
  check("message crosses live with author name", (await B.textContent(".msg .who")) === "Ada");
  await B.fill("#body", "Hi Ada, Bram here"); await B.click("#send");
  await A.waitForSelector('.msg:has-text("Bram here")', { timeout: 8000 });
  check("reply crosses back", true);
  await A.fill("#body", "unsent draft"); await A.reload(); await A.waitForSelector("#chat:not([hidden])");
  await A.click(`#room-list button:has-text("Room ${t}")`); await A.waitForSelector("#composer:not([hidden])");
  check("draft restored after reload", (await A.inputValue("#body")) === "unsent draft");
  await A.waitForFunction(() => document.querySelectorAll(".msg").length === 2, null, { timeout: 8000 });
  check("history reloaded", (await A.locator(".msg").count()) === 2);
  check("only own messages have delete", (await B.locator(".msg.mine .del").count()) === 1 && (await B.locator(".msg:not(.mine) .del").count()) === 0);
  await B.click(".msg.mine .del");
  await A.waitForSelector('.msg:has-text("Bram here")', { state: "detached", timeout: 8000 });
  check("delete propagates live", true);

  await A.fill("#room-name", `Vault ${t}`); await A.check("#room-private"); await A.click("#room-form button[type=submit]");
  await A.waitForSelector("#room-info:not([hidden])");
  check("owner sees invite form, no leave", !(await A.locator("#invite-form").isHidden()) && (await A.locator("#leave-room").isHidden()));
  await A.fill("#body", "members only"); await A.press("#body", "Enter"); await A.waitForSelector('.msg:has-text("members only")');
  await sleep(1200);
  check("B cannot see private room", (await B.locator(`#room-list button:has-text("Vault ${t}")`).count()) === 0);
  await A.fill("#invite-email", `bram${t}@test.local`); await A.click("#invite-form button");
  await B.waitForSelector(`#room-list button:has-text("Vault ${t}")`, { timeout: 8000 });
  check("invite arrives live", true);
  await A.waitForFunction(() => document.getElementById("members").textContent.includes("Bram"));
  check("member bar updates live", (await A.textContent("#members")).includes("2 members"));
  await B.click(`#room-list button:has-text("Vault ${t}")`); await B.waitForSelector('.msg:has-text("members only")');
  check("member sees lock, leave, no invite form", (await B.locator("#room-list .lock").count()) > 0 && !(await B.locator("#leave-room").isHidden()) && (await B.locator("#invite-form").isHidden()));
  await A.fill("#invite-email", `nobody${t}@test.local`); await A.click("#invite-form button"); await A.waitForSelector("#chat-error:not([hidden])");
  check("unknown email is a plain error", (await A.textContent("#chat-error")).includes("No account"));
  await B.click("#leave-room");
  await B.waitForSelector(`#room-list button:has-text("Vault ${t}")`, { state: "detached", timeout: 8000 });
  check("leave removes room from B", (await B.textContent("#room-title")) === "Choose a room");
  await A.waitForFunction(() => document.getElementById("members").textContent.includes("1 member"));
  check("owner bar shows 1 member again", true);

  const dl = A.waitForEvent("download", { timeout: 8000 });
  await A.click("#export");
  const file = await dl;
  const path = await file.path();
  const exported = JSON.parse(require("fs").readFileSync(path, "utf8"));
  check("export downloads my data", exported.person && exported.person.name === "Ada" && exported.messages.length >= 1, file.suggestedFilename());

  const P = await mk(390);
  await P.goto(BASE); await P.fill("#auth-email", `ada${t}@test.local`); await P.fill("#auth-password", PW); await P.click("#auth-submit");
  await P.waitForSelector("#chat:not([hidden])");
  await P.click("#rooms-toggle"); await sleep(250);
  check("phone drawer opens", (await P.locator("#rooms-panel.open").count()) === 1);
  await P.mouse.click(370, 400); await sleep(250);
  check("tap outside closes drawer", (await P.locator("#rooms-panel.open").count()) === 0);

  // The Desk: closed to Ada, open to the owner named in run.sh, filled from the locked collections.
  await A.click("#desk-toggle"); await A.waitForSelector("#desk-closed:not([hidden])");
  check("desk refuses a stranger with a sentence", (await A.textContent("#desk-closed")).includes("belongs to the person") && (await A.textContent("#room-title")) === "Desk");
  await A.click(`#room-list button:has-text("Room ${t}")`); await A.waitForSelector("#composer:not([hidden])");
  check("opening a room leaves the desk", (await A.locator("#desk").isHidden()) && (await A.getAttribute("#desk-toggle", "aria-pressed")) === "false");
  const su = await superuser();
  const doc = await su.collection("documents").create({ path: `browser/${t}.txt`, sha256: String(t).padStart(64, "b"), title: `Nursing note ${t}`, chars: 60, chunks: 1, bates_start: "CXI-000456" });
  await su.collection("chunks").create({ document: doc.id, ordinal: 0, text: `Patient refused medication. The signature block appears to have been added later, in different ink. ${t}`, model: "desk-test", dim: 4, embedding: [0, 0, 0, 0] });
  await su.collection("threads").create({ key: `k${t}`, organisation: `inspectorate-${t}.example`, source: "test", subject: "Complete file, please", messages_sent: 3, human_replies: 0, status: "OPEN", last_sent: "2026-03-01 10:00:00.000Z" });
  const O = await mk();
  await O.goto(BASE); await O.click("#auth-toggle");
  await O.fill("#auth-name", "Owner"); await O.fill("#auth-email", "desk@test.local"); await O.fill("#auth-password", PW); await O.click("#auth-submit");
  await O.waitForSelector("#chat:not([hidden]), #auth-error:not([hidden])");
  if (await O.locator("#auth-error:not([hidden])").count()) {  // already created by another suite on this spine: sign in instead
    await O.click("#auth-toggle"); await O.fill("#auth-email", "desk@test.local"); await O.fill("#auth-password", PW); await O.click("#auth-submit");
    await O.waitForSelector("#chat:not([hidden])");
  }
  await O.click("#desk-toggle"); await O.waitForSelector("#desk-body:not([hidden])");
  check("owner sees the desk", (await O.getAttribute("#desk-toggle", "aria-pressed")) === "true" && (await O.locator("#desk-closed").isHidden()));
  check("desk shows who is waiting", (await O.textContent("#desk-waiting")).includes(`inspectorate-${t}.example`) && (await O.textContent("#desk-waiting")).includes("written 3×"));
  check("desk shows the latest document with its number", (await O.textContent("#desk-documents")).includes(`Nursing note ${t}`) && (await O.textContent("#desk-documents")).includes("CXI-000456"));
  check("desk shows both seats", (await O.textContent("#desk-seats")).includes("Homei") && (await O.textContent("#desk-seats")).includes("Handi"));
  await O.fill("#desk-q", "different ink"); await O.press("#desk-q", "Enter");
  await O.waitForSelector(`.hit:has-text("Nursing note ${t}")`, { timeout: 8000 });
  check("desk search quotes the passage", (await O.textContent(".desk-results")).includes("different ink") && (await O.textContent(".desk-results")).includes("CXI-000456"));
  await O.fill("#desk-q", `zzz-not-there-${t}`); await O.press("#desk-q", "Enter");
  await O.waitForSelector('.desk-results:has-text("is not in the corpus text")', { timeout: 8000 });
  check("desk search says when nothing matches", true);
  await O.click("#desk-toggle");
  check("desk toggles back to the rooms", (await O.locator("#desk").isHidden()) && (await O.textContent("#room-title")) === "Choose a room");

  const W = await mk(); await W.goto(BASE);
  await W.fill("#auth-email", `ada${t}@test.local`); await W.fill("#auth-password", "wrong-password-1"); await W.click("#auth-submit");
  await W.waitForSelector("#auth-error:not([hidden])");
  check("bad password shows an error", (await W.textContent("#auth-error")).length > 0);
  check("no page errors", errors.length === 0, errors.join("; "));
  await browser.close();
  done("browser");
})().catch((e) => { console.error("FAIL", e); process.exit(1); });
