/// <reference path="../pb_data/types.d.ts" />
//
// Optional sign-up code.
//
// On localhost, anyone who can reach the spine is you. Behind a tunnel,
// anyone on the internet can reach it, and an open sign-up would let a
// stranger create an account and read every open room. So: set
//
//     CXI_SIGNUP_CODE=some-long-phrase
//
// before starting the spine, and creating an account requires that code in
// the request body as `signup_code`. Unset, sign-up stays open. Superusers
// creating accounts from the admin panel are never asked.
//
onRecordCreateRequest((e) => {
  const required = $os.getenv("CXI_SIGNUP_CODE");
  if (!required) return e.next();
  if (e.hasSuperuserAuth()) return e.next();
  const given = String((e.requestInfo().body || {}).signup_code || "");
  if (given !== required) {
    throw new ForbiddenError("This server needs a sign-up code. Ask the person who runs it.");
  }
  return e.next();
}, "users");
