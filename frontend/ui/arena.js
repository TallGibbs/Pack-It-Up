/* Stage B6 + B7 UI widget: Gemini 4 Neon Planning Loop & Competing Managed Agents Arena.
 *
 * Drop `<script src="ui/arena.js"></script>` into `frontend/index.html` to mount the
 * live AI Strategy Arena card above `#verifier-panel` without touching `index.html` internals.
 * Works both against the live FastAPI server (`/plan`, `/agents/start`, `/agents/{job_id}`)
 * and in `?mock=1` standalone browser mode.
 */
(function () {
  "use strict";

  const params = new URLSearchParams(location.search);
  const MOCK = params.get("mock") === "1";
  const API_BASE = (params.get("api") || "").replace(/\/+$/, "") || location.origin;
  const runId = params.get("run_id") || (window.PIU && window.PIU.lastRun && window.PIU.lastRun()) || "sample_venue";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  // Intercept a single `/solve` fetch when applying an exact arena/Neon winner placement
  let pendingPlanOverride = null;
  const origFetch = window.fetch.bind(window);
  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    if (pendingPlanOverride && /\/solve(\b|$)/.test(url)) {
      const plan = pendingPlanOverride;
      pendingPlanOverride = null;
      return new Response(JSON.stringify(plan), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return origFetch(input, init);
  };

  function applyWinnerToViewer(winnerPlan) {
    if (!winnerPlan) return;
    const strat = winnerPlan.strategy || {};
    const selTruck = document.getElementById("sel-truck");
    const selEngine = document.getElementById("sel-engine");
    const togDownsize = document.getElementById("tog-downsize");
    const btnResolve = document.getElementById("btn-resolve");
    const btnPlay = document.getElementById("btn-play");

    if (selTruck && strat.truck_id) selTruck.value = strat.truck_id;
    if (selEngine && strat.packer_engine) selEngine.value = strat.packer_engine;
    if (togDownsize && typeof strat.downsize_last_truck === "boolean") {
      const cur = togDownsize.getAttribute("aria-pressed") === "true";
      if (cur !== strat.downsize_last_truck) {
        togDownsize.setAttribute("aria-pressed", String(strat.downsize_last_truck));
      }
    }
    if (!MOCK) {
      pendingPlanOverride = winnerPlan;
    }
    if (btnResolve) {
      btnResolve.click();
      setTimeout(() => {
        const slider = document.getElementById("step-slider");
        if (slider) {
          slider.value = "0";
          slider.dispatchEvent(new Event("input"));
        }
        if (btnPlay && btnPlay.textContent.includes("Play")) btnPlay.click();
      }, 180);
    }
  }

  function injectStyles() {
    const style = document.createElement("style");
    style.textContent = `
      .arena-actions { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
      .arena-actions .btn { flex: 1; justify-content: center; font-size: 12.5px; padding: 8px 10px; }
      .arena-list { list-style: none; padding: 0; margin: 0; display: grid; gap: 7px; }
      .arena-row {
        padding: 8px 10px; border-radius: 10px; border: 1px solid var(--line);
        background: var(--bg); font-size: 12.5px; transition: border-color 0.2s, background 0.2s;
      }
      .arena-row.winner {
        border-color: var(--ok, #2da44e);
        background: color-mix(in srgb, var(--ok, #2da44e) 10%, var(--card));
      }
      .arena-row-top { display: flex; justify-content: space-between; align-items: center; gap: 6px; font-weight: 600; }
      .arena-score { font-variant-numeric: tabular-nums; font-weight: 700; }
      .arena-score.ok { color: var(--ok, #2da44e); }
      .arena-score.bad { color: var(--bad, #cf222e); }
      .arena-sub { font-size: 11.5px; color: var(--muted); margin-top: 3px; line-height: 1.35; }
    `;
    document.head.appendChild(style);
  }

  function mountPanel() {
    const verifier = document.getElementById("verifier-panel");
    if (!verifier || document.getElementById("arena-panel")) return;
    injectStyles();

    const card = document.createElement("section");
    card.className = "panel-card";
    card.id = "arena-panel";
    card.innerHTML = `
      <h2>
        <span>AI Strategy Arena</span>
        <span class="small muted" id="arena-status">Gemini 4 Neon + Agents</span>
      </h2>
      <div class="arena-actions">
        <button type="button" class="btn primary" id="btn-run-agents">⚡ Compete (4 Agents)</button>
        <button type="button" class="btn" id="btn-run-neon">🧠 Neon Loop (3 Rounds)</button>
      </div>
      <ul class="arena-list" id="arena-list">
        <li class="arena-sub">Launch 4 parallel Managed Agents or run the 3-round Gemini 4 Neon critique loop to watch the verifier score climb.</li>
      </ul>
    `;
    verifier.parentNode.insertBefore(card, verifier);

    document.getElementById("btn-run-agents").addEventListener("click", runAgentRace);
    document.getElementById("btn-run-neon").addEventListener("click", runNeonLoop);
  }

  function renderAgentRows(agents, statusText) {
    const statusEl = document.getElementById("arena-status");
    const listEl = document.getElementById("arena-list");
    if (statusEl && statusText) statusEl.textContent = statusText;
    if (!listEl) return;

    listEl.innerHTML = agents.map((a) => {
      const done = a.status === "completed";
      const sc = a.score || {};
      const badge = !done
        ? `<span class="arena-score">⏳ running…</span>`
        : `<span class="arena-score ${sc.valid ? "ok" : "bad"}">${a.is_winner ? "★ " : ""}${Number(sc.total || 0).toFixed(1)} pts</span>`;
      const meta = done
        ? `${esc(a.fleet_label || "")} · fill ${Number(sc.fill_pct || 0).toFixed(1)}% · ${sc.violation_count || 0} violations${a.via ? ` · ${esc(a.via)}` : ""}`
        : esc(a.persona || "Evaluating packing strategy in sandbox…");
      return `
        <li class="arena-row ${a.is_winner ? "winner" : ""}">
          <div class="arena-row-top">
            <span>${esc(a.name)}</span>
            ${badge}
          </div>
          <div class="arena-sub">${meta}</div>
        </li>
      `;
    }).join("");
  }

  function renderNeonRounds(rounds, modelName) {
    const statusEl = document.getElementById("arena-status");
    const listEl = document.getElementById("arena-list");
    if (statusEl) statusEl.textContent = modelName || "Neon 3-round climb";
    if (!listEl) return;

    const maxScore = Math.max(...rounds.map((r) => (r.score && r.score.valid ? r.score.total : -1)));
    listEl.innerHTML = rounds.map((r) => {
      const sc = r.score || {};
      const isBest = sc.valid && sc.total === maxScore;
      return `
        <li class="arena-row ${isBest ? "winner" : ""}">
          <div class="arena-row-top">
            <span>Round ${esc(r.round)} · ${esc(r.fleet_label)}</span>
            <span class="arena-score ${sc.valid ? "ok" : "bad"}">${isBest ? "★ " : ""}${Number(sc.total || 0).toFixed(1)} pts</span>
          </div>
          <div class="arena-sub">
            ${sc.violation_count || 0} violations · fill ${Number(sc.fill_pct || 0).toFixed(1)}% · LIFO ${Number(sc.lifo_score || 0).toFixed(1)}/10<br>
            ${esc(r.diagnosis || "")}
          </div>
        </li>
      `;
    }).join("");
  }

  async function runAgentRace() {
    const btnA = document.getElementById("btn-run-agents");
    const btnN = document.getElementById("btn-run-neon");
    btnA.disabled = true;
    btnN.disabled = true;

    try {
      if (MOCK) {
        const mockSpecs = [
          { name: "Agent 1 · Naive Volume Baseline", fleet_label: "2 × uhaul_26", via: "raw_py3dbp", score: { total: 0.0, valid: false, fill_pct: 44.7, violation_count: 149 } },
          { name: "Agent 2 · Heavy-First Structural", fleet_label: "3 × uhaul_26", via: "managed_agent", score: { total: 89.7, valid: true, fill_pct: 29.8, violation_count: 0 } },
          { name: "Agent 3 · Penn Station Store & LIFO", fleet_label: "3 × uhaul_26", via: "managed_agent", score: { total: 91.0, valid: true, fill_pct: 29.8, violation_count: 0 } },
          { name: "Agent 4 · Right-Sized Hybrid Fleet", fleet_label: "2 × uhaul_26 + 1 × uhaul_10", via: "managed_agent", is_winner: true, score: { total: 91.3, valid: true, fill_pct: 40.3, violation_count: 0 } },
        ];
        const live = mockSpecs.map((s) => ({ name: s.name, status: "running", persona: "Executing sandbox solver…" }));
        renderAgentRows(live, "0 / 4 finished");
        for (let i = 0; i < mockSpecs.length; i++) {
          await new Promise((r) => setTimeout(r, 480));
          live[i] = { ...mockSpecs[i], status: "completed", is_winner: i === 3 && i === mockSpecs.length - 1 };
          renderAgentRows(live, `${i + 1} / 4 finished`);
        }
        applyWinnerToViewer({ strategy: { truck_id: "uhaul_26", packer_engine: "constrained", downsize_last_truck: true } });
        return;
      }

      const startRes = await origFetch(`${API_BASE}/agents/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: runId }),
      });
      if (!startRes.ok) throw new Error(`HTTP ${startRes.status}`);
      let snap = await startRes.json();
      renderAgentRows(snap.agents || [], `${snap.completed_count || 0} / ${snap.total_count || 4} finished`);

      while (snap.status === "running") {
        await new Promise((r) => setTimeout(r, 550));
        const pollRes = await origFetch(`${API_BASE}/agents/${encodeURIComponent(snap.job_id)}`);
        if (!pollRes.ok) throw new Error(`Poll HTTP ${pollRes.status}`);
        snap = await pollRes.json();
        renderAgentRows(snap.agents || [], `${snap.completed_count || 0} / ${snap.total_count || 4} finished`);
      }

      if (snap.winner) {
        renderAgentRows(snap.agents || [], `Winner: ${snap.winner_name}`);
        applyWinnerToViewer(snap.winner);
      }
    } catch (e) {
      document.getElementById("arena-status").textContent = `Error: ${e.message}`;
    } finally {
      btnA.disabled = false;
      btnN.disabled = false;
    }
  }

  async function runNeonLoop() {
    const btnA = document.getElementById("btn-run-agents");
    const btnN = document.getElementById("btn-run-neon");
    btnA.disabled = true;
    btnN.disabled = true;
    document.getElementById("arena-status").textContent = "Running Neon rounds…";

    try {
      if (MOCK) {
        const mockRounds = [
          { round: 0, fleet_label: "2 × uhaul_20", diagnosis: "Initial unguided seed run before Gemini 4 Neon critique.", score: { total: 0.0, valid: false, fill_pct: 52.1, lifo_score: 3.4, violation_count: 138 } },
          { round: 1, fleet_label: "3 × uhaul_26", diagnosis: "Switched to physics-constrained engine, uhaul_26 ceiling clearance, and 6-store Penn Station routing.", score: { total: 89.7, valid: true, fill_pct: 29.8, lifo_score: 6.8, violation_count: 0 } },
          { round: 2, fleet_label: "3 × uhaul_26", diagnosis: "Aligned truck load sequence with Penn Station dock stops (stop 6 deep -> stop 1 near rear door).", score: { total: 91.0, valid: true, fill_pct: 29.8, lifo_score: 8.5, violation_count: 0 } },
          { round: 3, fleet_label: "2 × uhaul_26 + 1 × uhaul_10", diagnosis: "Right-sized trailing overflow truck to uhaul_10, lifting fleet fill from 29.8% to 40.3%.", score: { total: 91.3, valid: true, fill_pct: 40.3, lifo_score: 8.5, violation_count: 0 } },
        ];
        for (let i = 1; i <= mockRounds.length; i++) {
          renderNeonRounds(mockRounds.slice(0, i), `Round ${i - 1} / 3`);
          await new Promise((r) => setTimeout(r, 420));
        }
        applyWinnerToViewer({ strategy: { truck_id: "uhaul_26", packer_engine: "constrained", downsize_last_truck: true } });
        return;
      }

      const res = await origFetch(`${API_BASE}/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: runId, max_rounds: 3 }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      renderNeonRounds(data.rounds || [], data.model || "Gemini 4 Neon");
      if (data.winner) applyWinnerToViewer(data.winner);
    } catch (e) {
      document.getElementById("arena-status").textContent = `Error: ${e.message}`;
    } finally {
      btnA.disabled = false;
      btnN.disabled = false;
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountPanel);
  } else {
    mountPanel();
  }
})();
