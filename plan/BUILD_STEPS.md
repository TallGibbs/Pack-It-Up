# Build steps (event day)

The concrete steps behind [EVENT_DAY_PLAN.md](EVENT_DAY_PLAN.md), in build order. Each step ends with how we know it's done.

| Track | Owner | Covers |
|---|---|---|
| A: ingestion and analysis | Chris | Upload, the model provider layer, inventory from photos and video, Decisions API questions, review screen |
| B: packing plan and output | George | Catalog, solver, checker, Neon planning loop, Managed Agents, 3D trucks, unload order, arrival render | All code is written at the event in [TallGibbs/Pack-It-Up](https://github.com/TallGibbs/Pack-It-Up); this file stays in the private planning repo.

Build the solver and checker first: they don't need any model, so Track B can start right away.

## Stack (decide at 10:30)

- **Backend:** Python with FastAPI and the `google-genai` SDK.
- **Packer:** `py3dbp`, the [jerry800416/3D-bin-packing](https://github.com/jerry800416/3D-bin-packing) library (MIT licence).
- **Frontend:** one `index.html` with three.js loaded from a CDN. No build step.
- **Layout** of the code in Pack-It-Up:

```
backend/  app.py  catalog.py  perceive.py  gaps.py  expand.py
          solver.py  verify.py  planner.py  agents.py  render.py
          llm/  __init__.py  base.py  gemini.py  models.toml
frontend/ index.html
eval/     baseline_single_call.py  baseline_bedroom.py  run_eval.py  RESULTS.md
data/     item_catalog.csv  trucks.csv   (rebuilt today, or brought in and disclosed)
media/    venue and Penn Station photos and clips (git-ignored)
```

## Step 0: shared contracts (10:30 to 11:00, together)

1. **Keys.** DeepMind emails each of us a temporary AI Studio account with API keys already created; the same account works in Antigravity. Copy the key into `.env` yourself. Never paste it into chat, a commit or a screenshot, and expect it to stop working after the event. Run a "hello" call against each model ID you see in AI Studio: Hydrogen, Neon, the Decisions API and Nano Banana. Write the real IDs into `backend/llm/models.toml`. Done when all four answer.
   - **Model provider layer** (Chris, first 20 minutes). See the section below. Every model call goes through it from the first line of code.
2. **Inventory format.** Use `inventory.schema.json` (pre-event; kept in the private planning repo) as it is. Add a `stack_count` field for stacked chairs.
3. **Placement format** (what the solver hands the frontend):
   ```json
   {"trucks":[{"truck_id":"uhaul_26","index":0,"dims_in":[314,98,99],
     "items":[{"id":"t1_chairstack_01","label":"stacking chairs x10",
       "pos_in":[0,0,0],"size_in":[20,22,70],"load_seq":1,"fragile":false}]}],
    "score":{"total":0.0,"fill_pct":0.0,"violations":[]}}
   ```
4. **Data tables.**
   - Add venue rows to the catalog: folding table 6 ft, banquet round, stacking chair stack, monitor, projector, podium, whiteboard, power strip box.
   - Only use trucks that have interior dimensions. In `trucks.csv` (pre-event; kept in the private planning repo) that's the U-Haul 10, 15, 20 and 26 ft. The Penske rows and the cargo van have no dimensions.
5. **Photos.** Take 6 to 10 photos of the venue and put them in `media/`, which is git-ignored.
6. **Sample inventory.** Track B writes `sample_venue.json` by hand in the inventory format.

## Model provider layer

We use Gemini 4 today, and Chris may want to switch the same code to Claude models later. So **no file outside `backend/llm/` imports a model SDK**. Code asks for a job, not a model:

```python
from llm import for_job
inventory = for_job("perceive").generate_json(prompt, media=[clip], schema=INVENTORY_SCHEMA)
```

| Piece | What it does |
|---|---|
| `models.toml` | Maps each job to `provider:model`: `perceive`, `decide`, `plan`, `baseline`, `image`. Env vars such as `MODEL_PERCEIVE` override a line. Moving a job to Claude later is a config change plus an adapter |
| `base.py` | The interface: `generate_json(prompt, media, schema)`, `generate_text(prompt, media)`, `decide(question, media, options)`, `generate_image(prompt, refs)` |
| `gemini.py` | Today's only adapter: the `google-genai` SDK, schema passed as the response schema, video uploaded as a file |
| `claude.py` | Later, not today |
| Shared code in `__init__.py` | Load the JSON schema once; validate every response with `jsonschema` whatever the provider; retry once on invalid output; log job, provider, model and latency per call. The log feeds the "which model did which job" slide |

What won't carry over one-to-one, so design for it now without building it:

- **Video.** Gemini takes a video file directly. Claude's API takes images, not video, so a future Claude adapter samples frames from each clip. Keep `media` a list of file paths so either approach fits.
- **Decisions API.** Gemini-only. `decide()` gets a generic fallback: a structured-output call whose answer is an enum. The fallback is also plan B if the 10:30 test call fails, but using it loses Decisions API credit, which is 20% of the score.
- **Image generation.** Claude doesn't generate images, so `image` stays on Nano Banana or moves to another image provider.
- **Managed Agents.** Gemini-specific. `agents.py` takes a strategy and returns a placement. A local runner that calls the solver in-process is the fallback, and another agent platform could slot in later.

The default config is all Gemini 4. The rules require at least two Gemini 4 models with clear jobs, so nothing in the demo should run on another provider.

## Track B: packing plan and output (George)

| # | Step | Done when |
|---|---|---|
| B1 | `catalog.py`: load both CSVs, look up items by `catalog_id`, estimate weight at 7 lb per cubic foot | Lookup of `sofa_3seat` returns its dimensions and weight |
| B2 | `expand.py`: inventory becomes a list of boxes and pieces. Multiply items by quantity, turn container fullness into box counts by contents type, and set flags (upright, on edge, light only on top) | The sample venue inventory gives a flat list with a count |
| B3 | `solver.py`: run `py3dbp` against one truck. Leftovers open the next truck until everything is placed. Order heavy before light and big before small. Number the loading steps | Sample venue gives "N × uhaul_26" with every item placed |
| B4 | `verify.py`: pure-function checks for fit, overlap, support (at least 75% of the base supported), the upright and on-edge rules, light-only-on-top, and left-right weight balance. Combine into a weighted score | A deliberately broken plan fails with named violations |
| B5 | `index.html` 3D view: draw truck outlines and colour-coded boxes from the placement format, with a step-through in loading order | The sample plan renders and plays back |
| B6 | `planner.py`: the Neon loop. Neon reads the violations and returns changed strategy settings (ordering, rotations, truck size), then re-solve. Up to 3 rounds | The score improves across rounds and is logged |
| B7 | `agents.py`: Managed Agents. Run 3 or 4 runs in the background with different strategies. Each runs the solver in its sandbox and returns a placement. The checker picks the winner | Runs are visible in the UI as they finish |
| B8 | Unload order: reverse the loading order for each truck and show it as a list | Shown after the arrival beat |
| B9 | `render.py`: Nano Banana arrival image from the Penn Station photos plus crops of recognisable venue items, through `for_job("image")`. Show an "illustrative" badge | One image is shown in the UI |
| B10 | `labels.py` and a print page: one label per box with a QR code. The QR code **holds the data itself**, not a link: box ID, short name (see A6), room, contents, fragile flag, truck and load step, destination. Any phone camera reads it with no server or wifi. Keep it to a few hundred characters; shorten the contents list if needed. Also draw the QR code on the front face of each box in the 3D view. About 45 minutes | A printed label scanned with a phone camera shows the box's contents and destination |

Why QR labels are worth it: QR box-tracking apps already exist (Sortly, Encircle), but they only record what a person says they packed. Ours come out of the packing plan already filled in. See `research/moving-planner/notes/adjacent_inventory_scanning_apps.md` (pre-event; kept in the private planning repo).

## Track A: ingestion and analysis (Chris)

| # | Step | Done when |
|---|---|---|
| A0 | `backend/llm/`: the provider layer above, Gemini adapter only | `for_job("perceive").generate_text("hello")` answers, and switching the job's model in `models.toml` needs no code change |
| A1 | `perceive.py`: one Hydrogen call per photo or clip, through `for_job("perceive")`, with the response schema set to the inventory format. The prompt says to pick a `catalog_id` from the catalog list, give no dimensions, and remove duplicates | A venue photo returns valid JSON |
| A2 | Merge rooms: run calls in parallel, then combine. Duplicate items across photos are A3's job | Three photos give one inventory |
| A3 | `gaps.py`: Decisions API yes/no and multiple-choice questions. Is this container full? Is item X in photo 1 the same as item Y in photo 2? Is this fragile? Answers update the inventory | At least one real question is answered by the API and one is asked of the user |
| A4 | `app.py` endpoints. Chris: `POST /upload`, `GET /inventory`, `POST /answer`. George adds `POST /solve` and `POST /render` | Upload all the way to a placement works with curl |
| A5 | Review screen: item list with crops of where each was seen (the schema has `box_2d`), keep or trash toggles, and question cards | You can edit a quantity and re-solve |
| A6 | **Stretch, after 3 PM only.** `identify_box.py`: recognise a box from a photo, without the QR code. Plain cardboard boxes look almost the same, so use a middle ground: each box gets a short name that's easy to write and read ("Blue 7", "Kitchen C"), written on it in marker, with an optional photo of the contents before sealing. A photo of the box goes to `for_job("perceive")` to read the handwriting and note tape, size and damage, then `for_job("decide")` (Decisions API) picks the matching box from the stored list, or answers "none" | A photo of a marked box returns the right box and its contents. Log every miss in `FAILURES.md` |

A6 is part of the move, not a product of its own: on its own, a box recognizer would look like an "Image Analyzer," which the organizers list as a project to avoid. B10 gives A6 its short names, so build B10 first.

## Joining and checking (1:00 onward)

1. **Join the tracks (1:00 to 1:30).** Run real photos through inventory, questions, solver and checker to the 3D view. From here everything runs on real input.
2. **Baselines** (`eval/`):
   - Ask one model call for a full plan with coordinates, and score it with *our* checker.
   - Compare against the truck size the rental sites recommend by bedroom count.
3. **Test set.** Three venue spots filmed by us, plus rooms filmed by people outside the team if we can get them. Hand-count the items in 2 or 3 of them and report found, missed and double-counted.
4. **`RESULTS.md`:** one table with violations per plan and the percentage of valid plans, baseline against ours, and the number of rooms tested.
5. **`FAILURES.md`:** one line for every time something breaks, all day long.

## Not worked out yet

- **Decisions API.** We don't know its request shape: our notes come from third-party write-ups. Give A3 a 15-minute test call at 10:30 before we depend on it.
- **Speed of `py3dbp`.** It slows down past a few hundred items, which is why chair stacks count as one item. If it still drags, cap boxes per truck or switch to a simpler layer-by-layer packer.
