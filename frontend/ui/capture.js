// Pack It Up: the capture page (capture.html). Room cards, the upload queue, per-file progress,
// the top open question, and coming back to a move. Needs ui/api.js and ui/questions.js first.
(function () {
  "use strict";
  const { api, link, MOCK, params, $, isVideo, thumbHtml, totalBoxes } = window.PIU;
  const ACCEPT_EXT = /\.(jpe?g|png|heic|heif|webp|mp4|mov|m4v)$/i;
  const TUNNEL = /trycloudflare\.com$/i.test(location.hostname);
  const WARN_MB = TUNNEL ? 90 : 200;

  if (MOCK) $("#mock-banner").classList.remove("hidden");

  // One move is one run on the server. The run id is kept in the address (?run_id=), so a reload
  // comes back to the same move; see "coming back to a move" below.
  let runId = null;
  let firstSentAt = 0;
  const rooms = [];          // {el, name, locked, files: [row]}
  const usedNames = new Set();   // every file name in this run, lower case: the server keys files by name
  const queue = [];
  let uploading = false;
  let pollTimer = null;      // a poll is scheduled
  let polling = false;       // a poll is waiting on the server
  let lastRun = null;
  const Q = window.PIU_Q;
  const busyQ = new Set();
  let shownQ = "";        // id + busy state of the question card on screen, to avoid re-rendering under the user's thumb
  let qScrolled = false;
  let answeredHere = 0;

  // ---------- rooms ----------
  function addRoom() {
    const el = $("#room-tpl").content.firstElementChild.cloneNode(true);
    const room = { el, name: "", locked: false, files: [] };
    const input = $(".room-name", el);
    input.placeholder = rooms.length ? "Kitchen" : "Living room";
    input.value = "Room " + (rooms.length + 1);
    input.addEventListener("focus", () => { if (/^Room \d+$/.test(input.value)) input.select(); });
    [$(".cam", el), $(".lib", el)].forEach((inp) => {
      inp.addEventListener("click", () => setWaiting(room, true));   // the camera or photo picker is opening
      inp.addEventListener("cancel", () => setWaiting(room, false)); // closed without choosing (Safari 16.4+)
      inp.addEventListener("change", () => { setWaiting(room, false); pick(room, Array.from(inp.files || [])); inp.value = ""; });
    });
    rooms.push(room);
    $("#rooms").appendChild(el);
    return room;
  }

  // Between tapping a pick button and the browser's "change" event the page hears nothing, and on a
  // phone that gap is long: iOS converts each photo to JPEG (and re-encodes clips) before handing it
  // over, about 5 s for three photos (FAILURES.md 12:45). Show a "getting your files" row meanwhile so
  // the page doesn't look frozen. Browsers without the "cancel" event never say the picker was closed
  // empty-handed, so the row also clears itself a minute after the page is back in front.
  const WAIT_GIVE_UP_MS = 60000;
  function setWaiting(room, on) {
    clearTimeout(room.waitTimer);
    room.waiting = on;
    render(room);
  }
  window.addEventListener("focus", () => rooms.forEach((room) => {
    if (!room.waiting) return;
    clearTimeout(room.waitTimer);
    room.waitTimer = setTimeout(() => setWaiting(room, false), WAIT_GIVE_UP_MS);
  }));

  // A room's name is fixed once it has files: the server files them under that name.
  function lockRoom(room, name) {
    room.name = name;
    room.locked = true;
    const input = $(".room-name", room.el);
    input.value = name;
    input.readOnly = true;
  }

  function roomName(room) {
    if (room.locked) return room.name;
    let name = $(".room-name", room.el).value.trim() || "Room " + (rooms.indexOf(room) + 1);
    const taken = rooms.filter((r) => r !== room && r.locked).map((r) => r.name.toLowerCase());
    let n = 2, base = name;
    while (taken.includes(name.toLowerCase())) name = `${base} ${n++}`;
    return name;
  }

  // iPhone camera captures are all called image.jpg; the server keys files by name, so make each unique.
  function uniqueName(name) {
    if (!usedNames.has(name.toLowerCase())) { usedNames.add(name.toLowerCase()); return name; }
    const dot = name.lastIndexOf(".");
    const stem = dot > 0 ? name.slice(0, dot) : name, ext = dot > 0 ? name.slice(dot) : "";
    let i = 2;
    while (usedNames.has(`${stem}_${i}${ext}`.toLowerCase())) i++;
    usedNames.add(`${stem}_${i}${ext}`.toLowerCase());
    return `${stem}_${i}${ext}`;
  }

  function pick(room, files) {
    if (!files.length) return;
    const ok = files.filter((f) => /^(image|video)\//.test(f.type) || ACCEPT_EXT.test(f.name));
    const warn = $(".size-warn", room.el);
    const msgs = [];
    if (ok.length < files.length) msgs.push(`${files.length - ok.length} file(s) skipped: only photos and videos.`);
    const big = ok.filter((f) => f.size > WARN_MB * 1e6);
    if (big.length) msgs.push(`${big.map((f) => f.name).join(", ")} ${big.length > 1 ? "are" : "is"} over ${WARN_MB} MB and may be slow` +
      (TUNNEL ? " or rejected by the tunnel (100 MB limit). Shorter clips work better." : ". Shorter clips work better."));
    warn.textContent = msgs.join(" ");
    warn.classList.toggle("hidden", !msgs.length);
    if (!ok.length) return;

    lockRoom(room, roomName(room));

    const batch = ok.map((f) => {
      const name = uniqueName(f.name || "upload");
      const file = name === f.name ? f : new File([f], name, { type: f.type, lastModified: f.lastModified });
      const row = { name, file, kind: isVideo(name, f.type) ? "video" : "image",
                    phase: "queued", pct: 0, server: null, err: "" };
      room.files.push(row);
      return row;
    });
    queue.push({ room, rows: batch });
    render(room);
    pump();
  }

  // ---------- uploads: one at a time, so every upload after the first carries the run_id ----------
  async function pump() {
    if (uploading || !queue.length) return;
    uploading = true;
    const job = queue.shift();
    job.rows.forEach((r) => { r.phase = "uploading"; r.pct = 0; r.err = ""; });
    render(job.room);
    try {
      const res = await api.upload(job.rows.map((r) => r.file), job.room.name, runId, (p) => {
        job.rows.forEach((r) => (r.pct = p));
        render(job.room);
      });
      adoptRun(res.run_id);
      const skipped = new Set((res.skipped || []).map((s) => (typeof s === "string" ? s : s.name)));
      job.rows.forEach((r) => {
        r.phase = skipped.has(r.name) ? "failed" : "sent";
        if (r.phase === "failed") r.err = "server skipped this file";
      });
      if (!firstSentAt) firstSentAt = Date.now();
      startPolling();
    } catch (e) {
      job.rows.forEach((r) => { r.phase = "failed"; r.err = e.message; });
    }
    render(job.room);
    uploading = false;
    pump();
  }

  function retry(room, row) {
    row.phase = "queued";
    queue.push({ room, rows: [row] });
    render(room);
    pump();
  }

  // ---------- progress ----------
  // What a file's row says: {text, cls, bar (0 to 1, while uploading), busy (the server is working on it)}.
  function fileProgress(r) {
    if (r.phase === "queued") return { text: "waiting", cls: "" , bar: 0 };
    if (r.phase === "uploading") return { text: `uploading ${Math.round(r.pct * 100)}%`, cls: "", bar: r.pct };
    if (r.phase === "failed") return { text: r.err || "failed", cls: "failed" };
    const s = r.server || {};
    // "seen", not "items": the count includes fixtures and small things that end up in boxes
    if (s.perceive === "done") return { text: `done · ${s.items ?? "?"} seen${s.seconds != null ? ` · ${Math.round(s.seconds)} s` : ""}`, cls: "done" };
    if (s.perceive === "failed") return { text: "couldn't read this file" + (s.error ? `: ${s.error.slice(0, 80)}` : ""), cls: "failed" };
    if (s.perceive === "running") return { text: r.kind === "video" ? "watching and listening…" : "looking…", cls: "", busy: true };
    if (s.intake === "done") return { text: "received, queued", cls: "", busy: true };
    return { text: "received", cls: "", busy: true };
  }

  function render(room) {
    const ul = $(".files", room.el);
    ul.innerHTML = "";
    room.files.forEach((r) => {
      const st = fileProgress(r);
      const li = document.createElement("li");
      li.innerHTML = `<span aria-hidden="true">${r.kind === "video" ? "🎥" : "📷"}</span>
        <span class="name"></span><span class="state ${st.cls}"></span>`;
      $(".name", li).textContent = r.name;
      $(".state", li).textContent = st.text;
      if (r.phase === "failed") {
        const b = document.createElement("button");
        b.className = "btn link"; b.type = "button"; b.textContent = "Retry";
        b.style.gridColumn = "2 / 4"; b.style.justifySelf = "end";
        b.onclick = () => retry(room, r);
        li.appendChild(b);
      } else if (r.phase === "uploading" || st.busy) {
        const bar = document.createElement("div");
        bar.className = "bar" + (st.busy ? " busy" : "");
        bar.innerHTML = "<i></i>";
        if (!st.busy) bar.firstChild.style.width = Math.round((st.bar || 0) * 100) + "%";
        li.appendChild(bar);
      }
      ul.appendChild(li);
    });
    if (room.waiting) { // see setWaiting
      const li = document.createElement("li");
      li.innerHTML = `<span aria-hidden="true">⏳</span><span class="name">Getting your files from the phone…</span>
        <span class="state">a few seconds</span><div class="bar busy"><i></i></div>`;
      ul.appendChild(li);
    }
  }

  function allFinished(run) {
    const rows = rooms.flatMap((r) => r.files);
    if (queue.length || uploading) return false;
    const pending = rows.some((r) => r.phase === "sent" && !["done", "failed"].includes((r.server || {}).perceive));
    const stage = run && run.status && run.status.stage;
    return !pending && (stage === "done" || stage === "failed");
  }

  async function poll() {
    pollTimer = null;
    if (!runId || document.hidden) return;
    polling = true;
    try {
      const run = await api.getRun(runId);
      lastRun = run;
      const files = (run.status && run.status.files) || {};
      rooms.forEach((room) => {
        room.files.forEach((r) => { if (r.phase === "sent") r.server = files[r.name] || r.server; });
        render(room);
      });
      updateFooter(run);
      renderLiveQ(run.inventory);
      if (allFinished(run)) { polling = false; return; } // stop until the next upload
    } catch (e) {
      $("#found").innerHTML = `<b>Can't reach the server</b><span class="error"></span>`;
      $("#found .error").textContent = e.message;
    }
    polling = false;
    pollTimer = setTimeout(poll, 1000);
  }

  // One poll loop at most: an upload that finishes while a poll is waiting must not start a second.
  function startPolling() {
    if (!pollTimer && !polling) pollTimer = setTimeout(poll, 300);
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden && runId) startPolling(); });

  const plural = (k, word) => `${k} ${word}${k === 1 ? "" : word === "box" ? "es" : "s"}`;

  // What an inventory holds, in words: "12 items + 4 boxes". Boxes count too: a shelf of small decor
  // is 0 items and 4 boxes, and "0 items" alone reads as "found nothing" (FAILURES.md 12:45).
  function foundText(inv) {
    const n = inv.totals.item_count;
    const boxes = totalBoxes(inv);
    if (n && boxes) return `${plural(n, "item")} + ${plural(boxes, "box")}`;
    return boxes ? `${plural(boxes, "box")} of small things` : plural(n, "item");
  }

  function updateFooter(run) {
    const btn = $("#review-btn");
    const plan = $("#plan-btn");
    const inv = run.inventory;
    const done = allFinished(run);
    btn.href = link("review.html", { run_id: runId });
    plan.href = link("index.html", { run_id: runId });
    if (!inv) {
      $("#found").innerHTML = "<b>Looking…</b>Items appear as each file finishes";
      [btn, plan].forEach((b) => { b.setAttribute("aria-disabled", "true"); b.classList.remove("primary"); });
      btn.textContent = "Check list";
      return;
    }
    const nRooms = inv.rooms.length;
    [btn, plan].forEach((b) => b.removeAttribute("aria-disabled"));
    btn.textContent = "Check list";
    const slow = firstSentAt && Date.now() - firstSentAt > 60000;
    plan.classList.toggle("primary", done || slow);
    const failed = Object.values(run.status.files || {}).filter((f) => f.perceive === "failed").length;
    const head = done ? `${foundText(inv)} in ${plural(nRooms, "room")}` : `${foundText(inv)} found so far`;
    const sub = done ? (failed ? `${failed} file(s) couldn't be read` : "Ready to check")
                     : slow ? "Still working; you can review what's ready" : "Still looking…";
    $("#found").innerHTML = "<b></b><span></span>";
    $("#found b").textContent = head;
    $("#found span").textContent = sub;
  }

  // ---------- the top question, answered right here (decision 2026-11-21 11:38) ----------
  function renderLiveQ(inv, force) {
    const host = $("#live-q");
    if (!inv) return;
    const { open } = Q.pick(inv.questions, 1);
    const q = open[0];
    const key = q ? q.id + (busyQ.has(q.id) ? ":busy" : "") : "none:" + answeredHere;
    if (key === shownQ && !force) return;
    if (!force && host.contains(document.activeElement) && document.activeElement.tagName === "INPUT") return; // typing
    shownQ = key;
    if (!q) {
      host.innerHTML = answeredHere ? `<p class="small muted">✓ Thanks, that's all the questions for now.</p>` : "";
      return;
    }
    host.innerHTML = `<h2>${answeredHere ? "Next question" : "Quick question"}</h2>` +
      Q.cardHtml(q, { busy: busyQ.has(q.id), inv, thumbHtml: (ev, label) => thumbHtml(runId, inv, ev, label) });
    Q.bind(host, inv.questions, { onAnswer: answerLive });
    if (!qScrolled) { qScrolled = true; host.scrollIntoView({ behavior: "smooth", block: "center" }); }
  }

  async function answerLive(q, value) {
    busyQ.add(q.id);
    renderLiveQ(lastRun && lastRun.inventory);
    try {
      const inv = await api.answer(runId, q.id, value);
      busyQ.delete(q.id);
      answeredHere++;
      lastRun = { ...(lastRun || {}), inventory: inv };
      updateFooter(lastRun);
      renderLiveQ(inv, true);
    } catch (e) {
      busyQ.delete(q.id);
      renderLiveQ(lastRun && lastRun.inventory, true);
      const err = document.createElement("p");
      err.className = "error";
      err.textContent = `Couldn't save that answer: ${e.message}`;
      $("#live-q").appendChild(err);
    }
  }

  // ---------- coming back to a move ----------
  // Take `id` as this page's move: remember it, and put it in the address so a reload returns to it.
  function adoptRun(id) {
    runId = id;
    window.PIU.rememberRun(id);
    try { history.replaceState(null, "", link("capture.html", { run_id: id })); } catch (e) { /* file:// */ }
    $("#footer").classList.remove("hidden");
    $("#new-move").classList.remove("hidden");
    $("#resume").classList.add("hidden");
  }

  function notice(text) {
    $("#notice").textContent = text || "";
    $("#notice").classList.toggle("hidden", !text);
  }

  // Rebuild the room cards from GET /runs: `rooms` gives the names, `status.files` each file's state.
  // These rows have no File object; they are already on the server, so they never need a retry.
  function showRun(run) {
    const byRoom = {};
    Object.entries((run.status && run.status.files) || {}).forEach(([name, st]) => {
      usedNames.add(name.toLowerCase());
      (byRoom[st.room_id] = byRoom[st.room_id] || []).push({
        name, file: null, kind: st.kind === "video" ? "video" : "image", phase: "sent", pct: 0, server: st, err: "" });
    });
    (run.rooms || []).forEach((r) => {
      const room = addRoom();
      lockRoom(room, r.name);
      room.files = byRoom[r.id] || [];
      render(room);
    });
  }

  // ?run_id= in the address: load that move and carry on with it. Nothing can be picked until it has
  // loaded, because new file names must not repeat ones the run already has.
  async function resume(id) {
    notice("Loading your move…");
    let run;
    try {
      run = await api.getRun(id);
    } catch (e) {
      if (e.status === 404) return startFresh("That move isn't on this server any more, so this is a new one.");
      notice(`Can't reach the server (${e.message}). Trying again…`);
      setTimeout(() => resume(id), 2000);
      return;
    }
    notice("");
    showRun(run);
    adoptRun(id);
    addRoom();
    lastRun = run;
    updateFooter(run);
    renderLiveQ(run.inventory);
    startPolling();
  }

  function startFresh(why) {
    window.PIU.forgetRun();
    try { history.replaceState(null, "", link("capture.html")); } catch (e) { /* file:// */ }
    notice(why);
    addRoom();
  }

  // No run in the address, but this browser was in a move earlier: offer it, without getting in the
  // way. Picking files instead starts a new move and hides the offer.
  async function offerLastRun(id) {
    let run;
    try {
      run = await api.getRun(id);
    } catch (e) {
      if (e.status === 404) window.PIU.forgetRun();
      return;
    }
    if (runId) return; // an upload got there first
    const names = (run.rooms || []).map((r) => r.name);
    $("#resume-what").textContent = [names.slice(0, 3).join(", ") + (names.length > 3 ? "…" : ""),
      run.inventory ? foundText(run.inventory) : "still being listed"].filter(Boolean).join(" · ");
    $("#resume-yes").href = link("capture.html", { run_id: id });
    $("#resume").classList.remove("hidden");
  }
  $("#resume-no").addEventListener("click", () => $("#resume").classList.add("hidden"));

  // ---------- QR code for opening this page on a phone (laptop only) ----------
  function setupQr() {
    if (!matchMedia("(min-width: 900px) and (hover: hover)").matches) return;
    // Without the run id: everyone who scans the code starts their own move.
    const here = new URL(location.href);
    here.searchParams.delete("run_id");
    const url = here.href;
    $("#qr-url").textContent = url;
    if (/^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname)) {
      $("#qr").outerHTML = `<p class="small">This page is open on <b>localhost</b>, which a phone can't reach. Open it with the laptop's LAN address or the tunnel address to get a QR code.</p>`;
      return;
    }
    const s = document.createElement("script");
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js";
    s.onload = () => new window.QRCode($("#qr"), { text: url, width: 320, height: 320, correctLevel: window.QRCode.CorrectLevel.M });
    s.onerror = () => ($("#qr").outerHTML = "<p class='small muted'>QR library didn't load (offline?). Type the address below on the phone.</p>");
    document.head.appendChild(s);
  }

  $("#add-room").addEventListener("click", () => {
    const r = addRoom();
    const input = $(".room-name", r.el);
    input.focus();
    input.select();
  });
  $("#new-move").addEventListener("click", () => {
    if (!confirm("Start a new move? This page forgets the current one (the server keeps it).")) return;
    window.PIU.forgetRun();
    location.href = link("capture.html");
  });

  setupQr();
  const wanted = params.get("run_id");
  if (wanted) {
    resume(wanted);
  } else {
    addRoom();
    const last = window.PIU.lastRun();
    if (last) offerLastRun(last);
  }
})();
