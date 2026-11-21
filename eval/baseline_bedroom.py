"""Baseline B: Rental-site room/bedroom-count truck size heuristic.

Rental calculators recommend:
  - 1 room / studio-1BR -> 1 x U-Haul 10 ft
  - 2 rooms             -> 1 x U-Haul 15 ft
  - 3 rooms             -> 1 x U-Haul 20 ft
  - 4+ rooms            -> 1 x U-Haul 26 ft

Scores that single-truck recommendation against the real expanded inventory
with our physics solver + `verify.verify()` (counting overflow / unplaced items).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend import catalog, solver, verify

ROOT = Path(__file__).resolve().parents[1]


def recommend_truck_by_room_count(inventory: dict[str, Any]) -> str:
    n_rooms = max(1, len(inventory.get("rooms") or []))
    if n_rooms <= 1:
        return "uhaul_10"
    if n_rooms == 2:
        return "uhaul_15"
    if n_rooms == 3:
        return "uhaul_20"
    return "uhaul_26"


def run_bedroom_baseline(inventory: dict[str, Any]) -> dict[str, Any]:
    rec_truck = recommend_truck_by_room_count(inventory)
    solved = solver.solve(inventory, strategy={"truck_id": rec_truck, "downsize_last_truck": False})
    trucks = solved.get("trucks") or []
    # Rental calculators always quote 1 truck of that size; anything spilling into truck 2+ is overflow!
    first_truck = trucks[:1]
    overflow_items = [it for t in trucks[1:] for it in (t.get("items") or [])]
    unplaced = list(solved.get("unplaced") or []) + [
        {"id": it["id"], "label": it["label"], "reason": f"overflowed single {rec_truck} recommended by room count"}
        for it in overflow_items
    ]
    single_truck_plan = {
        "trucks": first_truck,
        "zones": solved.get("zones") or [],
        "unplaced": unplaced,
        "strategy": {"packer_engine": "bedroom_calculator", "recommended_truck": rec_truck},
    }
    score = verify.verify(single_truck_plan, check_zones=False)
    return {
        "recommended_truck": rec_truck,
        "needed_trucks_of_that_size": len(trucks),
        "overflow_piece_count": len(overflow_items),
        "score": score,
    }


if __name__ == "__main__":
    sample = json.loads((ROOT / "data" / "sample_venue.json").read_text(encoding="utf-8"))
    out = run_bedroom_baseline(sample)
    print(json.dumps({k: v for k, v in out.items() if k != "score"}, indent=2))
    print("Score:", out["score"]["total"], "Violations:", out["score"]["violation_count"])
