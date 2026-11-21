// Pack It Up: API client and the helpers both pages share (Track A). Everything is on window.PIU.
// Real server by default (same origin, or ?api=http://host:port); ?mock=1 uses frontend/mock/mock-api.js.
// Routes: see backend/ingest/api.py.
(function () {
  "use strict";
  const params = new URLSearchParams(location.search);
  const MOCK = params.get("mock") === "1";
  const API_BASE = (params.get("api") || "").replace(/\/+$/, "") || location.origin;

  // ---------- small helpers ----------
  const $ = (selector, el = document) => el.querySelector(selector);
  // Every piece of server or user text that goes into innerHTML passes through this.
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // A clip rather than a photo? By MIME type when the browser gives one, else by extension.
  const isVideo = (name, type) => /^video\//.test(type || "") || /\.(mp4|mov|m4v)$/i.test(name || "");

  // Boxes a container's contents are estimated to need: est_boxes is {box_medium: 2, ...}.
  const boxCount = (container) => Object.values(container.est_boxes || {}).reduce((a, n) => a + n, 0);
  // ...and across a whole inventory. Small loose things are boxed, not listed as items.
  const totalBoxes = (inv) => inv.rooms.flatMap((r) => r.containers || []).reduce((a, c) => a + boxCount(c), 0);

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

  // The server's `detail` is a sentence for our own errors, but a list of {msg, loc} for a request
  // FastAPI rejected itself (422); that list used to reach the page as "[object Object]".
  function detailText(detail, fallback) {
    if (typeof detail === "string" && detail) return detail;
    if (Array.isArray(detail) && detail.length) return detail.map((d) => (d && d.msg) || "").filter(Boolean).join("; ") || fallback;
    return fallback;
  }

  // True when the API is this laptop or a LAN address. Any other address reaches it through
  // Cloudflare (the demo tunnel), which refuses a request body over 100 MB.
  const API_HOST = (() => { try { return new URL(API_BASE).hostname; } catch (e) { return location.hostname; } })();
  const LOCAL_API = /^(localhost|127\.|\[::1\]|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)|\.(local|localhost|test)$/i.test(API_HOST);

  async function json(method, path, body) {
    let res;
    try {
      res = await fetch(API_BASE + path, {
        method,
        headers: body ? { "Content-Type": "application/json" } : {},
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch (e) { // fetch's own text is "Load failed" on iPhone, "Failed to fetch" elsewhere
      throw new Error("no connection");
    }
    if (!res.ok) {
      let detail = res.statusText || `error ${res.status}`;
      try { detail = detailText((await res.json()).detail, detail); } catch (e) { /* not json */ }
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
        files = (files || []).filter(Boolean);
        if (!files.length) return reject(new Error("No file to send. Choose it again.")); // never a request with no files (FAILURES.md 12:05)
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
          else if (xhr.status === 413) reject(new Error("Too big to send in one go (100 MB limit). Use a shorter clip."));
          else reject(new Error(detailText(data && data.detail, `Upload failed (${xhr.status || "network"}).`)));
        };
        // Airplane mode, a dropped signal, or the server stopped: the same words fit all three.
        xhr.onerror = () => reject(new Error("No connection. Check your signal, then tap Retry."));
        xhr.send(fd);
      });
    },
    getRun: (runId) => json("GET", `/runs/${encodeURIComponent(runId)}`),
    answer: (runId, questionId, answer) =>
      json("POST", `/answer/${encodeURIComponent(runId)}`, { question_id: questionId, answer }),
    patchItem: (runId, itemId, changes) =>
      json("PATCH", `/inventory/${encodeURIComponent(runId)}/items/${encodeURIComponent(itemId)}`, changes),
    // item: {room, catalog_id, quantity} or, for something not in the catalog, {room, label, dims_in: [L, W, H], quantity}
    addItem: (runId, item) => json("POST", `/inventory/${encodeURIComponent(runId)}/items`, item),
    // [{id, name, category, dims_in}]: what "Add an item" offers
    getCatalog: () => json("GET", "/catalog").then((r) => r.items),
    cropUrl(runId, ev, size, label) {
      if (!ev || !ev.sha256) return placeholder(label, tileKind(ev));
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

  // ---------- thumbnails ----------
  // Evidence is {source, sha256, kind, timestamp_s, box_2d}. With no file hash there is nothing to
  // crop: the item was only heard on a soundtrack (mic tile), or the user added it (initials tile).
  // A box means it was seen, even if the file's hash is missing (older inventories: a cupboard in a
  // room with no listed items got the mic tile).
  const tileKind = (ev) => (ev && ev.kind !== "user" && !ev.sha256 && !ev.box_2d ? "audio" : ev && ev.kind);

  // Container evidence carries the file name but not its hash; borrow the hash from an item seen in the same file.
  function withSha(inv, ev) {
    if (!ev || ev.sha256 || !ev.source || !ev.box_2d || !inv) return ev; // no box: heard-only, keep the mic tile
    const hit = inv.rooms.flatMap((r) => r.items).find((i) => i.evidence && i.evidence.source === ev.source && i.evidence.sha256);
    return hit ? { ...ev, sha256: hit.evidence.sha256, kind: ev.kind || hit.evidence.kind } : ev;
  }

  // <img> for an item's or container's evidence: the server's crop, or a placeholder tile if that fails.
  function thumbHtml(runId, inv, ev, label, { size = 160, lazy = false } = {}) {
    ev = withSha(inv, ev);
    const fallback = placeholder(label, tileKind(ev));
    const src = window.PIU.api.cropUrl(runId, ev, size, label);
    return `<img class="thumb"${lazy ? ' loading="lazy"' : ""} alt="" src="${esc(src)}" onerror="this.onerror=null;this.src='${fallback}'">`;
  }

  window.PIU = {
    MOCK,
    API_BASE,
    LOCAL_API,
    params,
    $,
    esc,
    isVideo,
    boxCount,
    totalBoxes,
    link,
    placeholder,
    tileKind,
    thumbHtml,
    rememberRun: (id) => remember(RUN_KEY, id),
    lastRun: () => recall(RUN_KEY),
    forgetRun: () => forget(RUN_KEY),
    api: MOCK ? window.PIU_MOCK : real,
  };
  if (MOCK && !window.PIU_MOCK) console.error("?mock=1 needs mock/mock-api.js loaded before ui/api.js");
})();
