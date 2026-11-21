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


def _all_routes(routes, prefix: str = ""):
    """Every (method, path) the app answers, walking into included routers (FastAPI keeps those nested)."""
    for route in routes:
        inner = getattr(route, "original_router", None) or getattr(route, "router", None)
        if getattr(route, "methods", None) and getattr(route, "path", None):
            for method in route.methods:
                if method not in ("HEAD", "OPTIONS"):
                    yield (method, prefix + route.path)
        elif inner is not None:
            yield from _all_routes(inner.routes, prefix + (getattr(route, "prefix", "") or ""))


def test_no_route_is_declared_twice() -> None:
    """Two routers once both declared POST /plan; the first one added answered and the other was never reached."""
    from backend.app import app

    seen: dict[tuple[str, str], int] = {}
    for key in _all_routes(app.routes):
        seen[key] = seen.get(key, 0) + 1
    # If these two are missing, the walk above no longer matches how FastAPI nests routers.
    assert ("POST", "/plan") in seen and ("POST", "/arena/plan") in seen
    assert [k for k, n in seen.items() if n > 1] == []
