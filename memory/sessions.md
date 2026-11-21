# Sessions

One row per working session, human or agent. Add your row when you start; update its status when you stop. Keep finished rows for today; clear them out after the event.

Status: `active`, `paused`, `done`. "Claims" lists the files or folders you are changing, so other sessions leave them alone.

| Started | Session | Who · tool | Repo · branch | Claims | Status and what's left |
|---|---|---|---|---|---|
| 2026-11-21 09:15 | GitHub repo setup for hackathon | Chris · Claude Code | both repos · `main` | Repo setup, `plan/EVENT_DAY_PLAN.md`, `plan/BUILD_STEPS.md`, `data/` structure, `memory/` | `done` at 11:00. PR #4 merged. Nothing left |
| 2026-11-21 10:46 | Hackathon ingestion pipeline plan | Chris · Claude Code | planning · merged in PR #4 | `plan/INGESTION_SPEC.md` | `paused`. Spec merged in PR #4 |
| 2026-11-21 10:50 | Build the ingestion pipeline (Track A) | Chris · Claude Code | Pack-It-Up · `main` | `backend/llm/`, `backend/ingest/`, `backend/prompts/`, `eval/hand_counts/`; also created `backend/catalog.py` and `data/item_catalog.csv`, which George owns | `done` at 11:18. I0-I7 plus audio (spoken facts, heard-only items, transcribe fallback) pushed to Pack-It-Up `main` (public) at 11:25, up to e3d4c7b. Next: film a real narrated clip; prompt work on missed items |
| 2026-11-21 10:57 | Build plan diagram | Chris · Claude Code | planning · `main` | `plan/build_plan_two_tracks.svg` | `done` at 11:00. Diagram committed to `plan/` and pushed; plan approval logged in decisions.md. Nothing left |
| 2026-11-21 11:05 | Upload and review UI (Track A) | Chris · Claude Code | Pack-It-Up · `main` | `frontend/capture.html`, `frontend/review.html`, `frontend/ui/`, `frontend/mock/`, `plan/UPLOAD_UI_SPEC.md`; one-line static mount in `backend/app.py` (agreed 11:38) | `active` again at 11:38: building the 11:38 decisions (question on capture page, Move/Stays/Sell/Toss, model-only questions hidden, static mount). First pass done 11:35, pushed up to e3d4c7b |
| 2026-11-21 11:16 | Move event-day plans and memory to public repo | Chris · Claude Code | Pack-It-Up · `docs/planning-docs-and-memory` | `plan/`, `memory/`, `AGENTS.md` step 2; planning repo `memory/README.md`, `AGENTS.md` | `done` at 11:25. PR #1 merged; planning repo `memory/` and `AGENTS.md` now point here; private PR #5 closed (spec is in `plan/` here). Nothing left |
| 2026-11-21 11:25 | Gemini skills for agents | Chris · Claude Code | both repos · `main` | `AGENTS.md` in both repos | `done` at 11:45. AGENTS.md has a Gemini API skills section, and `.claude/settings.json` makes Claude Code offer the plugin (Chris approved; force-added past the local `.claude/` exclude). Pushed. Nothing left |
| | George's build sessions | George · Antigravity or other | Pack-It-Up | Track B files: catalog, solver, checker, planner, agents, render, labels, `frontend/` | George to add his row |
