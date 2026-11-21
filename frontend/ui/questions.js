// Question cards, shared by capture.html (top question only) and review.html (all of them).
// Questions are shaped as backend/ingest/gaps.py writes them: options is {key: label} (or a list),
// or null with free_text; free_text "number" alongside options adds a number box; refers_to is an
// item id, a container label or a room id; shown marks the few the server wants the user to see.
(function () {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // Written for the model and pointing at images the user can't see: never an open card for the user
  // (decision 2026-11-21 11:38). The Decisions API's best guess stands; the user can still change it.
  const MODEL_ONLY = new Set(["same_item", "fixture_check"]);
  const ANSWERED_BY = { decisions_api: "Answered by the Decisions API", generate_json_fallback: "Answered by the model",
                        speech: "You said", user: "You answered" };

  // "more" is a prompt for the number box, not an answer the API accepts, so it never becomes a button.
  function options(q) {
    let out = [];
    if (Array.isArray(q.options)) out = q.options.map((o) => ({ key: String(o), label: String(o) }));
    else if (q.options && typeof q.options === "object") out = Object.entries(q.options).map(([key, label]) => ({ key, label: String(label) }));
    return q.free_text ? out.filter((o) => o.key !== "more") : out;
  }
  const isOpen = (q) => (q.status || "open") === "open";
  const guess = (q) => q.suggested ?? (q.model_answer && q.model_answer.answer);
  const label = (q, key) => { const o = options(q).find((x) => x.key === String(key)); return o ? o.label : key; };

  // {open: cards to ask, more: open ones not shown, answered: collapsed rows}
  function pick(qs, max, reopened) {
    qs = qs || [];
    reopened = reopened || new Set();
    const forUser = qs.filter((q) => isOpen(q) && !MODEL_ONLY.has(q.kind));
    const serverPicks = qs.some((q) => "shown" in q);
    let open = serverPicks ? forUser.filter((q) => q.shown) : forUser;
    if (!open.length && forUser.length) open = forUser; // server picked only model-only ones
    // always_show questions (closed cupboards: the demo's "is it full?") come first and don't count toward max
    const always = open.filter((q) => q.always_show);
    open = [...always, ...open.filter((q) => !q.always_show).slice(0, max)];
    const reopenedQs = qs.filter((q) => reopened.has(q.id) && (!isOpen(q) || MODEL_ONLY.has(q.kind)));
    const answered = qs.filter((q) => !reopened.has(q.id) && (!isOpen(q) || MODEL_ONLY.has(q.kind)));
    return { open: [...reopenedQs, ...open.filter((q) => !reopened.has(q.id))], more: forUser.length - open.length, answered };
  }

  // The item or container a question is about, for its thumbnail.
  function target(inv, q) {
    const ref = q.item_id || q.refers_to;
    const items = inv ? inv.rooms.flatMap((r) => r.items) : [];
    const conts = inv ? inv.rooms.flatMap((r) => r.containers || []) : [];
    const it = ref && items.find((i) => i.id === ref);
    if (it) return { ev: it.evidence, label: it.label };
    const c = conts.find((x) => x.id === q.container_id) || conts.find((x) => x.label === q.refers_to);
    if (c) return { ev: c.evidence, label: c.label };
    return { ev: q.evidence, label: q.kind === "include_class" ? "bags" : q.refers_to || q.text };
  }

  // thumbHtml(ev, label) is supplied by the page (it knows the run and the API).
  function cardHtml(q, { busy, thumbHtml, inv }) {
    const t = target(inv, q);
    const opts = options(q);
    const g = guess(q);
    const conf = q.model_answer && q.model_answer.confidence;
    const dis = busy ? "disabled" : "";
    let body = "";
    if (opts.length) {
      body += `<div class="opts">${opts.map((o) =>
        `<button class="btn${o.key === g ? " guess" : ""}" type="button" data-opt="${esc(o.key)}" ${dis}${q.answer === o.key ? ' aria-pressed="true"' : ""}>${esc(o.label)}${
          o.key === g ? `<small>best guess${conf != null ? ` · ${Math.round(conf * 100)}%` : ""}</small>` : ""}</button>`).join("")}</div>`;
    }
    if (!opts.length || q.free_text) {
      const num = q.free_text === "number";
      body += `<form class="opts free" data-free><input type="${num ? "number" : "text"}" ${num ? 'inputmode="numeric" min="0"' : ""} name="a" required
          placeholder="${opts.length ? "Other number" : "Type your answer"}" ${dis}><button class="btn primary" ${dis}>Save</button></form>`;
    }
    return `<div class="card q" data-q="${esc(q.id)}">
      <div class="row">${thumbHtml(t.ev, t.label)}
        <div><div class="kind">${esc((q.kind || "").replace(/_/g, " "))}</div>
        <div class="text clamp" data-clamp>${esc(q.user_text || q.text)}</div></div></div>
      ${body}
    </div>`;
  }

  function answeredHtml(q) {
    let who, val;
    if (isOpen(q)) { // model-only question still open: both decide() paths failed (model_error), or an older run
      who = "Decisions API best guess";
      val = guess(q) != null ? `<b>${esc(label(q, guess(q)))}</b>` : q.model_error ? "the model couldn't decide" : "none yet";
    } else {
      who = ANSWERED_BY[q.answered_by] || "Answered";
      // below 0.7 the server still applies model-only answers, flagged low_confidence: say it's a guess
      if (q.low_confidence) who = q.answered_by === "generate_json_fallback" ? "Model's best guess" : "Decisions API best guess";
      val = q.answered_by === "speech" && q.quote ? `<q>${esc(q.quote)}</q>` : `<b>${esc(label(q, q.answer))}</b>`;
    }
    return `<div class="card q answered" data-q="${esc(q.id)}">
      <div class="text clamp" data-clamp>${esc(q.user_text || q.text)}</div>
      <div class="small muted">${esc(who)}: ${val}
      <button class="btn link" type="button" data-reopen>Change</button></div></div>`;
  }

  // Wire up every card in host. onAnswer(q, value); onReopen(q).
  function bind(host, qs, { onAnswer, onReopen }) {
    host.querySelectorAll("[data-q]").forEach((card) => {
      const q = (qs || []).find((x) => x.id === card.dataset.q);
      if (!q) return;
      card.querySelectorAll("[data-opt]").forEach((b) => b.addEventListener("click", () => onAnswer(q, b.dataset.opt)));
      const form = card.querySelector("[data-free]");
      if (form) form.addEventListener("submit", (e) => { e.preventDefault(); const v = form.a.value.trim(); if (v) onAnswer(q, v); });
      const re = card.querySelector("[data-reopen]");
      if (re && onReopen) re.addEventListener("click", () => onReopen(q));
      card.querySelectorAll("[data-clamp]").forEach((el) => el.addEventListener("click", () => el.classList.toggle("clamp")));
    });
  }

  window.PIU_Q = { MODEL_ONLY, options, isOpen, guess, label, pick, target, cardHtml, answeredHtml, bind, esc };
})();
