"""Tests for Track B core modules: B1 (catalog), B2 (expand), B3 (solver), B4 (verify)."""
from __future__ import annotations

import json
from pathlib import Path

from backend import catalog, expand, solver, verify

ROOT = Path(__file__).resolve().parents[1]


def _base_truck(items: list[dict], dims: list[float] | None = None, max_weight_lb: float = 12859.0) -> dict:
    return {
        "trucks": [{
            "truck_id": "uhaul_26",
            "index": 0,
            "dims_in": dims or [314.0, 98.0, 99.0],
            "max_weight_lb": max_weight_lb,
            "items": items,
        }],
        "unplaced": [],
    }


def test_b1_catalog_trucks_and_penn_zones() -> None:
    sofa = catalog.lookup("sofa_3seat")
    assert sofa is not None
    assert sofa["dims_in"] == [84.0, 36.0, 34.0]
    assert sofa["weight_lb"] == 416.5  # 59.5 cu ft * 7 lb/cu ft

    # Track A resolve.py relies on get(id).get("weight_lb") staying None when CSV leaves it blank
    raw_sofa = catalog.get("sofa_3seat")
    assert raw_sofa is not None and raw_sofa.get("weight_lb") is None

    # Venue items exist
    for cid in ("folding_table_6ft", "banquet_round", "stacking_chair_stack", "podium", "whiteboard_mobile"):
        assert catalog.lookup(cid) is not None

    trucks = catalog.list_trucks()
    assert [t["truck_id"] for t in trucks] == ["uhaul_10", "uhaul_15", "uhaul_20", "uhaul_26"]
    assert catalog.get_truck("uhaul_26")["dims_in"] == [314.0, 98.0, 99.0]

    zones = catalog.list_penn_zones()
    assert len(zones) == 6
    assert [z["dock_stop"] for z in zones] == [1, 2, 3, 4, 5, 6]


def test_b2_expand_inventory_and_store_routing() -> None:
    sample = json.loads((ROOT / "data" / "sample_venue.json").read_text(encoding="utf-8"))
    pieces = expand.expand_inventory(sample)

    assert len(pieces) == 152
    assert sum(1 for p in pieces if p["is_box"]) == 42
    assert sum(1 for p in pieces if not p["is_box"]) == 110

    # `stays` items and `contents_unknown` closed containers do not go on the truck
    assert all(p["catalog_id"] != "plant_large" for p in pieces)
    assert all(p["source_id"] != "lounge_cont_03" for p in pieces)

    # All 6 Penn Station stores/zones receive stock and every assigned item clears its store doorway
    zones_by_id = catalog.load_penn_zones()
    assert len({p["dest_zone"] for p in pieces}) == 6
    for p in pieces:
        assert expand.can_pass_door(p, zones_by_id[p["dest_zone"]])


def test_b3_solver_sample_venue_and_mock_inventory() -> None:
    sample = json.loads((ROOT / "data" / "sample_venue.json").read_text(encoding="utf-8"))
    plan = solver.solve(sample)

    assert plan["unplaced"] == []
    assert plan["summary"]["total_items"] == 152
    assert plan["summary"]["zones_stocked"] == 6
    assert plan["score"]["valid"] is True
    assert plan["score"]["violations"] == []
    assert plan["score"]["total"] >= 85.0

    # Verify consecutive 1..N load_seq per truck
    for t in plan["trucks"]:
        assert [it["load_seq"] for it in t["items"]] == list(range(1, len(t["items"]) + 1))

    # Track A mock fixture also solves cleanly with zero violations
    mock_inv = json.loads((ROOT / "frontend" / "mock" / "inventory.json").read_text(encoding="utf-8"))
    mock_plan = solver.solve(mock_inv)
    assert mock_plan["score"]["valid"] is True
    assert mock_plan["score"]["violations"] == []

    # Oversized upright items on a 10-ft truck fail gracefully into `unplaced` instead of looping
    small_plan = solver.solve(sample, strategy={"truck_id": "uhaul_10"})
    assert len(small_plan["unplaced"]) == 3
    assert small_plan["score"]["valid"] is False
    assert "unplaced_item" in small_plan["score"]["violation_counts_by_rule"]


def test_b4_raw_py3dbp_caught_by_verifier() -> None:
    sample = json.loads((ROOT / "data" / "sample_venue.json").read_text(encoding="utf-8"))
    raw_plan = solver.solve(sample, strategy={"packer_engine": "raw_py3dbp"})
    sc = raw_plan["score"]
    assert sc["valid"] is False
    for expected_rule in ("support", "upright", "no_stack", "weight_balance"):
        assert expected_rule in sc["violation_counts_by_rule"]


def test_b4_deliberately_broken_plans_fail_with_named_violations() -> None:
    # 1. Fit (out of bounds)
    p_fit = _base_truck([{
        "id": "bad_fit", "label": "sofa", "pos_in": [260, 30, 0], "size_in": [84, 36, 34],
        "weight_lb": 150, "load_seq": 1, "fragile": False,
    }])
    res = verify.verify(p_fit, check_zones=False)
    assert not res["valid"] and "fit" in res["violation_counts_by_rule"]

    # 2. Truck overweight
    p_wt = _base_truck([{
        "id": "heavy", "label": "lead block", "pos_in": [0, 39, 0], "size_in": [20, 20, 20],
        "weight_lb": 2000, "load_seq": 1, "fragile": False,
    }], max_weight_lb=1500.0)
    res = verify.verify(p_wt, check_zones=False)
    assert not res["valid"] and "truck_overweight" in res["violation_counts_by_rule"]

    # 3. Overlap
    p_ov = _base_truck([
        {"id": "a", "label": "box a", "pos_in": [0, 40, 0], "size_in": [20, 20, 20], "weight_lb": 30, "load_seq": 1},
        {"id": "b", "label": "box b", "pos_in": [10, 40, 0], "size_in": [20, 20, 20], "weight_lb": 30, "load_seq": 2},
    ])
    res = verify.verify(p_ov, check_zones=False)
    assert not res["valid"] and "overlap" in res["violation_counts_by_rule"]

    # 4. Support (< 75% base supported: upper 20x20 overhangs by 50%) + load_seq_support
    p_sup = _base_truck([
        {"id": "base", "label": "table", "pos_in": [0, 40, 0], "size_in": [20, 20, 20],
         "weight_lb": 40, "stackable": "yes", "load_seq": 2},
        {"id": "top", "label": "box", "pos_in": [10, 40, 20], "size_in": [20, 20, 16],
         "weight_lb": 20, "stackable": "yes", "load_seq": 1},
    ])
    res = verify.verify(p_sup, check_zones=False)
    assert not res["valid"]
    assert "support" in res["violation_counts_by_rule"]
    assert "load_seq_support" in res["violation_counts_by_rule"]

    # 5. Upright & load_on_edge
    p_orient = _base_truck([
        {"id": " tipped_fridge", "label": "fridge", "pos_in": [0, 30, 0], "size_in": [70, 36, 32],
         "orig_dims_in": [36, 32, 70], "must_stay_upright": True, "weight_lb": 200, "load_seq": 1},
        {"id": "flat_mattress", "label": "mattress", "pos_in": [80, 20, 0], "size_in": [80, 60, 10],
         "orig_dims_in": [80, 60, 10], "load_on_edge": True, "weight_lb": 90, "load_seq": 2},
    ])
    res = verify.verify(p_orient, check_zones=False)
    assert not res["valid"]
    assert "upright" in res["violation_counts_by_rule"]
    assert "load_on_edge" in res["violation_counts_by_rule"]

    # 6. Stacking rules: no_stack, light_only_on_top, fragile_crushed
    p_stack = _base_truck([
        {"id": "nostack_base", "label": "chair", "pos_in": [0, 40, 0], "size_in": [24, 24, 30],
         "stackable": "no", "weight_lb": 30, "load_seq": 1},
        {"id": "on_nostack", "label": "box", "pos_in": [0, 40, 30], "size_in": [18, 18, 16],
         "stackable": "yes", "weight_lb": 15, "load_seq": 2},
        {"id": "sofa", "label": "sofa", "pos_in": [40, 30, 0], "size_in": [84, 36, 34],
         "stackable": "light_only", "weight_lb": 150, "load_seq": 3},
        {"id": "heavy_on_sofa", "label": "book box", "pos_in": [40, 30, 34], "size_in": [18, 18, 16],
         "stackable": "yes", "weight_lb": 45, "load_seq": 4},
        {"id": "fragile_base", "label": "glass box", "pos_in": [140, 40, 0], "size_in": [24, 24, 20],
         "stackable": "light_only", "fragile": True, "weight_lb": 25, "load_seq": 5},
        {"id": "crusher", "label": "tool box", "pos_in": [140, 40, 20], "size_in": [18, 18, 16],
         "stackable": "yes", "weight_lb": 50, "load_seq": 6},
    ])
    res = verify.verify(p_stack, check_zones=False)
    assert not res["valid"]
    assert "no_stack" in res["violation_counts_by_rule"]
    assert "light_only_on_top" in res["violation_counts_by_rule"]
    assert "fragile_crushed" in res["violation_counts_by_rule"]

    # 7. Left-right weight balance (all weight hugged against y=0 left wall)
    p_unbal = _base_truck([
        {"id": "left_heavy", "label": "safe", "pos_in": [0, 0, 0], "size_in": [30, 20, 30],
         "weight_lb": 500, "load_seq": 1},
    ])
    res = verify.verify(p_unbal, check_zones=False)
    assert not res["valid"] and "weight_balance" in res["violation_counts_by_rule"]

    # 8. Penn Station store doorway clearance & single-hall dumping (`zone_distribution`)
    dumped = _base_truck([
        {
            "id": f"it_{k}", "label": "merch", "pos_in": [k * 20, 40, 0], "size_in": [18, 18, 16],
            "orig_dims_in": [48, 40, 82] if k == 0 else [18, 18, 16],
            "must_stay_upright": (k == 0),
            "weight_lb": 25, "load_seq": k + 1,
            "dest_zone": "penn_merch_kiosk" if k == 0 else "penn_concourse",
        }
        for k in range(12)
    ])
    res = verify.verify(dumped, check_zones=True)
    assert not res["valid"]
    assert "zone_door_clearance" in res["violation_counts_by_rule"]
    assert "zone_distribution" in res["violation_counts_by_rule"]


def test_zone_distribution_small_move_needs_two_stores_not_three() -> None:
    """A one-corner capture cannot stock three stores; one store over 75% still fails (FAILURES.md 15:17)."""

    def placement(n: int, zones: list[str]) -> dict:
        return {
            "trucks": [{
                "truck_id": "uhaul_26",
                "items": [
                    {"id": f"it_{k}", "label": "box", "pos_in": [k * 6, 10, 0], "size_in": [5, 5, 5],
                     "weight_lb": 5, "load_seq": k + 1, "dest_zone": zones[k % len(zones)]}
                    for k in range(n)
                ],
            }],
        }

    def flagged(p: dict) -> bool:
        violations, _ = verify.verify_zones(p)
        return any(v["rule"] == "zone_distribution" for v in violations)

    two = ["penn_bookshop", "penn_cafe"]
    assert not flagged(placement(14, two))                     # the 14- and 17-piece moves that failed
    assert not flagged(placement(17, two))
    assert flagged(placement(verify.SMALL_MOVE_PIECES, two))   # a full-size move still needs three stores
    assert flagged(placement(14, ["penn_concourse"]))          # everything in one hall still fails
    lopsided = placement(20, two)
    for it in lopsided["trucks"][0]["items"][:16]:
        it["dest_zone"] = "penn_cafe"                          # 16 of 20 = 80% in one store
    assert flagged(lopsided)
