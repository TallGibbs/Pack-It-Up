# Sessions

One row per working session, human or agent. Add your row when you start; update its status when you stop. Keep finished rows for today; clear them out after the event.

Status: `active`, `paused`, `done`. "Claims" lists the files or folders you are changing, so other sessions leave them alone.

| Started | Session | Who · tool | Repo · branch | Claims | Status and what's left |
|---|---|---|---|---|---|
| 2026-11-21 09:15 | GitHub repo setup for hackathon | Chris · Claude Code | both repos · `main` | Repo setup, `plan/EVENT_DAY_PLAN.md`, `plan/BUILD_STEPS.md`, `data/` structure, `memory/` | `done` at 11:00. PR #4 merged. Nothing left |
| 2026-11-21 10:46 | Hackathon ingestion pipeline plan | Chris · Claude Code | planning · merged in PR #4 | `plan/INGESTION_SPEC.md` | `paused`. Spec merged in PR #4 |
| 2026-11-21 10:50 | Build the ingestion pipeline (Track A) | Chris · Claude Code | Pack-It-Up · `main` | `backend/llm/`, `backend/ingest/`, `backend/prompts/`, `eval/hand_counts/`; also created `backend/catalog.py` and `data/item_catalog.csv`, which George owns | `active`. At 11:08: I0, I1, I2 committed in Pack-It-Up (not pushed); I3 merge in progress. AGENTS/CLAUDE/GEMINI.md committed there too |
| 2026-11-21 10:57 | Build plan diagram | Chris · Claude Code | planning · `main` | `plan/build_plan_two_tracks.svg` | `done` at 11:00. Diagram committed to `plan/` and pushed; plan approval logged in decisions.md. Nothing left |
| 2026-11-21 11:05 | Upload and review UI (Track A) | Chris · Claude Code | planning · `plan/upload-ui-spec`; Pack-It-Up · `main` | `plan/UPLOAD_UI_SPEC.md`; in Pack-It-Up new files only: `frontend/capture.html`, `frontend/review.html`, `frontend/ui/`, `frontend/mock/`, README "Open the pages" section | `active`. Writing spec, then building against a mock API |
| 2026-11-21 11:16 | Move event-day plans and memory to public repo | Chris · Claude Code | Pack-It-Up · `docs/planning-docs-and-memory` | `plan/`, `memory/`, `AGENTS.md` step 2; planning repo `memory/README.md`, `AGENTS.md` | `active`. PR open in Pack-It-Up; after merge, point the planning repo here |
| | George's build sessions | George · Antigravity or other | Pack-It-Up | Track B files: catalog, solver, checker, planner, agents, render, labels, `frontend/` | George to add his row |
