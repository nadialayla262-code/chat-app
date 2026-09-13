// Sign-up code: with CXI_SIGNUP_CODE set on the spine, creating an account needs the code.
const { BASE, PocketBase, PW, check, blocked, done } = require("./lib");
(async () => {
  const pb = new PocketBase(BASE);
  const t = Date.now();
  const body = (extra) => ({ name: "X", email: `x${t}${Math.random().toString().slice(2, 6)}@test.local`, password: PW, passwordConfirm: PW, ...extra });
  await blocked("sign-up without code", () => pb.collection("users").create(body({})));
  await blocked("sign-up with wrong code", () => pb.collection("users").create(body({ signup_code: "nope" })));
  const u = await pb.collection("users").create(body({ signup_code: "open-sesame-test" }));
  check("sign-up with the code", !!u.id);
  check("code is not stored on the record", !("signup_code" in u));
  const su = new PocketBase(BASE);
  await su.collection("_superusers").authWithPassword("test@cxi.local", "test-superuser-pass");
  const v = await su.collection("users").create(body({}));
  check("superuser creates accounts without a code", !!v.id);
  done("signup_code");
})().catch((e) => { console.error("ERR", e.response || e); process.exit(1); });
