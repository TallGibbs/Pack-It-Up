# Ingestion pipeline spec (Track A)

Photos and video of a room go in. A resolved inventory comes out: every movable item with its label, size, specs, estimated weight and volume, plus the questions we could not answer from the footage. This is the build spec for Track A in [BUILD_STEPS.md](BUILD_STEPS.md). Where the two differ, this file wins for Track A.

All code goes in [TallGibbs/Pack-It-Up](https://github.com/TallGibbs/Pack-It-Up) (local checkout: `C:\Users\Gibbl\Documents\Projects\Pack-It-Up`). This spec was written in the private planning repo at the event and copied here on Nov 21; this copy is now the live one.

## What changed from BUILD_STEPS

| Before | Now | Why |
|---|---|---|
| The model gives no dimensions; size comes only from the catalog | The model estimates dimensions for every item, and code decides which size to trust: catalog first, model estimate second | The venue is full of items the catalog doesn't have (see "What the sample media shows"). Comparing the model's estimate with the catalog also catches a wrong catalog pick |
| Weight is 7 lb per cubic foot for everything | Weight comes from a density table keyed by material, with the model's own estimate as a cross-check | A marble-top console and a foam ottoman of the same size differ several times over in weight |
| Inventory schema has no size, weight or volume | The resolved inventory adds a `size` block per item | Track B's solver and the review screen both need it |
| Video is treated as pictures only | The soundtrack of every clip is processed too: a timestamped transcript, plus facts the person filming says out loud, applied to the inventory | People narrate while they film ("the bookshelf is full", "this chair stays", "there's a piano in the other room"). That answers questions the camera can't, and it's part of what Element 119 means by video beating a text description |

## Design rules

1. **No file outside `backend/llm/` imports a model SDK.** Code asks for a job: `for_job("perceive")`. Which provider and model does that job is set in `backend/llm/models.toml`. Swapping Gemini for Claude later means a new adapter file plus a config change.
2. **The model sees; code measures.** The model names items, picks a catalog row, estimates size and flags handling needs. Code computes volume, picks the size source and estimates weight. Numbers the solver uses must be traceable to a catalog row, a density table or a named model estimate.
3. **Every stage writes its output to disk.** A run folder holds each stage's JSON, so a failed stage can be re-run alone, the demo has a cached fallback, and the eval reads the same files.
4. **Cache every model call** by file hash, job, model and prompt version. Re-running on the same media costs nothing and works without wifi.
5. **Validate every model response** against its JSON schema in shared code, whatever the provider. Retry once with the validation error in the prompt, then fail the file loudly and log it to `FAILURES.md`.
6. **What a person says beats what the model guesses.** Order of trust, highest first: an answer typed in the review screen, then something the person filming said in the clip's audio, then the catalog, then the model's visual estimate.

## Pipeline

```
upload ─► 1 intake ─► 2 perceive (one call per file, in parallel) ─► 3 merge ─► 4 resolve ─► 5 questions ─► inventory.json
                                                                                         ▲            │
                                                                                         └── answers ◄┘  (POST /answer re-runs 4)
```

| Stage | File | Model call? | Input | Output (in `runs/<run_id>/`) |
|---|---|---|---|---|
| 1 Intake | `backend/ingest/intake.py` | No | Uploaded files, room name | `manifest.json`: one entry per file with hash, kind, mime, size, duration, path to the normalised copy |
| 2 Perceive | `backend/ingest/perceive.py` | `perceive` | One photo or clip, catalog list | `perception/<file>.json`, one per file |
| 3 Merge | `backend/ingest/merge.py` | No (optional `decide` for duplicates) | All perception files for a room | `merged.json`: one item list per room, duplicates folded |
| 4 Resolve | `backend/ingest/resolve.py` | No | `merged.json`, catalog, density table | `inventory.json`: the contract Track B reads |
| 5 Questions | `backend/ingest/gaps.py` | `decide` | `inventory.json`, the media | `questions.json`; answers patch `merged.json` and re-run stage 4 |

Every call also appends a line to `runs/<run_id>/calls.jsonl`: job, provider, model, prompt version, file, latency, tokens if reported, cache hit or miss, valid or not. That log feeds the "which model did which job" slide.

### Stage 1: intake

- Accept `.jpg .jpeg .png .heic .heif .webp .mp4 .mov .m4v`, matching the extension case-insensitively (the iPhone files are `IMG_6705.JPEG` and `IMG_6703.MP4`).
- HEIC photos convert to JPEG (`pillow-heif`). Photos larger than 2048 px on the long side are downscaled to 2048. Apply the EXIF rotation before saving.
- Videos stay as they are unless the provider rejects them. If it does, transcode to H.264 MP4 at 720p with `imageio-ffmpeg`, which ships its own ffmpeg binary, so nobody installs anything. **Keep the audio track in any transcode** (AAC); never pass `-an`.
- Hash each file (SHA-256 of the bytes). The hash is the cache key and the file's id in later stages.
- Read video duration and whether the clip has an audio track with `imageio-ffmpeg`, and store both (`duration_s`, `has_audio`) in the manifest.
- For a clip with audio, also extract the soundtrack to `audio/<hash>.m4a` (or `.wav`, 16 kHz mono). It is only used by the transcription fallback (see stage 2) and for replaying a quote in the review screen.
- Room name comes from the upload form; default to the folder name, else `room_1`.

### Stage 2: perceive

One call per file through `for_job("perceive").generate_json(prompt, media=[file], schema=PERCEPTION_SCHEMA)`. Run them in parallel with a limit of 6 at a time, a 90-second timeout, and one retry.

**What the model returns per file** (`PERCEPTION_SCHEMA`):

| Field | Type | Notes |
|---|---|---|
| `room_guess` | string | e.g. "lounge" |
| `scale_refs` | list of strings | Objects the model used for scale: door (80 in), counter (36 in), bar stool seat (30 in), floor plank width |
| `items[]` | list | One entry per distinct physical item or identical group, deduplicated within this file |
| `items[].label` | string | Short and specific: "rust bouclé barrel armchair" |
| `items[].catalog_id` | string | A row id from the catalog, or `unknown` |
| `items[].quantity` | int ≥ 1 | Identical items may be grouped: "bar stool ×4" |
| `items[].move_class` | enum | `movable`, `fixture`, `personal_belonging`, `small_loose` (see below) |
| `items[].est_dims_in` | `[length, width, height]` | Model estimate in inches, always filled, even when a catalog row is picked |
| `items[].dims_basis` | string | Which scale reference it used |
| `items[].material` | enum | `upholstered`, `wood_solid`, `wood_composite`, `metal`, `glass`, `stone`, `plastic`, `electronics`, `mixed` |
| `items[].est_weight_lb` | number | Model estimate for one unit; a cross-check only |
| `items[].fragile`, `must_stay_upright`, `disassemble`, `two_person`, `stackable` | bool | Handling specs |
| `items[].stack_count` | int | For stacked chairs or nested tables; 1 otherwise |
| `items[].evidence` | object | `timestamp_s` (video only), `box_2d` as `[ymin, xmin, ymax, xmax]` on a 0–1000 scale |
| `items[].partially_visible` | bool | Cut off by the frame edge or hidden behind something |
| `items[].confidence` | 0–1 | |
| `containers[]` | list | As in `inventory.schema.json` (pre-event; kept in the private planning repo): kind, contents, fullness, size. Add kind `open_surfaces` for shelves and tops with loose decor |
| `uncertain[]` | list of strings | Anything the model wants to ask: closed doors, items it can't identify, counts it isn't sure of |
| `transcript[]` | list | Clips only. Speech in the soundtrack as segments: `start_s`, `end_s`, `text`. Empty list when nobody speaks |
| `spoken_facts[]` | list | Clips only. Each thing said that changes the inventory: `timestamp_s`, `quote` (the words, verbatim), `kind`, `refers_to` (an item or container index in this response, or `null`), `value` |
| `spoken_facts[].kind` | enum | `disposition` (keep, sell, donate, trash), `not_moving` (stays behind, belongs to someone else), `contents` (what's inside, how full), `count` ("there are twelve of these"), `fragile`, `size` ("it's an eight-foot table"), `identity` ("that's a standing desk"), `unfilmed_item` (named but not on camera), `other` |
| `items[].heard_only` | bool | True for an item that was only mentioned in the audio and never seen |

**Audio.** Gemini takes a video file's soundtrack along with its frames, so the same perceive call covers both: no separate call is needed for Gemini. The prompt asks the model to:

- Transcribe any speech with timestamps.
- Treat speech from the person filming (close to the microphone, describing the room) as instructions about the inventory. Ignore background conversation, music and announcements; the venue clips will have other hackers talking nearby.
- Link each spoken fact to the item on screen at that moment when the words point at it ("this one", "that shelf"), using the timestamp.
- Add an item with `heard_only: true` when the narrator names something that never appears on camera.
- Never let speech remove an item silently: a `not_moving` fact sets the item's disposition, and it still shows in the review screen.

Clips without speech, and photos, return empty `transcript` and `spoken_facts` lists.

**`move_class` decides what gets packed.** Only `movable` items and the box estimate for `small_loose` items go to the solver.

| Class | Meaning | Examples from the sample photos | Goes to the solver |
|---|---|---|---|
| `movable` | Free-standing furniture or equipment | Sofas, armchairs, ottomans, bar stools, coffee and side tables, floor lamp, communal table, dining chairs, sideboard, open shelving unit, potted plant, framed art | Yes, as an item |
| `fixture` | Attached to the building | Built-in shelving, pendant lights, wall sconces, track lighting, the espresso bar counter, exit sign, fire extinguisher, security cameras, wall-mounted mirror | No; listed for the review screen only |
| `personal_belonging` | Belongs to people in the room, not the space | Backpacks, laptops, coats, water bottles, coffee cups | No; dropped from the inventory, counted in a footnote |
| `small_loose` | Under about 1.5 cu ft and boxable | Vases, books, cushions, sculpture, tissue box | As boxes, through `containers` with `kind: open_surfaces` |

**Prompt** (`backend/prompts/perceive_v1.md`, version string in the cache key):

- Give the full catalog as a compact table: `catalog_id | name | L×W×H in`. The model picks the closest row and size variant, or `unknown`.
- List the `move_class` rules and the examples above.
- Tell it to ignore reflections in mirrors and windows, count an item cut off at the frame edge once and mark it partial, and count each item once across a video even when the camera passes it twice.
- Ask for dimensions in inches with the scale reference named.
- For video, ask for the timestamp where each item is clearest.
- Say nothing about the hackathon or Penn Station. The prompt has to work on any home.

**Per-job settings in `models.toml`:** thinking level, media resolution, and video frame rate. Start with high media resolution for photos and 2 frames per second for clips under 60 seconds (the sample clips are 10 and 16 seconds; the default of 1 fps gives too few frames for a fast pan).

### Stage 3: merge

Within one room, the same item usually shows up in several photos and in the clip. Across rooms, items are different.

1. Group every perceived `movable` item in a room by `catalog_id` (or by normalised label when `unknown`).
2. Within a group, items from **different files** are presumed to be the same set. Quantity = the largest count seen in any single file, not the sum. Keep the evidence with the highest confidence, and keep the others as `also_seen_in`.
3. Items from the **same file** were already deduplicated by the model; add their quantities.
4. Flag a group for a duplicate question when the labels within it clearly differ (colour or material words don't match). Stage 5 asks the Decisions API "is item X in photo 1 the same as item Y in photo 2?" with both crops.
5. Containers merge the same way, by kind and contents. A known fullness beats `not_visible`.
6. Spoken facts follow the item they refer to into the merged group and are applied there: `disposition` and `not_moving` set the disposition, `contents` sets a container's contents and fullness, `count` replaces the quantity, `fragile` sets the flag, `size` replaces the model's estimate, `identity` sets the label and lets the model's catalog pick be revisited. Record each change on the item as `set_by_speech: [{"field", "quote", "source", "timestamp_s"}]` so the review screen can show "you said: …".
7. `heard_only` items are kept, with quantity from the speech if given, and always get an `unfilmed_area` question (stage 5) so the user confirms them.
8. Save every clip's transcript to `transcripts/<file>.json` in the run folder.

Rule 2 will undercount when two photos show different halves of a room that hold the same kind of item. Accept that for today; the count-check question in stage 5 is the safety net. Log it in `FAILURES.md` when it happens.

### Stage 4: resolve (no model call)

For each merged `movable` item:

**Size.**

| Case | Dimensions used | `size_source` |
|---|---|---|
| The narrator gave a size ("eight-foot table") | Spoken size for that dimension, the rest from the catalog or the model | `speech` |
| Catalog row picked, and the model's longest side is within ±35% of the catalog's longest side | Catalog | `catalog` |
| Catalog row picked, but outside ±35% | Model estimate, and raise a `size_check` question | `vision_estimate` |
| `unknown` with a model estimate | Model estimate | `vision_estimate` |
| No usable estimate | Category default from a small table in `resolve.py` | `category_default` |

Sort the three dimensions so length ≥ width for the solver, but keep height as height.

**Volume.** `volume_cuft = L × W × H / 1728`, per unit and total (× quantity). Stacks: the stack's own dimensions, quantity 1, `stack_count` kept for display.

**Weight.** Per unit:

1. Catalog weight, if the catalog has a `weight_lb` column for the row (it doesn't yet; see Coordination).
2. Otherwise `volume_cuft × density(material)`, from this table in `resolve.py`:

   | Material | lb per cu ft (whole-item bounding box) |
   |---|---|
   | upholstered | 5 |
   | plastic | 4 |
   | wood_composite | 8 |
   | wood_solid | 10 |
   | mixed | 7 |
   | metal | 10 |
   | electronics | 12 |
   | glass | 12 |
   | stone | 20 |

   These are rough starting values for bounding boxes, not solid material. Tune them against a few known items if there is time.
3. If the model's `est_weight_lb` is within ⅓× to 3× of the density figure, use the model's number (it has seen the item). Otherwise use the density figure. Record `weight_source` as `catalog`, `density`, or `vision_estimate`.

**Specs.** Handling flags from the catalog row win; model flags fill any the catalog doesn't set.

**Small loose items** go into the room's `open_surfaces` container with a rough count, and Track B's `expand.py` turns containers into boxes, as planned.

**Output item shape** (the existing schema plus the new `size` block):

```json
{
  "id": "malin_item_04",
  "label": "rust bouclé barrel armchair",
  "catalog_id": "armchair",
  "quantity": 1,
  "stack_count": 1,
  "confidence": 0.86,
  "move_class": "movable",
  "size": {
    "dims_in": [36, 36, 36],
    "size_source": "catalog",
    "vision_dims_in": [38, 36, 30],
    "volume_cuft_each": 27.0,
    "volume_cuft_total": 27.0,
    "weight_lb_each": 85,
    "weight_lb_total": 85,
    "weight_source": "vision_estimate",
    "material": "upholstered"
  },
  "fragile": false,
  "must_stay_upright": false,
  "disassemble": false,
  "two_person": false,
  "stackable": "light_only",
  "disposition": "undecided",
  "evidence": {"source": "IMG_6705.JPEG", "timestamp_s": null, "box_2d": [610, 520, 960, 700]},
  "also_seen_in": ["IMG_6703.MP4@4.0"],
  "notes": ""
}
```

Each room also gets totals: item count, total volume, total weight, and the counts of fixtures and personal belongings left out.

### Stage 5: questions

The Decisions API answers what it can from the media; the rest goes to the user. This is BUILD_STEPS step A3; first spend 15 minutes on a test call to learn the Decisions API's request shape.

**Triggers:**

| Kind | When | Asked of |
|---|---|---|
| `hidden_contents` | A container's fullness is `not_visible` | The user, after the Decisions API tries |
| `same_item` | Merge flagged a group with differing labels | The Decisions API, with both crops |
| `size_check` | The model's size and the catalog's disagree by more than 35% | The Decisions API: "Which is closer: A or B?" with the crop |
| `identify_item` | `unknown` catalog id and confidence below 0.6 | The user, with the crop |
| `count_check` | Partially visible items, or quantity above 4 | The Decisions API first |
| `include_class` | Any personal belongings found | The user, once per room: "Leave out the bags, laptops and coats?" |

| `unfilmed_area` | An item was only heard, never seen (`heard_only`) | The user, quoting what was said |

**Speech first:** before asking anything, check the item's `set_by_speech` list. A question whose answer the narrator already gave is not asked; it is shown as answered with the quote.

**Ranking:** order the questions by how many cubic feet the answer could change (`volume at stake × (1 − confidence)`), and show the user at most 5. Questions the Decisions API answered with confidence ≥ 0.7 are applied automatically and shown as answered.

**Interface:** `for_job("decide").decide(question, media, options) -> {"answer", "confidence", "rationale"}`. The Gemini adapter calls the Decisions API. The generic fallback is a structured `generate_json` call whose answer is an enum of the options; it also covers the case where the Decisions API test call fails at kickoff. Using the fallback loses Decisions API credit, so log which one ran.

**Answers** patch `merged.json` (quantity, catalog id, fullness, merge or split) and re-run stage 4 only.

## Model provider layer (`backend/llm/`)

BUILD_STEPS already sets this out. What the build needs on top:

```
backend/llm/
  __init__.py     for_job(), schema validation, retry, cache, call log, video fallback
  base.py         Provider interface and the Media type
  gemini.py       the only adapter today
  media.py        frame sampling and crops (imageio-ffmpeg, Pillow)
  models.toml     job → provider:model plus per-job settings
```

**Interface (`base.py`):**

```python
@dataclass
class Media:
    path: Path
    kind: Literal["image", "video", "audio"]
    mime: str
    sha256: str
    start_s: float | None = None   # optional clip window
    end_s: float | None = None

class Provider(Protocol):
    name: str
    capabilities: set[str]   # e.g. {"image_in", "video_in", "audio_in", "json_schema", "decide_native", "image_out"}
    def generate_json(self, prompt: str, media: list[Media], schema: dict, settings: dict) -> dict: ...
    def generate_text(self, prompt: str, media: list[Media], settings: dict) -> str: ...
    def decide(self, question: str, media: list[Media], options: list[str], settings: dict) -> dict: ...
    def generate_image(self, prompt: str, refs: list[Media], settings: dict) -> bytes: ...
```

**Shared code in `__init__.py`, not in adapters:**

- `for_job(name)` reads `models.toml`; an env var such as `MODEL_PERCEIVE=gemini:gemini-4-hydrogen` overrides the line.
- If the provider lacks `video_in`, `media.py` samples frames from the clip (2 fps, at most 60 frames) and passes them as images, with each frame's timestamp written into the prompt. A future Claude adapter gets video support for free this way.
- If the provider lacks `video_in` or `audio_in` and the clip has audio, shared code first sends the extracted soundtrack to `for_job("transcribe")` (any provider with `audio_in`) and puts the timestamped transcript into the perceive prompt as text, so the frames-only model can still produce `spoken_facts`. With Gemini on `perceive`, this path is not used.
- Audio media gets `kind: "audio"` in the `Media` type.
- If the provider lacks `decide_native`, `decide()` falls back to `generate_json` with an enum schema.
- Cache: `.cache/llm/<sha of job, model, prompt version, media hashes, schema>.json`. Git-ignore `.cache/`.
- Validate with `jsonschema`, retry once, log every call.

**Gemini adapter (`gemini.py`):**

- `google-genai` SDK. Key from `GEMINI_API_KEY` in `.env`.
- Photos go inline as bytes. Clips go through the Files API; wait until the file is active before calling. Cache the uploaded file name by hash for the session.
- Pass the schema as the response JSON schema. If the model rejects a schema feature, simplify the schema (no `$ref`, `oneOf` or `additionalProperties`) rather than dropping validation. Keep `PERCEPTION_SCHEMA` flat from the start so it also works with other providers.
- Map `settings` to thinking level, media resolution and video frame rate.

**`models.toml` starting point.** The model IDs are not confirmed; replace them with the IDs shown in AI Studio after the kickoff hello test.

```toml
[jobs.perceive]
model = "gemini:gemini-4-hydrogen"    # fast tier; one call per file
media_resolution = "high"
video_fps = 2
thinking = "low"

[jobs.decide]
model = "gemini:decisions-1"          # Decisions API; confirm the ID and request shape at kickoff

[jobs.transcribe]
model = "gemini:gemini-3.5-transcribe"  # only used when the perceive model can't hear; confirm the ID

[jobs.perceive_fallback]
model = "gemini:gemini-4-argon"       # if Hydrogen access is missing or its output is weak
```

Track B adds `plan`, `baseline` and `image`.

## Interfaces

**CLI**, for testing and for handing George real inventories early:

```powershell
python -m backend.ingest data/Inputs/Malin --room "Malin lounge"
```

It prints the run id and a summary table (item, quantity, size source, volume, weight) and writes the run folder.

**HTTP** (FastAPI, in `backend/app.py`):

| Route | Body | Returns |
|---|---|---|
| `POST /upload` | multipart files plus `room` | `{run_id}` right away; the pipeline runs in the background |
| `GET /runs/{run_id}` | | Stage status per file (for a progress display), then the inventory and open questions when done |
| `GET /inventory/{run_id}` | | `inventory.json` |
| `POST /answer/{run_id}` | `{question_id, answer}` | The updated inventory |
| `PATCH /inventory/{run_id}/items/{item_id}` | `{quantity?, disposition?, catalog_id?}` | The updated inventory (review screen edits) |
| `GET /media/{run_id}/{file_hash}/crop?box=…&t=…` | | A JPEG crop for the review thumbnail, cut from the photo or from the clip frame at `t` |

Several uploads with different room names under one `run_id` make a multi-room move.

## Speed budget

The demo script gives inventory 30 seconds (0:20 to 0:50).

- Photos: all perceive calls in parallel, so the slowest single call sets the time. Target under 20 seconds for 6 photos.
- Clips: the upload and processing wait is the slow part. Start uploading clips the moment intake finishes, before photos are sent.
- Show stage status as each file finishes, so the screen is never blank.
- If a call is still running at 60 seconds, show the inventory from the files that finished and mark the rest as pending.

## What the sample media shows

Checked by eye; no model call was made, because no API key was available in this session.

| File | What's there | What it means for the build |
|---|---|---|
| `Inputs/Malin/IMG_6705.JPEG` | Lounge: 2 sofas, 3 armchairs, 2 leather ottomans, 4 bar stools, a long counter on turned legs, coffee table, round side tables, floor lamp, rug, built-in shelving, a large wall mirror, espresso bar | The mirror reflects the room, so double counting is a real risk. Built-in shelving and the bar are fixtures. The counter table may be fixed to the wall; that's a `count_check` or `identify_item` question |
| `Inputs/Malin/IMG_6707.JPEG` | Close-up of a long sideboard with a stone top, a large framed canvas, and decor (sculpture, vase, book, tissue box) | Sideboard is not in the catalog. Decor is `small_loose`. A close-up has few scale references; the cabinet door height is the best one |
| `Inputs/Malin/IMG_6708.JPEG` | Work area: a long communal table with about 8 chairs, a second table, an open metal shelving unit on a credenza, boucle armchair, table lamp, potted plant, pendant lights; hackers' backpacks, laptops, coats and bottles everywhere | Personal belongings must be left out. Chairs partly hidden behind bags need a count check. The communal table is longer than any catalog table |
| `Inputs/Malin/IMG_6703.MP4`, `IMG_6704.MP4` | 16 s and 10 s clips, 7.0 and 4.3 MB, H.264 video with an audio track | Short pans: raise the frame rate to 2 fps. Small enough to upload whole. No transcode needed. Whether anyone speaks in them is not checked yet; the venue was busy, so expect background talk that must be ignored |
| `NYPenn/IMG_6698.MP4`, `IMG_6699.MP4` | 2 s and 4 s clips, H.264 with audio | Destination reference only; not run through ingestion |
| Photos in general | 2048 × 1536 JPEG, about 0.7 MB each, uppercase extensions | Within inline limits; no resizing needed for these |

**Catalog gaps** found in these three photos: ottoman or pouf, sideboard or credenza, accent or barrel chair, console or counter table, large communal table (10 ft or more), open shelving unit (étagère), table lamp, large potted plant, large framed art, flat area rug, espresso machine. Until rows exist, these go through as `unknown` with the model's size.

## Evaluation hooks

- **Hand count for Malin.** Count the movable items in IMG_6705 and IMG_6708 by hand into `eval/hand_counts/malin.json` (catalog id or label, quantity). Do it before the first model run so the count isn't anchored on the output.
- **`eval/score_inventory.py`** compares a run's `inventory.json` with a hand count: found, missed, double counted, and fixtures or personal belongings wrongly included. Matching is by catalog id, then by label.
- **Size check.** For 5 catalog items, report the model's estimate against the catalog dimensions as percent error. That's the honest answer to "how accurate is the size?"
- **Audio check.** Film one narrated clip with three or four spoken facts, write them down first, and report how many the pipeline applied correctly. Include one clip with background talk and no narration, and check that nothing was applied from it.
- **Demo tip.** Narrate while filming the live demo clip ("these chairs stack, the cabinet's full"). The judges see the inventory change because of what was said.
- Malin was shot on event day and counts as unprepared input. Keep any clip filmed for rehearsal out of the reported numbers.

## Build order

| # | Step | Done when | Time box |
|---|---|---|---|
| I0 | `backend/llm/`: interface, Gemini adapter, `models.toml`, cache, call log | `for_job("perceive").generate_text("hello")` answers; changing the model line needs no code change; a second identical call is a cache hit | 25 min |
| I1 | Intake: accepted types, HEIC, hashing, durations, run folder | The CLI on `data/Inputs/Malin` writes a correct `manifest.json` | 15 min |
| I2 | Perceive on one photo: schema, prompt v1, validation and retry | IMG_6705 returns valid JSON with fixtures and movables separated | 30 min |
| I3 | Perceive on clips, including the soundtrack; all files in parallel; merge with spoken facts applied | The Malin folder gives one room inventory, with no item counted from both the photo and the clip. A short narrated test clip ("this sofa stays; the shelf is full of books; there's a piano in the back room") produces a transcript, sets the sofa's disposition, fills the shelf's contents, and adds a `heard_only` piano | 45 min |
| I4 | Resolve: size source, volume, weight, specs, totals | Every movable item has dimensions, volume and weight, each with a source | 20 min |
| I5 | FastAPI routes and the crop endpoint | Upload to inventory works with curl; George's solver reads the inventory | 20 min |
| I6 | Questions: Decisions API test call, triggers, ranking, answers | At least one question is answered by the Decisions API and one by the user, and an answer changes the inventory | 45 min |
| I7 | Hand count and scorer | `eval/score_inventory.py` prints found, missed and double counted for Malin | 20 min |

Review screen (BUILD_STEPS A5) comes after I7 and uses the crop endpoint.

## Coordination with Track B (George)

- **Inventory contract.** Send George the item shape above as soon as I4 runs. His `expand.py` should read `size.dims_in` and `size.weight_lb_each` instead of looking up the catalog itself, so `unknown` items still pack.
- **Catalog.** George owns `data/item_catalog.csv` and `backend/catalog.py`. Ask him to add the venue rows plus the gap rows above, and an optional `weight_lb` column. If `catalog.py` doesn't exist yet when I4 starts, create it with only `load()` and `get(catalog_id)` and tell him, so he extends it rather than rewriting it.
- **Media.** Demo media is git-ignored in both repos. Copy `data/Inputs/Malin/*` from the planning repo into `Pack-It-Up/data/Inputs/Malin/` locally; never commit it.

## Not settled

- **Model IDs and access.** Hydrogen, Argon and the Decisions API IDs come from third-party notes. Confirm them in AI Studio at kickoff and update `models.toml`.
- **Decisions API request shape.** Unknown until the test call. The fallback keeps the pipeline working either way.
- **Schema features Gemini 4 accepts** in its response schema. Unknown until I2; keep the schema flat.
- **Size accuracy** from a single photo. No published figures exist; the size check in Evaluation is our own number.
- **HEVC video.** The sample clips are H.264, but other phones may record HEVC. The transcode step covers it if the Files API rejects one.
- **Speaker separation.** Whether Gemini can reliably tell the narrator from people talking nearby. If it can't, fall back to applying only facts that refer to something on screen at that moment, and log it in `FAILURES.md`.
- **Privacy.** Transcripts can contain names and bystanders' words. They stay in the git-ignored run folder (add `runs/` to `.gitignore`) and are never committed.
