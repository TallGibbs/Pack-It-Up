# Sessions

One row per working session, human or agent. Add your row when you start; update its status when you stop. Keep finished rows for today; clear them out after the event.

Status: `active`, `paused`, `done`. "Claims" lists the files or folders you are changing, so other sessions leave them alone.

| Started | Session | Who · tool | Repo · branch | Claims | Status and what's left |
|---|---|---|---|---|---|
| 2026-11-21 09:15 | GitHub repo setup for hackathon | Chris · Claude Code | both repos · `main` | Repo setup, `plan/EVENT_DAY_PLAN.md`, `plan/BUILD_STEPS.md`, `data/` structure, `memory/` | `done` at 11:00. PR #4 merged. Nothing left |
| 2026-11-21 10:46 | Hackathon ingestion pipeline plan | Chris · Claude Code | planning · merged in PR #4 | `plan/INGESTION_SPEC.md` | `paused`. Spec merged in PR #4 |
| 2026-11-21 10:50 | Build the ingestion pipeline (Track A) | Chris · Claude Code | Pack-It-Up · `main` | `backend/llm/`, `backend/ingest/`, `backend/prompts/`, `eval/hand_counts/`; also created `backend/catalog.py` and `data/item_catalog.csv`, which George owns | `active` at 11:45. I0-I7, audio, and the 11:30 in-person corrections (hand count, Decisions grading, closed containers, count options, prompt v3, model-only questions) pushed to `main`. Next: more runs per prompt to separate prompt effect from run-to-run variation |
| 2026-11-21 10:57 | Build plan diagram | Chris · Claude Code | planning · `main` | `plan/build_plan_two_tracks.svg` | `done` at 11:00. Diagram committed to `plan/` and pushed; plan approval logged in decisions.md. Nothing left |
| 2026-11-21 11:05 | Upload and review UI (Track A) | Chris · Claude Code | Pack-It-Up · `main` | `frontend/capture.html`, `frontend/review.html`, `frontend/ui/`, `frontend/mock/`, `plan/UPLOAD_UI_SPEC.md`; `/app` static mount in `backend/app.py` | `done` at 11:43. The 11:38 decisions are built (2d9cd36, 31233f6). Left: Chris runs the LAN `/health` check from his phone and installs `cloudflared` as backup; the API must be restarted with `--host 0.0.0.0` to serve `/app`; George confirms the `index.html?run_id=` handoff |
| 2026-11-21 11:16 | Move event-day plans and memory to public repo | Chris · Claude Code | Pack-It-Up · `docs/planning-docs-and-memory` | `plan/`, `memory/`, `AGENTS.md` step 2; planning repo `memory/README.md`, `AGENTS.md` | `done` at 11:25. PR #1 merged; planning repo `memory/` and `AGENTS.md` now point here; private PR #5 closed (spec is in `plan/` here). Nothing left |
| 2026-11-21 11:25 | Gemini skills for agents | Chris · Claude Code | both repos · `main` | `AGENTS.md` in both repos | `done` at 11:45. AGENTS.md has a Gemini API skills section, and `.claude/settings.json` makes Claude Code offer the plugin (Chris approved; force-added past the local `.claude/` exclude). Pushed. Nothing left |
| | George's build sessions | George · Antigravity or other | Pack-It-Up | Track B files: catalog, solver, checker, planner, agents, render, labels, `frontend/` | George to add his row |
