# Ingestion pipeline (Track A)

Photos and clips of a room go in; `runs/<run_id>/inventory.json` comes out.

```powershell
python -m backend.ingest data/Inputs/Malin --room "Malin lounge"
```

| Stage | File | Model job | Writes (in `runs/<run_id>/`) |
|---|---|---|---|
| 1 Intake | `intake.py` | none | `manifest.json`, `media/` |
| 2 Perceive | `perceive.py` | `perceive` | `perception/<file>.json` |
| 3 Merge | `merge.py` | none | `merged.json` |
| 4 Resolve | `resolve.py` | none | `inventory.json` |
| 5 Questions | `gaps.py` | `decide` | `questions.json` |

Every model call is logged to `runs/<run_id>/calls.jsonl` and cached in `.cache/llm/`.

## Inventory contract (for Track B)

`inventory.json` has `rooms[]`; each room has `items[]`, `containers[]`, `fixtures[]`, `left_out` and `totals`. Read sizes and weights from each item's `size` block, not from the catalog, so `unknown` items still pack:

```json
{
  "id": "malin_lounge_item_04",
  "label": "Room divider bookshelf",
  "catalog_id": "bookshelf_tall",
  "quantity": 1,
  "stack_count": 1,
  "size": {
    "dims_in": [96, 16, 84],
    "size_source": "vision_estimate",
    "volume_cuft_each": 74.67, "volume_cuft_total": 74.67,
    "weight_lb_each": 220, "weight_lb_total": 220,
    "weight_source": "vision_estimate",
    "material": "wood_solid"
  },
  "fragile": false, "must_stay_upright": false, "load_on_edge": false,
  "disassemble": true, "two_person": true, "stackable": "no",
  "disposition": "undecided",
  "evidence": {"source": "IMG_6703.MP4", "timestamp_s": 5.0, "box_2d": [0, 345, 761, 839]}
}
```

- `dims_in` is `[length, width, height]` with length >= width; height stays height.
- `size_source`: `speech` (the narrator gave a size), `catalog`, `vision_estimate` or `category_default`. `weight_source`: `catalog`, `density` or `vision_estimate`.
- `stackable` uses the catalog's values: `yes`, `no`, `light_only`.
- Skip items whose `disposition` is `trash`, `sell`, `donate` or `stays` (the narrator said it isn't moving). They stay in the list for the review screen.
- `heard_only: true` marks an item the narrator named but never filmed; its size comes from the catalog or a category default. It packs unless the user answers its `unfilmed_area` question with "no".
- `set_by_speech` lists what the narrator's words changed: `[{"field", "value", "quote", "source", "timestamp_s"}]`, so the review screen can show "you said: …". Containers carry the same list.

## Audio

Gemini hears each clip's soundtrack in the same perceive call. The model returns a timestamped `transcript` (narrator vs background) and `spoken_facts`; merge applies them. Order of trust: a typed answer, then the narrator, then the catalog, then the model's visual estimate. Transcripts are saved to `runs/<id>/transcripts/` and never committed. If the perceive model can't hear (no `audio_in`), shared code in `backend/llm/` transcribes the soundtrack with the `transcribe` job first and puts the transcript in the prompt; `MODEL_PERCEIVE_DISABLE=video_in,audio_in` forces that path for testing.
- Containers with `kind: open_surfaces` carry `est_volume_cuft` and `est_boxes` for loose decor.
