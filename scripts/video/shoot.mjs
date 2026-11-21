// Records the running app in headless Chrome through the DevTools protocol, for the submission video.
// Node 22+ (built-in fetch and WebSocket). Called by build.py:  node shoot.mjs <jobs.json> <chrome profile dir>
// jobs.json = [{id, url, width, height, dsf, mobile, wait_ms, steps:[{js}], mode:"record"|"still", out_dir, expect, read}]
// For each job, writes to out_dir: frames/NNNNN.jpg (record mode), still.png, meta.json
//   meta = {frames:[{f, t}], start_t, end_t, still, checks:[{...expect, ok, got}], read:{name: text}, errors:[]}
// Steps run in the page; helpers are on window.__v (sleep, scrollTo, scrollBy, scrollToText, click, clickText, waitFor).
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const jobs = JSON.parse(readFileSync(process.argv[2], "utf8"));
const PROFILE = process.argv[3];
const PORT = 9334;
const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const chrome = spawn(CHROME, [
  "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${PROFILE}`,
  "--hide-scrollbars", "--no-first-run", "--ignore-gpu-blocklist", "--enable-unsafe-swiftshader",
  "--allow-file-access-from-files", "about:blank",
], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const HELPERS = `window.__v = {
  sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
  ease: (t) => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2,
  scrollTo(y, ms) {
    const y0 = window.scrollY, max = document.documentElement.scrollHeight - innerHeight;
    const y1 = Math.max(0, Math.min(max, y)), t0 = performance.now();
    if (!ms || ms < 20) { window.scrollTo(0, y1); return Promise.resolve(y1); }
    return new Promise((res) => { const f = (now) => { const k = Math.min(1, (now - t0) / ms);
      window.scrollTo(0, y0 + (y1 - y0) * __v.ease(k)); k < 1 ? requestAnimationFrame(f) : res(y1); };
      requestAnimationFrame(f); });
  },
  scrollBy(dy, ms) { return __v.scrollTo(window.scrollY + dy, ms); },
  find(text) {
    const all = [...document.querySelectorAll('body *')].filter((e) => e.offsetParent !== null || e.tagName === 'SUMMARY');
    return all.find((e) => e.children.length === 0 && e.textContent.trim().includes(text))
        || all.reverse().find((e) => e.textContent.includes(text));
  },
  scrollToText(text, offset, ms) {
    const el = __v.find(text); if (!el) throw new Error('text not found: ' + text);
    return __v.scrollTo(el.getBoundingClientRect().top + window.scrollY - (offset || 0), ms);
  },
  click(sel) { const el = document.querySelector(sel); if (!el) throw new Error('no element ' + sel); el.click(); return sel; },
  clickText(text) { const el = __v.find(text); if (!el) throw new Error('text not found: ' + text); el.click(); return text; },
  waitFor(fn, timeout) { const t0 = Date.now(); return new Promise((res, rej) => { const iv = setInterval(() => {
      let ok = false; try { ok = fn(); } catch (e) {}
      if (ok) { clearInterval(iv); res(Math.round((Date.now() - t0) / 100) / 10); }
      else if (Date.now() - t0 > timeout) { clearInterval(iv); rej(new Error('timed out after ' + timeout + ' ms')); } }, 100); });
  },
};`;

async function target() {
  for (let i = 0; i < 60; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch (e) { /* not up yet */ }
    await sleep(250);
  }
  throw new Error("Chrome did not start");
}

const ws = new WebSocket(await target());
await new Promise((r) => (ws.onopen = r));
let id = 0;
const pending = new Map();
let onFrame = null;
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  else if (msg.method === "Page.screencastFrame" && onFrame) onFrame(msg.params);
};
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const n = ++id;
  pending.set(n, (msg) => (msg.error ? reject(new Error(method + ": " + msg.error.message)) : resolve(msg.result)));
  ws.send(JSON.stringify({ id: n, method, params }));
});
const evaluate = async (js) => {
  const r = await send("Runtime.evaluate", { expression: js, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result?.value;
};

await send("Page.enable");
await send("Runtime.enable");
await send("Page.addScriptToEvaluateOnNewDocument", { source: HELPERS });

for (const job of jobs) {
  const out = job.out_dir;
  mkdirSync(join(out, "frames"), { recursive: true });
  const meta = { id: job.id, frames: [], start_t: null, end_t: null, still: null, checks: [], read: {}, errors: [] };
  try {
    await send("Emulation.setDeviceMetricsOverride", { width: job.width, height: job.height, deviceScaleFactor: job.dsf, mobile: !!job.mobile });
    await send("Page.navigate", { url: job.url });
    await sleep(job.wait_ms || 3500);
    let n = 0;
    if (job.mode === "record") {
      onFrame = (p) => {
        const f = `frames/${String(n++).padStart(5, "0")}.jpg`;
        writeFileSync(join(out, f), Buffer.from(p.data, "base64"));
        meta.frames.push({ f, t: p.metadata.timestamp });
        send("Page.screencastFrameAck", { sessionId: p.sessionId }).catch(() => {});
      };
      await send("Page.startScreencast", { format: "jpeg", quality: 90, maxWidth: Math.round(job.width * job.dsf), maxHeight: Math.round(job.height * job.dsf), everyNthFrame: 1 });
      meta.start_t = Date.now() / 1000;
    }
    for (const step of job.steps || []) {
      try { const v = await evaluate(step.js); if (v !== undefined) console.log(`  ${job.id}:`, JSON.stringify(v).slice(0, 200)); }
      catch (e) { meta.errors.push(String(e.message || e).slice(0, 300)); console.log(`  ${job.id} step error:`, e.message); }
    }
    if (job.mode === "record") {
      meta.end_t = Date.now() / 1000;
      await send("Page.stopScreencast");
      await sleep(200);
      onFrame = null;
    }
    const png = await send("Page.captureScreenshot", { format: "png" });
    writeFileSync(join(out, "still.png"), Buffer.from(png.data, "base64"));
    meta.still = "still.png";
    for (const [name, sel] of Object.entries(job.read || {})) {
      meta.read[name] = await evaluate(`(document.querySelector(${JSON.stringify(sel)})||{}).textContent || ''`);
    }
    for (const ex of job.expect || []) {
      const got = await evaluate(ex.selector
        ? `(document.querySelector(${JSON.stringify(ex.selector)})||{}).textContent || ''`
        : `document.body.innerText`);
      meta.checks.push({ ...ex, ok: String(got).includes(ex.text), got: ex.selector ? String(got).slice(0, 200) : undefined });
    }
  } catch (e) {
    meta.errors.push(String(e.message || e).slice(0, 300));
  }
  writeFileSync(join(out, "meta.json"), JSON.stringify(meta, null, 1));
  console.log(`saved ${job.id}: ${meta.frames.length} frames, ${meta.errors.length} errors, checks ${meta.checks.map((c) => (c.ok ? "ok" : "FAIL")).join(",") || "-"}`);
}
ws.close();
chrome.kill();
