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
  "id": "malin_lounge_bookshelf_tall",
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
- Every container carries `est_volume_cuft` and `est_boxes` (`{catalog box id: count}`, e.g. `{"box_dish_pack": 5}`; `{}` when empty or closed). For a cabinet, shelf or closet it is the space inside for its kind and size class, capped by the furniture it is part of, times how full it is (`resolve.container_boxes`). The sizes and the box for each kind of contents are the ones in Track B's `backend/expand.py`, except that bathroom cabinets and `other` are smaller and the furniture cap applies; change the two files together. The `open_surfaces` line is sized from the loose decor seen. A shelf of decor can be counted in both; the figures are rough, and the review page says "about N boxes".
- Item ids come from the item's group (`room_1_armchair`, `room_1_unknown_potted_plant`), not from its place in the list, so an id means the same item after another photo of the room arrives. Treat them as opaque strings. Runs made before 13:30 on Nov 21 stored numbered ids (`room_1_item_07`); those still work for edits and answers.
- Closed containers (doors or drawers shut) come out with `fullness: "empty"`, `contents_unknown: true` and `note: "contents unknown, assumed empty"` (Chris's decision, Nov 21: footage can't see inside, so nothing guesses). The furniture holding them gets `contents_unknown: true`. The user is always asked (`hidden_contents`, `always_show: true`); the answer replaces the assumption.
- Upholstered seating is grouped by seat count (prompt v3 `seat_class`): `armchair` = single seat, `sofa_loveseat` = two seats, `sofa_3seat` = three or more.

## Questions

`questions.json` lists every question with `status` (`open` or `answered`), `answered_by` (`decisions_api`, `generate_json_fallback`, `speech`, `user`) and `shown` (the top 5 open ones by volume at stake, plus any with `always_show`). Count questions (`count_check`) offer numbers up to twice the estimate plus `"more"`, and take any typed whole number (`free_text: "number"`); `"more"` itself is not accepted as an answer.
