# Decisions

Append only, newest at the bottom. Format:

```
## 2026-11-21 10:58 · Short title
- **Decision:** what was decided
- **Why:** the reason
- **By:** who decided or agreed (Chris, George, both, organizers)
- **Replaces:** the earlier entry it overrides, if any
- **See:** links to the plan, spec, PR or commit
```

Entries before 11:00 on Nov 21 were written up afterwards from session notes, so their times are approximate.

---

## 2026-11-20 · Build the moving planner
- **Decision:** Our hackathon project is the moving planner ("Pack Perfect", now named Pack It Up): photos and video of a home in, labelled boxes, a truck size and a checked load order out.
- **Why:** Fits the winning pattern (messy real input, agents, a verifier, a score climbing on screen), and the research found the back half of the pipeline nearly empty.
- **By:** Both. The idea came from George.
- **See:** the planning repo's `README.md` and `plan/BUILD_PLAN.md` (pre-event; kept in the private planning repo)

## 2026-11-21 ~09:00 · Problem Statement Two: Element 119
- **Decision:** We enter under Problem Statement Two (Element 119). At least two Gemini 4 models with clear jobs, plus the Decisions API.
- **Why:** The posted rules. Video and images are the core input and generated media is part of the output.
- **By:** Both.
- **See:** [plan/EVENT_DAY_PLAN.md](../plan/EVENT_DAY_PLAN.md)

## 2026-11-21 09:20 · Public build repo Pack-It-Up, scaffold made before kickoff
- **Decision:** All code goes in the public repo [TallGibbs/Pack-It-Up](https://github.com/TallGibbs/Pack-It-Up). It was created at 9:20 AM with docs and empty folders only, no code, and its README says so. This planning repo stays private.
- **Why:** The rules require a public repo showing only work done at the event. Chris asked for the repo before kickoff; the event plan had said to create it after 10:30, so the README discloses the early scaffold.
- **By:** Chris.
- **See:** Pack-It-Up commit `56a0925`

## 2026-11-21 ~09:45 · Demo: move this hackathon to Penn Station
- **Decision:** The live demo photographs the venue and plans the move of everything in it to NY Penn Station. The product story stays "people moving home"; the venue move is the demo. Fleet sizing (how many trucks), unload order, and one illustrative arrival render. Placing items inside Penn Station is out of scope.
- **Why:** Venue photos taken live satisfy the "no scripted inputs" rule, and the judges see their own room packed.
- **By:** Chris.
- **See:** [plan/EVENT_DAY_PLAN.md](../plan/EVENT_DAY_PLAN.md#demo-scenario-move-this-hackathon-to-penn-station)

## 2026-11-21 ~09:45 · Media never goes in git
- **Decision:** Photos and clips stay on our laptops. Both repos track only the folders (`data/Inputs/<room>/`, `data/NYPenn/`) via `.gitkeep`, and per-folder `.gitignore` files ignore everything else. Share media directly between us.
- **Why:** The Penn Station shots show identifiable members of the public, venue shots show other hackers, and the living room is home footage.
- **By:** Chris.
- **See:** Pack-It-Up commit `4f33203`, [data/README.md](../data/README.md)

## 2026-11-21 ~10:15 · Track owners
- **Decision:** Chris owns Track A, ingestion and analysis (upload, model provider layer, inventory, Decisions API questions, review screen). George owns Track B, packing plan and output (catalog, solver, checker, Neon loop, Managed Agents, 3D trucks, unload order, arrival render, QR labels).
- **Why:** Agreed between them.
- **By:** Both.
- **See:** [plan/BUILD_STEPS.md](../plan/BUILD_STEPS.md)

## 2026-11-21 ~10:15 · Keys from DeepMind's temporary accounts
- **Decision:** DeepMind emails temporary AI Studio accounts with API keys already created; the same account works in Antigravity. Keys go only in `.env`. Never in chat, commits, screenshots or this folder.
- **Why:** Organizer instructions.
- **By:** Organizers.

## 2026-11-21 ~10:15 · Swappable model providers
- **Decision:** No file outside `backend/llm/` imports a model SDK. Code calls `for_job("<job>")`, and `backend/llm/models.toml` maps each job to `provider:model`. The demo runs on Gemini 4 only.
- **Why:** The DeepMind keys are temporary, and Chris may switch jobs to Claude models after the event.
- **By:** Chris.
- **See:** [plan/BUILD_STEPS.md](../plan/BUILD_STEPS.md#model-provider-layer), [plan/INGESTION_SPEC.md](../plan/INGESTION_SPEC.md)

## 2026-11-21 ~10:40 · Ingestion spec governs Track A
- **Decision:** [plan/INGESTION_SPEC.md](../plan/INGESTION_SPEC.md) is the build spec for Track A and wins over BUILD_STEPS where they differ. Main changes: the model estimates dimensions and code picks the size source; weight comes from a density table by material; each item gets a `size` block; spoken facts from clip audio are applied to the inventory.
- **Why:** The venue is full of items the catalog doesn't have, and narration answers questions the camera can't.
- **By:** Chris.
- **Replaces:** BUILD_STEPS rules that the model gives no dimensions and that weight is a flat 7 lb per cubic foot, for Track A.
- **See:** PR #4 in the private planning repo

## 2026-11-21 ~10:50 · QR box labels core, box recognition stretch
- **Decision:** B10 (George, core): one printable label per box with a QR code that holds the box's data itself, so a phone reads it with no server. A6 (Chris, stretch after 3 PM): identify a marker-labelled box from a photo with the model plus the Decisions API.
- **Why:** QR box apps only record what a person packed; ours come pre-filled from the plan. Recognition fits Element 119 but plain boxes look alike, so it stays a stretch.
- **By:** Chris.
- **See:** [plan/BUILD_STEPS.md](../plan/BUILD_STEPS.md)

## 2026-11-21 10:58 · Shared team memory in the planning repo
- **Decision:** Decisions, active sessions and open questions live in `memory/` in this private repo. Every agent session reads it at start and updates it as it works. Pack-It-Up's `AGENTS.md` holds the public build rules and points here.
- **Why:** Several agent sessions run in parallel and each starts with no knowledge of the others.
- **By:** Chris.
- **See:** [memory/README.md](README.md)

## 2026-11-21 11:00 · Two-track build plan approved
- **Decision:** We build to the two tracks in BUILD_STEPS.md as drawn. Track A (Chris): upload and model layer, Hydrogen inventory, Decisions API questions, review screen. Track B (George): catalog and expand, solver and checker, Neon loop and agents, 3D trucks and outputs. Track A hands the inventory JSON to Track B at the 1:00 join, and review-screen edits go back to the solver to re-solve.
- **Why:** Reviewed together before building; each track can work on its own until 1:00.
- **By:** Both.
- **See:** [plan/build_plan_two_tracks.svg](../plan/build_plan_two_tracks.svg), [plan/BUILD_STEPS.md](../plan/BUILD_STEPS.md)

## 2026-11-21 11:12 · Decisions API model is `gemini-decision-1` on `v1alpha`
- **Decision:** `decide()` uses the native Decisions API with model `gemini-decision-1`, which `models.list()` shows only under api_version `v1alpha` (v1beta returns 404). Answers at or above 0.7 calibrated probability apply automatically; below that the question goes to the user with the API's suggestion. Hydrogen `generate_json` stays as the `decide_fallback` job. Resolves the open question on the Decisions model ID.
- **Why:** Found by the Track A build session at 11:06. Malin runs: 21 live calls, no errors, median 1.8 s, 4 questions auto-answered in the 11:09 run. Accuracy of those answers not yet graded by a person.
- **By:** Chris approved recording it.
- **See:** Pack-It-Up `backend/llm/models.toml`, `backend/ingest/gaps.py`, `FAILURES.md` 10:56 and 11:06

## 2026-11-21 11:22 · All work moves to the public repo
- **Decision:** Everything written at the event goes in Pack-It-Up. The plans written today (`plan/`) and this team memory (`memory/`) were copied here and are now the live copies; the private planning repo keeps only work from before the event (research, BUILD_PLAN, starter data) and a pointer here.
- **Why:** The event rules want the public repo to hold the work done at the event, and Chris wants all work public.
- **By:** Chris.
- **Replaces:** 2026-11-21 10:58, shared team memory in the planning repo.
- **See:** [plan/README.md](../plan/README.md)

## 2026-11-21 11:30 · Agents use Google's gemini-skills
- **Decision:** Every agent loads Google's public [gemini-skills](https://github.com/google-gemini/gemini-skills) (`gemini-api-dev` first) before writing Gemini API code, for both the hackathon and the product after it. Install steps are in Pack-It-Up's AGENTS.md. Where the skill and our measured settings disagree, `backend/llm/models.toml` and `FAILURES.md` win; for example the skill puts the Decisions API on v1beta, but our keys need v1alpha.
- **Why:** The skill carries current SDK usage and model IDs; agents otherwise write code against the deprecated `google-generativeai` SDK or retired models.
- **By:** Chris.
- **See:** Pack-It-Up [AGENTS.md](https://github.com/TallGibbs/Pack-It-Up/blob/main/AGENTS.md#gemini-api-skills)
