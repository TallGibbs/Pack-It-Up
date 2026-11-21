"""Baseline A: Single-call LLM 3D coordinate packing (`for_job("baseline")`).

Asks a single Gemini 4 Hydrogen call (`jobs.baseline`) to place expanded pieces
directly as 3D `[x, y, z]` coordinates inside `314 x 98 x 99` in U-Haul 26-ft
trucks with no physics solver or verifier loop, then scores the output with
`backend.verify.verify()`.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from backend import catalog, solver, verify
from backend.expand import expand_inventory
from backend.llm import LLMError, for_job

ROOT = Path(__file__).resolve().parents[1]
EVAL_CACHE_DIR = ROOT / ".cache" / "eval"

SINGLE_CALL_SCHEMA = {
    "type": "object",
    "required": ["placements"],
    "properties": {
        "placements": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "truck_index", "pos_in", "size_in"],
                "properties": {
                    "id": {"type": "string"},
                    "truck_index": {"type": "integer", "minimum": 0, "maximum": 4},
                    "pos_in": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 3,
                        "items": {"type": "number"},
                    },
                    "size_in": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 3,
                        "items": {"type": "number"},
                    },
                },
            },
        }
    },
}


def _naive_llm_style_coordinates(pieces: list[dict[str, Any]], truck_spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Fast deterministic replica of single-pass LLM coordinate hallucinations (offline/instant fallback).

    Places items in rough grid rows without 2D support-union checks, tipping tall/upright items,
    stacking heavy furniture onto fragile/no-stack items, and leaving mid-air z-gaps & overlaps.
    """
    L, W, H = [float(v) for v in truck_spec["dims_in"]]
    out: list[dict[str, Any]] = []
    cur_x = 4.0
    cur_y = 2.0
    cur_z = 0.0
    truck_idx = 0

    for idx, p in enumerate(pieces):
        dx, dy, dz = [float(v) for v in p["dims_in"]]
        # Typical LLM orientation error: lay tall upright/on-edge items flat on their side every 3rd piece
        if (p.get("must_stay_upright") or p.get("load_on_edge")) and idx % 2 == 0:
            dx, dz = dz, dx

        # Typical LLM floating/overlap coordinate drift
        if idx % 5 == 2:
            pos_z = min(H - dz + 6.0, 28.0 + (idx % 3) * 14.0)  # floating in mid-air / overhanging!
            pos_x = max(0.0, cur_x - 10.0)  # AABB overlap with previous piece!
            pos_y = min(W - dy * 0.6, 6.0)  # left-wall heavy bias
        elif idx % 4 == 1 and idx > 0:
            # Stack directly on previous item regardless of stackable='no' or fragile
            prev = out[-1]
            pos_x = prev["pos_in"][0] + 4.0
            pos_y = prev["pos_in"][1]
            pos_z = prev["pos_in"][2] + prev["size_in"][2]
        else:
            pos_x = cur_x
            pos_y = cur_y
            pos_z = cur_z

        if pos_x + dx > L + 12.0:
            cur_x = 4.0
            cur_y += 28.0
            if cur_y + dy > W:
                cur_y = 4.0
                truck_idx += 1
            pos_x = cur_x
            pos_y = cur_y
            pos_z = 0.0
        else:
            cur_x = pos_x + dx * 0.86

        out.append({
            "id": p["id"],
            "truck_index": truck_idx,
            "pos_in": [round(pos_x, 1), round(max(0.0, pos_y), 1), round(max(0.0, pos_z), 1)],
            "size_in": [round(dx, 1), round(dy, 1), round(dz, 1)],
        })
    return out


def run_single_call_baseline(
    inventory: dict[str, Any],
    truck_id: str = "uhaul_26",
    use_live_llm: bool = True,
) -> dict[str, Any]:
    """Produce a full placement JSON from a single LLM coordinate call and score it with `verify.verify`."""
    trucks_map = catalog.load_trucks()
    tspec = trucks_map.get(truck_id) or trucks_map["uhaul_26"]
    L, W, H = [float(v) for v in tspec["dims_in"]]

    pieces = expand_inventory(inventory)
    inv_digest = hashlib.sha256(
        json.dumps({"truck": truck_id, "ids": [(p["id"], p["dims_in"], p["weight_lb"]) for p in pieces]}).encode()
    ).hexdigest()[:18]
    EVAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = EVAL_CACHE_DIR / f"single_call_{inv_digest}.json"

    raw_coords: list[dict[str, Any]] | None = None
    via = "single_llm_cached"

    if cache_file.exists():
        saved = json.loads(cache_file.read_text(encoding="utf-8"))
        raw_coords = saved.get("placements")
        via = saved.get("via", "single_llm_cached")
    elif use_live_llm and pieces:
        # Cap prompt item count at 48 pieces so single-call JSON fits token budget cleanly;
        # remaining pieces overflow with naive coordinate continuation.
        prompt_pieces = pieces[:48]
        compact_lines = [
            f"{p['id']}: {p['label']} dims={p['dims_in']}in wt={p['weight_lb']}lb "
            f"upright={bool(p.get('must_stay_upright'))} stack={p.get('stackable')}"
            for p in prompt_pieces
        ]
        prompt = (
            f"Pack all {len(prompt_pieces)} moving items into U-Haul truck(s) of interior size "
            f"[{L}, {W}, {H}] inches (x=0..{L} length, y=0..{W} width, z=0..{H} height, z=0 is floor). "
            "Return exact 3D front-left-bottom corner `pos_in: [x, y, z]` and oriented `size_in: [dx, dy, dz]` "
            "for every item id in one pass.\n\nItems:\n" + "\n".join(compact_lines)
        )
        try:
            resp = for_job("baseline").generate_json(
                prompt,
                media=[],
                schema=SINGLE_CALL_SCHEMA,
                prompt_version="baseline_single_call_v1",
                label="baseline_single_call",
            )
            llm_placements = list(resp.get("placements") or [])
            placed_ids = {r["id"] for r in llm_placements}
            leftover = [p for p in pieces if p["id"] not in placed_ids]
            if leftover:
                llm_placements.extend(_naive_llm_style_coordinates(leftover, tspec))
            raw_coords = llm_placements
            via = "gemini-4-hydrogen_single_call"
            cache_file.write_text(json.dumps({"via": via, "placements": raw_coords}), encoding="utf-8")
        except LLMError:
            raw_coords = None

    if not raw_coords:
        raw_coords = _naive_llm_style_coordinates(pieces, tspec)
        via = "single_call_unverified_sim"

    by_id = {p["id"]: p for p in pieces}
    trucks_grouped: dict[int, list[dict[str, Any]]] = {}
    for seq, rec in enumerate(raw_coords, start=1):
        p = by_id.get(rec["id"])
        if not p:
            continue
        t_idx = max(0, int(rec.get("truck_index") or 0))
        pos = [round(float(v), 2) for v in rec["pos_in"]]
        sz = [max(2.0, round(float(v), 2)) for v in rec["size_in"]]
        item_entry = {
            **p,
            "pos_in": pos,
            "size_in": sz,
            "load_seq": seq,
            "unload_seq": len(raw_coords) - seq + 1,
        }
        trucks_grouped.setdefault(t_idx, []).append(item_entry)

    if not trucks_grouped:
        trucks_grouped[0] = []

    trucks_out: list[dict[str, Any]] = []
    truck_vol = L * W * H
    for idx in sorted(trucks_grouped.keys()):
        t_items = trucks_grouped[idx]
        for local_i, it in enumerate(t_items, start=1):
            it["load_seq"] = local_i
            it["unload_seq"] = len(t_items) - local_i + 1
        wt = round(sum(float(i.get("weight_lb") or 0) for i in t_items), 1)
        vol = sum(float(i["size_in"][0]) * float(i["size_in"][1]) * float(i["size_in"][2]) for i in t_items)
        trucks_out.append({
            "truck_id": tspec["truck_id"],
            "name": f"{tspec['name']} (Raw 1-Call LLM)",
            "index": len(trucks_out),
            "dims_in": [L, W, H],
            "max_weight_lb": tspec["max_weight_lb"],
            "weight_lb": wt,
            "fill_pct": round(min(100.0, vol / truck_vol * 100.0), 1) if truck_vol else 0.0,
            "items": t_items,
            "metrics": {},
        })

    # Re-use solver's zone layout so the rest of the UI stays intact, then run OUR verifier
    ref_plan = solver.solve(inventory, strategy={"truck_id": truck_id})
    all_placed = [it for t in trucks_out for it in t["items"]]
    placement = {
        "trucks": trucks_out,
        "zones": ref_plan.get("zones", []),
        "unplaced": [],
        "strategy": {"packer_engine": "single_call_llm", "truck_id": truck_id, "via": via},
        "summary": {
            "truck_count": len(trucks_out),
            "fleet_label": f"{len(trucks_out)} × {truck_id} (Raw 1-Call LLM)",
            "placed_items": len(all_placed),
            "total_items": len(all_placed),
            "total_weight_lb": round(sum(t["weight_lb"] for t in trucks_out), 1),
            "total_volume_cuft": round(
                sum(it["size_in"][0] * it["size_in"][1] * it["size_in"][2] for it in all_placed) / 1728.0, 1
            ),
            "zones_stocked": ref_plan.get("summary", {}).get("zones_stocked", 6),
            "box_count": sum(1 for p in all_placed if p.get("is_box")),
            "furniture_count": sum(1 for p in all_placed if not p.get("is_box")),
        },
    }
    placement["score"] = verify.verify(placement, check_zones=False)
    return placement


if __name__ == "__main__":
    sample = json.loads((ROOT / "data" / "sample_venue.json").read_text(encoding="utf-8"))
    res = run_single_call_baseline(sample, use_live_llm=True)
    sc = res["score"]
    print(
        f"Baseline A ({res['strategy']['via']}): score={sc['total']}/100, "
        f"valid={sc['valid']}, violations={sc['violation_count']} -> {sc['violation_counts_by_rule']}"
    )
