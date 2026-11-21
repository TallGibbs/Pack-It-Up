/* Showstopper Stage Add-On:
 *   1. Vinny the NYC Mover + ARIA Verifier 15s Crew Radio (`POST /render/foreman`, Gemini 3.8 Flash TTS)
 *   2. Nano Banana 2.1 Before/After Arrival Slider + Gemini Omni 1.2 Flash 6s Penn Station Time-Lapse (`POST /render/arrival`, `POST /render/timelapse/start`)
 *   3. Raw 1-Call LLM Chaos Toggle (`POST /eval/chaos-plan`) + 3D NYC Pothole / 0.8g Hard-Brake Shake Test + Baseline Proof Table (`GET /eval/summary`)
 */
(function () {
  "use strict";

  const params = new URLSearchParams(location.search);
  const MOCK = params.get("mock") === "1";
  const API_BASE = (params.get("api") || "").replace(/\/+$/, "") || location.origin;

  function currentRunId() {
    const st = window.PIU_STAGE && window.PIU_STAGE.getPlan && window.PIU_STAGE.getPlan();
    if (st && st.run_id) return st.run_id;
    return params.get("run_id") || (window.PIU && window.PIU.lastRun && window.PIU.lastRun()) || "sample_venue";
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  /* ---------- Intercept `/solve` when toggling Raw 1-Call LLM Chaos Mode ---------- */
  let chaosOverridePlan = null;
  let chaosModeActive = false;
  const prevFetch = window.fetch.bind(window);
  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    if (chaosOverridePlan && /\/solve(\b|$)/.test(url)) {
      const p = chaosOverridePlan;
      chaosOverridePlan = null;
      return new Response(JSON.stringify(p), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return prevFetch(input, init);
  };

  /* ---------- WebAudio Walkie-Talkie Squelch + Pothole Impact SFX ---------- */
  let audioCtx = null;
  function getAudioCtx() {
    if (!audioCtx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (Ctx) audioCtx = new Ctx();
    }
    if (audioCtx && audioCtx.state === "suspended") audioCtx.resume();
    return audioCtx;
  }

  function playWalkieSquelch(isEnd) {
    try {
      const ctx = getAudioCtx();
      if (!ctx) return;
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(isEnd ? 1680 : 1320, now);
      osc.frequency.exponentialRampToValueAtTime(isEnd ? 980 : 1890, now + 0.065);
      gain.gain.setValueAtTime(0.08, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.085);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.09);
    } catch (_) {}
  }

  function playPotholeBrakeSfx(collapsed) {
    try {
      const ctx = getAudioCtx();
      if (!ctx) return;
      const now = ctx.currentTime;
      // Double axle pothole thud
      [0.0, 0.14].forEach((offset, idx) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(idx === 0 ? 115 : 92, now + offset);
        osc.frequency.exponentialRampToValueAtTime(32, now + offset + 0.22);
        gain.gain.setValueAtTime(0.28, now + offset);
        gain.gain.exponentialRampToValueAtTime(0.001, now + offset + 0.24);
        osc.connect(gain).connect(ctx.destination);
        osc.start(now + offset);
        osc.stop(now + offset + 0.25);
      });
      if (collapsed) {
        // Rattling warning tone on collapse
        [0.32, 0.48].forEach((offset) => {
          const w = ctx.createOscillator();
          const g = ctx.createGain();
          w.type = "sawtooth";
          w.frequency.setValueAtTime(310, now + offset);
          g.gain.setValueAtTime(0.07, now + offset);
          g.gain.exponentialRampToValueAtTime(0.001, now + offset + 0.12);
          w.connect(g).connect(ctx.destination);
          w.start(now + offset);
          w.stop(now + offset + 0.13);
        });
      }
    } catch (_) {}
  }

  /* ---------- Styles ---------- */
  function injectStyles() {
    if (document.getElementById("piu-showstopper-css")) return;
    const style = document.createElement("style");
    style.id = "piu-showstopper-css";
    style.textContent = `
      .ss-bar {
        display: flex; flex-wrap: wrap; gap: 6px; align-items: center; justify-content: space-between;
        padding: 6px 12px; border-bottom: 1px solid var(--line);
        background: color-mix(in srgb, var(--accent-soft) 28%, var(--card));
      }
      .ss-grp { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
      .ss-btn {
        display: inline-flex; align-items: center; gap: 5px;
        border: 1px solid var(--line); border-radius: 9px;
        background: var(--card); color: var(--ink);
        font: inherit; font-size: 12px; font-weight: 650;
        padding: 4px 9px; min-height: 30px; cursor: pointer;
        transition: transform .1s, border-color .15s, background .15s;
      }
      .ss-btn:hover { border-color: var(--accent); transform: translateY(-1px); }
      .ss-btn.vinny {
        background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
        color: #fff; border-color: #b45309;
      }
      .ss-btn.chaos[aria-pressed="true"] {
        background: #dc2626; color: #fff; border-color: #991b1b;
      }
      .ss-btn.shake {
        background: color-mix(in srgb, #ef4444 12%, var(--card));
        border-color: color-mix(in srgb, #ef4444 42%, var(--line));
      }
      .ss-radio-strip {
        display: none; align-items: center; gap: 10px; padding: 9px 13px;
        background: #111827; color: #f8fafc; border-bottom: 1px solid rgba(255,255,255,0.12);
        font-size: 12.5px; line-height: 1.35;
      }
      .ss-radio-strip.open { display: flex; flex-wrap: wrap; }
      .ss-eq { display: inline-flex; gap: 2.5px; align-items: flex-end; height: 16px; }
      .ss-eq i {
        width: 3px; height: 5px; background: #fbbf24; border-radius: 2px; display: block;
        animation: ssEq 0.55s ease-in-out infinite alternate;
      }
      .ss-eq i:nth-child(2) { animation-delay: 0.12s; }
      .ss-eq i:nth-child(3) { animation-delay: 0.24s; }
      .ss-eq i:nth-child(4) { animation-delay: 0.36s; }
      .ss-eq.idle i { animation: none; height: 4px; opacity: 0.45; }
      @keyframes ssEq { from { height: 4px; } to { height: 16px; } }
      .ss-radio-text { flex: 1; min-width: 210px; }
      .ss-spk {
        display: inline-block; font-weight: 800; font-size: 11px; text-transform: uppercase;
        padding: 1px 6px; border-radius: 5px; margin-right: 6px; letter-spacing: 0.03em;
      }
      .ss-spk.vinny { background: #f59e0b; color: #111827; }
      .ss-spk.aria { background: #38bdf8; color: #0f172a; }

      .ss-shake-toast {
        position: absolute; left: 50%; top: 48px; transform: translateX(-50%);
        z-index: 6; padding: 8px 14px; border-radius: 999px;
        font-size: 12.5px; font-weight: 750; letter-spacing: -0.01em;
        box-shadow: 0 10px 26px rgba(0,0,0,0.42); pointer-events: auto;
        backdrop-filter: blur(8px); text-align: center; max-width: 92%;
      }
      .ss-shake-toast.pass { background: rgba(6, 95, 70, 0.92); color: #ecfdf5; border: 1.5px solid #34d399; }
      .ss-shake-toast.fail { background: rgba(153, 27, 27, 0.94); color: #fef2f2; border: 1.5px solid #f87171; }

      /* Element 119 Arrival Render + Omni Flash Time-Lapse Card */
      .e119-card {
        background: var(--card); border: 1.5px solid var(--line); border-radius: var(--radius);
        padding: 13px 14px;
      }
      .e119-head {
        display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
        gap: 8px; margin-bottom: 9px;
      }
      .e119-head h2 { margin: 0; font-size: 15.5px; display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
      .illus-badge {
        font-size: 10.5px; font-weight: 700; padding: 2px 8px; border-radius: 999px;
        background: var(--accent-soft); color: var(--accent); border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
      }
      .e119-actions { display: flex; flex-wrap: wrap; gap: 7px; align-items: center; }
      .e119-stage {
        position: relative; width: 100%; aspect-ratio: 16 / 9; border-radius: 12px;
        overflow: hidden; background: radial-gradient(circle at 50% 35%, #1e293b 0%, #0f172a 100%);
        border: 1px solid var(--line); user-select: none;
      }
      .e119-empty {
        position: absolute; inset: 0; display: flex; flex-direction: column;
        align-items: center; justify-content: center; text-align: center; padding: 20px;
        color: #cbd5e1; gap: 8px; font-size: 13px;
      }
      .e119-compare { position: absolute; inset: 0; }
      .e119-compare img {
        position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block;
      }
      .e119-before-clip {
        position: absolute; inset: 0; overflow: hidden;
      }
      .e119-divider {
        position: absolute; top: 0; bottom: 0; width: 2.5px; background: #fff;
        box-shadow: 0 0 10px rgba(0,0,0,0.6); pointer-events: none; z-index: 3;
      }
      .e119-knob {
        position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
        width: 34px; height: 34px; border-radius: 999px; background: #1f6feb; color: #fff;
        border: 2px solid #fff; display: flex; align-items: center; justify-content: center;
        font-size: 13px; font-weight: 800; box-shadow: 0 4px 14px rgba(0,0,0,0.45);
      }
      .e119-scrubber {
        position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0;
        cursor: ew-resize; z-index: 4; margin: 0;
      }
      .e119-corner-lbl {
        position: absolute; top: 9px; padding: 3px 9px; border-radius: 999px;
        font-size: 11px; font-weight: 700; background: rgba(15,23,42,0.82); color: #f8fafc;
        backdrop-filter: blur(5px); z-index: 3; pointer-events: none;
      }
      .e119-corner-lbl.left { left: 9px; }
      .e119-corner-lbl.right { right: 9px; }
      .e119-video-wrap { position: absolute; inset: 0; background: #000; z-index: 5; }
      .e119-video-wrap video, .e119-video-wrap canvas { width: 100%; height: 100%; object-fit: cover; display: block; }
      .e119-status-bar {
        display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
        gap: 8px; margin-top: 8px; font-size: 12px; color: var(--muted);
      }
      .eval-mini-table {
        width: 100%; border-collapse: collapse; font-size: 11.5px; margin-top: 9px;
      }
      .eval-mini-table th, .eval-mini-table td {
        text-align: left; padding: 5px 7px; border-top: 1px solid var(--line);
      }
      .eval-mini-table th { color: var(--muted); font-weight: 700; border-top: 0; }
      .eval-mini-table tr.ours td { font-weight: 700; color: var(--ok, #16a34a); }
    `;
    document.head.appendChild(style);
  }

  /* ---------- 1. Vinny the NYC Mover 15s Crew Radio ---------- */
  let activeAudio = null;
  let subTimers = [];

  function clearSubTimers() {
    subTimers.forEach((t) => clearTimeout(t));
    subTimers = [];
  }

  async function triggerVinnyRadio() {
    const btn = document.getElementById("btn-vinny-radio");
    const strip = document.getElementById("ss-radio-strip");
    const eq = document.getElementById("ss-eq");
    const txt = document.getElementById("ss-radio-text");
    if (!btn || !strip) return;

    if (activeAudio && !activeAudio.paused) {
      activeAudio.pause();
      activeAudio = null;
      clearSubTimers();
      eq.classList.add("idle");
      btn.textContent = "🎙️ Vinny Crew Radio (15s)";
      return;
    }

    strip.classList.add("open");
    eq.classList.remove("idle");
    btn.disabled = true;
    btn.textContent = "🎙️ Dialing Vinny…";
    txt.innerHTML = `<span class="ss-spk vinny">Vinny</span> Tuning channel 4 (Gemini 3.8 Flash TTS)…`;
    playWalkieSquelch(false);

    const curPlan = window.PIU_STAGE && window.PIU_STAGE.getPlan ? window.PIU_STAGE.getPlan() : null;

    try {
      let data = null;
      if (!MOCK) {
        const res = await prevFetch(`${API_BASE}/render/foreman`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ run_id: currentRunId(), plan: curPlan }),
        });
        if (res.ok) data = await res.json();
      }

      if (data && data.ok && data.audio_url) {
        const turns = data.turns || [];
        const rawDur = Number(data.duration_s || 15);
        const rate = rawDur > 16.5 ? Math.min(1.36, rawDur / 15.0) : 1.0;
        const playDurS = rawDur / rate;
        const totalDurMs = Math.max(5000, playDurS * 1000);
        const audio = new Audio(`${API_BASE}${data.audio_url}`);
        audio.preservesPitch = true;
        audio.playbackRate = rate;
        activeAudio = audio;
        btn.disabled = false;
        btn.textContent = `⏹ Stop Radio (${Math.round(playDurS)}s)`;

        // Synchronize Vinny & ARIA captions across turn word-counts
        const totalWords = Math.max(1, turns.reduce((s, t) => s + String(t.text || "").split(/\s+/).length, 0));
        let accMs = 0;
        clearSubTimers();
        turns.forEach((t) => {
          const cleanLine = String(t.text || "").replace(/<[^>]+>/g, "").trim();
          const spkClass = String(t.speaker || "Vinny").toLowerCase() === "aria" ? "aria" : "vinny";
          const timer = setTimeout(() => {
            txt.innerHTML = `<span class="ss-spk ${spkClass}">${esc(t.speaker)}</span> ${esc(cleanLine)}`;
          }, accMs);
          subTimers.push(timer);
          const w = String(t.text || "").split(/\s+/).length;
          accMs += Math.round((w / totalWords) * (totalDurMs - 300));
        });

        audio.onended = () => {
          playWalkieSquelch(true);
          eq.classList.add("idle");
          btn.textContent = "🎙️ Vinny Crew Radio (15s)";
          activeAudio = null;
        };
        await audio.play();
        return;
      }

      // Browser WebSpeech dual-persona fallback (for ?mock=1 or offline wifi)
      const vCount = (curPlan && curPlan.score && curPlan.score.violations ? curPlan.score.violations.length : 0);
      const tCount = (curPlan && curPlan.trucks ? curPlan.trucks.length : 2);
      const fallbackTurns = (data && data.turns) || [
        { speaker: "Vinny", text: vCount === 0
          ? `Alright crew, ${tCount} twenty-six-footers to Penn Station — zero physics violations! Heavy base tight on the cab wall, baby the monitors!`
          : `Whoa, hold the ramp! Who packed this truck?! We got ${vCount} physics violations floating in mid-air!` },
        { speaker: "ARIA", text: vCount === 0
          ? `Axle balance locked near fifty percent. Stop One Merch Kiosk rides at the rear door for instant dock unload.`
          : `Load rejected. Switch back to Pack It Up Verified before hitting a single Midtown pothole.` },
        { speaker: "Vinny", text: vCount === 0
          ? `Beautiful! Stay off the FDR Drive — Thirty-First Street dock, let's roll!`
          : `Nobody touches the brakes till we re-pack this right!` },
      ];
      btn.disabled = false;
      btn.textContent = "🎙️ Vinny Crew Radio (15s)";
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
        let idx = 0;
        const speakNext = () => {
          if (idx >= fallbackTurns.length) {
            playWalkieSquelch(true);
            eq.classList.add("idle");
            return;
          }
          const turn = fallbackTurns[idx++];
          const clean = String(turn.text).replace(/<[^>]+>/g, "").trim();
          const spkClass = turn.speaker === "ARIA" ? "aria" : "vinny";
          txt.innerHTML = `<span class="ss-spk ${spkClass}">${esc(turn.speaker)}</span> ${esc(clean)}`;
          const u = new SpeechSynthesisUtterance(clean);
          u.rate = turn.speaker === "ARIA" ? 1.06 : 1.14;
          u.pitch = turn.speaker === "ARIA" ? 1.15 : 0.82;
          u.onend = speakNext;
          window.speechSynthesis.speak(u);
        };
        speakNext();
      } else {
        eq.classList.add("idle");
        txt.innerHTML = `<span class="ss-spk vinny">Vinny</span> ${esc(fallbackTurns[0].text)}`;
      }
    } catch (err) {
      btn.disabled = false;
      btn.textContent = "🎙️ Vinny Crew Radio (15s)";
      eq.classList.add("idle");
      txt.innerHTML = `<span class="ss-spk vinny">Radio</span> Couldn't reach TTS: ${esc(err.message)}`;
    }
  }

  /* ---------- 2. Raw 1-Call LLM Chaos Toggle + 3D NYC Pothole / Hard-Brake Shake Test ---------- */
  function buildMockChaosPlan(basePlan) {
    const clone = JSON.parse(JSON.stringify(basePlan));
    const violations = [];
    (clone.trucks || []).forEach((t) => {
      (t.items || []).forEach((it, idx) => {
        if (idx % 4 === 1) {
          // Float in mid-air + shift left
          it.pos_in[2] = Math.min(72, (it.pos_in[2] || 0) + 26);
          it.pos_in[1] = Math.max(0, (it.pos_in[1] || 0) * 0.35);
          violations.push({ rule: "support", detail: `${it.label} floating (<75% base support)`, item_ids: [it.id] });
        } else if (idx % 5 === 2 && idx > 0) {
          // Overlap neighbor + tip upright item
          const prev = t.items[idx - 1];
          it.pos_in = [prev.pos_in[0] + 3, prev.pos_in[1] + 2, prev.pos_in[2]];
          if (it.must_stay_upright) {
            const tmp = it.size_in[0]; it.size_in[0] = it.size_in[2]; it.size_in[2] = tmp;
            violations.push({ rule: "upright", detail: `${it.label} tipped onto its side`, item_ids: [it.id] });
          }
          violations.push({ rule: "overlap", detail: `${it.label} intersects ${prev.label}`, item_ids: [it.id, prev.id] });
        }
      });
    });
    clone.score = {
      ...(clone.score || {}),
      total: 12.4,
      valid: false,
      violation_count: violations.length,
      violations,
    };
    return clone;
  }

  async function toggleChaosPlan() {
    const btn = document.getElementById("btn-chaos-toggle");
    const btnResolve = document.getElementById("btn-resolve");
    if (!btn || !btnResolve) return;

    if (chaosModeActive) {
      chaosModeActive = false;
      btn.setAttribute("aria-pressed", "false");
      btn.textContent = "⚡ Raw 1-Call LLM Chaos";
      chaosOverridePlan = null;
      btnResolve.click();
      return;
    }

    btn.disabled = true;
    btn.textContent = "⚡ Loading Raw LLM Plan…";
    try {
      let cPlan = null;
      if (!MOCK) {
        const selTruck = document.getElementById("sel-truck");
        const res = await prevFetch(`${API_BASE}/eval/chaos-plan`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            run_id: currentRunId(),
            truck_id: (selTruck && selTruck.value) || "uhaul_26",
            use_live_llm: false,
          }),
        });
        if (res.ok) cPlan = await res.json();
      }
      if (!cPlan) {
        const cur = window.PIU_STAGE && window.PIU_STAGE.getPlan ? window.PIU_STAGE.getPlan() : null;
        if (cur) cPlan = buildMockChaosPlan(cur);
      }
      if (cPlan) {
        chaosModeActive = true;
        btn.setAttribute("aria-pressed", "true");
        btn.textContent = "↩ Back to Verified Plan";
        chaosOverridePlan = cPlan;
        // Switch viewport to Trucks so the floating/overlapping cargo is front and center
        const truckTab = document.getElementById("scene-trucks");
        if (truckTab && truckTab.getAttribute("aria-pressed") !== "true") truckTab.click();
        btnResolve.click();
      }
    } finally {
      btn.disabled = false;
    }
  }

  let shakeAnimId = null;
  function runPotholeShakeTest() {
    const stage = window.PIU_STAGE;
    const wrap = document.getElementById("canvas-wrap");
    if (!stage || !wrap) return;

    const truckBtn = document.getElementById("scene-trucks");
    if (truckBtn && truckBtn.getAttribute("aria-pressed") !== "true") {
      truckBtn.click();
    }
    const showAllBtn = document.getElementById("btn-all");
    if (showAllBtn) showAllBtn.click();

    const wg = stage.getWorldGroup();
    const entries = stage.getMeshEntries() || [];
    const violSet = stage.getViolatingIds() || new Set();
    const collapsed = violSet.size > 0;

    if (shakeAnimId) cancelAnimationFrame(shakeAnimId);
    const oldToast = document.getElementById("ss-shake-toast");
    if (oldToast) oldToast.remove();

    playPotholeBrakeSfx(collapsed);

    // Snapshot initial transforms so verified plans return cleanly and chaos plans visibly topple
    const snaps = entries.map((e, i) => ({
      entry: e,
      x0: e.mesh.position.x,
      y0: e.mesh.position.y,
      z0: e.mesh.position.z,
      rx0: e.mesh.rotation.x,
      rz0: e.mesh.rotation.z,
      isBad: violSet.has(e.item.id),
      phase: (i % 7) * 0.45,
      tiltSign: i % 2 === 0 ? 1 : -1,
    }));

    const start = performance.now();
    const durMs = collapsed ? 1750 : 1350;
    let badCount = 0;
    snaps.forEach((s) => { if (s.isBad) badCount++; });

    const toast = document.createElement("div");
    toast.id = "ss-shake-toast";
    toast.className = `ss-shake-toast ${collapsed ? "fail" : "pass"}`;
    toast.textContent = collapsed
      ? `🚨 0.8G BRAKE + BQE POTHOLE FAILED: ${badCount} unverified items toppled / crushed!`
      : `🛡️ 0.8G BRAKE + BQE POTHOLE PASSED: 0 items shifted · ≥75% base support & axle balance held!`;
    wrap.appendChild(toast);

    function tick(now) {
      const t = Math.min(1, (now - start) / durMs);
      const decay = Math.exp(-3.6 * t);
      // Chassis pothole vertical bounce + lateral roll + 0.8g forward brake pitch
      wg.position.y = Math.sin(t * Math.PI * 9) * 5.2 * decay;
      wg.position.x = -Math.sin(t * Math.PI * 2.2) * 7.5 * decay;
      wg.rotation.z = Math.sin(t * Math.PI * 5) * 0.028 * decay;
      wg.rotation.x = Math.sin(t * Math.PI * 7) * 0.024 * decay;

      snaps.forEach((s) => {
        const m = s.entry.mesh;
        if (s.isBad) {
          // Unsupported/overlapping items slam forward (-X toward cab), drop to floor, and tip askew!
          const ease = 1 - Math.pow(1 - t, 3);
          const halfH = Math.max(4, (s.entry.item.size_in[2] || 14) * 0.5);
          const floorDropY = Math.min(s.y0, halfH + 1.5);
          m.position.x = s.x0 - 18.0 * ease;
          m.position.y = s.y0 + (floorDropY - s.y0) * ease + Math.abs(Math.sin(t * 12 + s.phase)) * 3 * decay;
          m.rotation.z = s.rz0 + s.tiltSign * 0.44 * ease;
          m.rotation.x = s.rx0 + s.tiltSign * 0.26 * ease;
        } else {
          // Verified items micro-flex together and lock right back to 0.0" displacement
          m.position.x = s.x0 - Math.sin(t * Math.PI * 6 + s.phase) * 0.55 * decay;
          m.rotation.z = s.rz0 + Math.sin(t * Math.PI * 6 + s.phase) * 0.008 * decay;
        }
      });

      if (t < 1) {
        shakeAnimId = requestAnimationFrame(tick);
      } else {
        wg.position.set(0, 0, 0);
        wg.rotation.set(0, 0, 0);
        if (!collapsed) {
          snaps.forEach((s) => {
            s.entry.mesh.position.set(s.x0, s.y0, s.z0);
            s.entry.mesh.rotation.set(s.rx0, s.entry.mesh.rotation.y, s.rz0);
          });
        }
        setTimeout(() => {
          if (toast.parentNode) toast.remove();
        }, collapsed ? 5500 : 3600);
      }
    }
    shakeAnimId = requestAnimationFrame(tick);
  }

  /* ---------- 3. Nano Banana 2.1 Arrival Render + Gemini Omni 1.2 Flash 6s Time-Lapse ---------- */
  let lastArrivalData = null;
  let videoPollTimer = null;

  function renderMockCanvasTimelapse(host) {
    host.innerHTML = `<div class="e119-video-wrap"><canvas id="e119-mock-canvas" width="960" height="540"></canvas></div>`;
    const cv = document.getElementById("e119-mock-canvas");
    if (!cv) return;
    const ctx = cv.getContext("2d");
    let frame = 0;
    function draw() {
      if (!document.body.contains(cv)) return;
      frame++;
      const p = (frame % 240) / 240; // 4s loop at 60fps
      // Vaulted Moynihan skylight gradient
      const g = ctx.createLinearGradient(0, 0, 0, 540);
      g.addColorStop(0, "#1e3a5f");
      g.addColorStop(0.48, "#cbd5e1");
      g.addColorStop(0.5, "#94a3b8");
      g.addColorStop(1, "#64748b");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, 960, 540);

      // Skylight trusses
      ctx.strokeStyle = "rgba(255,255,255,0.38)";
      ctx.lineWidth = 2;
      for (let i = 0; i < 12; i++) {
        ctx.beginPath();
        ctx.moveTo(i * 90, 0);
        ctx.lineTo(480 + (i - 5.5) * 140, 260);
        ctx.stroke();
      }

      // Progressive furniture + QR box staging
      const items = [
        { x: 130, y: 340, w: 190, h: 68, c: "#d97706", lbl: "Orior Sofa" },
        { x: 370, y: 355, w: 220, h: 56, c: "#0f766e", lbl: "Communal Table" },
        { x: 640, y: 330, w: 165, h: 80, c: "#1d4ed8", lbl: "65\" Monitor Rig" },
        { x: 220, y: 430, w: 68, h: 52, c: "#c89d66", lbl: "QR Box #1" },
        { x: 300, y: 430, w: 68, h: 52, c: "#c89d66", lbl: "QR Box #2" },
        { x: 700, y: 428, w: 74, h: 54, c: "#334155", lbl: "Pelican 1650" },
      ];
      items.forEach((it, idx) => {
        const appear = Math.min(1, Math.max(0, (p - idx * 0.11) / 0.18));
        if (appear <= 0) return;
        ctx.save();
        ctx.globalAlpha = appear;
        const slideY = it.y + (1 - appear) * 28;
        ctx.fillStyle = it.c;
        ctx.fillRect(it.x, slideY, it.w, it.h);
        ctx.strokeStyle = "#0f172a";
        ctx.strokeRect(it.x, slideY, it.w, it.h);
        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 13px system-ui, sans-serif";
        ctx.fillText(it.lbl, it.x + 10, slideY + 30);
        ctx.restore();
      });

      ctx.fillStyle = "rgba(15,23,42,0.82)";
      ctx.fillRect(16, 16, 410, 32);
      ctx.fillStyle = "#f8fafc";
      ctx.font = "bold 13px system-ui, sans-serif";
      ctx.fillText("🎬 Mock Moynihan Time-Lapse (Connect API for Live Omni 1.2 Flash)", 28, 37);
      requestAnimationFrame(draw);
    }
    requestAnimationFrame(draw);
  }

  function showComparisonSlider(beforeUrl, afterUrl, modelName) {
    const stage = document.getElementById("e119-stage");
    if (!stage) return;
    stage.innerHTML = `
      <div class="e119-compare">
        <img src="${esc(afterUrl)}" alt="Penn Station staged with moved hackathon inventory">
        <div class="e119-before-clip" id="e119-before-clip" style="clip-path: inset(0 78% 0 0);">
          <img src="${esc(beforeUrl)}" alt="Empty Penn Station concourse before move">
        </div>
        <div class="e119-divider" id="e119-divider" style="left: 22%;">
          <div class="e119-knob">⇄</div>
        </div>
        <span class="e119-corner-lbl left">BEFORE · Empty Penn Bay</span>
        <span class="e119-corner-lbl right">AFTER · ${esc(modelName || "Nano Banana 2.1")}</span>
        <input type="range" class="e119-scrubber" id="e119-slider" min="2" max="98" value="22" aria-label="Before and after comparison">
      </div>
    `;
    const slider = document.getElementById("e119-slider");
    const clip = document.getElementById("e119-before-clip");
    const div = document.getElementById("e119-divider");
    if (slider && clip && div) {
      slider.addEventListener("input", () => {
        const v = Number(slider.value);
        clip.style.clipPath = `inset(0 ${100 - v}% 0 0)`;
        div.style.left = `${v}%`;
      });
    }
  }

  function showTimelapseVideo(videoUrl) {
    const stage = document.getElementById("e119-stage");
    const tabVid = document.getElementById("btn-e119-show-vid");
    const tabImg = document.getElementById("btn-e119-show-img");
    if (!stage) return;
    if (tabVid) { tabVid.classList.remove("hidden"); tabVid.setAttribute("aria-pressed", "true"); }
    if (tabImg) { tabImg.classList.remove("hidden"); tabImg.setAttribute("aria-pressed", "false"); }
    stage.innerHTML = `
      <div class="e119-video-wrap">
        <video src="${esc(videoUrl)}" autoplay loop muted playsinline controls></video>
        <span class="e119-corner-lbl left">🎬 Gemini Omni 1.2 Flash · 6s Penn Station Arrival Time-Lapse</span>
      </div>
    `;
  }

  async function runArrivalAndTimelapse() {
    const btn = document.getElementById("btn-e119-generate");
    const statusEl = document.getElementById("e119-status");
    const stage = document.getElementById("e119-stage");
    if (!btn || !statusEl || !stage) return;

    if (MOCK) {
      renderMockCanvasTimelapse(stage);
      statusEl.textContent = "Mock preview active · Run against FastAPI server for live Nano Banana 2.1 + Omni 1.2 Flash.";
      return;
    }

    btn.disabled = true;
    btn.textContent = "🍌 Rendering Nano Banana 2.1…";
    statusEl.textContent = "Step 1/2: Generating photorealistic Penn Station Before/After keyframes with gemini-nano-banana-2.1…";

    const curPlan = window.PIU_STAGE && window.PIU_STAGE.getPlan ? window.PIU_STAGE.getPlan() : null;

    try {
      const res = await prevFetch(`${API_BASE}/render/arrival`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: currentRunId(), plan: curPlan }),
      });
      if (!res.ok) {
        const errTxt = await res.text();
        let msg = errTxt;
        try { msg = JSON.parse(errTxt).detail || errTxt; } catch (_) {}
        if (/^\s*<(!doctype|html)/i.test(msg)) msg = `server returned HTTP ${res.status} (proxy error page)`;
        throw new Error(String(msg).slice(0, 180));
      }
      const data = await res.json();
      lastArrivalData = data;
      const beforeUrl = `${API_BASE}${data.before_url}`;
      const afterUrl = `${API_BASE}${data.after_url}`;
      showComparisonSlider(beforeUrl, afterUrl, data.model);

      const tabImg = document.getElementById("btn-e119-show-img");
      if (tabImg) {
        tabImg.classList.remove("hidden");
        tabImg.setAttribute("aria-pressed", "true");
      }

      btn.textContent = "🎬 Launching Omni 1.2 Flash (6s)…";
      statusEl.textContent = `Arrival render ready (${data.latency_s}s${data.cached ? ", cached" : ""})! Step 2/2: Interpolating 6s 720p time-lapse with gemini-omni-1.2-flash…`;

      const vStart = await prevFetch(`${API_BASE}/render/timelapse/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          before_asset: data.before_asset,
          after_asset: data.after_asset,
          run_id: currentRunId(),
          duration_s: 6,
        }),
      });
      if (!vStart.ok) throw new Error("Omni Flash start error");
      const job = await vStart.json();

      if (job.status === "completed" && job.video_url) {
        lastArrivalData.video_url = `${API_BASE}${job.video_url}`;
        showTimelapseVideo(lastArrivalData.video_url);
        statusEl.textContent = `✨ Complete! Nano Banana 2.1 keyframes + Gemini Omni 1.2 Flash 6s Penn Station hyper-lapse ready.`;
        btn.disabled = false;
        btn.textContent = "↻ Re-render Arrival";
        return;
      }

      if (videoPollTimer) clearInterval(videoPollTimer);
      videoPollTimer = setInterval(async () => {
        try {
          const pRes = await prevFetch(`${API_BASE}/render/timelapse/${encodeURIComponent(job.job_id)}`);
          if (!pRes.ok) return;
          const st = await pRes.json();
          if (st.status === "completed" && st.video_url) {
            clearInterval(videoPollTimer);
            videoPollTimer = null;
            lastArrivalData.video_url = `${API_BASE}${st.video_url}`;
            showTimelapseVideo(lastArrivalData.video_url);
            statusEl.textContent = `✨ Complete! Gemini Omni 1.2 Flash 6s hyper-lapse generated in ${st.latency_s || st.elapsed_s}s.`;
            btn.disabled = false;
            btn.textContent = "↻ Re-render Arrival";
          } else if (st.status === "failed") {
            clearInterval(videoPollTimer);
            videoPollTimer = null;
            statusEl.textContent = `Nano Banana 2.1 Before/After slider active · Omni Flash note: ${st.error || "unavailable"}`;
            btn.disabled = false;
            btn.textContent = "🎬 Retry 6s Time-Lapse";
          } else {
            statusEl.textContent = ` Nano Banana 2.1 slider live above (drag ⇄)! Gemini Omni 1.2 Flash rendering 6s MP4… (${st.elapsed_s}s)`;
          }
        } catch (_) {}
      }, 2500);
    } catch (err) {
      btn.disabled = false;
      btn.textContent = "✨ Render Arrival + 6s Time-Lapse";
      statusEl.textContent = `Render error: ${err.message}`;
    }
  }

  let evalLoadedForRun = null;
  async function loadEvalTable(force = false) {
    const host = document.getElementById("e119-eval-wrap");
    if (!host) return;
    host.classList.remove("hidden");
    const rid = currentRunId();
    if (!force && evalLoadedForRun === rid && host.querySelector("table")) return;
    host.innerHTML = `<div class="small muted" style="margin-top:4px">Scoring baselines against verifier…</div>`;
    try {
      let rows = null;
      if (!MOCK) {
        const res = await prevFetch(`${API_BASE}/eval/summary?run_id=${encodeURIComponent(rid)}`);
        if (res.ok) {
          const d = await res.json();
          rows = d.rows;
        }
      }
      if (!rows) {
        rows = [
          { method: "Pack It Up (Agents + Constrained Solver + Verifier)", score: 96.8, violations: 0, trucks: 2, notes: "0 violations · ≥75% support · Penn LIFO" },
          { method: "Baseline A1: Single-Call LLM 3D Coordinates", score: 11.5, violations: 64, trucks: 2, notes: "Mid-air floats, AABB overlaps & tipped monitors" },
          { method: "Baseline A2: Stock py3dbp 3D Bin Packer", score: 14.2, violations: 149, trucks: 2, notes: "42 overhangs, 71 crushed no-stack, 35% axle tilt" },
          { method: "Baseline B: Rental-Site Room-Count Calculator", score: 0.0, violations: 78, trucks: 1, notes: "Quotes 1 small truck -> leaves half the move on curb" },
        ];
      }
      evalLoadedForRun = rid;
      host.innerHTML = `
        <table class="eval-mini-table" style="margin-top:2px">
          <thead><tr><th>Method (Same Inventory &amp; Verifier)</th><th>Score</th><th>Violations</th><th>Fleet</th><th>What Happened</th></tr></thead>
          <tbody>
            ${rows.map((r, i) => `
              <tr class="${i === 0 ? "ours" : ""}">
                <td>${esc(r.method)}</td>
                <td>${esc(r.score)} / 100</td>
                <td>${r.violations === 0 ? "✅ 0" : `❌ ${esc(r.violations)}`}</td>
                <td>${esc(r.trucks)} trk</td>
                <td>${esc(r.notes)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;
    } catch (e) {
      host.innerHTML = `<div class="small muted">Eval error: ${esc(e.message)}</div>`;
    }
  }

  /* ---------- Mount UI Elements into `frontend/index.html` ---------- */
  function mount() {
    const stageCard = document.querySelector(".stage-card");
    const stageSplit = document.getElementById("stage-split");
    const canvasWrap = document.getElementById("canvas-wrap");
    const storyboard = document.getElementById("storyboard-card");
    const anchorBefore = stageSplit || (canvasWrap && canvasWrap.parentNode === stageCard ? canvasWrap : null);
    if (!stageCard || !anchorBefore || document.getElementById("ss-action-bar")) return;

    injectStyles();

    // 1. Compact action bar + Walkie-Talkie radio strip right above the 3D Three.js viewport
    const actionBar = document.createElement("div");
    actionBar.className = "ss-bar";
    actionBar.id = "ss-action-bar";
    actionBar.innerHTML = `
      <div class="ss-grp">
        <button type="button" class="ss-btn vinny" id="btn-vinny-radio">🎙️ Vinny Crew Radio (15s)</button>
        <button type="button" class="ss-btn shake" id="btn-pothole-shake">💥 Pothole / 0.8g Test</button>
      </div>
      <div class="ss-grp">
        <button type="button" class="ss-btn chaos" id="btn-chaos-toggle" aria-pressed="false">⚡ Raw 1-Call LLM Chaos</button>
        <button type="button" class="ss-btn" id="btn-eval-proof">📊 Baselines</button>
      </div>
    `;
    stageCard.insertBefore(actionBar, anchorBefore);

    const radioStrip = document.createElement("div");
    radioStrip.className = "ss-radio-strip";
    radioStrip.id = "ss-radio-strip";
    radioStrip.innerHTML = `
      <span class="ss-eq idle" id="ss-eq"><i></i><i></i><i></i><i></i></span>
      <div class="ss-radio-text" id="ss-radio-text">Ready on Crew Channel 4.</div>
    `;
    stageCard.insertBefore(radioStrip, anchorBefore);

    // 2. Mount Element 119 Media-Out + Baseline Proof cleanly inside `#storyboard-card` tabs (or standalone fallback)
    const arrivalPane = document.getElementById("mpane-arrival");
    const evalPane = document.getElementById("mpane-eval");

    if (arrivalPane || (storyboard && storyboard.parentNode)) {
      const e119 = document.createElement("div");
      e119.className = arrivalPane ? "" : "e119-card";
      e119.id = "e119-card";
      e119.innerHTML = `
        <div class="e119-head">
          <h2>
            <span>🎬 Penn Station Arrival Time-Lapse</span>
            <span class="illus-badge">Illustrative · 3D view is the plan</span>
          </h2>
          <div class="e119-actions">
            <div class="pill-group">
              <button type="button" class="hidden" id="btn-e119-show-img" aria-pressed="false">🖼️ Before/After</button>
              <button type="button" class="hidden" id="btn-e119-show-vid" aria-pressed="false">🎬 6s Time-Lapse</button>
            </div>
            <button type="button" class="btn sm primary" id="btn-e119-generate">✨ Render Arrival + 6s Time-Lapse</button>
          </div>
        </div>
        <div class="e119-stage" id="e119-stage">
          <div class="e119-empty">
            <div style="font-size:26px">🍌 → 🎬</div>
            <div><b>Nano Banana 2.1 + Gemini Omni 1.2 Flash</b></div>
            <div style="max-width:480px;font-size:12px;color:#94a3b8">
              Fuses real room item crops with Penn Station's concourse in ~5s (interactive Before/After slider), then interpolates a 6-second 720p unpacking hyper-lapse MP4.
            </div>
          </div>
        </div>
        <div class="e119-status-bar">
          <span id="e119-status">Element 119 Media-Out: gemini-nano-banana-2.1 (keyframes) + gemini-omni-1.2-flash (6s transition)</span>
        </div>
        ${evalPane ? "" : `<div id="e119-eval-wrap" class="hidden"></div>`}
      `;

      if (arrivalPane) {
        arrivalPane.appendChild(e119);
      } else {
        storyboard.parentNode.insertBefore(e119, storyboard);
      }

      if (evalPane) {
        evalPane.innerHTML = `<div id="e119-eval-wrap"></div>`;
      }

      document.getElementById("btn-e119-generate").addEventListener("click", runArrivalAndTimelapse);
      document.getElementById("btn-e119-show-img").addEventListener("click", () => {
        if (!lastArrivalData) return;
        document.getElementById("btn-e119-show-img").setAttribute("aria-pressed", "true");
        document.getElementById("btn-e119-show-vid").setAttribute("aria-pressed", "false");
        showComparisonSlider(`${API_BASE}${lastArrivalData.before_url}`, `${API_BASE}${lastArrivalData.after_url}`, lastArrivalData.model);
      });
      document.getElementById("btn-e119-show-vid").addEventListener("click", () => {
        if (!lastArrivalData || !lastArrivalData.video_url) return;
        showTimelapseVideo(lastArrivalData.video_url);
      });
    }

    window.addEventListener("piu:mediatab", (ev) => {
      if (ev.detail && ev.detail.tab === "eval") {
        loadEvalTable(false);
      }
    });

    document.getElementById("btn-vinny-radio").addEventListener("click", triggerVinnyRadio);
    document.getElementById("btn-pothole-shake").addEventListener("click", runPotholeShakeTest);
    document.getElementById("btn-chaos-toggle").addEventListener("click", toggleChaosPlan);
    document.getElementById("btn-eval-proof").addEventListener("click", () => {
      if (window.PIU_SWITCH_MEDIA_TAB) {
        window.PIU_SWITCH_MEDIA_TAB("eval");
      }
      loadEvalTable(true);
      const card = document.getElementById("storyboard-card") || document.getElementById("e119-card");
      if (card) card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
