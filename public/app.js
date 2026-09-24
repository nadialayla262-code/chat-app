/* CXI Chat — the page.
 *
 * No framework, no build step. This file knows nothing about the back end;
 * it talks to `cxi` (cxi.js), which is the one file that does.
 */
(() => {
  "use strict";

  // ---------- DOM ----------
  const $ = (id) => document.getElementById(id);
  const el = {
    auth: $("auth"),
    chat: $("chat"),
    authForm: $("auth-form"),
    nameField: $("name-field"),
    name: $("auth-name"),
    codeField: $("code-field"),
    code: $("auth-code"),
    email: $("auth-email"),
    password: $("auth-password"),
    authHint: $("auth-hint"),
    authSubmit: $("auth-submit"),
    authToggle: $("auth-toggle"),
    authError: $("auth-error"),
    roomsToggle: $("rooms-toggle"),
    roomsPanel: $("rooms-panel"),
    roomTitle: $("room-title"),
    signout: $("signout"),
    exportBtn: $("export"),
    you: $("you"),
    roomList: $("room-list"),
    roomForm: $("room-form"),
    roomName: $("room-name"),
    roomPrivate: $("room-private"),
    roomInfo: $("room-info"),
    members: $("members"),
    inviteForm: $("invite-form"),
    inviteEmail: $("invite-email"),
    leaveRoom: $("leave-room"),
    messageList: $("message-list"),
    emptyState: $("empty-state"),
    composer: $("composer"),
    body: $("body"),
    send: $("send"),
    chatError: $("chat-error"),
    deskToggle: $("desk-toggle"),
    desk: $("desk"),
    deskClosed: $("desk-closed"),
    deskBody: $("desk-body"),
    deskSearchForm: $("desk-search-form"),
    deskQ: $("desk-q"),
    deskResults: $("desk-results"),
    deskRegister: $("desk-register"),
    deskWaiting: $("desk-waiting"),
    deskDocumentsSub: $("desk-documents-sub"),
    deskDocuments: $("desk-documents"),
    deskSeats: $("desk-seats"),
    boardSub: $("board-sub"),
    boardForm: $("board-form"),
    boardTitle: $("board-title"),
    boardStage: $("board-stage"),
    boardPriority: $("board-priority"),
    boardArea: $("board-area"),
    boardColumns: $("board-columns"),
    boardParked: $("board-parked-list"),
  };

  // ---------- State ----------
  const state = {
    mode: "signin", // or "signup"
    rooms: [],
    roomId: null,
    messages: [],
    unwatchMessages: null,
    unwatchRooms: null,
    openToken: 0,   // which openRoom call is the current one
    desk: false,    // the Desk is showing instead of a room
    projects: [],
    unwatchProjects: null,
  };

  // ---------- Helpers ----------
  const showError = (node, err) => { node.textContent = cxi.explain(err); node.hidden = false; };
  const clearError = (node) => { node.hidden = true; node.textContent = ""; };
  const me = () => cxi.auth.me() || {};

  const fmtTime = (iso) => {
    const d = new Date(iso);
    const sameDay = d.toDateString() === new Date().toDateString();
    const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return sameDay ? time : `${d.toLocaleDateString()} ${time}`;
  };
  const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString() : "");
  const authorName = (m) => m.author_name || (m.author === me().id ? (me().name || "you") : "someone");
  const byName = (a, b) => a.name.localeCompare(b.name);
  const draftKey = (roomId) => `cxi-chat:draft:${roomId}`;

  // ---------- Screens ----------
  const showAuth = () => { el.chat.hidden = true; el.auth.hidden = false; el.email.focus(); };
  const showChat = () => {
    el.auth.hidden = true;
    el.chat.hidden = false;
    el.you.textContent = `Signed in as ${me().name || me().email}`;
  };

  // ---------- Auth ----------
  const setMode = (mode) => {
    state.mode = mode;
    const signup = mode === "signup";
    el.nameField.hidden = !signup;
    el.codeField.hidden = !signup;
    el.authSubmit.textContent = signup ? "Create account" : "Sign in";
    el.authToggle.textContent = signup ? "Have an account? Sign in" : "New here? Create an account";
    el.authHint.hidden = !signup;
    el.password.autocomplete = signup ? "new-password" : "current-password";
    clearError(el.authError);
  };

  el.authToggle.addEventListener("click", () => setMode(state.mode === "signin" ? "signup" : "signin"));

  el.authForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError(el.authError);
    const email = el.email.value.trim();
    const password = el.password.value;
    el.authSubmit.disabled = true;
    try {
      if (state.mode === "signup") {
        const name = el.name.value.trim() || email.split("@")[0];
        await cxi.auth.signUp({ name, email, password, code: el.code.value.trim() });
      } else {
        await cxi.auth.signIn({ email, password });
      }
      el.password.value = "";
      await enterChat();
    } catch (err) {
      showError(el.authError, err);
    } finally {
      el.authSubmit.disabled = false;
    }
  });

  el.exportBtn.addEventListener("click", async () => {
    clearError(el.chatError);
    try {
      const data = await cxi.auth.exportAll();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `cxi-chat-export-${(me().name || "me").replace(/\W+/g, "-")}.json`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (err) {
      showError(el.chatError, err);
    }
  });

  /** Tear down everything about the current person: feeds, room, list. Used by sign-out and by a session ending on its own. */
  const reset = async () => {
    closeDesk();
    await leaveRoom();
    if (state.unwatchRooms) { state.unwatchRooms(); state.unwatchRooms = null; }
    state.rooms = [];
    el.roomList.innerHTML = "";
    el.you.textContent = "";
  };

  el.signout.addEventListener("click", async () => {
    await reset();
    cxi.auth.signOut();
    showAuth();
  });

  // ---------- Rooms ----------
  const renderRooms = () => {
    el.roomList.innerHTML = "";
    for (const r of state.rooms) {
      const li = document.createElement("li");
      if (r.id === state.roomId) li.className = "active";
      const b = document.createElement("button");
      b.type = "button";
      if (r.private) {
        const lock = document.createElement("span");
        lock.className = "lock";
        lock.textContent = "🔒";
        lock.setAttribute("aria-label", "Private room");
        b.appendChild(lock);
      }
      b.appendChild(document.createTextNode(r.name));
      b.title = r.topic || r.name;
      b.addEventListener("click", () => openRoom(r.id));
      li.appendChild(b);
      el.roomList.appendChild(li);
    }
  };

  const watchRooms = async () => {
    state.unwatchRooms = await cxi.rooms.watch(({ action, room }) => {
      const i = state.rooms.findIndex((r) => r.id === room.id);
      if (action === "delete") {
        if (i >= 0) state.rooms.splice(i, 1);
        if (state.roomId === room.id) leaveRoom();
      } else if (i >= 0) {
        state.rooms[i] = room;
      } else {
        state.rooms.push(room);
      }
      state.rooms.sort(byName);
      renderRooms();
      if (room.id === state.roomId) renderRoomInfo();
    });
  };

  const renderRoomInfo = () => {
    const room = state.rooms.find((r) => r.id === state.roomId);
    if (!room || !room.private) { el.roomInfo.hidden = true; return; }
    const names = room.members.map((m) => m.name || "someone");
    el.members.textContent = `Private · ${names.length} ${names.length === 1 ? "member" : "members"}: ${names.join(", ")}`;
    const owner = room.created_by === me().id;
    el.inviteForm.hidden = !owner;
    el.leaveRoom.hidden = owner;
    el.roomInfo.hidden = false;
  };

  el.leaveRoom.addEventListener("click", async () => {
    if (!state.roomId) return;
    clearError(el.chatError);
    try {
      await cxi.rooms.leave(state.roomId);
      // The room disappears from our list via the feed; leave it now regardless.
      state.rooms = state.rooms.filter((r) => r.id !== state.roomId);
      await leaveRoom();
    } catch (err) {
      showError(el.chatError, err);
    }
  });

  el.inviteForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError(el.chatError);
    const email = el.inviteEmail.value.trim();
    if (!email || !state.roomId) return;
    try {
      await cxi.rooms.invite(state.roomId, email);
      el.inviteEmail.value = "";
      // The rooms feed delivers the updated member list; nothing else to do.
    } catch (err) {
      showError(el.chatError, err);
    }
  });

  el.roomForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError(el.chatError);
    const name = el.roomName.value.trim();
    if (!name) return;
    try {
      const room = await cxi.rooms.create({ name, private: el.roomPrivate.checked });
      el.roomName.value = "";
      el.roomPrivate.checked = false;
      if (!state.rooms.some((r) => r.id === room.id)) {
        state.rooms.push(room);
        state.rooms.sort(byName);
      }
      await openRoom(room.id);
    } catch (err) {
      showError(el.chatError, err);
    }
  });

  el.roomsToggle.addEventListener("click", (e) => {
    e.stopPropagation();
    el.roomsPanel.classList.toggle("open");
  });
  // Tap anywhere outside the drawer to close it (phone layout).
  document.addEventListener("click", (e) => {
    if (el.roomsPanel.classList.contains("open") && !el.roomsPanel.contains(e.target)) {
      el.roomsPanel.classList.remove("open");
    }
  });

  // ---------- Messages ----------
  const renderMessage = (m) => {
    const mine = m.author === me().id;
    const div = document.createElement("div");
    div.className = "msg" + (mine ? " mine" : "");
    div.dataset.id = m.id;

    const meta = document.createElement("div");
    meta.className = "meta";
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = authorName(m);
    const when = document.createElement("time");
    when.dateTime = m.created;
    when.textContent = fmtTime(m.created);
    meta.append(who, when);

    if (mine) {
      const del = document.createElement("button");
      del.type = "button";
      del.className = "del";
      del.textContent = "delete";
      del.setAttribute("aria-label", "Delete this message");
      del.addEventListener("click", async () => {
        try { await cxi.messages.remove(m.id); }
        catch (err) { showError(el.chatError, err); }
      });
      meta.appendChild(del);
    }

    const text = document.createElement("div");
    text.className = "text";
    text.textContent = m.body;

    div.append(meta, text);
    return div;
  };

  const renderMessages = () => {
    el.messageList.innerHTML = "";
    if (!state.roomId) {
      el.emptyState.textContent = "Pick a room on the left, or create one.";
      el.messageList.appendChild(el.emptyState);
      return;
    }
    if (state.messages.length === 0) {
      el.emptyState.textContent = "No messages yet. Say something.";
      el.messageList.appendChild(el.emptyState);
      return;
    }
    // Only follow the bottom if the reader was already there; never yank someone out of the history.
    const wasAtBottom = el.messageList.scrollHeight - el.messageList.scrollTop - el.messageList.clientHeight < 80;
    for (const m of state.messages) el.messageList.appendChild(renderMessage(m));
    if (wasAtBottom || el.messageList.dataset.fresh !== "no") el.messageList.scrollTop = el.messageList.scrollHeight;
    el.messageList.dataset.fresh = "no";
  };

  const upsertMessage = (m) => {
    const i = state.messages.findIndex((x) => x.id === m.id);
    if (i >= 0) state.messages[i] = { ...state.messages[i], ...m, author_name: m.author_name || state.messages[i].author_name };
    else state.messages.push(m);
    renderMessages();
  };
  const removeMessage = (id) => {
    state.messages = state.messages.filter((x) => x.id !== id);
    renderMessages();
  };

  const leaveRoom = async () => {
    if (state.unwatchMessages) { state.unwatchMessages(); state.unwatchMessages = null; }
    state.roomId = null;
    state.messages = [];
    el.roomTitle.textContent = "Choose a room";
    el.composer.hidden = true;
    el.roomInfo.hidden = true;
    renderRooms();
    renderMessages();
  };

  const openRoom = async (roomId) => {
    if (state.roomId === roomId && !state.desk) { el.roomsPanel.classList.remove("open"); return; }
    closeDesk();
    await leaveRoom();
    clearError(el.chatError);
    const token = ++state.openToken;
    const room = state.rooms.find((r) => r.id === roomId);
    state.roomId = roomId;
    el.roomTitle.textContent = room ? room.name : "Room";
    el.roomsPanel.classList.remove("open");
    renderRooms();
    renderRoomInfo();

    el.messageList.dataset.fresh = "yes";   // first render of a room always lands at the bottom
    // Restore an unsent draft for this room. If you were interrupted, it waits.
    try { el.body.value = localStorage.getItem(draftKey(roomId)) || ""; } catch (_) {}
    el.composer.hidden = false;

    try {
      // Subscribe before loading history so nothing sent in between is lost;
      // upsert dedupes anything that arrives both ways.
      const unwatch = await cxi.messages.watch(roomId, ({ action, message }) => {
        if (state.roomId !== roomId) return;
        if (action === "delete") removeMessage(message.id);
        else upsertMessage(message);
      });
      if (token !== state.openToken) { unwatch(); return; }  // another room was opened meanwhile
      state.unwatchMessages = unwatch;
      const history = await cxi.messages.history(roomId, 100);
      if (token !== state.openToken) return;
      const seen = new Set(history.map((m) => m.id));
      state.messages = history.concat(state.messages.filter((m) => !seen.has(m.id)));
      renderMessages();
    } catch (err) {
      showError(el.chatError, err);
    }
    el.body.focus();
  };

  el.body.addEventListener("input", () => {
    if (!state.roomId) return;
    try { localStorage.setItem(draftKey(state.roomId), el.body.value); } catch (_) {}
  });
  el.body.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      el.composer.requestSubmit();
    }
  });

  el.composer.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError(el.chatError);
    const body = el.body.value.trim();
    if (!body || !state.roomId) return;
    el.send.disabled = true;
    try {
      const sent = await cxi.messages.send(state.roomId, body);
      el.body.value = "";
      try { localStorage.removeItem(draftKey(state.roomId)); } catch (_) {}
      el.messageList.dataset.fresh = "yes";  // your own line always brings you to the bottom
      upsertMessage(sent); // the live feed also delivers it; upsert dedupes by id
    } catch (err) {
      showError(el.chatError, err);
    } finally {
      el.send.disabled = false;
      el.body.focus();
    }
  });

  // ---------- Desk ----------
  // One screen behind the chat. The page only draws what the server sends;
  // pb_hooks/desk.pb.js decides who may see it (CXI_DESK_OWNERS).
  const li = (parent, ...parts) => {
    const item = document.createElement("li");
    for (const p of parts) if (p) item.appendChild(p);
    parent.appendChild(item);
    return item;
  };
  const span = (cls, text) => { const s = document.createElement("span"); s.className = cls; s.textContent = text; return s; };

  const renderDesk = (d) => {
    el.deskClosed.hidden = true;
    el.deskBody.hidden = false;
    const r = d.register || {};
    el.deskRegister.textContent = `${r.open_threads || 0} open · ${r.organisations_written_to || 0} organisations written to · ${r.never_answered_by_a_person || 0} never answered by a person · ${r.dead_addresses || 0} dead addresses`;
    el.deskWaiting.innerHTML = "";
    if (!d.waiting || !d.waiting.length) li(el.deskWaiting, span("soft", "Nobody. Load the mail register to see who owes you a reply."));
    for (const t of d.waiting || []) {
      li(el.deskWaiting, span("strong", t.organisation), span("soft", t.subject || "(no subject)"),
        span("soft", `written ${t.messages_sent}× · last ${fmtDate(t.last_sent)} · ${t.human_replies} human ${t.human_replies === 1 ? "reply" : "replies"}`));
    }
    el.deskDocumentsSub.textContent = `${d.counts && d.counts.documents || 0} in the corpus`;
    el.deskDocuments.innerHTML = "";
    if (!d.documents || !d.documents.length) li(el.deskDocuments, span("soft", "None yet. Index a folder with workers/index.py."));
    for (const doc of d.documents || []) {
      const bates = doc.bates_start ? (doc.bates_end && doc.bates_end !== doc.bates_start ? `${doc.bates_start} – ${doc.bates_end}` : doc.bates_start) : "";
      li(el.deskDocuments, span("strong", doc.title || doc.path), span("soft", doc.path), span("soft", [bates, `${doc.chars || 0} characters`, fmtDate(doc.created)].filter(Boolean).join(" · ")));
    }
    el.deskSeats.innerHTML = "";
    for (const seat of d.seats || []) {
      const status = !seat.present ? "not started yet" : seat.last_spoke ? `last spoke ${fmtDate(seat.last_spoke)}${seat.room ? " in " + seat.room : ""}` : "seated, has not spoken yet";
      const head = span("strong", "");
      head.append(span(seat.present ? "seat on" : "seat off", seat.present ? "● " : "○ "), document.createTextNode(seat.name));
      li(el.deskSeats, head, span("soft", status));
    }
  };

  const renderResults = (res) => {
    el.deskResults.innerHTML = "";
    if (!res.q) return;
    const head = document.createElement("p");
    head.className = "soft";
    head.textContent = res.results.length ? `“${res.q}” in ${res.documents_matched} ${res.documents_matched === 1 ? "document" : "documents"}` : `“${res.q}” is not in the corpus text.`;
    el.deskResults.appendChild(head);
    for (const doc of res.results) {
      const card = document.createElement("div");
      card.className = "hit";
      const title = document.createElement("div");
      title.className = "strong";
      title.textContent = (doc.bates_start ? doc.bates_start + "  " : "") + (doc.title || doc.path);
      card.appendChild(title);
      for (const sn of doc.snippets) {
        const q = document.createElement("blockquote");
        q.textContent = sn.text;
        card.appendChild(q);
      }
      el.deskResults.appendChild(card);
    }
  };

  // ---------- The board ----------
  // Yours only: the server rules give each person their own rows. Stages
  // move left and right, priority cycles, nothing is deleted, only parked.
  const STAGES = ["idea", "working", "built", "live", "done"];
  const STAGE_LABEL = { idea: "Ideas", working: "Working on", built: "Built", live: "Live", done: "Done", parked: "Parked" };
  const PRIORITY_LABEL = { 1: "now", 2: "next", 3: "later" };
  const byPriority = (a, b) => ((a.priority || 9) - (b.priority || 9)) || a.title.localeCompare(b.title);

  const patchProject = async (id, patch) => {
    clearError(el.chatError);
    try { upsertProject(await cxi.projects.update(id, patch)); }
    catch (err) { showError(el.chatError, err); }
  };
  const smallBtn = (label, title, onClick) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "tiny"; b.textContent = label; b.title = title; b.setAttribute("aria-label", title);
    b.addEventListener("click", onClick);
    return b;
  };
  const renderCard = (p) => {
    const card = document.createElement("div");
    card.className = "pcard" + (p.priority === 1 ? " now" : "");
    card.dataset.id = p.id;
    const head = document.createElement("div");
    head.className = "pcard-title";
    if (p.link) {
      const a = document.createElement("a"); a.href = p.link; a.target = "_blank"; a.rel = "noopener"; a.textContent = p.title; head.appendChild(a);
    } else head.textContent = p.title;
    const meta = span("soft", [p.area, p.priority ? PRIORITY_LABEL[p.priority] : ""].filter(Boolean).join(" · "));
    const acts = document.createElement("div");
    acts.className = "pcard-acts";
    const i = STAGES.indexOf(p.stage);
    if (p.stage === "parked") {
      acts.appendChild(smallBtn("unpark", "Back to ideas", () => patchProject(p.id, { stage: "idea" })));
    } else {
      if (i > 0) acts.appendChild(smallBtn("◀", `Back to ${STAGE_LABEL[STAGES[i - 1]]}`, () => patchProject(p.id, { stage: STAGES[i - 1] })));
      if (i < STAGES.length - 1) acts.appendChild(smallBtn("▶", `On to ${STAGE_LABEL[STAGES[i + 1]]}`, () => patchProject(p.id, { stage: STAGES[i + 1] })));
      const next = p.priority === 1 ? 2 : p.priority === 2 ? 3 : p.priority === 3 ? null : 1;
      acts.appendChild(smallBtn(p.priority ? PRIORITY_LABEL[p.priority] : "priority", "Cycle priority: now, next, later, none", () => patchProject(p.id, { priority: next })));
      acts.appendChild(smallBtn("park", "Park it (never deleted)", () => patchProject(p.id, { stage: "parked" })));
    }
    card.append(head, meta, acts);
    if (p.notes) { const n = document.createElement("p"); n.className = "soft pcard-notes"; n.textContent = p.notes; card.insertBefore(n, acts); }
    return card;
  };
  const renderBoard = () => {
    const live = state.projects.filter((p) => p.stage !== "parked");
    const parked = state.projects.filter((p) => p.stage === "parked");
    el.boardSub.textContent = live.length ? `${live.length} on the board · ${live.filter((p) => p.priority === 1).length} marked now` : "Nothing on the board yet. Add a thing above, or load a CSV with workers/board_load.py.";
    el.boardColumns.innerHTML = "";
    for (const stage of STAGES) {
      const col = document.createElement("section");
      col.className = "board-col";
      col.dataset.stage = stage;
      const items = live.filter((p) => p.stage === stage).sort(byPriority);
      const h = document.createElement("h4");
      h.textContent = `${STAGE_LABEL[stage]} · ${items.length}`;
      col.appendChild(h);
      for (const p of items) col.appendChild(renderCard(p));
      el.boardColumns.appendChild(col);
    }
    el.boardParked.innerHTML = "";
    for (const p of parked.sort(byPriority)) li(el.boardParked, renderCard(p));
  };
  const upsertProject = (p) => {
    const i = state.projects.findIndex((x) => x.id === p.id);
    if (i >= 0) state.projects[i] = p; else state.projects.push(p);
    renderBoard();
  };
  const loadBoard = async () => {
    if (state.unwatchProjects) { state.unwatchProjects(); state.unwatchProjects = null; }
    try {
      // Feed first, then the list, merged by id: nothing added in between is missed.
      state.unwatchProjects = await cxi.projects.watch(({ action, project }) => {
        if (action === "delete") { state.projects = state.projects.filter((x) => x.id !== project.id); renderBoard(); }
        else upsertProject(project);
      });
      const listed = await cxi.projects.list();
      const seen = new Set(listed.map((p) => p.id));
      state.projects = listed.concat(state.projects.filter((p) => !seen.has(p.id)));
      renderBoard();
    } catch (err) {
      showError(el.chatError, err);
    }
  };
  el.boardForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError(el.chatError);
    const title = el.boardTitle.value.trim();
    if (!title) return;
    try {
      const p = await cxi.projects.create({ title, stage: el.boardStage.value, priority: Number(el.boardPriority.value) || null, area: el.boardArea.value.trim(), source: "desk" });
      el.boardTitle.value = ""; el.boardArea.value = "";
      upsertProject(p);
      el.boardTitle.focus();
    } catch (err) {
      showError(el.chatError, err);
    }
  });

  const openDesk = async () => {
    await leaveRoom();
    state.desk = true;
    el.desk.hidden = false;
    el.messageList.hidden = true;
    el.roomTitle.textContent = "Desk";
    el.deskToggle.setAttribute("aria-pressed", "true");
    el.roomsPanel.classList.remove("open");
    renderRooms();
    el.deskResults.innerHTML = "";
    await loadBoard();
    try {
      renderDesk(await cxi.desk.load());
    } catch (err) {
      el.deskBody.hidden = true;
      el.deskClosed.textContent = cxi.explain(err);
      el.deskClosed.hidden = false;
    }
  };
  const closeDesk = () => {
    if (!state.desk) return;
    state.desk = false;
    if (state.unwatchProjects) { state.unwatchProjects(); state.unwatchProjects = null; }
    state.projects = [];
    el.desk.hidden = true;
    el.messageList.hidden = false;
    el.deskToggle.setAttribute("aria-pressed", "false");
    if (!state.roomId) el.roomTitle.textContent = "Choose a room";
  };

  el.deskToggle.addEventListener("click", async () => {
    if (state.desk) { closeDesk(); renderMessages(); return; }
    await openDesk();
  });
  el.deskSearchForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = el.deskQ.value.trim();
    if (!q) { el.deskResults.innerHTML = ""; return; }
    try { renderResults(await cxi.desk.search(q)); }
    catch (err) { showError(el.chatError, err); }
  });

  // ---------- Boot ----------
  const enterChat = async () => {
    showChat();
    try {
      // Feed first, then the list, merged by id: a room created or an invite
      // received in between is not missed.
      await watchRooms();
      const listed = await cxi.rooms.list();
      const seen = new Set(listed.map((r) => r.id));
      state.rooms = listed.concat(state.rooms.filter((r) => !seen.has(r.id))).sort(byName);
      renderRooms();
    } catch (err) {
      showError(el.chatError, err);
    }
  };

  cxi.auth.onSignedOut(async () => { if (!el.chat.hidden) { await reset(); showAuth(); } });

  (async () => {
    setMode("signin");
    if (await cxi.auth.resume()) { await enterChat(); return; }
    showAuth();
  })();
})();
