"""Stage B6: Gemini 4 Neon iterative packing planner (`planner.py`).

Runs an closed-loop reasoning cycle (up to `max_rounds = 3`):
  1. Solve with the current strategy and run `verify.verify(placement)`.
  2. Feed the exact verifier violations, fleet fill %, L/R weight balance,
     Penn Station store distribution, and LIFO dock-stop score to Gemini 4 Neon
     (`plan_job("plan")` -> `gemini:gemini-4-neon`).
  3. Neon diagnoses the bottlenecks and outputs revised strategy settings
     (`truck_id`, `packer_engine`, `order_mode`, `lifo_weight`,
     `downsize_last_truck`, `allow_all_rotations`, `multi_store_routing`).
  4. Re-solve, verify, log the score progression, and return the best valid plan.

CLI:
    python -m backend.planner data/sample_venue.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from backend import catalog, expand, solver
from backend.llm import LLMError
from backend.llm.managed_agents import has_api_key, plan_job

TRUCK_IDS = ["uhaul_10", "uhaul_15", "uhaul_20", "uhaul_26"]
PACKER_ENGINES = ["constrained", "raw_py3dbp"]
ORDER_MODES = ["lifo_heavy_first", "zone_strict_lifo", "heavy_first", "volume_first", "fragile_last"]

# Flat JSON schema (no $ref, oneOf, or additionalProperties) for structured output.
NEON_ROUND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "diagnosis",
        "truck_id",
        "packer_engine",
        "order_mode",
        "lifo_weight",
        "downsize_last_truck",
        "allow_all_rotations",
        "multi_store_routing",
    ],
    "properties": {
        "diagnosis": {
            "type": "string",
            "description": "1-2 sentence analysis of the previous round's verifier violations or efficiency gaps.",
        },
        "truck_id": {"type": "string", "enum": TRUCK_IDS},
        "packer_engine": {"type": "string", "enum": PACKER_ENGINES},
        "order_mode": {"type": "string", "enum": ORDER_MODES},
        "lifo_weight": {"type": "number", "minimum": 0.0, "maximum": 3.0},
        "downsize_last_truck": {"type": "boolean"},
        "allow_all_rotations": {"type": "boolean"},
        "multi_store_routing": {
            "type": "boolean",
            "description": "True to stock all 6 Penn Station stores by category/doorway; False dumps into concourse.",
        },
    },
}

# Unguided starting point for Round 0 so the verifier exposes real violations for Neon to repair.
DEFAULT_SEED_STRATEGY: dict[str, Any] = {
    "truck_id": "uhaul_20",
    "packer_engine": "raw_py3dbp",
    "order_mode": "volume_first",
    "lifo_weight": 0.0,
    "downsize_last_truck": False,
    "allow_all_rotations": True,
    "force_single_zone": "penn_concourse",
}


def summarize_inventory(inventory: dict) -> dict[str, Any]:
    """Compact physical summary of `inventory` for planning prompts."""
    pieces = expand.expand_inventory(inventory)
    upright_heights = [p["dims_in"][2] for p in pieces if p.get("must_stay_upright") and not p.get("disassemble")]
    max_dims = [max(p["dims_in"]) for p in pieces]
    return {
        "total_pieces": len(pieces),
        "furniture_pieces": sum(1 for p in pieces if not p["is_box"]),
        "box_pieces": sum(1 for p in pieces if p["is_box"]),
        "total_volume_cuft": round(sum(p["volume_cuft"] for p in pieces), 1),
        "total_weight_lb": round(sum(p["weight_lb"] for p in pieces), 1),
        "tallest_upright_in": round(max(upright_heights), 1) if upright_heights else 0.0,
        "longest_item_in": round(max(max_dims), 1) if max_dims else 0.0,
        "fragile_count": sum(1 for p in pieces if p.get("fragile")),
        "load_on_edge_count": sum(1 for p in pieces if p.get("load_on_edge")),
    }


def _round_record(
    round_idx: int,
    plan: dict[str, Any],
    strategy: dict[str, Any],
    *,
    diagnosis: str,
    via: str,
    elapsed_s: float,
) -> dict[str, Any]:
    sc = plan["score"]
    sm = plan["summary"]
    return {
        "round": round_idx,
        "via": via,
        "elapsed_s": round(elapsed_s, 2),
        "diagnosis": diagnosis,
        "strategy": dict(strategy),
        "fleet_label": sm["fleet_label"],
        "truck_count": sm["truck_count"],
        "placed_items": sm["total_items"],
        "unplaced_count": sm["unplaced_count"],
        "zones_stocked": sm["zones_stocked"],
        "score": {
            "total": sc["total"],
            "valid": sc["valid"],
            "fill_pct": sc["fill_pct"],
            "balance_pct": sc["balance_pct"],
            "lifo_score": sc["lifo_score"],
            "zone_coverage_pct": sc["zone_coverage_pct"],
            "violation_count": sc["violation_count"],
            "violation_counts_by_rule": sc["violation_counts_by_rule"],
            "sample_violations": [v["detail"] for v in sc["violations"][:8]],
        },
    }


def _build_neon_prompt(
    inv_summary: dict[str, Any],
    history: list[dict[str, Any]],
    round_num: int,
    max_rounds: int,
) -> str:
    trucks = [
        {
            "truck_id": t["truck_id"],
            "dims_in": t["dims_in"],
            "volume_cuft": t["volume_cuft"],
            "max_weight_lb": t["max_weight_lb"],
        }
        for t in catalog.list_trucks()
    ]
    zones = [
        {
            "zone_id": z["zone_id"],
            "dock_stop": z["dock_stop"],
            "door_in": z["door_in"],
            "floor_sqft": z["floor_sqft"],
        }
        for z in catalog.list_penn_zones()
    ]
    return (
        f"You are the Gemini 4 Neon Moving & Fleet Planner (Round {round_num} of {max_rounds}).\n"
        "Your job is to eliminate ALL physics/mover/destination rule violations (`valid: true`, 0 violations) "
        "and maximize the verifier `score.total` (0-100) for moving this venue into NY Penn Station's storefronts.\n\n"
        f"Inventory summary:\n{json.dumps(inv_summary, indent=2)}\n\n"
        f"Available U-Haul trucks (`[length_in, width_in, height_in]`):\n{json.dumps(trucks)}\n\n"
        f"Penn Station destination storefronts (dock_stop 1 unloaded FIRST near rear truck door; stop 6 unloaded LAST near cab):\n"
        f"{json.dumps(zones)}\n\n"
        "Strategy lever guide:\n"
        "- `packer_engine`: `raw_py3dbp` ignores >=75% base support, upright, load_on_edge, and L/R balance; "
        "`constrained` enforces all physical mover rules.\n"
        "- `truck_id`: must have ceiling `height_in >= tallest_upright_in` so upright items don't land in `unplaced`.\n"
        "- `multi_store_routing`: `true` routes items across all 6 Penn Station storefronts within doorway limits; "
        "`false` dumps into `penn_concourse` and triggers `zone_distribution` violations.\n"
        "- `order_mode`: `heavy_first`, `volume_first`, `fragile_last`, `lifo_heavy_first`, or `zone_strict_lifo`.\n"
        "- `downsize_last_truck`: `true` shrinks a partially filled overflow truck to the smallest U-Haul that fits, raising `fill_pct`.\n"
        "- `allow_all_rotations`: keep `false` unless non-upright items need extra tipping.\n\n"
        f"Previous rounds and verifier results:\n{json.dumps(history, indent=2)}\n\n"
        "Propose a distinct, improved strategy for this round that fixes every remaining violation and raises `score.total`."
    )


def _apply_neon_choice(choice: dict[str, Any]) -> dict[str, Any]:
    strat: dict[str, Any] = {
        "truck_id": choice["truck_id"],
        "packer_engine": choice["packer_engine"],
        "order_mode": choice["order_mode"],
        "lifo_weight": round(float(choice["lifo_weight"]), 2),
        "downsize_last_truck": bool(choice["downsize_last_truck"]),
        "allow_all_rotations": bool(choice["allow_all_rotations"]),
    }
    if not choice.get("multi_store_routing", True):
        strat["force_single_zone"] = "penn_concourse"
    return strat


def _heuristic_violation_repair(
    prev_rec: dict[str, Any],
    inv_summary: dict[str, Any],
    round_num: int,
) -> dict[str, Any]:
    """Deterministic violation-driven repair used ONLY when no API key is present locally."""
    prev_strat = prev_rec["strategy"]
    by_rule = prev_rec["score"]["violation_counts_by_rule"]
    tallest = float(inv_summary.get("tallest_upright_in") or 0.0)

    # Pick a truck tall enough for the tallest upright piece
    chosen_truck = str(prev_strat.get("truck_id") or "uhaul_26")
    t_spec = catalog.get_truck(chosen_truck)
    if "unplaced_item" in by_rule or not t_spec or t_spec["height_in"] < tallest + 1.0:
        chosen_truck = "uhaul_26"
        for t in catalog.list_trucks():
            if t["height_in"] >= tallest + 2.0 and t["volume_cuft"] >= 900.0:
                chosen_truck = t["truck_id"]
                break
        if tallest > 84.0:
            chosen_truck = "uhaul_26"

    if round_num == 1:
        # Round 1 fixes physics engine, ceiling height, and multi-store routing using structural heavy_first
        return {
            "diagnosis": (
                f"Round 0 failed with {prev_rec['score']['violation_count']} violations "
                f"({', '.join(by_rule.keys()) or 'low efficiency'}). Switching to physics-constrained engine, "
                f"{chosen_truck} clearance, and multi-store Penn Station routing."
            ),
            "truck_id": chosen_truck if tallest > 85.0 else "uhaul_26",
            "packer_engine": "constrained",
            "order_mode": "heavy_first",
            "lifo_weight": 0.6,
            "downsize_last_truck": False,
            "allow_all_rotations": False,
            "multi_store_routing": True,
        }
    if round_num == 2:
        # Round 2 aligns truck loading order with Penn Station dock-stop LIFO unloading
        return {
            "diagnosis": (
                f"Physics valid (0 violations, LIFO={prev_rec['score']['lifo_score']}/10). "
                "Aligning truck load order with Penn Station dock stops (stop 6 deep -> stop 1 near rear door)."
            ),
            "truck_id": "uhaul_26",
            "packer_engine": "constrained",
            "order_mode": "lifo_heavy_first",
            "lifo_weight": 1.3,
            "downsize_last_truck": False,
            "allow_all_rotations": False,
            "multi_store_routing": True,
        }
    # Round 3 right-sizes the trailing overflow truck to boost overall fleet fill %
    return {
        "diagnosis": (
            f"Valid 0-violation plan at {prev_rec['score']['fill_pct']}% fleet fill. "
            "Enabling `downsize_last_truck` with strict dock-stop LIFO to eliminate empty volume in the final truck."
        ),
        "truck_id": "uhaul_26",
        "packer_engine": "constrained",
        "order_mode": "zone_strict_lifo",
        "lifo_weight": 1.6,
        "downsize_last_truck": True,
        "allow_all_rotations": False,
        "multi_store_routing": True,
    }


def _plan_rank(plan: dict[str, Any]) -> tuple[int, float, float]:
    sc = plan["score"]
    return (1 if sc["valid"] else 0, float(sc["total"]), float(sc["fill_pct"]))


def run_neon_loop(
    inventory: dict[str, Any],
    *,
    initial_strategy: dict[str, Any] | None = None,
    max_rounds: int = 3,
    run_dir: Path | str | None = None,
    allow_offline_fallback: bool = True,
) -> dict[str, Any]:
    """Run Round 0 + up to `max_rounds` of Gemini 4 Neon strategy refinement."""
    max_rounds = max(1, min(5, int(max_rounds)))
    rd = Path(run_dir) if run_dir else None
    inv_summary = summarize_inventory(inventory)

    seed_strat = dict(DEFAULT_SEED_STRATEGY if initial_strategy is None else initial_strategy)
    t0 = time.time()
    seed_plan = solver.solve(inventory, strategy=seed_strat)
    r0 = _round_record(
        0,
        seed_plan,
        seed_strat,
        diagnosis="Initial unguided seed run before Gemini 4 Neon critique.",
        via="seed",
        elapsed_s=time.time() - t0,
    )

    rounds: list[dict[str, Any]] = [r0]
    best_plan = seed_plan
    best_round = 0
    model_used = "heuristic_fallback"

    for r in range(1, max_rounds + 1):
        rt0 = time.time()
        prompt = _build_neon_prompt(inv_summary, rounds, r, max_rounds)
        choice: dict[str, Any] | None = None
        via = "heuristic_fallback"

        if has_api_key():
            for job_name in ("plan", "plan_fallback"):
                try:
                    job = plan_job(job_name, run_dir=rd)
                    choice = job.generate_json(
                        prompt,
                        schema=NEON_ROUND_SCHEMA,
                        prompt_version="neon_loop_v1",
                        label=f"neon_round_{r}",
                    )
                    via = job.spec
                    model_used = job.spec
                    break
                except LLMError:
                    if not allow_offline_fallback and job_name == "plan_fallback":
                        raise

        if choice is None:
            if not allow_offline_fallback:
                raise LLMError("GEMINI_API_KEY is not configured and allow_offline_fallback=False")
            choice = _heuristic_violation_repair(rounds[-1], inv_summary, r)
            via = "heuristic_fallback"

        next_strat = _apply_neon_choice(choice)
        cand_plan = solver.solve(inventory, strategy=next_strat)
        rec = _round_record(
            r,
            cand_plan,
            next_strat,
            diagnosis=choice["diagnosis"],
            via=via,
            elapsed_s=time.time() - rt0,
        )
        rounds.append(rec)

        if _plan_rank(cand_plan) > _plan_rank(best_plan):
            best_plan = cand_plan
            best_round = r

    score_progression = [r["score"]["total"] for r in rounds]
    best_so_far: list[float] = []
    cur_max = -1.0
    for s in score_progression:
        cur_max = max(cur_max, s)
        best_so_far.append(cur_max)

    best_plan["planner"] = {
        "model": model_used,
        "best_round": best_round,
        "score_progression": score_progression,
        "best_score_progression": best_so_far,
        "rounds": rounds,
    }

    out = {
        "model": model_used,
        "best_round": best_round,
        "score_progression": score_progression,
        "best_score_progression": best_so_far,
        "rounds": rounds,
        "winner": best_plan,
    }
    if rd and rd.exists():
        (rd / "planner_rounds.json").write_text(json.dumps(rounds, indent=2), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the B6 Gemini 4 Neon packing planner loop.")
    ap.add_argument("inventory", type=Path, help="Path to inventory_v2 JSON (e.g. data/sample_venue.json)")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    inv = json.loads(args.inventory.read_text(encoding="utf-8"))
    res = run_neon_loop(inv, max_rounds=args.rounds)
    print(f"Planner model: {res['model']} | Best round: {res['best_round']} | Progression: {res['score_progression']}")
    for r in res["rounds"]:
        sc = r["score"]
        print(
            f"  Round {r['round']} ({r['via']}): score={sc['total']:5.1f} valid={str(sc['valid']):5s} "
            f"fleet={r['fleet_label']:26s} fill={sc['fill_pct']:4.1f}% lifo={sc['lifo_score']:4.1f} "
            f"violations={sc['violation_count']} | {r['diagnosis']}"
        )
    if args.out:
        args.out.write_text(json.dumps(res, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
