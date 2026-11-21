// In-browser mock of the Track A routes, for building the pages without a server or key.
// Loaded by capture.html and review.html; used when the URL has ?mock=1.
// Fixture: mock/inventory.json. State lives in sessionStorage so it survives the capture -> review hop.
(function () {
  "use strict";
  const KEY = "piu_mock_v1";
  const DEMO_RUN = "mock-demo";
  let fixture = null;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const clone = (x) => JSON.parse(JSON.stringify(x));
  const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "room";

  function load() {
    try { return JSON.parse(sessionStorage.getItem(KEY)) || { runs: {} }; } catch (e) { return memory; }
  }
  let memory = { runs: {} };
  function save(state) {
    memory = state;
    try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* private mode: memory only */ }
  }

  async function getFixture() {
    if (!fixture) {
      const res = await fetch("mock/inventory.json");
      if (!res.ok) throw new Error("mock fixture missing: serve frontend/ over http (python -m http.server)");
      fixture = await res.json();
    }
    return fixture;
  }

  function newRun(id) {
    return { id, created: Date.now(), rooms: [], itemEdits: {}, contEdits: {}, answers: {} };
  }

  // Seconds after upload at which a file finishes "perceive": photos quick, clips slower.
  function doneAfter(file, i) {
    return 1.5 + i * 1.1 + (file.kind === "video" ? 3.5 : 0);
  }

  function fileStatus(file, i, now) {
    const t = (now - file.uploadedAt) / 1000;
    const s = { room_id: file.room_id, kind: file.kind, intake: t > 0.4 ? "done" : "running" };
    if (t > 0.6) s.perceive = t >= doneAfter(file, i) ? "done" : "running";
    if (s.perceive === "done") {
      s.items = 4 + ((file.name.length * 7 + i * 5) % 15);
      s.seconds = Math.round(doneAfter(file, i) * 10) / 10;
    }
    return s;
  }

  function applyItemChanges(item, ch) {
    Object.assign(item, ch);
    const sz = item.size;
    sz.volume_cuft_total = Math.round(sz.volume_cuft_each * item.quantity * 100) / 100;
    sz.weight_lb_total = Math.round(sz.weight_lb_each * item.quantity * 10) / 10;
  }

  const MOVING = (d) => d === "keep" || d === "undecided";
  const r1 = (x) => Math.round(x * 10) / 10;

  function build(run, now) {
    const fx = fixture;
    const status = { stage: "created", files: {}, errors: [], perceive_failed: [] };
    const rooms = [];
    const questions = [];
    let allDone = run.rooms.length > 0;
    let lastDone = 0;

    run.rooms.forEach((room, ri) => {
      const src = fx.rooms[room.fixture % fx.rooms.length];
      const pre = room.id + "-";
      let done = 0;
      room.files.forEach((f, i) => {
        const st = fileStatus(f, i, now);
        status.files[f.name] = st;
        if (st.perceive === "done") {
          done++;
          lastDone = Math.max(lastDone, f.uploadedAt + doneAfter(f, i) * 1000);
        }
      });
      if (done < room.files.length) allDone = false;
      if (!done) return;

      // Map the fixture's file names onto the names actually uploaded to this room.
      const fmap = {};
      src.files.forEach((n, i) => (fmap[n] = room.files[i % room.files.length].name));
      const ren = (ev) => ev && { ...ev, source: fmap[ev.source] || ev.source };

      const frac = done / room.files.length;
      const shown = Math.max(1, Math.ceil(src.items.length * frac));
      const items = [];
      src.items.slice(0, shown).forEach((it0) => {
        const it = clone(it0);
        it.id = pre + it.id;
        it.evidence = ren(it.evidence);
        it.set_by_speech = (it.set_by_speech || []).map((s) => ({ ...s, source: fmap[s.source] || s.source }));
        it.also_seen_in = (it.also_seen_in || []).map((s) => s.replace(/^[^@]+/, (n) => fmap[n] || n));
        const ch = run.itemEdits[it.id];
        if (ch && ch.remove) return;
        if (ch) applyItemChanges(it, ch);
        items.push(it);
      });
      const containers = frac < 1 ? [] : src.containers.map((c0) => {
        const c = clone(c0);
        c.id = pre + c.id;
        c.evidence = ren(c.evidence);
        Object.assign(c, run.contEdits[c.id] || {});
        return c;
      });
      const keep = items.filter((i) => MOVING(i.disposition));
      rooms.push({
        room: { id: room.id, name: room.name },
        files: room.files.map((f) => f.name),
        items, containers,
        fixtures: frac < 1 ? [] : src.fixtures,
        left_out: frac < 1 ? { fixtures: 0, personal_belongings: 0, personal_belonging_kinds: {} } : src.left_out,
        totals: {
          item_count: keep.reduce((a, i) => a + i.quantity, 0),
          item_lines: keep.length,
          volume_cuft: r1(keep.reduce((a, i) => a + i.size.volume_cuft_total, 0)),
          weight_lb: r1(keep.reduce((a, i) => a + i.size.weight_lb_total, 0)),
          boxed_volume_cuft: r1(containers.reduce((a, c) => a + (c.est_volume_cuft || 0), 0)),
        },
      });

      // Questions arrive once every file in the room is done (stage 5 runs last).
      if (frac === 1 && now - lastDone > 1000) {
        fx.questions.filter((q) => q.room_id === src.room.id).forEach((q0) => {
          const q = clone(q0);
          delete q.mock_effects;
          q.id = pre + q.id;
          q.room_id = room.id;
          // refers_to is an item id, a container label or the room id, as in backend/ingest/gaps.py
          if (src.items.some((i) => i.id === q.refers_to)) {
            q.refers_to = pre + q.refers_to;
            if (!items.some((i) => i.id === q.refers_to)) return; // item removed
          } else if (q.refers_to === src.room.id) q.refers_to = room.id;
          if (run.answers[q.id] != null) {
            Object.assign(q, { status: "answered", answer: run.answers[q.id], answered_by: "user" });
          }
          questions.push(q);
        });
      }
    });

    const anyFile = Object.values(status.files);
    if (!anyFile.length) status.stage = "created";
    else if (!allDone) status.stage = anyFile.some((f) => f.perceive) ? "perceive" : "intake_done";
    else status.stage = now - lastDone > 1000 ? "done" : "questions";
    status.updated = new Date(now).toISOString().slice(0, 19);

    const roomList = run.rooms.map((r) => ({ id: r.id, name: r.name })); // as GET /runs: every room, in upload order
    if (!rooms.length) return { run_id: run.id, rooms: roomList, status };
    const sum = (k) => r1(rooms.reduce((a, r) => a + r.totals[k], 0));
    const inventory = {
      schema_version: "inventory_v2", run_id: run.id, generated: status.updated, rooms,
      totals: { item_count: sum("item_count"), volume_cuft: sum("volume_cuft"), weight_lb: sum("weight_lb"),
                boxed_volume_cuft: sum("boxed_volume_cuft") },
      questions, answers_applied: [],
    };
    return { run_id: run.id, rooms: roomList, status, inventory, partial: status.stage !== "done",
             questions: questions.filter((q) => q.status === "open") };
  }

  async function withRun(runId, fn) {
    await getFixture();
    const state = load();
    if (runId === DEMO_RUN && !state.runs[DEMO_RUN]) seedDemo(state);
    const run = state.runs[runId];
    if (!run) { const e = new Error(`no run ${runId}`); e.status = 404; throw e; }
    const out = fn(run, state);
    save(state);
    return out;
  }

  // A finished two-room run, so review.html?mock=1 works on its own.
  function seedDemo(state) {
    const run = newRun(DEMO_RUN);
    const long = Date.now() - 600000;
    fixture.rooms.forEach((r, i) => {
      run.rooms.push({ id: r.room.id, name: r.room.name, fixture: i,
        files: r.files.map((n) => ({ name: n, kind: /\.(mp4|mov|m4v)$/i.test(n) ? "video" : "image",
                                     room_id: r.room.id, bytes: 1, uploadedAt: long })) });
    });
    state.runs[DEMO_RUN] = run;
  }

  window.PIU_MOCK = {
    DEMO_RUN,
    async upload(files, room, runId, onProgress) {
      await getFixture();
      const total = files.reduce((a, f) => a + (f.size || 0), 0);
      const ms = Math.min(4000, 600 + total / 4e4); // pretend: about 40 MB/s, capped at 4 s
      const t0 = Date.now();
      while (Date.now() - t0 < ms) {
        onProgress && onProgress((Date.now() - t0) / ms);
        await sleep(100);
      }
      onProgress && onProgress(1);
      const state = load();
      const id = runId || "mock-" + Date.now().toString(36);
      const run = state.runs[id] || (state.runs[id] = newRun(id));
      const rid = slug(room);
      let r = run.rooms.find((x) => x.id === rid);
      if (!r) run.rooms.push((r = { id: rid, name: room, fixture: run.rooms.length, files: [] }));
      const now = Date.now();
      files.forEach((f) => r.files.push({ name: f.name, kind: /^video\//.test(f.type) || /\.(mp4|mov|m4v)$/i.test(f.name) ? "video" : "image",
                                          room_id: rid, bytes: f.size, uploadedAt: now }));
      save(state);
      return { run_id: id, room_id: rid, files: files.map((f) => f.name), skipped: [] };
    },
    getRun: (runId) => withRun(runId, (run) => build(run, Date.now())),
    async answer(runId, questionId, answer) {
      await sleep(350);
      return withRun(runId, (run) => {
        const [roomId] = questionId.split("-");
        const room = run.rooms.find((r) => r.id === roomId);
        const src = room && fixture.rooms[room.fixture % fixture.rooms.length];
        const q = src && fixture.questions.find((x) => roomId + "-" + x.id === questionId);
        if (!q) { const e = new Error(`no question ${questionId}`); e.status = 404; throw e; }
        answer = String(answer).trim();
        if (answer === "more" || (q.options && !(answer in q.options) && !(q.free_text === "number" && /^\d+$/.test(answer)))) { const e = new Error(`answer must be one of ${Object.keys(q.options).join(", ")}`); e.status = 400; throw e; }
        if (!answer) { const e = new Error("empty answer"); e.status = 400; throw e; }
        run.answers[questionId] = answer;
        const effects = q.mock_effects || {};
        const eff = effects[answer] || effects["*"] || {};
        if (eff.item_id) {
          const id = roomId + "-" + eff.item_id;
          const ch = { ...eff.changes };
          if (ch.label_from_answer) { delete ch.label_from_answer; ch.label = answer; }
          if (ch.quantity_from_answer) { delete ch.quantity_from_answer; ch.quantity = parseInt(answer, 10) || 1; }
          run.itemEdits[id] = { ...(run.itemEdits[id] || {}), ...ch };
        }
        if (eff.container_id) {
          const id = roomId + "-" + eff.container_id;
          run.contEdits[id] = { ...(run.contEdits[id] || {}), ...eff.changes };
        }
        return build(run, Date.now()).inventory;
      });
    },
    async patchItem(runId, itemId, changes) {
      await sleep(250);
      return withRun(runId, (run) => {
        const ch = { ...changes };
        if ("quantity" in ch && (!Number.isInteger(ch.quantity) || ch.quantity < 0)) {
          const e = new Error("quantity must be a non-negative integer"); e.status = 400; throw e;
        }
        if (ch.quantity === 0) Object.assign(ch, { quantity: 1, disposition: "trash" }); // as the server does
        run.itemEdits[itemId] = { ...(run.itemEdits[itemId] || {}), ...ch };
        return build(run, Date.now()).inventory;
      });
    },
    cropUrl: (runId, ev, size, label) => window.PIU.placeholder(label, ev && !ev.sha256 ? "audio" : ev && ev.kind),
    reset() { save({ runs: {} }); },
  };
})();
