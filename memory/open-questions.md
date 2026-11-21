# Open questions and undecided ideas

Move an item to [decisions.md](decisions.md) once it is decided, and delete it here.

## Waiting on the organizers
- Is reference data prepared before the event (the item catalog and truck tables) acceptable if we disclose it? Until answered, rebuild it today or disclose it in Pack-It-Up's README.
- Does the Managed Agents prize require a specific agent or model?
- Can the live demo use footage filmed in the judging room?

## Waiting on a person
- **Handoff from the upload pages to the 3D view (George to confirm; Chris confirms in person).** "Plan the truck load" on `capture.html` and `review.html` opens `frontend/index.html?run_id=<run_id>`, adding `&api=<base>` or `&mock=1` when the page has them. Proposed for `index.html`: read `run_id` from the URL, fetch `GET /inventory/{run_id}` (or call a Track B `POST /solve {run_id}`), and solve from it every time the page opens, so re-solve after an edit is just tapping the button again (decision 11:38). Fields to read per item: `quantity`, `disposition` (pack only `keep` and `undecided`), `size.dims_in` (L, W, H inches; height is height), `size.weight_lb_each`, `fragile`, `must_stay_upright`, `two_person`, `stackable`, `stack_count`; per room `containers[].est_boxes` (e.g. `{"box_medium": 2}`). With `mock=1` there is no server: use `frontend/mock/inventory.json`. (George)
- **Who owns `backend/catalog.py` and `data/item_catalog.csv`?** The plan gives them to George; the Track A session created first versions so ingestion could start. George should extend them rather than rewrite them. (Chris and George)
- **Living room media.** `data/Inputs/Living Room/` is empty. Is the home photo still coming? (Chris)

## Ideas proposed, not decided
- **Lifting guidance on unload steps:** tags such as "two-person lift" or "over 50 lb", using the catalog's `two_person` flag and weights. About 30 minutes in B8. Suggested as core.
- **Truck-mode reminder:** one checklist line on the final plan screen telling drivers to use a truck-aware nav setting. About 5 minutes. Check which apps really have a truck mode before naming one.
- **Route warnings:** low clearances and hills between the venue and Penn Station for the chosen truck's height. Stretch after 3 PM; needs an exterior-height column in `trucks.csv` and a data source we haven't picked.
