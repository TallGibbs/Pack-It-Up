# frontend

The phone pages for Track A: film or pick photos and clips, watch them being processed, check the inventory, hand it to the packing plan. Plain HTML and JS, no build step, no framework. The spec is [plan/UPLOAD_UI_SPEC.md](../plan/UPLOAD_UI_SPEC.md). Track B's 3D view (`index.html`) is not in the repo yet.

**Edits here are live.** `backend/app.py` serves this folder at `/app` straight from the working tree, so a saved file is on the demo address at once. Try changes with `?mock=1` first.

## Files

| File | What it does |
|---|---|
| `capture.html` | Room cards, upload queue, per-file progress, the top open question, footer links to review and the plan |
| `review.html` | Totals bar, question cards, item list with quantity and Move / Stays / Sell / Toss, handoff button |
| `ui/api.js` | `window.PIU`: the API client (real server or mock), page links, the last-run memory, placeholder thumbnails |
| `ui/questions.js` | `window.PIU_Q`: which questions to show, question card HTML, click wiring. Used by both pages |
| `ui/style.css` | Shared styles, phone first |
| `mock/mock-api.js` | `window.PIU_MOCK`: the same five API methods, run in the browser from `mock/inventory.json` |

Each page loads `mock/mock-api.js`, then `ui/api.js`, then `ui/questions.js`, then its own inline script. The order matters: `api.js` picks the mock when the URL has `?mock=1`.

## Rules the code follows

- **The server's reply is the state.** `POST /answer` and `PATCH …/items/{id}` return the whole inventory, and `GET /runs/{run_id}` returns status plus inventory. Pages re-render from the reply and keep only small pending state (a quantity being typed, a request in flight).
- **Every API method exists twice:** in `real` in `ui/api.js` and in `PIU_MOCK`. Add or change both, with the same arguments and reply shape. Routes are listed at the top of `backend/ingest/api.py`.
- **Links between pages go through `PIU.link(page, {run_id})`** so `?mock=1` and `?api=` carry over.
- **Text from the server or the user goes through `esc()` or `textContent`**, never straight into `innerHTML`.

## What a "move" is

The pages say "move"; the API and the disk say "run". One move is one `run_id`, one folder `runs/<run_id>/` on the server, and any number of rooms.

- The server makes the `run_id` on the first `POST /upload` that arrives without one. Later uploads from the same page send it back, which adds files or rooms to the same move.
- `capture.html` keeps the `run_id` in a script variable only. Reloading the page, or opening it from review's "Film another room" link, starts with no run, so the next upload starts a new move.
- `review.html` takes the run from `?run_id=`, or else from the last run this browser saw (`localStorage` key `piu_last_run`).
- There is no login. Anyone with a `run_id` can read and edit that move.

## URL parameters

| Parameter | Pages | Effect |
|---|---|---|
| `?mock=1` | both | No server: the mock answers, with invented items |
| `?api=http://host:port` | both | Call an API on another origin (page work with `python -m http.server`) |
| `?run_id=…` | `review.html` | Which move to show |
