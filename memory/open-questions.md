# Open questions and undecided ideas

Move an item to [decisions.md](decisions.md) once it is decided, and delete it here.

## Waiting on the organizers
- Is reference data prepared before the event (the item catalog and truck tables) acceptable if we disclose it? Until answered, rebuild it today or disclose it in Pack-It-Up's README.
- Does the Managed Agents prize require a specific agent or model?
- Can the live demo use footage filmed in the judging room?

## Waiting on a person
- **Handoff from the upload pages to the 3D view (George to confirm; Chris confirms in person).** "Plan the truck load" on `capture.html` and `review.html` opens `frontend/index.html?run_id=<run_id>`, adding `&api=<base>` or `&mock=1` when the page has them. Proposed for `index.html`: read `run_id` from the URL, fetch `GET /inventory/{run_id}` (or call a Track B `POST /solve {run_id}`), and solve from it every time the page opens, so re-solve after an edit is just tapping the button again (decision 11:38). Fields to read per item: `quantity`, `disposition` (pack only `keep` and `undecided`), `size.dims_in` (L, W, H inches; height is height), `size.weight_lb_each`, `fragile`, `must_stay_upright`, `two_person`, `stackable`, `stack_count`; per room `containers[].est_boxes` (e.g. `{"box_medium": 2}`). With `mock=1` there is no server: use `frontend/mock/inventory.json`. Items a person adds on the review page ("add a piano", branch `feature/add-item`) arrive in the same shape with `source: "user_added"`; their `evidence.source` and `evidence.sha256` are `null`, so don't look up footage for them. (George)
- **Box estimates for cabinets, shelves and closets: are the sizes right, and does the solver take the new box ids? (George and Chris)** Since 13:27 every container in `inventory.json` has `est_boxes`, not only loose decor, and the keys can be `box_small`, `box_medium`, `box_large`, `box_dish_pack` or `box_wardrobe` (all catalog ids). The sizes are rough figures from the review session (`CONTAINER_CUFT`, `KIND_CUFT`, `INSIDE_SHARE`, `BOX_FOR_CONTENTS` at the top of `backend/ingest/resolve.py`): a copy of run 120009 went from 9.4 to 49.8 boxed cu ft next to 114 cu ft of furniture. Change those tables to change the estimates. **Checked at 13:45:** there is no Shopify code in the repo or on `track-b`; Shopify is one optional line in `plan/EVENT_DAY_PLAN.md` (a "buy these boxes" list from the box counts). George's `backend/expand.py` on `track-b` has its own table for the same job (`CONTAINER_FULL_CUFT`, `CONTENTS_BOX_SPEC`, `FULLNESS_FACTOR`) and uses it only when a container has no `est_boxes`; since 13:27 every container has one, so the ingest figures are what his solver packs, and it already accepts all five box ids. On copies of three runs the two tables agree on the kitchen run (11 against 10 boxes) and the Malin run (9 and 9). They differ on run 120009: 15 boxes from ingest, 47 from George's table, 23 from George's table with ingest's 60%-of-the-furniture cap; a full medicine cabinet is 1 box against 6. **Settled at 13:41 for now** (decisions.md): ingest uses George's table with two exceptions, smaller bathroom cabinets and `other`, and the 60% cap. Left for George: confirm or change those two, and keep `expand.py`'s copy in step.
- **Who owns `backend/catalog.py` and `data/item_catalog.csv`?** The plan gives them to George; the Track A session created first versions so ingestion could start. George should extend them rather than rewrite them. (Chris and George)
- **Living room media.** `data/Inputs/Living Room/` is empty. Is the home photo still coming? (Chris)

## Left by the Track A ingestion session (12:10)
- **Demo processes.** The API (laptop-only, port 8000) and the named tunnel run in two minimized windows on Chris's laptop. If the laptop restarts, run `powershell -ExecutionPolicy Bypass -File run_demo.ps1` from the repo, then check https://packitup.temperedanalytics.com/health. A separate quick tunnel (trycloudflare.com) started by the upload UI session may also still be running.
- **"Plan the truck load" is a 404** until Track B adds `frontend/index.html`. (George)
- **Capture page sends an upload with no files** (seen once as a 422). Small guard in `frontend/capture.html`. (Track A UI)
- **A real narrated clip** for the audio check; the passing check used a text-to-speech stand-in. Film it in the Camera app and add it with Choose files. (Chris)
- **Accuracy work is on hold** (decision 11:55): one run per prompt can't separate prompt v3 from run-to-run variation; recall on Malin is 67-75% against the in-person count.

## Left by the review session (14:00)
- **The box table lives in three places:** `backend/ingest/resolve.py`, George's `backend/expand.py` on `track-b`, and `frontend/mock/mock-api.js`. Change them together. George has not seen the two exceptions (smaller bathroom cabinets and `other`; a container holds at most 60% of the furniture it is part of). (George, Chris)
- **Box weights are not in the pound total.** The review page's "lb" counts furniture only; George's table has a packed weight per box. (Track A, after the join)
- **Not tried on a phone:** everything this session merged was checked on copies of moves, on the live server with a test move, or in a desktop browser at 375 px. (Chris)
- **From the 13:10 review, not started:** `?api=` on the real pages; `GET /analysis/runs` lists every move's id to anyone; a move interrupted by an API restart stays "still working" for good; two phones adding to one move can clash on file names; tap targets under 44 px, no visible focus on the two pick buttons, and progress not announced to screen readers. (Track A)
- **Branches that can be deleted on GitHub:** `feature/review-server-fixes`, `feature/edit-checks`, `feature/box-table`, `feature/belongings-mock`. All four are in `main`. (Chris)

## Ideas proposed, not decided
- **Lifting guidance on unload steps:** tags such as "two-person lift" or "over 50 lb", using the catalog's `two_person` flag and weights. About 30 minutes in B8. Suggested as core.
- **Truck-mode reminder:** one checklist line on the final plan screen telling drivers to use a truck-aware nav setting. About 5 minutes. Check which apps really have a truck mode before naming one.
- **Route warnings:** low clearances and hills between the venue and Penn Station for the chosen truck's height. Stretch after 3 PM; needs an exterior-height column in `trucks.csv` and a data source we haven't picked.
