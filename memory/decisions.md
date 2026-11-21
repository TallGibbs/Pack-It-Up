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

## 2026-11-21 11:38 · Demo question answered on the capture page
- **Decision:** The top open question appears as a card on the capture page, under the upload progress, as soon as the server raises it, and is answered there. The review page stays but can be skipped: the capture page also links straight to the packing plan.
- **Why:** The demo gives inventory and one live question 30 seconds (0:20 to 0:50); a page change costs time, and a list screen risks looking like a dashboard.
- **By:** Chris.
- **See:** [plan/UPLOAD_UI_SPEC.md](../plan/UPLOAD_UI_SPEC.md)

## 2026-11-21 11:38 · Item choices: Move / Stays / Sell / Toss
- **Decision:** Each item on the review page offers Move (`keep`), Stays (`stays`), Sell (`sell`) and Toss (`trash`). `donate` is no longer offered; an item already marked donate shows as a badge. Only Move and undecided items go to the truck.
- **Why:** Fits both the moving-home story and the venue demo, where "stays" is the common case, and four buttons fit a phone row.
- **By:** Chris.

## 2026-11-21 11:38 · Model-only questions don't go to the user
- **Decision:** `same_item` and `fixture_check` questions are never shown to the user as open cards. The Decisions API's best guess is applied, and the question shows as answered with a Change link.
- **Why:** Their text is written for the model ("the last image is a new sighting…") and refers to images the user can't see.
- **By:** Chris.
- **See:** `backend/ingest/gaps.py` (ingestion session owns it)

## 2026-11-21 11:38 · Re-solve on "Plan the truck load"
- **Decision:** Review edits change only the inventory. Tapping "Plan the truck load" opens Track B's page with the run id, and it solves from the latest inventory; no live truck count on the review page.
- **Why:** No dependency on solver speed or a solve route that isn't defined yet. A judge's change at 2:00 is: edit, then tap the button again.
- **By:** Chris.

## 2026-11-21 11:38 · API server serves the pages
- **Decision:** `backend/app.py` mounts `frontend/` as static files at `/app`, so the phone opens `/app/capture.html` on the same port as the API, and one tunnel address covers both. The upload UI session makes the one-line change after telling the ingestion session.
- **Why:** A tunnel exposes one port; two servers would need two tunnel addresses.
- **By:** Chris.

## 2026-11-21 11:38 · Handoff contract with Track B
- **Decision:** "Plan the truck load" opens `frontend/index.html?run_id=<run_id>` (plus `&api=` or `&mock=1` when set). The upload UI session writes the contract into open-questions.md and the session notes for George to confirm; Chris confirms with George in person.
- **By:** Chris.

## 2026-11-21 11:38 · Phone connection: test LAN now, tunnel as backup
- **Decision:** Chris opens `http://<laptop IP>:8000/health` on his phone on the venue wifi. If it answers, the demo uses LAN; either way a Cloudflare quick tunnel (`cloudflared`) is installed as a backup, and the README says how to start it.
- **Why:** The live phone upload is 35% of the score, and venue wifi often blocks device-to-device traffic.
- **By:** Chris.

## 2026-11-21 11:30 · Closed containers: assume empty, always ask
- **Decision:** A container whose fullness is `not_visible` (closed doors or drawers) is not sent to the Decisions API. Resolve and box counts treat it as empty, it is flagged "contents unknown, assumed empty" (on the container and on the furniture holding it), and the user is always asked, on top of the five ranked questions.
- **Why:** Footage can't see inside a closed cabinet; in the 11:09 run the Decisions API guessed "empty" at 0.36 for a sideboard whose contents Chris couldn't see in person either.
- **By:** Chris.
- **See:** `backend/ingest/gaps.py` (`hidden_contents`), `backend/ingest/resolve.py`, `eval/grading/malin_decisions_1109.md`.

## 2026-11-21 11:30 · Upholstered seating by seat count
- **Decision:** The perceive prompt (v3) classifies sofas and chairs by seats (single, two, three, sectional) rather than by names like armchair or loveseat, and asks for extra care counting partly hidden repeated items and the room's edges. Count questions offer up to twice the estimate plus "more" and a typed number.
- **Why:** Size is what packing needs. In person the Malin lounge has 6 bar stools and 16 work chairs; the pipeline said 5 and 10, and the count question offered at most 12.
- **By:** Chris.

## 2026-11-21 11:55 · Build and verify the full pipeline before optimizing
- **Decision:** Hold accuracy work (more prompt versions, repeat-run variation tests, tape-measured sizes, long re-filming) until the whole flow is built and checked end to end: phone capture, inventory, questions, solver, 3D view. Chris will film a few more short clips; no tape measure is available, and no 5-minute videos.
- **By:** Chris.

## 2026-11-21 11:55 · Try a personal Gemini API key next to the event key
- **Decision:** Chris creates his own AI Studio key and tests whether it reaches the Gemini 4 models and the Decisions API, because he has no admin control over the event account. The code holds both: `GEMINI_API_KEY` (event) and `GEMINI_API_KEY_PERSONAL`, chosen with `GEMINI_KEY_PROFILE=PERSONAL`. The event key stays the default until the test says otherwise.
- **By:** Chris.

## 2026-11-21 12:00 · Event key only (replaces 11:55 "Try a personal Gemini API key")
- **Decision:** The event key in `.env` (`GEMINI_API_KEY`) is the only key used today. No personal key. That key already reaches all four Gemini 4 models and the Decisions API (`gemini-decision-1`, api_version `v1alpha`).
- **Note:** The unused key-profile switch (`GEMINI_KEY_PROFILE`) stays in `backend/llm/gemini.py`; it does nothing unless set.
- **By:** Chris.

## 2026-11-21 12:00 · Fixed demo address on Chris's domain
- **Decision:** The demo runs at https://packitup.temperedanalytics.com/, a named Cloudflare tunnel (`pack-it-up`) on Chris's `temperedanalytics.com` to the API on the demo laptop. The temporary trycloudflare.com tunnel stays as a fallback.
- **Why:** The Hackathon wifi blocks phone-to-laptop traffic, and a quick tunnel's address changes whenever it restarts, which would break the QR codes on the slides and cards. A fixed name survives restarts.
- **Limits:** It works only while the laptop runs the API and the tunnel. Anyone with the address can use the app and see uploads; there is no login.
- **By:** Chris.

## 2026-11-21 12:19 · Coming back continues the same move
- **Decision:** A person who uploads, leaves and returns carries on with the same move (run), not a new one. The capture page keeps the run id in its address, so a reload continues; opened without one, it offers the last move this browser was in, and picking files without answering starts a new move. The QR code leaves the run id out, so each person who scans it gets their own move.
- **Why:** A move takes hours or days, and phones reload background tabs, often after the camera has been open. Before this, a reload or review's "Film another room" link silently started a new move.
- **By:** Chris, on the quality-check session's recommendation.
- **See:** [frontend/README.md](../frontend/README.md#what-a-move-is), branch `feature/resume-move`

## 2026-11-21 13:10 · Model-use history copied to Chris's Databricks
- **Decision:** The model-use history (`backend/analysis/`) is also copied to Chris's own Databricks Free Edition workspace, catalog `pack_it_up`, schema `model_use`, so it outlives this laptop. The local `.history/analysis.db` stays the source the page reads; the copy is one-way, in the background, every minute.
- **Why:** Chris wants the record kept apart from local files. Not MongoDB (Chris's choice). Not Google Cloud: the event key reaches only the Gemini API, and the event's account is temporary.
- **Limits:** Databricks stores data only; no model runs there, so the demo stays on Gemini 4. The workspace address and token live only in `.env`.
- **By:** Chris.

## 2026-11-21 13:27 · Item ids come from the item's group; cabinets and shelves get box estimates
- **Decision:** Merge the review session's three server fixes. An item's id is built from its group (`room_1_armchair`), so an edit or answer stays on its item when another photo of the room arrives; only the latest answer to a question is applied; every container carries `est_volume_cuft` and `est_boxes`.
- **Why:** On a copy of a Malin run a Toss moved to a different item in 103 of 172 tries, and no cabinet, shelf or closet had ever added a box (0 of 53).
- **Limits:** The box sizes (space inside per kind and size class, capped at 60% of the furniture) are the review session's rough figures; Chris merged them knowing that, and George has not agreed them. `est_boxes` keys now include `box_small`, `box_large`, `box_dish_pack` and `box_wardrobe`.
- **By:** Chris, on the review session's recommendation. The phone test session's own id fix (ids kept in `item_ids.json`) was taken back out in favour of this one.
- **See:** [backend/ingest/README.md](../backend/ingest/README.md), FAILURES.md 13:10 and 13:25 rows
