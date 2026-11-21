// Pack It Up: API client for the capture and review pages (Track A).
// Real server by default (same origin, or ?api=http://host:port); ?mock=1 uses frontend/mock/mock-api.js.
// Routes: see backend/ingest/api.py.
(function () {
  "use strict";
  const params = new URLSearchParams(location.search);
  const MOCK = params.get("mock") === "1";
  const API_BASE = (params.get("api") || "").replace(/\/+$/, "") || location.origin;

  function store(kind) {
    try { return window[kind]; } catch (e) { return null; }
  }
  function remember(key, value) {
    try { store("localStorage").setItem(key, value); } catch (e) { /* private mode */ }
  }
  function recall(key) {
    try { return store("localStorage").getItem(key); } catch (e) { return null; }
  }
  function forget(key) {
    try { store("localStorage").removeItem(key); } catch (e) { /* private mode */ }
  }
  // The last move this browser was in. Mock runs are kept apart: they don't exist on the server.
  const RUN_KEY = "piu_last_run" + (MOCK ? "_mock" : "");

  // Link to another page, keeping ?mock and ?api.
  function link(page, extra) {
    const q = new URLSearchParams();
    if (MOCK) q.set("mock", "1");
    if (params.get("api")) q.set("api", params.get("api"));
    Object.entries(extra || {}).forEach(([k, v]) => v != null && q.set(k, v));
    const s = q.toString();
    return page + (s ? "?" + s : "");
  }

  async function json(method, path, body) {
    const res = await fetch(API_BASE + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch (e) { /* not json */ }
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    return res.json();
  }

  const real = {
    // POST /upload with XHR, because fetch has no upload progress.
    upload(files, room, runId, onProgress) {
      return new Promise((resolve, reject) => {
        const fd = new FormData();
        files.forEach((f) => fd.append("files", f, f.name));
        fd.append("room", room);
        if (runId) fd.append("run_id", runId);
        const xhr = new XMLHttpRequest();
        xhr.open("POST", API_BASE + "/upload");
        xhr.upload.onprogress = (e) => e.lengthComputable && onProgress && onProgress(e.loaded / e.total);
        xhr.onload = () => {
          let data = null;
          try { data = JSON.parse(xhr.responseText); } catch (e) { /* not json */ }
          if (xhr.status >= 200 && xhr.status < 300 && data) resolve(data);
          else reject(new Error((data && data.detail) || `upload failed (${xhr.status || "network"})`));
        };
        xhr.onerror = () => reject(new Error("Couldn't reach the server. Is the phone on the same network, or using the tunnel address?"));
        xhr.send(fd);
      });
    },
    getRun: (runId) => json("GET", `/runs/${encodeURIComponent(runId)}`),
    answer: (runId, questionId, answer) =>
      json("POST", `/answer/${encodeURIComponent(runId)}`, { question_id: questionId, answer }),
    patchItem: (runId, itemId, changes) =>
      json("PATCH", `/inventory/${encodeURIComponent(runId)}/items/${encodeURIComponent(itemId)}`, changes),
    cropUrl(runId, ev, size, label) {
      if (!ev || !ev.sha256) return placeholder(label, ev && ev.kind);
      const q = new URLSearchParams({ size: String(size || 160) });
      if (ev.box_2d) q.set("box", ev.box_2d.join(","));
      if (ev.timestamp_s != null) q.set("t", String(ev.timestamp_s));
      return `${API_BASE}/media/${encodeURIComponent(runId)}/${ev.sha256.slice(0, 16)}/crop?${q}`;
    },
  };

  // Grey tile with the item's initials; used for heard-only items, mock mode and failed crops.
  function placeholder(label, kind) {
    const words = String(label || "?").replace(/[^\p{L}\p{N} ]/gu, "").split(/\s+/).filter(Boolean);
    const initials = (words[0] || "?")[0] + ((words[1] || "")[0] || "");
    let h = 0;
    for (const c of String(label || "")) h = (h * 31 + c.charCodeAt(0)) % 360;
    const glyph = kind === "audio" ? "\u{1F3A4}" : initials.toUpperCase();
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="10" fill="hsl(${h},35%,62%)"/><text x="32" y="40" font-family="system-ui,sans-serif" font-size="22" font-weight="600" text-anchor="middle" fill="#fff">${glyph}</text></svg>`;
    return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  }

  window.PIU = {
    MOCK,
    API_BASE,
    params,
    link,
    placeholder,
    rememberRun: (id) => remember(RUN_KEY, id),
    lastRun: () => recall(RUN_KEY),
    forgetRun: () => forget(RUN_KEY),
    api: MOCK ? window.PIU_MOCK : real,
  };
  if (MOCK && !window.PIU_MOCK) console.error("?mock=1 needs mock/mock-api.js loaded before ui/api.js");
})();
