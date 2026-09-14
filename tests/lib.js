// Shared bits for the test scripts. Node only, no packages beyond the vendored SDK.
const path = require("path");
const { execSync } = require("child_process");

const BASE = process.env.CXI_TEST_URL || "http://127.0.0.1:8099";
const PocketBase = require(path.join(__dirname, "..", "public", "vendor", "pocketbase.umd.js"));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PW = "correct-horse-battery";

/** Playwright if installed locally or globally, else null. */
function playwright() {
  try { return require("playwright"); } catch (_) {}
  try {
    const root = execSync("npm root -g", { encoding: "utf8" }).trim();
    return require(path.join(root, "playwright"));
  } catch (_) { return null; }
}

/** A signed-in client with a fresh account. */
async function person(name) {
  const pb = new PocketBase(BASE);
  const email = `${name.toLowerCase()}${Date.now()}${Math.floor(Math.random() * 1e4)}@test.local`;
  await pb.collection("users").create({ name, email, password: PW, passwordConfirm: PW });
  await pb.collection("users").authWithPassword(email, PW);
  return { pb, id: pb.authStore.record.id, email, name };
}

/** A signed-in client for a fixed email (created if needed). The Desk owners in run.sh are fixed emails. */
async function personWithEmail(name, email) {
  const pb = new PocketBase(BASE);
  try { await pb.collection("users").create({ name, email, password: PW, passwordConfirm: PW }); } catch (_) {}
  await pb.collection("users").authWithPassword(email, PW);
  return { pb, id: pb.authStore.record.id, email, name };
}
/** The test superuser, for seeding locked collections. */
async function superuser() {
  const pb = new PocketBase(BASE);
  await pb.collection("_superusers").authWithPassword("test@cxi.local", "test-superuser-pass");
  return pb;
}

let failures = 0;
function check(label, ok, detail = "") {
  console.log(`${ok ? "  ok  " : "  FAIL"} ${label}${detail ? "  " + detail : ""}`);
  if (!ok) failures += 1;
}
async function blocked(label, fn) {
  try { await fn(); check(label, false, "(was allowed)"); }
  catch (e) { check(label, true, `${e.status || ""}`); }
}
function done(name) {
  console.log(failures ? `${name}: ${failures} FAILED` : `${name}: all passed`);
  process.exit(failures ? 1 : 0);
}

module.exports = { BASE, PocketBase, sleep, PW, playwright, person, personWithEmail, superuser, check, blocked, done };
