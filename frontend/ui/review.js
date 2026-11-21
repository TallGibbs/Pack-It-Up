// Pack It Up: the review page (review.html). Totals, question cards, the item list with quantity
// and Move / Stays / Sell / Toss, and "Add an item". Needs ui/api.js and ui/questions.js first.
(function () {
  "use strict";
  const { api, link, MOCK, params, $, esc, thumbHtml, boxCount, totalBoxes } = window.PIU;
  const fmt = (n, d = 0) => (n == null ? "–" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d }));
  const mmss = (t) => (t == null ? "" : `${Math.floor(t / 60)}:${String(Math.round(t % 60)).padStart(2, "0")}`);
  const MAX_QUESTIONS = 5;
  const OUT = new Set(["sell", "donate", "trash", "stays"]);
  const SEGS = [["keep", "Move"], ["stays", "Stays"], ["sell", "Sell"], ["trash", "Toss"]];
  const SIZE_SRC = { catalog: "catalog", vision_estimate: "estimate", speech: "you said", category_default: "default", user: "you typed" };
  const WT_SRC = { catalog: "catalog", vision_estimate: "estimate", density: "by material", speech: "you said" };

  if (MOCK) $("#mock-banner").classList.remove("hidden");

  const runId = params.get("run_id") || (MOCK ? window.PIU_MOCK.DEMO_RUN : window.PIU.lastRun());
  let inv = null;
  let partial = false;
  const pendingQty = {};    // itemId -> qty shown while the PATCH is debounced or in flight
  const qtyTimers = {};
  const saveState = {};     // itemId -> "saving" | {error, retry}; absent when the row is saved
  const reopened = new Set();
  const busyQ = new Set();
  let inFlight = 0;
  let pollTimer = null;
  let lastTotals = {};
  let answeredOpen = false; // the folded list of answered questions stays as the user left it across re-renders

  // Every link back to filming (steps line, top button, bottom button) returns to the same move, not a new one.
  document.querySelectorAll(".to-capture").forEach((a) => (a.href = link("capture.html", { run_id: runId })));

  if (!runId) {
    $("#sub").textContent = "No move yet.";
    $("#rooms").innerHTML = `<p><a class="btn primary" href="${esc(link("capture.html"))}">Film your rooms first</a></p>`;
    return;
  }
  window.PIU.rememberRun(runId);
  $("#handoff").href = link("index.html", { run_id: runId });
  $("#step-pack").href = link("index.html", { run_id: runId }); // the steps line goes forward as well as back

  // ---------- data ----------
  async function load() {
    pollTimer = null;
    let run = null;
    try {
      run = await api.getRun(runId);
      $("#err").classList.add("hidden");
    } catch (e) {
      showError(e.status === 404 ? `No move called ${runId} on this server.` : `Can't reach the server: ${e.message}`);
      if (e.status === 404) return;
    }
    if (run && !run.inventory) {
      $("#sub").textContent = "Still looking at your photos and clips…";
      partial = true;
    } else if (run && !inFlight) {
      partial = !!run.partial;
      try { setInventory(run.inventory); } catch (e) { console.error(e); showError(`Display error: ${e.message}`); }
    }
    if (partial && !document.hidden) pollTimer = setTimeout(load, 2000);
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden && partial && !pollTimer) load(); });

  function setInventory(next) {
    inv = next;
    render();
  }

  function showError(msg) {
    const el = $("#err");
    el.textContent = msg;
    el.classList.remove("hidden");
  }

  async function send(itemId, changes) {
    saveState[itemId] = "saving";
    renderItem(itemId);
    inFlight++;
    try {
      const next = await api.patchItem(runId, itemId, changes);
      delete saveState[itemId];
      if ("quantity" in changes && pendingQty[itemId] === changes.quantity) delete pendingQty[itemId];
      inFlight--;
      setInventory(next);
    } catch (e) {
      inFlight--;
      delete pendingQty[itemId];
      saveState[itemId] = { error: e.message, retry: () => send(itemId, changes) };
      render();
    }
  }

  function stepQty(itemId, delta) {
    const it = findItem(itemId);
    if (!it) return;
    const cur = pendingQty[itemId] ?? it.quantity;
    const next = Math.max(0, cur + delta);
    if (next === cur) return;
    pendingQty[itemId] = next;
    renderItem(itemId);
    clearTimeout(qtyTimers[itemId]);
    qtyTimers[itemId] = setTimeout(() => send(itemId, { quantity: next }), 400);
  }

  function setDisposition(itemId, d) {
    const it = findItem(itemId);
    if (!it || it.disposition === d) return;
    it.disposition = d; // optimistic; the server's reply replaces it
    renderItem(itemId);
    send(itemId, { disposition: d });
  }

  async function answer(q, value) {
    busyQ.add(q.id);
    renderQuestions();
    inFlight++;
    try {
      const next = await api.answer(runId, q.id, value);
      reopened.delete(q.id);
      busyQ.delete(q.id);
      inFlight--;
      setInventory(next);
    } catch (e) {
      busyQ.delete(q.id);
      inFlight--;
      renderQuestions();
      showError(`Couldn't save that answer: ${e.message}`);
    }
  }

  // ---------- lookups ----------
  const allItems = () => (inv ? inv.rooms.flatMap((r) => r.items) : []);
  const findItem = (id) => allItems().find((i) => i.id === id);

  const thumb = (ev, label) => thumbHtml(runId, inv, ev, label, { lazy: true });

  // ---------- render ----------
  function render() {
    if (!inv) return;
    renderTotals();
    renderQuestions();
    renderRooms();
    renderFooter();
    const nRooms = inv.rooms.length;
    $("#sub").textContent = partial
      ? "Still working on some files; more items may appear."
      : `${nRooms} room${nRooms > 1 ? "s" : ""}. Fix anything wrong, then plan the truck.`;
  }

  function renderTotals() {
    const t = inv.totals || {};
    const boxes = totalBoxes(inv);
    const vals = { "t-items": fmt(t.item_count), "t-vol": fmt(t.volume_cuft), "t-wt": fmt(t.weight_lb), "t-boxes": boxes ? "+" + boxes : "0" };
    Object.entries(vals).forEach(([id, v]) => {
      const el = document.getElementById(id);
      if (lastTotals[id] != null && lastTotals[id] !== v) {
        el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
      }
      el.textContent = v;
      lastTotals[id] = v;
    });
  }

  // Question cards come from ui/questions.js (shared with capture.html).
  const Q = window.PIU_Q;
  const isOpen = (q) => Q.isOpen(q) && !Q.MODEL_ONLY.has(q.kind);

  function renderQuestions() {
    const host = $("#questions");
    const { open, more, answered } = Q.pick(inv.questions, MAX_QUESTIONS, reopened);
    if (!open.length && !answered.length) { host.innerHTML = ""; return; }
    let html = open.length ? `<h2>${open.length === 1 ? "One question" : `${open.length} quick questions`}</h2>` : "";
    html += open.map((q) => Q.cardHtml(q, { busy: busyQ.has(q.id), thumbHtml: (ev, label) => thumb(ev, label), inv })).join("");
    if (more > 0) html += `<p class="small muted">${more} smaller question${more > 1 ? "s" : ""} not shown; best guesses used.</p>`;
    if (answered.length) {
      html += `<details class="answered-list"${answeredOpen ? " open" : ""}><summary>${answered.length} answered · see or change</summary>` +
        answered.map(Q.answeredHtml).join("") + `</details>`;
    }
    host.innerHTML = html;
    const folded = host.querySelector(".answered-list");
    if (folded) folded.addEventListener("toggle", () => (answeredOpen = folded.open));
    Q.bind(host, inv.questions, { onAnswer: answer, onReopen: (q) => { reopened.add(q.id); renderQuestions(); } });
  }

  // One sentence can set several fields ("the shelf is full of books": contents and fullness); show it once.
  function uniqQuotes(list) {
    const seen = new Set();
    return (list || []).filter((x) => x && x.quote && !seen.has(x.quote) && seen.add(x.quote));
  }

  function itemHtml(it) {
    const qty = pendingQty[it.id] ?? it.quantity;
    const sz = it.size || {};
    const d = sz.dims_in || [];
    const dims = d.length === 3 ? `${fmt(d[0])} × ${fmt(d[1])} × ${fmt(d[2])} in` : "size unknown";
    const badges = [];
    if (it.source === "user_added") badges.push(`<span class="badge heard">added by you</span>`);
    if (it.heard_only) badges.push(`<span class="badge heard">🎙️ heard, not filmed</span>`);
    if (it.partially_visible) badges.push(`<span class="badge">partly hidden</span>`);
    if (it.contents_unknown) badges.push(`<span class="badge">contents unknown, assumed empty</span>`);
    if (it.stack_count > 1) badges.push(`<span class="badge">stack of ${esc(it.stack_count)}</span>`);
    if (it.fragile) badges.push(`<span class="badge">fragile</span>`);
    if (it.two_person) badges.push(`<span class="badge">two-person lift</span>`);
    if (it.must_stay_upright) badges.push(`<span class="badge">keep upright</span>`);
    if (it.disassemble) badges.push(`<span class="badge">take apart</span>`);
    const said = uniqQuotes(it.set_by_speech).map((s) =>
      `<div class="said">You said <q>${esc(s.quote)}</q> <span class="muted">· ${esc(mmss(s.timestamp_s))} in ${esc(s.source)}</span></div>`).join("");
    const disp = it.disposition || "undecided";
    // Move / Stays / Sell / Toss (decision 2026-11-21 11:38). Undecided counts as Move; any other
    // server value (e.g. an older "donate") shows as a badge until a segment is tapped.
    if (!SEGS.some(([v]) => v === disp) && disp !== "undecided") badges.unshift(`<span class="badge heard">${esc(disp)}</span>`);
    const seg = SEGS.map(([v, name]) => `<button type="button" data-disp="${v}" aria-pressed="${disp === v}"
        class="${disp === "undecided" && v === "keep" ? "implied" : ""}">${name}</button>`).join("");
    const st = saveState[it.id];
    const status = st === "saving" ? `<div class="saving">Saving…</div>`
      : st && st.error ? `<div class="saving error"><button class="btn link" type="button" data-retry>Didn't save (${esc(st.error)}). Tap to retry</button></div>` : "";
    return `<div class="card item${OUT.has(disp) ? " out" : ""}" data-item="${esc(it.id)}">
      ${thumb(it.evidence, it.label)}
      <div>
        <div class="label">${esc(it.label)}</div>
        <div class="meta"><b>${esc(dims)}</b> · ${esc(SIZE_SRC[sz.size_source] || sz.size_source || "")}</div>
        <div class="meta"><b>${fmt(sz.weight_lb_each)} lb</b>${qty > 1 ? " each" : ""} · ${esc(WT_SRC[sz.weight_source] || sz.weight_source || "")}
          · ${fmt(sz.volume_cuft_total, 1)} cu ft</div>
        ${badges.length ? `<div class="badges">${badges.join("")}</div>` : ""}
      </div>
      ${said}
      <div class="controls">
        <div class="stepper" role="group" aria-label="Quantity">
          <button type="button" data-step="-1" aria-label="One fewer">−</button>
          <output>${esc(qty)}</output>
          <button type="button" data-step="1" aria-label="One more">+</button>
        </div>
        <div class="seg" role="group" aria-label="What happens to it">${seg}</div>
      </div>
      ${status}
    </div>`;
  }

  function bindItem(el) {
    const id = el.dataset.item;
    el.querySelectorAll("[data-step]").forEach((b) => b.addEventListener("click", () => stepQty(id, Number(b.dataset.step))));
    el.querySelectorAll("[data-disp]").forEach((b) => b.addEventListener("click", () => setDisposition(id, b.dataset.disp)));
    const r = el.querySelector("[data-retry]");
    if (r) r.addEventListener("click", () => saveState[id].retry());
  }

  function renderItem(id) {
    const el = document.querySelector(`[data-item="${CSS.escape(id)}"]`);
    const it = findItem(id);
    if (!el || !it) return;
    const tmp = document.createElement("div");
    tmp.innerHTML = itemHtml(it);
    const fresh = tmp.firstElementChild;
    // keep the loaded thumbnail instead of re-fetching it
    fresh.replaceChild(el.querySelector(".thumb"), fresh.querySelector(".thumb"));
    el.replaceWith(fresh);
    bindItem(fresh);
  }

  function renderRooms() {
    const host = $("#rooms");
    let html = "";
    inv.rooms.forEach((room) => {
      const items = [...room.items].sort((a, b) =>
        (OUT.has(a.disposition) - OUT.has(b.disposition)) || ((b.size?.volume_cuft_total || 0) - (a.size?.volume_cuft_total || 0)));
      const t = room.totals || {};
      html += `<div class="room-h"><h2>${esc(room.room.name)}</h2><span>${fmt(t.item_count)} items · ${fmt(t.volume_cuft)} cu ft</span></div>`;
      html += items.map(itemHtml).join("") || `<p class="muted">Nothing found yet.</p>`;
      html += `<p class="add-row"><button class="btn block" type="button" data-add-room="${esc(room.room.id)}">+ Add an item to ${esc(room.room.name)}</button></p>`;
      const conts = room.containers || [];
      if (conts.length) {
        html += `<div class="card containers"><b>Packed into boxes</b><ul style="padding-left:18px;margin:6px 0 0">` +
          conts.map((c) => {
            const n = boxCount(c);
            const what = c.items && c.items.length ? c.items.join(", ") : c.contents;
            const full = c.contents_unknown || c.fullness === "not_visible" ? "closed: contents unknown, assumed empty" : c.fullness;
            const said = uniqQuotes(c.set_by_speech).map((x) => ` <span class="said-inline">you said <q>${esc(x.quote)}</q></span>`).join("");
            return `<li>${esc(c.label)}: ${esc([what, full].filter(Boolean).join(", "))}${n ? ` · <b>about ${n} box${n > 1 ? "es" : ""}</b>` : ""}${said}</li>`;
          }).join("") + `</ul></div>`;
      }
      const lo = room.left_out || {};
      const kinds = Object.entries(lo.personal_belonging_kinds || {}).sort((a, b) => b[1] - a[1])
        .map(([k, n]) => `${n} ${k}${n > 1 && !/s$/.test(k) ? "s" : ""}`).join(", ");
      if (lo.fixtures || lo.personal_belongings) {
        html += `<p class="leftout">Left out: ${fmt(lo.fixtures)} fixture${lo.fixtures === 1 ? "" : "s"}` +
          (room.fixtures && room.fixtures.length ? ` (${esc(room.fixtures.map((f) => f.label).slice(0, 3).join(", "))}${room.fixtures.length > 3 ? "…" : ""})` : "") +
          (lo.personal_belongings ? `, ${fmt(lo.personal_belongings)} personal belongings${kinds ? ` (${esc(kinds)})` : ""}` : "") + `.</p>`;
      }
    });
    host.innerHTML = html;
    host.querySelectorAll("[data-item]").forEach(bindItem);
    host.querySelectorAll("[data-add-room]").forEach((b) => b.addEventListener("click", () =>
      openAdd(inv.rooms.find((r) => r.room.id === b.dataset.addRoom).room)));
  }

  // ---------- add an item the camera didn't see ----------
  // The sheet is a <dialog> outside #rooms, so a poll re-rendering the list doesn't disturb it.
  // The server sizes the item (catalog size, or the typed one) and returns the whole inventory.
  const add = { room: null, catalog: null, pick: null, qty: 1 }; // pick: a catalog id, "custom", or null
  const dlg = $("#add-dialog");

  function addError(msg) {
    $("#add-err").textContent = msg || "";
    $("#add-err").classList.toggle("hidden", !msg);
  }

  async function openAdd(room) {
    Object.assign(add, { room, pick: null, qty: 1 });
    $("#add-room-name").textContent = `to ${room.name}`;
    ["#add-search", "#add-name", "#add-l", "#add-w", "#add-h"].forEach((s) => ($(s).value = ""));
    addError("");
    renderAdd();
    dlg.showModal();
    if (add.catalog) return;
    try {
      add.catalog = await api.getCatalog();
    } catch (e) {
      add.catalog = [];
      addError(`Couldn't load the item list (${e.message}). "Not in the list" still works.`);
    }
    renderAdd();
  }

  function renderAdd() {
    const q = $("#add-search").value.trim().toLowerCase();
    const row = (id, name, note) => `<button type="button" class="pickrow" data-pick="${esc(id)}" aria-pressed="${add.pick === id}">
        <span>${esc(name)}</span><small>${esc(note)}</small></button>`;
    let html = "";
    if (!add.catalog) {
      html = `<p class="muted small">Loading the list…</p>`;
    } else {
      const hits = add.catalog.filter((c) => !q || `${c.name} ${c.category}`.toLowerCase().includes(q));
      const byCategory = {};
      hits.forEach((c) => (byCategory[c.category] = byCategory[c.category] || []).push(c));
      html = Object.keys(byCategory).sort().map((cat) => `<div class="kind">${esc(cat)}</div>` +
        byCategory[cat].map((c) => row(c.id, c.name, c.dims_in.map((d) => fmt(d)).join(" × ") + " in")).join("")).join("");
      if (q && !hits.length) html = `<p class="muted small">Nothing in the list matches “${esc(q)}”.</p>`;
    }
    html += row("custom", "Not in the list", "type a name and size");
    $("#add-list").innerHTML = html;
    $("#add-list").querySelectorAll("[data-pick]").forEach((b) => b.addEventListener("click", () => {
      add.pick = b.dataset.pick;
      addError("");
      renderAdd();
      if (add.pick === "custom") { if (q && !$("#add-name").value) $("#add-name").value = $("#add-search").value.trim(); $("#add-name").focus(); }
    }));
    $("#add-custom").classList.toggle("hidden", add.pick !== "custom");
    $("#add-qty").textContent = add.qty;
    const picked = (add.catalog || []).find((c) => c.id === add.pick);
    $("#add-go").disabled = !add.pick;
    $("#add-go").textContent = picked ? `Add ${picked.name}` : "Add";
  }

  async function submitAdd() {
    if (!add.pick) return;
    const body = { room: add.room.id, quantity: add.qty };
    if (add.pick === "custom") {
      const label = $("#add-name").value.trim();
      const dims = ["#add-l", "#add-w", "#add-h"].map((s) => Number($(s).value));
      if (!label || dims.some((d) => !(d > 0 && d <= 240))) {
        return addError("Give it a name, and a length, width and height in inches (up to 240).");
      }
      Object.assign(body, { label, dims_in: dims });
    } else {
      body.catalog_id = add.pick;
    }
    const before = new Set(allItems().map((i) => i.id));
    $("#add-go").disabled = true;
    inFlight++;
    try {
      const next = await api.addItem(runId, body);
      inFlight--;
      dlg.close();
      setInventory(next);
      const fresh = allItems().find((i) => !before.has(i.id));
      const el = fresh && document.querySelector(`[data-item="${CSS.escape(fresh.id)}"]`);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (e) {
      inFlight--;
      $("#add-go").disabled = false;
      addError(`Couldn't add it: ${e.message}`);
    }
  }

  $("#add-search").addEventListener("input", renderAdd);
  $("#add-minus").addEventListener("click", () => { add.qty = Math.max(1, add.qty - 1); renderAdd(); });
  $("#add-plus").addEventListener("click", () => { add.qty = Math.min(500, add.qty + 1); renderAdd(); });
  $("#add-cancel").addEventListener("click", () => dlg.close());
  $("#add-form").addEventListener("submit", (e) => { e.preventDefault(); submitAdd(); });

  function renderFooter() {
    const t = inv.totals || {};
    const open = (inv.questions || []).filter(isOpen).length;
    const btn = $("#handoff");
    btn.removeAttribute("aria-disabled");
    $("#handoff-note").innerHTML = `<b>${fmt(t.item_count)} items · ${fmt(t.volume_cuft)} cu ft</b>` +
      (open ? `${open} question${open > 1 ? "s" : ""} open; guesses used` : partial ? "Some files still processing" : "Edits carry over to the plan");
  }

  load();
})();
