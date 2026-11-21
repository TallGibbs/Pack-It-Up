"""Stage B2: expand an `inventory_v2` JSON into a flat list of packable pieces and boxes.

Reads dimensions and weights from each item's `size` block (the Track A inventory
contract) rather than overriding from the catalog, multiplies by `quantity`, turns
room `containers` into typed moving boxes by contents and fullness, normalizes
mover handling flags (`must_stay_upright`, `load_on_edge`, `stackable`, `fragile`,
`two_person`), and assigns each piece to a Penn Station destination store/zone
(`data/penn_zones.csv`).

Coordinate & dimension convention shared across Track B:
    dims_in = [length_in (x), width_in (y), height_in (z)]
"""
from __future__ import annotations

import math
import re
from typing import Any

from backend import catalog

NOT_ON_TRUCK = {"trash", "sell", "donate", "stays", "removed"}

FULLNESS_FACTOR: dict[str, float] = {
    "empty": 0.0,
    "not_visible": 0.0,
    "quarter": 0.25,
    "half": 0.50,
    "three_quarters": 0.75,
    "full": 1.0,
}

# Full-container packable volume (cu ft, including packing pad factor) by (kind, size).
CONTAINER_FULL_CUFT: dict[str, dict[str, float]] = {
    "closet": {"small": 12.0, "medium": 24.0, "large": 42.0},
    "kitchen_cabinet": {"small": 8.0, "medium": 16.0, "large": 28.0},
    "pantry": {"small": 8.0, "medium": 15.0, "large": 26.0},
    "bathroom_cabinet": {"small": 4.0, "medium": 8.0, "large": 14.0},
    "bookshelf": {"small": 9.0, "medium": 18.0, "large": 30.0},
    "dresser_drawers": {"small": 8.0, "medium": 15.0, "large": 24.0},
    "desk": {"small": 4.5, "medium": 9.0, "large": 15.0},
    "toy_storage": {"small": 6.0, "medium": 13.5, "large": 22.5},
    "garage_shelving": {"small": 12.0, "medium": 24.0, "large": 42.0},
    "open_surfaces": {"small": 4.5, "medium": 9.0, "large": 15.0},
    "other": {"small": 6.0, "medium": 12.0, "large": 24.0},
}

# Contents -> (box_catalog_id, packed_weight_lb, force_fragile)
CONTENTS_BOX_SPEC: dict[str, tuple[str, float, bool]] = {
    "books": ("box_small", 38.0, False),
    "tools": ("box_small", 40.0, False),
    "papers_office": ("box_small", 30.0, False),
    "papers": ("box_small", 30.0, False),
    "dishes_glassware": ("box_dish_pack", 35.0, True),
    "clothes_hanging": ("box_wardrobe", 38.0, False),
    "pots_pans": ("box_medium", 28.0, False),
    "pantry_food": ("box_medium", 30.0, False),
    "toiletries": ("box_small", 22.0, False),
    "decor": ("box_medium", 20.0, True),
    "linens": ("box_large", 22.0, False),
    "clothes_folded": ("box_large", 26.0, False),
    "toys": ("box_large", 20.0, False),
    "mixed": ("box_medium", 26.0, False),
}


def _norm_stackable(val: Any, fragile: bool = False) -> str:
    if isinstance(val, bool):
        if not val or fragile:
            return "no"
        return "yes"
    s = str(val or "").strip().lower()
    if s in ("yes", "no", "light_only"):
        return "no" if (fragile and s == "yes") else s
    return "no"


def _short_room_tag(room_name: str, fallback: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z0-9]+", room_name or "") if w.lower() not in {"the", "and", "of", "room"}]
    if not words:
        return fallback.capitalize()
    tag = words[0].capitalize()
    return tag[:8]


def can_pass_door(piece: dict, zone: dict) -> bool:
    """Check whether `piece` can pass through `zone['door_in'] = [door_w, door_h]`."""
    dw, dh = sorted(zone["door_in"])
    l, w, h = piece["dims_in"]
    if piece.get("must_stay_upright") and not piece.get("disassemble"):
        # Must remain upright (height h vertical) while passing through door_height_in.
        return h <= zone["door_in"][1] + 1e-4 and min(l, w) <= zone["door_in"][0] + 1e-4
    # Can rotate or come through disassembled on its two smallest dimensions.
    s0, s1 = sorted([l, w, h])[:2]
    return s0 <= dw + 1e-4 and s1 <= dh + 1e-4


def _expand_item(item: dict, room_id: str, room_name: str) -> list[dict]:
    disp = (item.get("disposition") or "undecided").strip().lower()
    if disp in NOT_ON_TRUCK:
        return []
    qty = int(item.get("quantity") or 0)
    if qty <= 0:
        return []

    cid = item.get("catalog_id") or "unknown"
    cat_info = catalog.lookup(cid) if cid != "unknown" else None
    sz = item.get("size") or {}

    dims = sz.get("dims_in")
    if not (isinstance(dims, list) and len(dims) == 3 and all(isinstance(d, (int, float)) and d > 0 for d in dims)):
        dims = list(cat_info["dims_in"]) if cat_info else [24.0, 24.0, 24.0]
    else:
        dims = [float(dims[0]), float(dims[1]), float(dims[2])]
        dims = [max(dims[0], dims[1]), min(dims[0], dims[1]), dims[2]]

    vol_each = round((dims[0] * dims[1] * dims[2]) / 1728.0, 2)
    weight_each = sz.get("weight_lb_each")
    if weight_each is None or float(weight_each) <= 0:
        weight_each = cat_info["weight_lb"] if cat_info else round(vol_each * catalog.DEFAULT_LB_PER_CUFT, 1)
    weight_each = round(float(weight_each), 1)

    fragile = bool(item.get("fragile", cat_info["fragile"] if cat_info else False))
    must_stay_upright = bool(item.get("must_stay_upright", cat_info["must_stay_upright"] if cat_info else False))
    load_on_edge = bool(
        item["load_on_edge"]
        if "load_on_edge" in item and item["load_on_edge"] is not None
        else (cat_info["load_on_edge"] if cat_info else False)
    )
    disassemble = bool(item.get("disassemble", False))
    two_person = bool(item.get("two_person", cat_info["two_person"] if cat_info else False)) or weight_each > 50.0
    stackable = _norm_stackable(
        item.get("stackable", cat_info["stackable"] if cat_info else "no"),
        fragile=fragile,
    )
    category = (cat_info["category"] if cat_info else None) or sz.get("material") or "movable"
    stack_count = int(item.get("stack_count") or 1)
    src_id = item.get("id") or cid

    pieces: list[dict] = []
    for idx in range(1, qty + 1):
        pid = f"{src_id}_{idx:02d}" if qty > 1 else str(src_id)
        pieces.append({
            "id": pid,
            "source_id": src_id,
            "label": item.get("label") or (cat_info["name"] if cat_info else "item"),
            "catalog_id": cid,
            "category": category,
            "room_id": room_id,
            "room_name": room_name,
            "is_box": False,
            "box_short_name": None,
            "contents": None,
            "dims_in": list(dims),
            "volume_cuft": vol_each,
            "weight_lb": weight_each,
            "fragile": fragile,
            "must_stay_upright": must_stay_upright,
            "load_on_edge": load_on_edge,
            "disassemble": disassemble,
            "two_person": two_person,
            "stackable": stackable,
            "stack_count": stack_count,
            "heard_only": bool(item.get("heard_only", False)),
            "evidence": item.get("evidence"),
            "dest_zone": item.get("dest_zone"),
        })
    return pieces


def _container_box_counts(container: dict, box_scale: float = 1.0) -> list[tuple[str, int, float, bool]]:
    """Return list of (box_catalog_id, count, weight_lb, fragile) for one container."""
    fullness = (container.get("fullness") or "empty").strip().lower()
    if fullness in ("empty", "not_visible") or container.get("contents_unknown"):
        return []

    contents = (container.get("contents") or "mixed").strip().lower()
    default_box_id, default_wt, force_fragile = CONTENTS_BOX_SPEC.get(contents, CONTENTS_BOX_SPEC["mixed"])
    is_fragile = bool(container.get("fragile")) or force_fragile

    est_boxes = container.get("est_boxes")
    if isinstance(est_boxes, dict) and est_boxes:
        out: list[tuple[str, int, float, bool]] = []
        for box_cid, raw_cnt in est_boxes.items():
            cnt = max(0, round(int(raw_cnt) * box_scale))
            if cnt <= 0:
                continue
            _, wt, ff = CONTENTS_BOX_SPEC.get(contents, ("box_medium", 25.0, False))
            if box_cid == "box_small":
                wt = max(wt, 30.0)
            elif box_cid == "box_large":
                wt = min(wt, 26.0)
            elif box_cid == "box_dish_pack":
                wt, ff = 35.0, True
            elif box_cid == "box_wardrobe":
                wt = 38.0
            out.append((box_cid, cnt, wt, is_fragile or ff))
        return out

    factor = FULLNESS_FACTOR.get(fullness, 0.5) * box_scale
    if factor <= 0:
        return []

    kind = (container.get("kind") or "other").strip().lower()
    sz_name = (container.get("size") or "medium").strip().lower()
    kind_table = CONTAINER_FULL_CUFT.get(kind, CONTAINER_FULL_CUFT["other"])
    target_cuft = kind_table.get(sz_name, kind_table["medium"]) * factor

    box_info = catalog.lookup(default_box_id) or catalog.lookup("box_medium")
    assert box_info is not None
    box_vol = max(1.0, box_info["volume_cuft"])
    count = max(1, math.ceil(target_cuft / box_vol))
    return [(box_info["catalog_id"], count, default_wt, is_fragile)]


def _expand_containers(
    containers: list[dict],
    room_id: str,
    room_name: str,
    room_box_counter: dict[str, int],
    box_scale: float = 1.0,
) -> list[dict]:
    boxes: list[dict] = []
    room_tag = _short_room_tag(room_name, room_id)

    for cont in containers:
        specs = _container_box_counts(cont, box_scale=box_scale)
        if not specs:
            continue
        cont_id = cont.get("id") or f"{room_id}_cont"
        cont_label = cont.get("label") or "packed container"
        contents_raw = cont.get("contents") or "mixed"
        items_preview = cont.get("items")
        if isinstance(items_preview, list) and items_preview:
            contents_desc = ", ".join(str(x) for x in items_preview[:5])
        else:
            contents_desc = f"{contents_raw.replace('_', ' ')} ({cont_label})"

        local_idx = 0
        for box_cid, count, wt_lb, is_fragile in specs:
            box_info = catalog.lookup(box_cid) or catalog.lookup("box_medium")
            assert box_info is not None
            dims = list(box_info["dims_in"])
            dims = [max(dims[0], dims[1]), min(dims[0], dims[1]), dims[2]]
            stackable = _norm_stackable(box_info["stackable"], fragile=is_fragile)
            if is_fragile and box_cid != "box_dish_pack":
                # Fragile boxes can take light items at most, never heavy stacks.
                stackable = "light_only"
            for _ in range(count):
                local_idx += 1
                room_box_counter[room_tag] = room_box_counter.get(room_tag, 0) + 1
                short_name = f"{room_tag} {room_box_counter[room_tag]}"
                boxes.append({
                    "id": f"{cont_id}_box_{local_idx:02d}",
                    "source_id": cont_id,
                    "label": f"{box_info['name']} · {short_name} ({cont_label})",
                    "catalog_id": box_cid,
                    "category": "box",
                    "room_id": room_id,
                    "room_name": room_name,
                    "is_box": True,
                    "box_short_name": short_name,
                    "contents": contents_desc,
                    "contents_kind": contents_raw,
                    "dims_in": dims,
                    "volume_cuft": box_info["volume_cuft"],
                    "weight_lb": round(wt_lb, 1),
                    "fragile": is_fragile or box_info["fragile"],
                    "must_stay_upright": box_info["must_stay_upright"] or is_fragile,
                    "load_on_edge": False,
                    "disassemble": False,
                    "two_person": wt_lb > 50.0,
                    "stackable": stackable,
                    "stack_count": 1,
                    "heard_only": False,
                    "evidence": cont.get("evidence"),
                    "dest_zone": cont.get("dest_zone"),
                })
    return boxes


def _zone_affinity(piece: dict, zone: dict) -> float:
    text = " ".join(
        str(piece.get(k) or "")
        for k in ("label", "catalog_id", "contents", "contents_kind", "category", "room_name")
    ).lower()
    cat = str(piece.get("category") or "").lower()

    score = 0.0
    for kw in zone.get("keywords", []):
        if kw and kw in text:
            score += 32.0
    for zcat in zone.get("categories", []):
        if zcat and (zcat == cat or zcat in text):
            score += 20.0

    # Route boxes to matching retail/store units based on their contents.
    if piece.get("is_box"):
        ck = str(piece.get("contents_kind") or "").lower()
        zid = zone["zone_id"]
        if ck in ("books",) and zid == "penn_bookshop":
            score += 40.0
        elif ck in ("dishes_glassware", "pots_pans", "pantry_food") and zid == "penn_cafe":
            score += 40.0
        elif ck in ("papers_office", "papers") and zid == "penn_tech_hub":
            score += 36.0
        elif ck in ("clothes_folded", "clothes_hanging", "toys") and zid == "penn_merch_kiosk":
            score += 38.0
        elif ck in ("decor", "linens") and zid in ("penn_lounge", "penn_bookshop"):
            score += 28.0

    # Slight penalty on concourse unless it's true concourse banquet/stage gear,
    # so Penn Station storefronts get stocked first instead of dumping everything into one hall.
    if zone["zone_type"] == "concourse" and score < 25.0:
        score -= 12.0

    return score


def assign_penn_zones(
    pieces: list[dict],
    zones: list[dict] | None = None,
    strategy: dict | None = None,
) -> list[dict]:
    """Assign each piece to a Penn Station store/zone respecting doorway clearance and store capacity."""
    zones = list(zones or catalog.list_penn_zones())
    if not zones:
        return pieces
    zone_by_id = {z["zone_id"]: z for z in zones}
    strategy = strategy or {}
    overrides: dict[str, str] = dict(strategy.get("zone_overrides") or {})
    single_zone = strategy.get("force_single_zone")

    used_floor: dict[str, float] = {z["zone_id"]: 0.0 for z in zones}
    used_vol: dict[str, float] = {z["zone_id"]: 0.0 for z in zones}
    used_wt: dict[str, float] = {z["zone_id"]: 0.0 for z in zones}
    max_floor_ratio = float(strategy.get("zone_max_floor_ratio", 0.58))
    max_vol_ratio = float(strategy.get("zone_max_vol_ratio", 0.50))

    # Group identical source_ids slightly while assigning larger/specialized pieces first
    # so anchor furniture claims store floor space before small filler boxes.
    order = sorted(
        range(len(pieces)),
        key=lambda i: (not pieces[i]["is_box"], pieces[i]["volume_cuft"], pieces[i]["weight_lb"]),
        reverse=True,
    )

    for idx in order:
        p = pieces[idx]
        explicit = (
            single_zone
            or overrides.get(p["id"])
            or overrides.get(p["source_id"])
            or overrides.get(p["catalog_id"])
            or p.get("dest_zone")
        )
        if explicit and explicit in zone_by_id:
            chosen = zone_by_id[explicit]
        else:
            best_zone = None
            best_score = -1e9
            footprint_sqft = (p["dims_in"][0] * p["dims_in"][1]) / 144.0
            for z in zones:
                if not can_pass_door(p, z):
                    continue
                zid = z["zone_id"]
                floor_cap = z["floor_sqft"] * (0.85 if z["zone_type"] == "concourse" else max_floor_ratio)
                vol_cap = z["volume_cuft"] * (0.80 if z["zone_type"] == "concourse" else max_vol_ratio)
                if used_floor[zid] + footprint_sqft > floor_cap:
                    continue
                if used_vol[zid] + p["volume_cuft"] > vol_cap:
                    continue
                if used_wt[zid] + p["weight_lb"] > z["max_weight_lb"]:
                    continue

                fill_ratio = used_floor[zid] / max(1.0, floor_cap)
                # Under-stocked non-concourse storefronts get a boost so every store gets filled.
                underfill_bonus = (1.0 - fill_ratio) * (18.0 if z["zone_type"] != "concourse" else 4.0)
                sc = _zone_affinity(p, z) + underfill_bonus
                if sc > best_score:
                    best_score = sc
                    best_zone = z

            chosen = best_zone or zone_by_id.get("penn_concourse") or zones[-1]

        zid = chosen["zone_id"]
        p["dest_zone"] = zid
        p["dest_zone_name"] = chosen["name"]
        p["dock_stop"] = chosen["dock_stop"]
        used_floor[zid] += (p["dims_in"][0] * p["dims_in"][1]) / 144.0
        used_vol[zid] += p["volume_cuft"]
        used_wt[zid] += p["weight_lb"]

    return pieces


def expand_inventory(inventory: dict, strategy: dict | None = None) -> list[dict]:
    """Expand `inventory_v2` JSON into flat packable furniture pieces and moving boxes."""
    strategy = strategy or {}
    box_scale = float(strategy.get("box_scale", 1.0))

    pieces: list[dict] = []
    room_box_counter: dict[str, int] = {}

    for r_idx, room_block in enumerate(inventory.get("rooms", []), start=1):
        r_meta = room_block.get("room") or {}
        room_id = r_meta.get("id") or f"room_{r_idx}"
        room_name = r_meta.get("name") or room_id

        for item in room_block.get("items", []):
            pieces.extend(_expand_item(item, room_id, room_name))

        pieces.extend(
            _expand_containers(
                room_block.get("containers", []),
                room_id,
                room_name,
                room_box_counter,
                box_scale=box_scale,
            )
        )

    assign_penn_zones(pieces, strategy=strategy)
    return pieces
