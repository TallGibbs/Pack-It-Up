# Hackathon Learnings (Gemini 4 NYC · Nov 21, 2026)

Distilled from `FAILURES.md`, `memory/decisions.md`, `eval/RESULTS.md`, and `AGENTS.md` during the **Pack It Up** build.

---

## 1. Gemini 4 API & SDK Gotchas

- **Use `google-genai`, never the deprecated `google-generativeai`.** Centralize all model calls behind a single module (`backend/llm/`) with a `models.toml` job-to-model mapping (`for_job("<job>")`) so models and API versions can be swapped without touching feature code.
- **API versions matter (`v1` vs `v1beta` vs `v1alpha`):**
  - `google-genai >= 3.0.0` defaults `genai.Client()` to `v1`.
  - `gemini-decision-1` (Decisions API) was only listed under `api_version = "v1alpha"` (returning 404 on `v1beta`). Always keep a generic `generate_json` fallback job (`gemini-4-hydrogen`).
  - `gemini-3.8-flash-tts` and `gemini-omni-1.2-flash` were only listed under `api_version = "v1beta"` (404 on `v1`).
  - `gemini-3.5-transcribe` was not in the event key's model list; `gemini-4-hydrogen` handles audio transcription natively.
- **Prompt & output hygiene:**
  - Models can leak reasoning into short label fields; trim/clean labels (e.g., `clean_label()` trimming over 60 chars at parentheses/dashes).
  - Never ask a vision/decisions model to guess what footage cannot show (e.g., fullness of closed cabinets). Assume empty, flag it, and ask the user directly.
  - Keep a deterministic checker/verifier in the loop (`backend/verify.py`): `gemini-4-neon` planner loops can mispredict whether a setting change helps, so the verifier—not the model—must pick the winning plan.
- **Gemini-generated presentation assets:** Using `for_job(...)` + a facts-only brief + an automated number checker (failing if any number in the generated output isn't in the brief) keeps slides, narration, and video grounded in `eval/RESULTS.md`.

---

## 2. 3D Bin Packing, Physics & Labels (`Track B`)

- **Stock `py3dbp` breaks real-world moving rules:** Across 26 moves in `eval/RESULTS.md`, raw `py3dbp` broke 298 rules (mean 11.5 per move: floating/unsupported items, `no_stack` violations, tipped upright items, L/R weight imbalance), whereas the physics-constrained solver (`backend/solver.py`) achieved **26 of 26 valid (0 violations)**.
- **Walk-in tier-by-tier loading:** Sorting `load_seq` by `(z, x, y)` loads the entire floor before upper tiers, requiring movers to step on lower boxes. Use a support-DAG topological sort ordered by floor-standing plane `stand_x`, door-flush stacking anchors, and an arm's-reach setback cap (`<= 24 in`).
- **Avoid "Jenga tower" stacking on sparse loads:** Negative stacking bonuses can beat floor cost (`z=0`) and stack 4 boxes into an unbraced 64-in tower. Replace with gravitational potential energy (`U = m * g * z_cm`) floor-first packing when floor utilization is `<= 50%`, plus `0.45g` shake/topple slenderness limits and auto-sizing down to a 9 ft Cargo Van (`uhaul_van`).
- **U-Haul bedroom rule vs. actual load:** Across 26 venue-room moves, U-Haul's room-count rule picked a truck that was too small on 18 moves (8 of 16 unique sets).
- **Scannable QR codes:** Decorative hash grids won't scan on phone cameras; use a real ISO/IEC 18004 Reed-Solomon encoder (Versions 1–14, 4-module quiet zone) and place box QR labels on **top flaps only** (not sides).

---

## 3. External Integrations (Shopify MCP & NYC Open Data)

- **Shopify `mcp.shop.com` (`ShopMCPClient`):**
  - Requires `MCP-Protocol-Version: 2026-07-28`, `Mcp-Method: tools/call`, `Mcp-Name: <tool>`, and `_meta` fields (`io.modelcontextprotocol/protocolVersion`, `io.modelcontextprotocol/clientCapabilities`).
  - Catalog searches for moving boxes can return tiny jewelry mailers; enforce dimension/pack-size guardrails, NYC `ships_to` filtering, and store consolidation (dropping a store when moving items to an existing store costs less than ~$15 shipping).
- **NYC DOT Live Traffic (Socrata):** Sorting multi-year archives on unindexed `data_as_of DESC` times out. Sort by Socrata's primary row index (`$order=:id DESC`) instead.

---

## 4. Web, Tunneling, Media & Concurrency

- **Cloudflare edge caching:** Without `Cache-Control: no-cache` on static frontend assets (and cache-busting `?v=` query strings), Cloudflare can serve stale JS/CSS against fresh HTML and break the app.
- **Cloudflare 100 MB request limit:** Enforce a `< 95 MB` per-request cap in the browser and batch multi-file uploads to avoid `413` errors on mobile video uploads.
- **Media frame extraction (`ffmpeg`):** Asking `ffmpeg` for a timestamp past a short clip's duration exits with an error; catch failures without `check=True` and fall back to the last half-second.
- **Windows file-locking & async routes:**
  - `os.replace` raises `PermissionError` under concurrent reads on Windows; retry briefly in `write_json`/`read_json`.
  - Keep blocking file/hash/ffmpeg intake routes as plain `def` (so FastAPI runs them in worker threads) rather than `async def` blocking the event loop.
- **Stable item IDs:** Never key user edits (`Toss`/`Sell`/counts) by sorted list position—a new photo in the room renumbers the list and moves edits to the wrong item. Key items by stable group IDs.
- **Duplicate route & DOM mount checks:** Add a test asserting no `(method, path)` is registered twice in FastAPI, and defer initial `fetch` calls until `DOMContentLoaded` when panel scripts wrap `fetch`.

---

## 5. Multi-Agent & Hackathon Workflow

- **Two-track ownership + `memory/`:** Splitting ownership (`Track A` vs `Track B` in `AGENTS.md`) and maintaining `memory/decisions.md`, `memory/sessions.md`, and `FAILURES.md` prevented parallel agent sessions from overwriting each other.
- **Git worktrees:** Isolated worktrees kept parallel features clean before merging into `main`.
- **Keep secrets and media out of git:** `.env`, `runs/`, `.cache/`, and `data/Inputs/` stayed git-ignored so the public repo remained safe to share.
