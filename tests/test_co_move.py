"""Unit & API tests for Human + Robot Co-Move Biomechanics, Penn Station Occupancy,
and `gemini-robotics-er-2-preview` spatial scan integration.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import co_move, solver
from backend.app import app

REPO_ROOT = Path(__file__).resolve().parents[1]


def _sample_plan() -> dict:
    inv = json.loads((REPO_ROOT / "data" / "sample_venue.json").read_text(encoding="utf-8"))
    return solver.solve(inv)


def test_co_move_splits_robots_and_human_biomechanics():
    plan = _sample_plan()
    res = co_move.analyze_co_move(plan, occupancy_mode="permitted_bays")

    assert res["total_items"] > 20
    assert res["total_weight_lb"] > 500
    role_counts = {r["role"]: r["count"] for r in res["roles"]}
    assert sum(role_counts.values()) == res["total_items"]
    # Standard boxes should offload to dock_robot / amr_cart while bulky furniture stays human_ergo
    assert res["offloaded_items"] > 0
    assert res["offloaded_pct"] > 0
    assert role_counts["human_ergo"] > 0
    assert 60 <= res["ergo_score"] <= 100
    assert len(res["doorway_playbook"]) > 0


def test_penn_station_occupancy_modes_and_commuter_keepout():
    plan = _sample_plan()
    base = co_move.audit_penn_occupancy(plan, occupancy_mode="permitted_bays")
    crowded = co_move.audit_penn_occupancy(plan, occupancy_mode="crowded_stalls_35")
    tight = co_move.audit_penn_occupancy(plan, occupancy_mode="rush_hour_55")

    assert base["gross_station_sqft"] == 41808
    assert base["untouched_station_pct"] > 90.0
    assert base["net_clear_floor_sqft"] > crowded["net_clear_floor_sqft"] > tight["net_clear_floor_sqft"]
    assert len(base["zones"]) == 6
    assert "96.0%" in base["plothole_answer"]


def test_co_move_http_endpoints_and_mocked_robotics_scan():
    client = TestClient(app)

    r_an = client.post("/co-move/analyze", json={"run_id": "sample_venue", "occupancy_mode": "crowded_stalls_35"})
    assert r_an.status_code == 200
    body = r_an.json()
    assert body["penn_occupancy"]["occupancy_mode"] == "crowded_stalls_35"
    assert body["total_items"] > 20

    fake_scan = {
        "scene_summary": "Clear floor pouf near exit first, then stage boxes on AMR cart.",
        "clear_path_ready": False,
        "waypoints": [
            {"step": 1, "kind": "clear_first", "point": [320, 710], "label": "Floor Pouf", "instruction": "Move aside"},
            {"step": 2, "kind": "robot_pick", "point": [220, 510], "label": "Sealed Box", "instruction": "AMR pickup"},
        ],
    }
    with patch("backend.llm.Job.generate_json", return_value=fake_scan):
        r_sc = client.post("/co-move/scan", json={"run_id": "sample_venue", "target": "destination"})
        assert r_sc.status_code == 200
        sc = r_sc.json()
        assert sc["target"] == "destination"
        assert len(sc["waypoints"]) == 2
        assert sc["preview_data_url"].startswith("data:image/jpeg;base64,")
