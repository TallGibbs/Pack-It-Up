# Open questions and undecided ideas

Move an item to [decisions.md](decisions.md) once it is decided, and delete it here.

## Waiting on the organizers
- Is reference data prepared before the event (the item catalog and truck tables) acceptable if we disclose it? Until answered, rebuild it today or disclose it in Pack-It-Up's README.
- Does the Managed Agents prize require a specific agent or model?
- Can the live demo use footage filmed in the judging room?

## Waiting on a person
- **After the join (13:55): for George.** `track-b` is merged into `main` and live (decisions.md 13:55); `index.html` reads `run_id` and solves through `POST /solve` as the 11:38 contract said. Still open: (1) is there Track B work not yet pushed? Push it to `main`. (2) Track B makes no model calls; B6 (Neon reads the verifier result and changes the strategy) is the smallest way to put the second model on screen. (3) The fleet uses one truck size: move 133201 gets a second 26 ft truck for 3 items; should "Downsize last truck" be on by default? (4) `index.html` falls back to the in-browser solver when `/solve` fails and only the badge says so. (5) Were `data/trucks.csv`, `data/penn_zones.csv` and `data/sample_venue.json` written today or brought in? If brought in, list them in README. (George)
- **After the planner loop (14:14): for George.** B6 is built and live (decisions.md 14:14), written from Chris's session in your files. (1) Do you have your own `planner.py`? None was on `origin/track-b` or `origin/main` at 14:00. (2) The checker scores five 10 ft trucks (94.9) above two 26 ft trucks (91.5) on move 133201, because efficiency points count fill and not the number of trucks. Should `verify.py` count trucks? (3) `allow_all_rotations` is what removes the extra truck on move 133201 and on `sample_venue`: it tips pieces not marked upright or on-edge onto a side. Is that acceptable for every such piece, or should some catalog items be marked upright? (4) B7 (Managed Agents) is not built.
- **Box estimates for cabinets, shelves and closets: are the sizes right, and does the solver take the new box ids? (George and Chris)** Since 13:27 every container in `inventory.json` has `est_boxes`, not only loose decor, and the keys can be `box_small`, `box_medium`, `box_large`, `box_dish_pack` or `box_wardrobe` (all catalog ids). The sizes are rough figures from the review session (`CONTAINER_CUFT`, `KIND_CUFT`, `INSIDE_SHARE`, `BOX_FOR_CONTENTS` at the top of `backend/ingest/resolve.py`): a copy of run 120009 went from 9.4 to 49.8 boxed cu ft next to 114 cu ft of furniture. Change those tables to change the estimates. **Checked at 13:45:** there is no Shopify code in the repo or on `track-b`; Shopify is one optional line in `plan/EVENT_DAY_PLAN.md` (a "buy these boxes" list from the box counts). George's `backend/expand.py` on `track-b` has its own table for the same job (`CONTAINER_FULL_CUFT`, `CONTENTS_BOX_SPEC`, `FULLNESS_FACTOR`) and uses it only when a container has no `est_boxes`; since 13:27 every container has one, so the ingest figures are what his solver packs, and it already accepts all five box ids. On copies of three runs the two tables agree on the kitchen run (11 against 10 boxes) and the Malin run (9 and 9). They differ on run 120009: 15 boxes from ingest, 47 from George's table, 23 from George's table with ingest's 60%-of-the-furniture cap; a full medicine cabinet is 1 box against 6. **Settled at 13:41 for now** (decisions.md): ingest uses George's table with two exceptions, smaller bathroom cabinets and `other`, and the 60% cap. Left for George: confirm or change those two, and keep `expand.py`'s copy in step.
- **Who owns `backend/catalog.py` and `data/item_catalog.csv`?** The plan gives them to George; the Track A session created first versions so ingestion could start. George should extend them rather than rewrite them. (Chris and George)
- **Living room media.** `data/Inputs/Living Room/` is empty. Is the home photo still coming? (Chris)

## Left by the Track A ingestion session (12:10)
- **Demo processes.** Since 14:56 `run_demo.ps1` starts a hidden keeper that restarts the API (laptop-only, port 8000) and the named tunnel when either stops (FAILURES.md 14:57). After a reboot or sign-out, run `powershell -ExecutionPolicy Bypass -File run_demo.ps1` from the repo. After a Python change reaches the main checkout, run it with `-RestartApi`; `-Status` shows what is running. Not covered: an API that is running but stuck.
- **Capture page sends an upload with no files** (seen once as a 422). Small guard in `frontend/capture.html`. (Track A UI)
- **A real narrated clip** for the audio check; the passing check used a text-to-speech stand-in. Film it in the Camera app and add it with Choose files. (Chris)
- **Accuracy work is on hold** (decision 11:55): one run per prompt can't separate prompt v3 from run-to-run variation; recall on Malin is 67-75% against the in-person count.

## Left by the review session (14:00)
- **The box table lives in three places:** `backend/ingest/resolve.py`, George's `backend/expand.py` on `track-b`, and `frontend/mock/mock-api.js`. Change them together. George has not seen the two exceptions (smaller bathroom cabinets and `other`; a container holds at most 60% of the furniture it is part of). (George, Chris)
- **Box weights are not in the pound total.** The review page's "lb" counts furniture only; George's table has a packed weight per box. (Track A, after the join)
- **Not tried on a phone:** everything this session merged was checked on copies of moves, on the live server with a test move, or in a desktop browser at 375 px. (Chris)
- **From the 13:10 review, not started:** `?api=` on the real pages; `GET /analysis/runs` lists every move's id to anyone; a move interrupted by an API restart stays "still working" for good; two phones adding to one move can clash on file names; tap targets under 44 px, no visible focus on the two pick buttons, and progress not announced to screen readers. (Track A)

## Left by the phone test session (13:55)
- **A clip over 95 MB has not been tried on a phone.** The capture page refuses it at the demo address (Cloudflare's 100 MB limit); seen only with stubbed sends in the desktop browser. To check: film about 90 seconds in the Camera app and pick it. Chris chose to skip it. (Chris)
- **Two files being read at the same moment has not happened on a phone.** The two-phone step used photos the server had seen, so they came back from the model-call cache. Stub tests at 12:15 and a desktop test at 13:10 cover it. To check: a fresh clip on each phone, picked together. (Chris)
- **A stored answer can show as failed after a fixture answer removes its item** (`answers_applied`, FAILURES.md 13:44). Harmless; `gaps.reapply_answers` could skip it. (Track A)
- **What sent the one upload with no files at 12:05 is still unknown.** The page can no longer send one. (Track A)

## Ideas proposed, not decided
- *(Moved lifting guidance, truck-mode reminder, and live route/parking warnings to active Track B decisions — see `decisions.md`.)*
