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

## 2026-11-21 13:41 · Box estimates use George's table, with two exceptions
- **Decision:** `backend/ingest/resolve.py` takes its container sizes and its box for each kind of contents from George's table in `backend/expand.py` (`track-b`). Two exceptions stay: bathroom cabinets and `other` are smaller, and a container holds at most 60% of the listed furniture it is part of.
- **Why:** Both tracks should give the same boxes, and George's solver packs whatever `est_boxes` ingest writes. His table alone gave 47 boxes (116 cu ft) on Chris's phone run 120009 next to 114 cu ft of furniture, with a full medicine cabinet at 6 boxes; with the exceptions it is 19. On the kitchen run and two Malin runs the result is the same as his table (10, 9, 9).
- **Limits:** George has not seen the two exceptions. The table now exists in both files; change them together.
- **By:** Chris, on the review session's recommendation. Replaces the box sizes in the 13:27 entry.

## 2026-11-21 13:52 · Personal belongings can be packed
- **Decision:** Answering the personal-belongings question "they are part of the move" adds a `personal belongings` box line to that room and takes them off the left-out list; "leave them out" puts them back. Before, the answer was recorded and ignored.
- **Why:** The page asked a question whose answer changed nothing (run 120009: Chris's answer, and the 2 helmets still left out).
- **Limits:** Sized from what the things measure in the footage, no padding, at least one box per eight things; the review session's figures. An answer stored before 13:52 takes effect the next time its move is rebuilt.
- **By:** Chris, on the review session's recommendation.
- **See:** [backend/ingest/README.md](../backend/ingest/README.md), FAILURES.md 13:55 row

## 2026-11-21 13:55 · Track B joined into `main`
- **Decision:** George's `track-b` (33d6084) is merged into `main`, and the demo runs the joined app: capture, review, then `frontend/index.html` solving from the move's latest inventory through `POST /solve`. New Track B work lands on `main` from here, not on `track-b`.
- **Why:** The trial merge had only keep-both conflicts in five shared files, George's tests passed, his solver packed every inventory in `runs/`, and a trash edit and an added piano on the review page each changed the next solve.
- **Limits:** George has not been asked about work he hasn't pushed. Track B makes no model calls yet (B6, B7 and B9 are not built). George's files are as they were on `track-b`.
- **By:** Chris, on the join study session's recommendation.
- **See:** commit 5d3ce65, FAILURES.md 13:55 row

## 2026-11-21 14:14 · Neon planner loop (B6) merged into `main`
- **Decision:** The planner loop is merged and live: `backend/planner.py`, job `plan` = `gemini-4-neon`, `POST /plan`, and "Plan with Neon" on `frontend/index.html`. The model proposes solver settings; `verify.py` scores every round and the best round with no violations is kept.
- **Why:** Track B made no model calls, and the event plan says the planning model is never cut. On move 133201 the loop goes from 91.5 on two 26 ft trucks to 95.2 on one.
- **Limits:** Built from Chris's session in George's files (`pack_api.py`, `index.html`); George has not reviewed it. The gain comes mostly from `allow_all_rotations`. See FAILURES.md 14:10 rows.
- **By:** Chris (go-ahead to merge and restart).
- **See:** commits f250ff9 to f7d50d9, open-questions.md "After the planner loop"

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

## 2026-11-21 14:16 · Reframe Orior mode as White-Glove Care tribute (keep all pieces in the move simulation)
- **Decision:** Default the venue Orior feature to **✨ Orior White-Glove Care (`orior_white_glove=True`)** rather than excluding Orior furniture from the move: keep every piece in the simulation as a respectful proof of concept for venues/homes that *do* move, clearly note that The Malin's bespoke Orior pieces (Newry, Ireland) would never leave the club in real life, and pay tribute to Orior's standards by forbidding any stacking on stone/upholstery (`stackable="no"`), adding +2" breathable pad/crate clearance, requiring upright 2-person handling, and including cotton covers & stone corner guards in the `shop.dev` kit.
- **Why:** Keeps the full-room move simulation intact while warmly honoring The Malin and Orior's craftsmanship without implying their curated pieces would ever be moved out.
- **By:** George.
- **Replaces:** The `orior_curated_stays` UI default in `2026-11-21 13:58 · Integrate on-site Malin × Orior (Ireland) & Cinema Rental (Adorama / ARRI) domain rules`.
- **See:** `backend/pack_api.py`, `frontend/ui/commerce.js`, `plan/PITCH_NOTES.md`, `frontend/pitch.html`

## 2026-11-21 14:30 · Human + Robot Co-Move Biomechanics, `gemini-robotics-er-2-preview`, and Penn Station Occupancy Envelope
- **Decision:** Add a fast standalone Human + Robot Co-Move & Destination Occupancy module (`backend/co_move.py`, `backend/co_move_api.py`, `frontend/ui/co-move.js`) plus `[jobs.robotics]` (`gemini-robotics-er-2-preview` on `v1beta`, with `gemini-4-neon` fallback): (1) split every solved move between realistic dock/concourse robotics (Stretch/Pickle box unloaders `<=50 lb`, Moynihan AMR shuttle carts, XSTO/Zonzini tracked stair dollies) and human biomechanics crews (40 lb box safe-lift target, fatigue-spaced `load_seq`, diagonal doorway tilt-and-pivot + leg-unbolting instructions, and `[y, x]` path/grip/keep-out spatial overlays); (2) explicitly account for **Penn Station already being full of commuters, escalators, counters, and FDNY egress lanes** by auditing each stop against net permitted tenant/pop-up envelopes (95.6% of Moynihan's 41,808 sq ft kept untouched), Stop 5 Mezzanine (+20 ft) freight-elevator limits, MTA off-peak load-in windows, and crowded-stall stress tests.
- **Why:** Moving tech today stops at video quotes (Yembo/Shyft) while 60% of moving injuries are back injuries; pairing realistic dock/cart robotics with human biomechanics and accounting for occupied Penn Station spaces closes a major real-world & pitch plot hole without using pixel-hallucinated world physics (`genie-4`).
- **By:** George.
- **See:** `backend/co_move.py`, `backend/co_move_api.py`, `frontend/ui/co-move.js`, `backend/llm/models.toml`, `backend/llm/gemini.py`

## 2026-11-21 14:55 · Walk-in tier-by-tier truck loading (never step on first-level boxes)
- **Decision:** Truck and room packing sequences must build vertical columns/tiers from the cab wall (`x=0`) toward the rear door (`x=L`) while movers stand on bare empty truck floor, and elevated items (`z>0`) must stay within 24 inches of their supporting stack's door-facing front (`walk_in_access` rule in `backend/verify.py`), rather than packing the entire floor in-to-out before loading upper levels.
- **Why:** Filling the entire truck floor before loading level 2 forces movers to walk on top of first-level cardboard boxes to reach the front of the truck.
- **By:** George.
- **See:** `backend/solver.py`, `backend/verify.py`, `frontend/index.html`, `tests/test_track_b.py`

## 2026-11-21 15:11 · Both Neon controls stay; the arena loop is `POST /arena/plan`
- **Decision:** The page keeps both Neon controls. "Plan with Neon" in the What-If card keeps `POST /plan` (`planner.plan_with_model`); the arena card's "Neon Loop (3 Rounds)" moves to `POST /arena/plan` (`planner.run_neon_loop`). No method and path may be declared twice; `tests/test_planner.py` checks it.
- **Why:** After George's join both routers declared `POST /plan`, the pack route answered, and the arena button got a reply it could not read. A separate path was the smallest change that makes both work.
- **Limits:** George has not been asked. His route, widget and route test were changed from Chris's session. The two loops still pick different plans for the same inventory (FAILURES.md 15:11).
- **By:** Chris (go-ahead to fix and restart).
- **See:** commit de14707, FAILURES.md 15:01 and 15:11 rows

## 2026-11-21 15:14 · Submission video: voice, music, opening, end card, name
- **Decision:** The 1-minute video in `plan/VIDEO_SCRIPT.md` uses voice Charon (`gemini-3.8-flash-tts`), no music, a 4 s generated opening (`gemini-omni-1.2-flash`, labelled "generated" on screen and in the description), an end card with the QR code, the demo address and the GitHub link, and the original move 133201 as it is (its id and name show on screen; no renamed copy). The build code is written now; narration, capture and the final render wait for Chris's go.
- **Why:** Chris's answers to D1-D6 in the plan.
- **By:** Chris.
- **See:** `plan/VIDEO_SCRIPT.md` section 7

## 2026-11-21 15:18 · Element 119 Time-Lapse (`render.py`), Vinny 15s Crew Radio TTS (`foreman.py`), and 3D Chaos + Pothole Test
- **Decision:** Prioritize and ship: (1) **Element 119 Media-Out (`backend/render.py`, `backend/render_api.py`)** combining `gemini-nano-banana-2.1` Before/After Penn Station arrival keyframes (interactive drag slider, labelled illustrative) with a 6-second 720p `gemini-omni-1.2-flash` (`v1beta`) unpacking hyper-lapse MP4; (2) **Vinny + ARIA 15s NYC Crew Radio (`backend/foreman.py`)** using multi-speaker `gemini-3.8-flash-tts` (`Puck` + `Kore` on `v1beta`) grounded in live fleet/violation/LIFO metrics; and (3) **Raw 1-Call LLM Chaos Toggle + 3D NYC Pothole / 0.8g Brake Test + `eval/BASELINES.md`** (`eval/baseline_single_call.py`, `eval/baseline_bedroom.py`, `backend/eval_api.py`, `frontend/ui/showstopper.js`).
- **Why:** Turns Element 119 media generation, multimodal audio, and the 25% baseline proof rubric into instant, memorable visual and audio moments inside `frontend/index.html`.
- **By:** George.
- **See:** `backend/render.py`, `backend/foreman.py`, `backend/render_api.py`, `backend/eval_api.py`, `frontend/ui/showstopper.js`, `eval/BASELINES.md`

## 2026-11-21 15:19 · Each move shows what its model calls cost
- **Decision:** The app links to a Usage view for the move you are in (`/app/models.html?run_id=<move>`), and that view shows an estimated cost: the tokens each model reported for the move, times Google's list price for that model. All moves together have the same summary, and the table of every run has a cost column.
- **Why:** People should see what their use of the app cost. (Chris)
- **Limits:** It is an estimate at list prices (`backend/analysis/prices.toml`, read from Google's pricing page on Nov 21), not a bill: cached calls cost nothing, failed attempts and Google's discount for repeated input are not counted, and the event key may not be charged at all. Argon's price doubles on Dec 1, 2026; the file holds the price through Nov 30.

## 2026-11-21 15:28 · QR box labels go on the TOP flaps only (never on the sides)
- **Decision:** Place QR shipping labels strictly on the **TOP surface (`+Y`)** of every box across the 3D U-Haul truck view, 3D Penn Station venue view, printable QR label sheet (`MOUNT:TOP-FLAPS`), `backend/labels.py`, pitch notes, and the Nano Banana 2.1 + Gemini Omni 1.2 Flash arrival renders (keeping box side walls clean kraft cardboard).
- **Why:** Looking down at boxes in 3D or standing over sealed cartons during staging/unloading scans naturally from the top flaps rather than sideways on vertical walls.
- **By:** George.
- **See:** `frontend/index.html`, `frontend/ui/penn-venue-3d.js`, `backend/labels.py`, `backend/render.py`, `frontend/pitch.html`, `plan/PITCH_NOTES.md`

## 2026-11-21 15:35 · Auto right-size to 9 ft Cargo Van + Potential Energy & Shake/Topple floor-first physics
- **Decision:** Add `uhaul_van` (U-Haul 9 ft Cargo Van) and default fleet selection to `auto` (smallest van/truck that fits with 0 violations); keep boxes flat on the floor (`z=0`, minimum gravitational potential energy `U = m*g*z_cm`) whenever cargo fits comfortably on the deck (`<=50%` floor area), enforce `0.45g` braking/pothole slenderness bracing limits (`shake_stability`), and fail verification (`oversized_truck`) if a sparse single-van load is placed in a giant box truck.
- **Why:** Red-teaming with 4 boxes previously picked a 26-ft truck (`0.7%` fill), stacked all 4 boxes into a 64-in Jenga tower on an empty floor, and passed all checks.
- **By:** George.
- **See:** `data/trucks.csv`, `backend/solver.py`, `backend/verify.py`, `frontend/index.html`, `tests/test_track_b.py`

## 2026-11-21 15:41 · Supply kit: fewer stores over the cheapest store per item
- **Decision:** The Move Supply Kit picks stores for the whole kit, not item by item. A store is dropped when moving its lines to stores already in the kit costs less than an estimated $15 shipping fee per store (`EST_SHIPPING_PER_STORE_CENTS` in `backend/commerce.py`). The browser fallback in `frontend/ui/commerce.js` uses the same rule.
- **Why:** Each Shopify store is its own cart and its own shipping charge; a $5.80 tape cart was charged $25 shipping. One cart per store is a Shopify limit, so fewer stores is the only way to fewer carts. (Chris)
- **Limits:** $15 is a guess; real shipping is only known at checkout. A store stays when it is the only one in the kit offering a line within $15.
- **By:** Chris. Track B files (George's), changed at Chris's request.
- **See:** commit 12aa644, FAILURES.md 15:41 row

## 2026-11-21 15:40 · Demo and presentation outputs are made by Gemini
- **Decision:** The slide deck, the demo video's narration lines and cards, and any other output judges see that is not the app itself are made by a Gemini model through `backend/llm/` from a brief of facts, not written or designed by the coding agent. The Claude-made judging deck is replaced by `frontend/slides/index.html` (Gemini 4 Carbon, `python -m scripts.slides.build`, served at `/app/slides/`). App screenshots and recordings stay real captures.
- **Why:** Chris: the deck had a distinctly "Claude" look; this is a Gemini-built product.
- **By:** Chris.
- **See:** `AGENTS.md` "Demo and presentation outputs are made by Gemini", `.claude/skills/gemini-outputs/SKILL.md`, `scripts/slides/`, `scripts/video/brief.md`

## 2026-11-21 15:53 · Results table, slides and video numbers stay as they are while testing goes on
- **Decision:** `eval/RESULTS.md`, the slide brief and the video script are not refreshed for now. They are rebuilt once, after the solver stops changing.
- **Why:** The solver and checker changed at 15:34, 15:39 and 15:46 (tier-by-tier loading, a 9 ft cargo van, two new rules), and each change moves the scores and truck choices. A rebuild started at 15:45 was out of date before it finished.
- **By:** Chris.
- **See:** open-questions.md, 'Left by the whole-repo review session (15:55)'

## 2026-11-21 16:05 · `labels.py` in the track-b merge: keep main's encoder, add George's helpers
- **Decision:** When merging `track-b` (9490c64), keep the `backend/labels.py` already on `main` (used by `/labels`, `labels.html` and `tests/test_labels.py`) and add George's top-flap helpers on top of it, rather than his second encoder. `encode_qr_matrix` now returns bools so his test passes.
- **Why:** His branch version dropped `labels_for_run`, `qr_png_bytes` and `identify_box_from_photo`, which the live routes call.
- **By:** Chris (Track B file, at his request).
- **See:** merge 2f26c31; open-questions.md, 'Left by the branch audit session (16:18)'

## 2026-11-21 16:16 · Merged branches deleted
- **Decision:** Delete `feature/sign-in` (local and GitHub), `track-b-planner` (GitHub), the local `claude/recursing-chatterjee-0c606b`, and the `sign-in` and `recursing-chatterjee-0c606b` worktrees. All their commits were on `main`; `track-b` stays because George still pushes to it.
- **By:** Chris.

## 2026-11-21 16:30 · One branch for final testing: `track-b` deleted
- **Decision:** `main` is the only branch. `origin/track-b` (tip 9e3ae29) was deleted; every commit on it was already in `main`. This replaces the 16:16 entry's "`track-b` stays". George pulls `main` and pushes there from now on.
- **Why:** Chris wanted all parallel work on one branch before final testing.
- **By:** Chris.

## 2026-11-21 21:38 · Home footage removed from git history; `main` force-pushed
- **Decision:** Rewrite `main` without the five files in `data/Inputs/Malin/` that 80e7578 added (two clips, three photos), and force-push it. `main` went from 4118686 to 46abb77 (255 commits; the upload commit held only those files, so it is gone). Every file in `main` is otherwise unchanged.
- **Why:** The repo is public and the files are footage of a home.
- **Left:** Every checkout made before 21:38 must re-clone, or run `git fetch origin && git reset --hard origin/main` with no local work, before pushing again; a plain push would bring the old history back. GitHub still serves the old commit by its ID until GitHub Support clears its cache (Chris to ask).
- **By:** Chris.

## 2026-11-21 21:52 · Keep the Decisions model after the event, on Chris's own key
- **Decision:** The `decide` and `judge` jobs stay on `gemini-decision-1` when the app moves to Chris's own Gemini key. No move to a chat model (Claude or Gemini) for these jobs.
- **Why:** It costs $0.10 per 1M input tokens and nothing for output, and a request's shared input is billed once however many questions it asks (`backend/analysis/prices.toml`): a fifteenth of Hydrogen's input price, a thirtieth of Neon's. It returns a probability per option, which the 0.7 auto-apply line (`gaps.py`) and the judge's escalation lines (`judge_plan.py`) depend on; a chat model's confidence is text it writes. In the one graded room, answers at 0.7 or more were 4 of 4 right, those below 2 of 5 (`eval/RESULTS.md`, section 5). Open one-pass models (Jev-like, e.g. Nimble) work the same way if we ever leave Gemini.
- **Budget note:** the Decisions model is a small part of a move's cost; Hydrogen reading clips and Neon planning are most of it (move 133201: about $1.20). The Usage page has no price for the Omni video, TTS or robotics models, so it counts them as $0 and understates. Argon's price doubles on Dec 1, 2026.
- **By:** Chris.
- **See:** open-questions.md, 'Using the cheap Decisions model more'

