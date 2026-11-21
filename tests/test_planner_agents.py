"""Tests for Stage B6 (`planner.py` Neon loop) and Stage B7 (`agents.py` competing agents + `/plan` & `/agents` API)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import agents, arena_api, planner
from backend.llm import managed_agents

ROOT = Path(__file__).resolve().parents[1]


def test_no_sdk_import_outside_backend_llm() -> None:
    """Enforce AGENTS.md rule: only `backend/llm/` may import a model SDK."""
    for rel in ("backend/planner.py", "backend/agents.py", "backend/arena_api.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "from google" not in src and "import google" not in src, f"{rel} must not import google SDK directly"


def test_b6_neon_loop_improves_score_across_rounds_offline() -> None:
    sample = json.loads((ROOT / "data" / "sample_venue.json").read_text(encoding="utf-8"))
    with patch.object(managed_agents, "has_api_key", return_value=False):
        res = planner.run_neon_loop(sample, max_rounds=3)

    rounds = res["rounds"]
    assert len(rounds) == 4  # Round 0 seed + 3 refinement rounds
    scores = res["score_progression"]
    assert scores[0] < 50.0  # Seed round has violations
    assert rounds[0]["score"]["valid"] is False
    # Subsequent rounds eliminate all violations and climb monotonically
    assert rounds[1]["score"]["valid"] is True
    assert scores[1] > scores[0]
    assert scores[2] >= scores[1]
    assert scores[3] >= scores[2]
    assert res["winner"]["score"]["valid"] is True
    assert res["winner"]["score"]["violation_count"] == 0


def test_b6_neon_loop_uses_plan_job_when_api_key_present() -> None:
    mock_inv = json.loads((ROOT / "frontend" / "mock" / "inventory.json").read_text(encoding="utf-8"))
    canned_rounds = [
        {
            "diagnosis": "Switch from raw_py3dbp to physics-constrained engine and uhaul_26.",
            "truck_id": "uhaul_26",
            "packer_engine": "constrained",
            "order_mode": "heavy_first",
            "lifo_weight": 0.5,
            "downsize_last_truck": False,
            "allow_all_rotations": False,
            "multi_store_routing": True,
        },
        {
            "diagnosis": "Optimize Penn Station dock-stop LIFO and downsize truck.",
            "truck_id": "uhaul_26",
            "packer_engine": "constrained",
            "order_mode": "zone_strict_lifo",
            "lifo_weight": 1.6,
            "downsize_last_truck": True,
            "allow_all_rotations": False,
            "multi_store_routing": True,
        },
    ]

    class _FakeJob:
        spec = "gemini:gemini-4-neon"

        def __init__(self) -> None:
            self.calls = 0

        def generate_json(self, prompt: str, schema: dict, prompt_version: str = "", label: str = "") -> dict:
            out = canned_rounds[min(self.calls, len(canned_rounds) - 1)]
            self.calls += 1
            return out

    fake_job = _FakeJob()
    with (
        patch.object(managed_agents, "has_api_key", return_value=True),
        patch.object(planner, "has_api_key", return_value=True),
        patch.object(planner, "plan_job", return_value=fake_job),
    ):
        res = planner.run_neon_loop(mock_inv, max_rounds=2, allow_offline_fallback=False)

    assert fake_job.calls == 2
    assert res["model"] == "gemini:gemini-4-neon"
    assert res["winner"]["score"]["valid"] is True
    assert res["score_progression"][-1] > res["score_progression"][0]


def test_b7_competing_agents_and_managed_agent_sandbox_path() -> None:
    mock_inv = json.loads((ROOT / "frontend" / "mock" / "inventory.json").read_text(encoding="utf-8"))

    def _fake_managed_agent(prompt: str, **kwargs):
        return {
            "output_text": json.dumps({
                "diagnosis": "Sandbox script verified downsized fleet with strict Penn Station LIFO.",
                "truck_id": "uhaul_26",
                "packer_engine": "constrained",
                "order_mode": "zone_strict_lifo",
                "lifo_weight": 1.7,
                "downsize_last_truck": True,
                "allow_all_rotations": False,
                "multi_store_routing": True,
            }),
            "interaction_id": "inter_test_123",
            "environment_id": "env_sandbox_456",
            "agent": "antigravity-preview-09-2026",
            "agent_model": "gemini-4-neon",
            "status": "completed",
        }

    with (
        patch.object(agents, "has_api_key", return_value=True),
        patch.object(agents, "run_managed_agent", side_effect=_fake_managed_agent) as mock_ma,
    ):
        res = agents.run_competing_agents(mock_inv, mode="managed_agent")

    # 3 remote Managed Agents + 1 baseline anchor = 4 competing runs
    assert mock_ma.call_count == 3
    assert len(res["agents"]) == 4
    assert res["winner"]["score"]["valid"] is True
    winners = [a for a in res["agents"] if a["is_winner"]]
    assert len(winners) == 1
    assert winners[0]["score"]["valid"] is True


def test_b7_background_race_endpoints_via_fastapi() -> None:
    test_app = FastAPI()
    test_app.include_router(arena_api.router)
    client = TestClient(test_app)
    with patch.object(agents, "has_api_key", return_value=False):
        r_plan = client.post("/plan", json={"run_id": "mock-demo", "max_rounds": 2})
        assert r_plan.status_code == 200
        plan_body = r_plan.json()
        assert plan_body["winner"]["score"]["valid"] is True
        assert len(plan_body["rounds"]) == 3

        r_start = client.post("/agents/start", json={"run_id": "mock-demo", "mode": "local"})
        assert r_start.status_code == 200
        job_id = r_start.json()["job_id"]

        snap = None
        for _ in range(30):
            r_poll = client.get(f"/agents/{job_id}")
            assert r_poll.status_code == 200
            snap = r_poll.json()
            if snap["status"] == "completed":
                break
            time.sleep(0.05)

        assert snap is not None and snap["status"] == "completed"
        assert snap["completed_count"] == 4
        assert snap["winner"]["score"]["valid"] is True
