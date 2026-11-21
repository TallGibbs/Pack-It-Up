"""Tests for the planner loop (B6). No model is called: `ask` stands in for it."""
from __future__ import annotations

import json
from pathlib import Path

from backend import planner

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = json.loads((ROOT / "data" / "sample_venue.json").read_text(encoding="utf-8"))


def _answer(reason: str = "try it", stop: bool = False, **settings) -> dict:
    return {"reason": reason, "stop": stop, "settings": {**planner.DEFAULTS, **settings}}


def test_planner_keeps_the_best_round_and_logs_each_one() -> None:
    prompts: list[str] = []

    def ask(prompt: str, round_no: int) -> dict:
        prompts.append(prompt)
        if round_no == 2:  # the unchecked baseline packer: many violations
            return _answer("worse on purpose", packer_engine="raw_py3dbp")
        return _answer("smaller last truck", downsize_last_truck=True)

    out = planner.plan_with_model(SAMPLE, ask=ask)
    rounds = out["rounds"]

    assert [r["round"] for r in rounds] == [1, 2, 3]
    assert [r["source"] for r in rounds] == ["start", "model", "model"]
    assert rounds[1]["changed"] == {"packer_engine": ["constrained", "raw_py3dbp"]}
    assert rounds[1]["violation_count"] > 0 and not rounds[1]["valid"]
    assert rounds[2]["reason"] == "smaller last truck"

    # The winner is never worse than the start, and a round with violations cannot win over a clean one.
    best = rounds[out["best_round"] - 1]
    assert best["valid"] and out["best_score"] >= out["first_score"]
    assert out["plan"]["score"]["total"] == best["score"]
    assert out["plan"]["summary"]["fleet_label"] == best["fleet"]

    # The model reads the checker's digest, not the placement list.
    assert '"violations_by_rule"' in prompts[1] and "pos_in" not in prompts[1]
    json.dumps(out)  # the route returns this as is


def test_planner_falls_back_to_the_plain_solve_when_the_model_fails() -> None:
    def ask(prompt: str, round_no: int) -> dict:
        raise RuntimeError("no network")

    out = planner.plan_with_model(SAMPLE, ask=ask)
    assert len(out["rounds"]) == 1 and out["best_round"] == 1
    assert "failed" in out["note"]
    assert out["plan"]["score"]["valid"]


def test_planner_stops_on_repeated_settings_and_ignores_unknown_values() -> None:
    def ask(prompt: str, round_no: int) -> dict:
        return _answer("nothing better", stop=True)  # the starting settings again

    out = planner.plan_with_model(SAMPLE, ask=ask)
    assert len(out["rounds"]) == 1 and "Stopped after round 1" in out["note"]

    cleaned = planner._clean_settings({"truck_id": "semi_53", "order_mode": "random", "truck_sequence": ["uhaul_10", "x"],
                                       "light_max_lb": 999})
    assert cleaned == {**planner.DEFAULTS, "truck_sequence": ["uhaul_10"]}
