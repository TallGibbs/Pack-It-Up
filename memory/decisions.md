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

## 2026-11-21 11:55 · Track B builds on branch `track-b` before the join
- **Decision:** Track B works on branch `track-b` and merges into `main` when joining with Track A.
- **Why:** Isolates Track B solver, catalog and frontend work while Track A finishes ingestion and phone testing on `main`.
- **By:** George.

## 2026-11-21 11:55 · Penn Station move stocks retail stores, café, kiosks and lounges
- **Decision:** Instead of unloading everything into one open concourse, the Penn Station destination includes distinct retail storefronts, café stall, bookshop, tech hub, merch kiosk, ticketed lounge and concourse zones (`data/penn_zones.csv`), each with dimensions, doorway clearances, weight limits and loading-dock stop order.
- **Why:** Moving into one giant open hall is trivial; filling constrained storefronts with doorway limits and LIFO dock-stop ordering creates real packing and routing trade-offs that showcase Gemini 4 planning and verification.
- **By:** George.
- **Replaces:** The "placing items inside Penn Station is out of scope" clause of `2026-11-21 ~09:45 · Demo: move this hackathon to Penn Station`.

## 2026-11-21 12:08 · Include Shopify `shop.dev` Commerce Bonus Track in Track B output
- **Decision:** Track B's output must include the Shopify Commerce Bonus Track (`shop.dev` / `https://mcp.shop.com` UCP MCP): automatically compute the Move Supply Kit (exact moving box counts by size plus tape, bubble wrap, moving blankets, stretch wrap, mattress bags, and lifting straps from physics flags), discover & verify real Shopify merchant offers with `gemini-decision-1` + `gemini-4-neon`, consolidate into live multi-item Shopify carts & Shop Pay checkouts (`continue_url`), surface Haul-vs-Replace / Sell comps, and embed an interactive Shopping Agent.
- **Why:** Turns the computed packing plan into an immediately actionable move purchase and enters the open Shopify Build with Commerce bonus prize track.
- **By:** George.
- **Replaces:** `plan/EVENT_DAY_PLAN.md` "Optional: Shopify bonus track — Only if we are ahead at 3:00 PM".
- **See:** `backend/commerce.py`, `backend/commerce_api.py`, `frontend/ui/commerce.js`, `frontend/shop.html`, `frontend/index.html`

## 2026-11-21 13:04 · Live Point A→B truck route tips, city parking, and calm end-to-end unpack support
- **Decision:** The Track B output app (`frontend/index.html`) includes Point A to Point B route intelligence informed by real-time street routing, weather/wind, truck height/restriction data, and traffic speeds plus Gemini 4 synthesis: tolls, roads/parkways that prohibit trucks, a reminder to switch to commercial truck mode on the user's phone maps app, and city parking/curb tips. It also supports the user calmly through the entire move until unpacking the very last item, without being pushy or overbearing.
- **Why:** Moving doesn't end when the 3D load plan is computed—renters get stuck on no-truck parkways, surprise tolls, city curb rules, and finding/unpacking boxes at destination.
- **By:** George.
- **Replaces:** `memory/open-questions.md` undecided stretch notes on "Truck-mode reminder" and "Route warnings".
- **See:** `data/trucks.csv`, `backend/route_guide.py`, `backend/route_api.py`, `frontend/ui/journey.js`, `frontend/index.html`

## 2026-11-21 12:16 · Two separate final judge steps (Move Plan Judge, then Hackathon Rubric Judge)
- **Decision:** Add two distinct judge steps at the end of the pipeline rather than combining them: (1) `backend/judge_plan.py` evaluates the solved truck load, Penn Station store LIFO routing, verifier checks, and arrival render via multi-question Decisions API (`noul` + `choice` + `score`) with Gemini 4 escalation on low confidence; (2) `backend/judge_rubric.py` separately audits the run, model logs, baselines, and compliance gates against the four Cerebral Valley judging criteria (Round 1 35/25/20/20 and Round 2 25/25/25/25). Extend `backend/llm/` with `decide_batch()` to keep all SDK calls inside `backend/llm/`.
- **Why:** Keeps product-facing move readiness separate from hackathon submission self-scoring while showcasing `gemini-decision-1`'s single-pass `noul`, `choice`, and `score` capabilities from the official Builder Guide.
- **By:** George.

## 2026-11-21 13:58 · Integrate on-site Malin × Orior (Ireland) & Cinema Rental (Adorama / ARRI) domain rules into product and pitch
- **Decision:** Add real-world venue & production domain rules gathered from in-person conversations at the hackathon into the catalog, solver API, `shop.dev` commerce kit, What-If UI, and pitch cards: (1) **Malin × Orior rule (`orior_curated_stays`)** reflecting that The Malin's parent company **Orior** (bespoke Irish design house, Newry, est. 1979) curates custom travertine/bouclé/mohair pieces per club and never moves furniture between locations (plus breathable cotton covers & stone corner guards in `commerce.py` when commissioning a new space); (2) **Cinema Production Rig (`pelican_1650`, `pelican_1510`, `c_stand_cart`, `magliner_camera_cart`)** reflecting **Adorama Rental / ARRI Rental** camera-truck rules (1650 floor base, unstacked 1510 lens cases, upright locked carts, outward QR return labels, and E-track straps/case foam via `mcp.shop.com`).
- **Why:** Grounds both the engineering and the 3-minute live demo in real domain constraints discovered directly from the venue team and event film crew in the room.
- **By:** George.
- **See:** `data/item_catalog.csv`, `data/penn_zones.csv`, `backend/pack_api.py`, `backend/commerce.py`, `frontend/ui/commerce.js`, `plan/PITCH_NOTES.md`, `frontend/pitch.html`
