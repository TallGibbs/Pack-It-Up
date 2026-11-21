"""Stage 4: resolve. No model call: the model sees, code measures.

For each merged movable item: pick the size source (catalog, vision estimate or
category default), compute volume, estimate weight (catalog, density table, or the
model's own estimate when it agrees with the density figure), and settle handling
specs (catalog flags win). Writes runs/<run_id>/inventory.json, the contract Track B reads.
"""
from __future__ import annotations

import datetime as dt

from backend import catalog

from .common import read_json, run_dir, update_status, write_json

SIZE_TOLERANCE = 0.35  # model's longest side within +-35% of the catalog's -> trust the catalog
VOLUME_RANGE = (0.5, 2.0)  # ...and its bounding-box volume within this factor of the catalog's

# lb per cubic foot of whole-item bounding box (rough starting values; see INGESTION_SPEC)
DENSITY = {"upholstered": 5, "plastic": 4, "wood_composite": 8, "wood_solid": 10, "mixed": 7,
           "metal": 10, "electronics": 12, "glass": 12, "stone": 20}

# Open frames (shelving, lamps, chairs, stools, tables, plants) have bounding boxes that are mostly air.
# Tuned on Malin: a 96x16x84 in open wood shelf ~260 lb, a floor lamp ~17 lb.
OPEN_FRAME_FACTOR = 0.35
OPEN_FRAME_PREFIXES = ("shelving", "bookshelf", "floor_lamp", "table_lamp", "stool", "bar_stool", "chair",
                       "dining_chair", "office_chair", "patio_chair", "table", "coffee_table", "end_table",
                       "dining_table", "console_table", "counter_table", "patio_table", "desk", "potted_plant")

# Used only when the model gave no usable dimensions. Keyed by merge.canon_key nouns.
CATEGORY_DEFAULT_DIMS = {
    "ottoman": [20, 20, 18], "sideboard": [72, 18, 32], "console_table": [60, 16, 30], "counter_table": [96, 18, 42],
    "framed_art": [36, 3, 28], "potted_plant": [24, 24, 60], "table_lamp": [16, 16, 26], "floor_lamp": [14, 14, 62],
    "shelving_unit": [36, 14, 72], "trash_bin": [14, 12, 24], "rug": [96, 10, 10], "mirror": [30, 3, 48],
    "bench": [48, 16, 18], "stool": [16, 16, 30], "armchair": [34, 34, 32], "chair": [20, 22, 34],
    "table": [60, 36, 30], "espresso_machine": [24, 18, 18], "tv": [50, 6, 30],
}
GENERIC_DEFAULT_DIMS = [24, 24, 24]

BOX_CUFT = 3.0  # box_medium, for open_surfaces estimates
NOT_ON_TRUCK = ("trash", "sell", "donate", "stays")  # "stays": the narrator said it is not moving
PACK_FACTOR = 2.0  # loose items take about twice their own volume once boxed and padded


def _yes(v) -> bool | None:
    if v in (None, ""):
        return None
    return str(v).strip().lower() in ("yes", "true", "1")


def _orient(dims: list[float]) -> list[float]:
    """Length >= width for the solver; height stays height."""
    l, w, h = dims
    return [max(l, w), min(l, w), h]


def _usable(dims) -> bool:
    return bool(dims) and len(dims) == 3 and all(isinstance(d, (int, float)) and d > 0 for d in dims)


def pick_size(item: dict, row: dict | None) -> tuple[list[float], str, dict | None]:
    """-> (dims_in, size_source, size_check or None)."""
    vision = _orient(item["est_dims_in"]) if _usable(item.get("est_dims_in")) else None
    choice = item.get("size_choice")  # set by a size_check answer
    if row and vision and item.get("stack_count", 1) <= 1:
        cat = [row["length_in"], row["width_in"], row["height_in"]]
        if choice == "catalog":
            return _orient(cat), "catalog", None
        if choice == "vision":
            return vision, "vision_estimate", None
        ratio = max(vision) / max(cat)
        vol_ratio = (vision[0] * vision[1] * vision[2]) / (cat[0] * cat[1] * cat[2])
        # Spec rule: longest side within +-35%. Added: volume within 0.5x-2x, which catches a
        # 96-in-wide shelving unit matched to a 32-in-wide bookshelf (same longest side, 4.7x the volume).
        if abs(ratio - 1) <= SIZE_TOLERANCE and VOLUME_RANGE[0] <= vol_ratio <= VOLUME_RANGE[1]:
            return _orient(cat), "catalog", None
        return vision, "vision_estimate", {"catalog_dims_in": _orient(cat), "vision_dims_in": vision,
                                           "longest_side_ratio": round(ratio, 2), "volume_ratio": round(vol_ratio, 2)}
    if vision:
        return vision, "vision_estimate", None
    if row:
        return _orient([row["length_in"], row["width_in"], row["height_in"]]), "catalog", None
    noun = item.get("group_key", "").split(":", 1)[-1]
    return list(CATEGORY_DEFAULT_DIMS.get(noun, GENERIC_DEFAULT_DIMS)), "category_default", None


def is_open_frame(item: dict) -> bool:
    keys = {item.get("catalog_id", ""), item.get("group_key", "").split(":", 1)[-1]}
    return any(k.startswith(OPEN_FRAME_PREFIXES) for k in keys if k)


def pick_weight(volume_each: float, material: str, model_lb: float | None, row: dict | None,
                open_frame: bool = False) -> tuple[float, str]:
    if row and row.get("weight_lb"):
        return round(row["weight_lb"], 1), "catalog"
    density_lb = volume_each * DENSITY.get(material, DENSITY["mixed"]) * (OPEN_FRAME_FACTOR if open_frame else 1)
    if model_lb and density_lb > 0 and density_lb / 3 <= model_lb <= density_lb * 3:
        return round(model_lb, 1), "vision_estimate"
    return round(density_lb, 1), "density"


def resolve_item(item: dict) -> dict:
    row = catalog.get(item["catalog_id"]) if item["catalog_id"] != "unknown" else None
    dims, size_source, size_check = pick_size(item, row)
    if item.get("speech_size"):  # the narrator gave a size: that dimension from speech, the rest as picked
        idx = {"length": 0, "width": 1, "height": 2}
        dims = list(dims)
        for dim, inches in item["speech_size"].items():
            dims[idx.get(dim, 0)] = inches
        dims, size_source, size_check = _orient(dims), "speech", None
    dims = [round(d, 1) for d in dims]
    vol_each = round(dims[0] * dims[1] * dims[2] / 1728, 2)
    material = item.get("material") or "mixed"
    w_each, w_source = pick_weight(vol_each, material, item.get("est_weight_lb"), row, is_open_frame(item))
    qty = item["quantity"]

    # Handling specs: catalog row wins, model fills the rest.
    spoken = {r["field"] for r in item.get("set_by_speech", [])}

    def spec(cat_col: str, model_key: str) -> bool:
        if model_key in spoken:  # speech beats the catalog
            return bool(item.get(model_key))
        v = _yes(row.get(cat_col)) if row else None
        return bool(item.get(model_key)) if v is None else v

    stackable = (row or {}).get("stackable_on_top") or ("yes" if item.get("stackable") else "no")
    out = {
        "id": item["id"],
        "label": item["label"],
        "catalog_id": item["catalog_id"],
        "quantity": qty,
        "stack_count": item.get("stack_count", 1),
        "confidence": item["confidence"],
        "move_class": "movable",
        "size": {
            "dims_in": dims,
            "size_source": size_source,
            "vision_dims_in": _orient(item["est_dims_in"]) if _usable(item.get("est_dims_in")) else None,
            "catalog_dims_in": _orient([row["length_in"], row["width_in"], row["height_in"]]) if row else None,
            "volume_cuft_each": vol_each,
            "volume_cuft_total": round(vol_each * qty, 2),
            "weight_lb_each": w_each,
            "weight_lb_total": round(w_each * qty, 1),
            "weight_source": w_source,
            "vision_weight_lb": item.get("est_weight_lb"),
            "material": material,
        },
        "fragile": spec("fragile", "fragile"),
        "must_stay_upright": spec("must_stay_upright", "must_stay_upright"),
        "load_on_edge": bool(_yes((row or {}).get("load_on_edge"))),
        "disassemble": bool(item.get("disassemble")),
        "two_person": spec("two_person", "two_person") or w_each > 50,
        "stackable": stackable,
        "disposition": item.get("disposition", "undecided"),
        "partially_visible": item.get("partially_visible", False),
        "evidence": item["evidence"],
        "also_seen_in": item.get("also_seen_in", []),
        "per_file_counts": item.get("per_file_counts", {}),
        "notes": item.get("notes", ""),
        "heard_only": bool(item.get("heard_only")),
        "set_by_speech": item.get("set_by_speech", []),
    }
    if size_check:
        out["size_check"] = size_check
    return out


def _containers(room: dict) -> list[dict]:
    rid = room["id"]
    out = []
    open_count = 0
    for c in room["containers"]:
        if c["kind"] == "open_surfaces":
            open_count += c.get("est_item_count", 0)
            continue
        out.append({"id": f"{rid}_cont_{len(out) + 1:02d}", "label": c["label"], "kind": c["kind"],
                    "contents": c["contents"], "fullness": c["fullness"], "size": c["size"],
                    "est_item_count": c.get("est_item_count", 0), "seen_in": c.get("seen_in", []),
                    "evidence": {"source": c["seen_in"][0], **(c.get("evidence") or {})} if c.get("seen_in") else None,
                    "set_by_speech": c.get("set_by_speech", []), "created_by_speech": c.get("created_by_speech", False)})
    # One open_surfaces container per room for loose decor, sized from the small_loose items.
    small = room.get("small_loose", [])
    small_count = sum(s["quantity"] for s in small)
    small_vol = sum(s["quantity"] * (s["est_dims_in"][0] * s["est_dims_in"][1] * s["est_dims_in"][2]) / 1728
                    for s in small if _usable(s.get("est_dims_in")))
    count = max(open_count, small_count)
    if count:
        boxed = max(small_vol * PACK_FACTOR, BOX_CUFT * (count / 8))
        out.append({"id": f"{rid}_cont_{len(out) + 1:02d}", "label": "loose decor on open surfaces",
                    "kind": "open_surfaces", "contents": "decor", "fullness": "quarter", "size": "small",
                    "est_item_count": count, "items": [f"{s['label']} x{s['quantity']}" for s in small],
                    "fragile": any(s.get("fragile") for s in small),
                    "est_volume_cuft": round(boxed, 1), "est_boxes": {"box_medium": max(1, round(boxed / BOX_CUFT))}})
    return out


def resolve_room(room: dict) -> dict:
    items = [resolve_item(it) for it in room["items"] if it.get("disposition") != "removed"]
    containers = _containers(room)
    keep = [i for i in items if i["disposition"] not in NOT_ON_TRUCK]
    box_vol = sum(c.get("est_volume_cuft", 0) for c in containers)
    return {
        "room": {"id": room["id"], "name": room["name"]},
        "files": room["files"],
        "items": items,
        "containers": containers,
        "fixtures": [{"label": f["label"], "quantity": f["quantity"]} for f in room["fixtures"]],
        "left_out": {"fixtures": sum(f["quantity"] for f in room["fixtures"]),
                     "personal_belongings": room["personal_belongings"]["count"],
                     "personal_belonging_kinds": room["personal_belongings"]["kinds"]},
        "totals": {
            "item_count": sum(i["quantity"] for i in keep),
            "item_lines": len(keep),
            "volume_cuft": round(sum(i["size"]["volume_cuft_total"] for i in keep), 1),
            "weight_lb": round(sum(i["size"]["weight_lb_total"] for i in keep), 1),
            "boxed_volume_cuft": round(box_vol, 1),
            "size_sources": _count(i["size"]["size_source"] for i in keep),
            "weight_sources": _count(i["size"]["weight_source"] for i in keep),
        },
    }


def _count(values) -> dict:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def resolve(run_id: str) -> dict:
    rd = run_dir(run_id)
    merged = read_json(rd / "merged.json")
    rooms = [resolve_room(r) for r in merged["rooms"]]
    questions = read_json(rd / "questions.json", {}).get("questions", [])
    inv = {
        "schema_version": "inventory_v2",
        "run_id": run_id,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "rooms": rooms,
        "totals": {
            "item_count": sum(r["totals"]["item_count"] for r in rooms),
            "volume_cuft": round(sum(r["totals"]["volume_cuft"] for r in rooms), 1),
            "weight_lb": round(sum(r["totals"]["weight_lb"] for r in rooms), 1),
            "boxed_volume_cuft": round(sum(r["totals"]["boxed_volume_cuft"] for r in rooms), 1),
        },
        "questions": questions,
        "answers_applied": merged.get("answers_applied", []),
    }
    write_json(rd / "inventory.json", inv)
    update_status(rd, stage="resolve_done")
    return inv
