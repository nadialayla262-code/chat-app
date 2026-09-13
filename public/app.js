/* CXI Chat — thin client over PocketBase.
 *
 * No framework, no build step. Open the page, it talks to the PocketBase
 * that served it. Everything here is readable in one sitting on purpose.
 */
(() => {
  "use strict";

  const pb = new PocketBase(window.location.origin);
  pb.autoCancellation(false);

  // ---------- DOM ----------
  const $ = (id) => document.getElementById(id);
  const el = {
    auth: $("auth"),
    chat: $("chat"),
    authForm: $("auth-form"),
    nameField: $("name-field"),
    name: $("auth-name"),
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
    you: $("you"),
    roomList: $("room-list"),
    roomForm: $("room-form"),
    roomName: $("room-name"),
    messageList: $("message-list"),
    emptyState: $("empty-state"),
    composer: $("composer"),
    body: $("body"),
    send: $("send"),
    chatError: $("chat-error"),
  };

  // ---------- State ----------
  const state = {
    mode: "signin", // or "signup"
    rooms: [],
    roomId: null,
    messages: [],
    unsubMessages: null,
    unsubRooms: null,
  };

  // ---------- Helpers ----------
  const showError = (node, err) => {
    let text = "Something went wrong.";
    if (err && err.response && err.response.data) {
      // PocketBase field errors: { field: { message } }
      const fields = Object.entries(err.response.data)
        .map(([k, v]) => `${k}: ${v.message}`)
        .join(" ");
      text = fields || err.response.message || err.message;
    } else if (err && err.message) {
      text = err.message;
    }
    node.textContent = text;
    node.hidden = false;
  };
  const clearError = (node) => { node.hidden = true; node.textContent = ""; };

  const fmtTime = (iso) => {
    const d = new Date(iso);
    const today = new Date();
    const sameDay = d.toDateString() === today.toDateString();
    const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return sameDay ? time : `${d.toLocaleDateString()} ${time}`;
  };

  const authorName = (m) => {
    const a = m.expand && m.expand.author;
    if (a && a.name) return a.name;
    if (m.author === pb.authStore.record?.id) return me().name || "you";
    return "someone";
  };
  const me = () => pb.authStore.record || {};

  const draftKey = (roomId) => `cxi-chat:draft:${roomId}`;

  // ---------- Screens ----------
  const showAuth = () => {
    el.chat.hidden = true;
    el.auth.hidden = false;
    el.email.focus();
  };
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
    el.authSubmit.textContent = signup ? "Create account" : "Sign in";
    el.authToggle.textContent = signup ? "Have an account? Sign in" : "New here? Create an account";
    el.authHint.hidden = !signup;
    el.password.autocomplete = signup ? "new-password" : "current-password";
    clearError(el.authError);
  };

  el.authToggle.addEventListener("click", () => {
    setMode(state.mode === "signin" ? "signup" : "signin");
  });

  el.authForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError(el.authError);
    const email = el.email.value.trim();
    const password = el.password.value;
    el.authSubmit.disabled = true;
    try {
      if (state.mode === "signup") {
        const name = el.name.value.trim() || email.split("@")[0];
        await pb.collection("users").create({
          name, email, password, passwordConfirm: password,
        });
      }
      await pb.collection("users").authWithPassword(email, password);
      el.password.value = "";
      await enterChat();
    } catch (err) {
      showError(el.authError, err);
    } finally {
      el.authSubmit.disabled = false;
    }
  });

  el.signout.addEventListener("click", async () => {
    await leaveRoom();
    if (state.unsubRooms) { state.unsubRooms(); state.unsubRooms = null; }
    pb.authStore.clear();
    state.rooms = [];
    el.roomList.innerHTML = "";
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
      b.textContent = r.name;
      b.title = r.topic || r.name;
      b.addEventListener("click", () => openRoom(r.id));
      li.appendChild(b);
      el.roomList.appendChild(li);
    }
  };

  const loadRooms = async () => {
    state.rooms = await pb.collection("rooms").getFullList({ sort: "name" });
    renderRooms();
  };

  const watchRooms = async () => {
    state.unsubRooms = await pb.collection("rooms").subscribe("*", (e) => {
      const i = state.rooms.findIndex((r) => r.id === e.record.id);
      if (e.action === "delete") {
        if (i >= 0) state.rooms.splice(i, 1);
        if (state.roomId === e.record.id) leaveRoom();
      } else if (i >= 0) {
        state.rooms[i] = e.record;
      } else {
        state.rooms.push(e.record);
      }
      state.rooms.sort((a, b) => a.name.localeCompare(b.name));
      renderRooms();
    });
  };

  el.roomForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError(el.chatError);
    const name = el.roomName.value.trim();
    if (!name) return;
    try {
      const room = await pb.collection("rooms").create({ name, created_by: me().id });
      el.roomName.value = "";
      if (!state.rooms.some((r) => r.id === room.id)) {
        state.rooms.push(room);
        state.rooms.sort((a, b) => a.name.localeCompare(b.name));
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
    const div = document.createElement("div");
    div.className = "msg" + (m.author === me().id ? " mine" : "");
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

    if (m.author === me().id) {
      const del = document.createElement("button");
      del.type = "button";
      del.className = "del";
      del.textContent = "delete";
      del.setAttribute("aria-label", "Delete this message");
      del.addEventListener("click", async () => {
        try { await pb.collection("messages").delete(m.id); }
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
      el.messageList.appendChild(el.emptyState);
      el.emptyState.textContent = "Pick a room on the left, or create one.";
      return;
    }
    if (state.messages.length === 0) {
      el.messageList.appendChild(el.emptyState);
      el.emptyState.textContent = "No messages yet. Say something.";
      return;
    }
    for (const m of state.messages) el.messageList.appendChild(renderMessage(m));
    el.messageList.scrollTop = el.messageList.scrollHeight;
  };

  const upsertMessage = (m) => {
    const i = state.messages.findIndex((x) => x.id === m.id);
    if (i >= 0) state.messages[i] = { ...state.messages[i], ...m, expand: m.expand || state.messages[i].expand };
    else state.messages.push(m);
    renderMessages();
  };
  const removeMessage = (id) => {
    state.messages = state.messages.filter((x) => x.id !== id);
    renderMessages();
  };

  const leaveRoom = async () => {
    if (state.unsubMessages) { state.unsubMessages(); state.unsubMessages = null; }
    state.roomId = null;
    state.messages = [];
    el.roomTitle.textContent = "Choose a room";
    el.composer.hidden = true;
    renderRooms();
    renderMessages();
  };

  const openRoom = async (roomId) => {
    if (state.roomId === roomId) { el.roomsPanel.classList.remove("open"); return; }
    await leaveRoom();
    clearError(el.chatError);
    const room = state.rooms.find((r) => r.id === roomId);
    state.roomId = roomId;
    el.roomTitle.textContent = room ? room.name : "Room";
    el.roomsPanel.classList.remove("open");
    renderRooms();

    // Restore an unsent draft for this room. If you were interrupted, it waits.
    try { el.body.value = localStorage.getItem(draftKey(roomId)) || ""; } catch (_) {}
    el.composer.hidden = false;

    try {
      const page = await pb.collection("messages").getList(1, 100, {
        filter: `room = "${roomId}"`,
        sort: "-created",
        expand: "author",
      });
      state.messages = page.items.reverse();
      renderMessages();

      state.unsubMessages = await pb.collection("messages").subscribe("*", (e) => {
        if (e.record.room !== state.roomId) return;
        if (e.action === "delete") removeMessage(e.record.id);
        else upsertMessage(e.record);
      }, { filter: `room = "${roomId}"`, expand: "author" });
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
      const rec = await pb.collection("messages").create(
        { room: state.roomId, author: me().id, body },
        { expand: "author" },
      );
      el.body.value = "";
      try { localStorage.removeItem(draftKey(state.roomId)); } catch (_) {}
      upsertMessage(rec); // realtime will also deliver it; upsert dedupes by id
    } catch (err) {
      showError(el.chatError, err);
    } finally {
      el.send.disabled = false;
      el.body.focus();
    }
  });

  // ---------- Boot ----------
  const enterChat = async () => {
    showChat();
    try {
      await loadRooms();
      await watchRooms();
    } catch (err) {
      showError(el.chatError, err);
    }
  };

  pb.authStore.onChange(() => {
    if (!pb.authStore.isValid && !el.chat.hidden) showAuth();
  });

  (async () => {
    setMode("signin");
    if (pb.authStore.isValid) {
      try {
        await pb.collection("users").authRefresh();
        await enterChat();
        return;
      } catch (_) {
        pb.authStore.clear();
      }
    }
    showAuth();
  })();
})();
