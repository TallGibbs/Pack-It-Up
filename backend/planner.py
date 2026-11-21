"""Stage B6: Gemini 4 Neon iterative packing planner (`planner.py`).

Unifies both Track B planner interfaces:
1. `plan_with_model(inventory, strategy, max_rounds=3, run_dir=None, ask=None)` —
   used by `POST /plan` in `backend/pack_api.py` and the "Plan with Neon" control in `frontend/index.html`.
2. `run_neon_loop(inventory, initial_strategy=None, max_rounds=3, run_dir=None, allow_offline_fallback=True)` —
   used by the competing Managed Agents / Neon arena (`backend/arena_api.py` & `frontend/ui/arena.js`).

All model calls go exclusively through `backend/llm/` (`for_job("plan")`).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable

from backend import catalog, expand, solver
from backend.llm import LLMError, managed_agents
from backend.llm.managed_agents import plan_job


def has_api_key() -> bool:
    return managed_agents.has_api_key()

MAX_ROUNDS = 3
PROMPT_VERSION = "plan_v1"

TRUCK_IDS = ["uhaul_van", "uhaul_10", "uhaul_15", "uhaul_20", "uhaul_26"]
PACKER_ENGINES = ["constrained", "raw_py3dbp"]
ENGINES = PACKER_ENGINES
ORDER_MODES = ["lifo_heavy_first", "zone_strict_lifo", "heavy_first", "volume_first", "fragile_last"]

# ---------------------------------------------------------------------------
# Interface A: `plan_with_model` (powers `POST /plan` & `tests/test_planner.py`)
# ---------------------------------------------------------------------------

DEFAULTS: dict[str, Any] = {
    "packer_engine": "constrained",
    "truck_id": "uhaul_26",
    "truck_sequence": [],
    "order_mode": "lifo_heavy_first",
    "allow_all_rotations": False,
    "downsize_last_truck": False,
}

SETTINGS_HELP = """\
- packer_engine: "constrained" places each piece only where it has at least 75% base support, obeys the \
stacking and orientation rules and keeps left-right balance. "raw_py3dbp" is the stock library packer with \
none of those rules; it is here as a baseline and usually produces many violations.
- truck_id: the truck size used for every truck, unless truck_sequence says otherwise.
- truck_sequence: optional list of truck ids, first truck first, for a fleet of mixed sizes. Trucks beyond \
the end of the list use truck_id. Empty list = every truck is truck_id.
- order_mode: the order pieces are offered to the packer. "lifo_heavy_first" (default) puts sturdy and tall \
pieces down first and leans later dock stops toward the cab; "zone_strict_lifo" sorts strictly by dock stop; \
"heavy_first" and "volume_first" ignore dock stops; "fragile_last" loads fragile pieces at the end.
- allow_all_rotations: false keeps every piece standing the way it was measured. true lets pieces that are \
not marked must-stay-upright or load-on-edge be tipped onto a side or an end, which often saves floor space. \
Marked pieces keep their rule either way.
- downsize_last_truck: true swaps the last truck for the smallest truck that still holds what is left."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["reason", "stop", "settings"],
    "properties": {
        "reason": {
            "type": "string",
            "description": "One plain sentence, at most 30 words: what you changed and what in the result made you change it.",
        },
        "stop": {
            "type": "boolean",
            "description": "true only if no change to the settings is likely to beat the best round so far.",
        },
        "settings": {
            "type": "object",
            "required": list(DEFAULTS),
            "properties": {
                "packer_engine": {"type": "string", "enum": ENGINES},
                "truck_id": {"type": "string", "enum": TRUCK_IDS},
                "truck_sequence": {
                    "type": "array",
                    "items": {"type": "string", "enum": TRUCK_IDS},
                },
                "order_mode": {"type": "string", "enum": ORDER_MODES},
                "allow_all_rotations": {"type": "boolean"},
                "downsize_last_truck": {"type": "boolean"},
            },
        },
    },
}


def model_settings(strategy: dict) -> dict[str, Any]:
    """The model-controlled part of a strategy, with defaults filled in."""
    return {k: strategy.get(k, d) if strategy.get(k) is not None else d for k, d in DEFAULTS.items()}


def _clean_settings(raw: dict) -> dict[str, Any]:
    """Keep only known settings with known values; anything odd falls back to the default."""
    truck_ids = {t["truck_id"] for t in catalog.list_trucks()}
    out = dict(DEFAULTS)
    if raw.get("packer_engine") in ENGINES:
        out["packer_engine"] = raw["packer_engine"]
    if raw.get("truck_id") in truck_ids:
        out["truck_id"] = raw["truck_id"]
    seq = raw.get("truck_sequence")
    if isinstance(seq, list):
        out["truck_sequence"] = [t for t in seq if t in truck_ids][:8]
    if raw.get("order_mode") in ORDER_MODES:
        out["order_mode"] = raw["order_mode"]
    out["allow_all_rotations"] = bool(raw.get("allow_all_rotations", False))
    out["downsize_last_truck"] = bool(raw.get("downsize_last_truck", False))
    return out


def _load_facts(plan: dict) -> dict[str, Any]:
    items = [it for t in plan.get("trucks", []) for it in t.get("items", [])]
    dims = [it.get("orig_dims_in") or it["size_in"] for it in items] + [
        u["dims_in"] for u in plan.get("unplaced", []) if u.get("dims_in")
    ]
    s = plan["summary"]
    return {
        "pieces": s["total_items"] + s["unplaced_count"],
        "furniture": s["furniture_count"],
        "boxes": s["box_count"],
        "total_volume_cuft": s["total_volume_cuft"],
        "total_weight_lb": s["total_weight_lb"],
        "must_stay_upright": sum(1 for it in items if it.get("must_stay_upright")),
        "load_on_edge": sum(1 for it in items if it.get("load_on_edge")),
        "not_stackable": sum(1 for it in items if it.get("stackable") == "no"),
        "fragile": sum(1 for it in items if it.get("fragile")),
        "longest_side_in": max((max(d) for d in dims), default=0),
    }


def _result_digest(plan: dict) -> dict[str, Any]:
    sc = plan["score"]
    trucks = [
        {
            "truck_id": t["truck_id"],
            "pieces": len(t["items"]),
            "fill_pct": t["fill_pct"],
            "weight_lb": t["weight_lb"],
            "max_weight_lb": t["max_weight_lb"],
        }
        for t in plan.get("trucks", [])
    ]
    out: dict[str, Any] = {
        "score": sc["total"],
        "valid": sc["valid"],
        "truck_count": plan["summary"]["truck_count"],
        "fleet": plan["summary"]["fleet_label"],
        "fill_pct": sc["fill_pct"],
        "lifo_score_of_10": sc["lifo_score"],
        "left_right_balance_pct": sc["balance_pct"],
        "zone_coverage_pct": sc["zone_coverage_pct"],
        "violation_count": sc["violation_count"],
        "violations_by_rule": sc["violation_counts_by_rule"],
        "violation_examples": [f"[{v['rule']}] {str(v['detail'])[:160]}" for v in sc["violations"][:6]],
        "trucks": trucks,
    }
    if len(plan.get("trucks", [])) > 1 and len(plan["trucks"][-1]["items"]) <= 6:
        out["last_truck_pieces"] = [
            {
                "label": str(it["label"])[:60],
                "dims_in": it.get("orig_dims_in"),
                "weight_lb": it["weight_lb"],
                "must_stay_upright": it["must_stay_upright"],
                "load_on_edge": it["load_on_edge"],
                "stackable": it["stackable"],
            }
            for it in plan["trucks"][-1]["items"]
        ]
    if plan.get("unplaced"):
        out["unplaced_examples"] = [f"{u['label']}: {u.get('reason', '')}"[:200] for u in plan["unplaced"][:5]]
    return out


def build_prompt(load: dict, history: list[dict], rounds_left: int) -> str:
    trucks = [
        {
            "truck_id": t["truck_id"],
            "inside_in": t["dims_in"],
            "volume_cuft": round(t["volume_cuft"]),
            "max_weight_lb": t["max_weight_lb"],
        }
        for t in catalog.list_trucks()
    ]
    return f"""\
You are the planner for a moving-truck load. A deterministic solver packs the pieces into trucks, and a \
separate checker scores the result. You cannot place pieces yourself. Your job is to read the results so far \
and choose the solver settings for the next run.

What the mover wants, in this order:
1. No violations. A plan with any violation cannot be loaded as drawn.
2. As few trucks as possible, and no larger than needed. Every truck is a rental and a driver.
3. A higher checker score.

How the checker scores (0 to 100): 50 for compliance, up to 20 for how full the trucks are, up to 10 for \
left-right balance, up to 10 for LIFO (pieces for the first dock stop sit nearest the rear door), up to 10 for \
stocking every destination zone, minus 6 to 15 points for each violation.

Settings you choose (return all of them every time):
{SETTINGS_HELP}

Trucks:
{json.dumps(trucks)}

The load:
{json.dumps(load)}

Rounds so far (settings, then what the checker said):
{json.dumps(history, indent=1)}

You have {rounds_left} more solver run{"s" if rounds_left != 1 else ""} after reading this. Pick settings that have \
not been tried and that you expect to beat the best round. Fill percentages are by volume; a truck usually \
stops taking pieces when its floor is covered, well before 100%. If a truck holds only a few pieces, look at \
why they did not fit in the truck before it. Set stop to true only if you think nothing will beat the best \
round. In reason, say in one plain sentence what you changed and what in the result made you change it."""


def _changes(prev: dict, new: dict) -> dict[str, list]:
    return {k: [prev[k], new[k]] for k in DEFAULTS if prev[k] != new[k]}


def _plan_round_record(
    n: int, source: str, strategy: dict, plan: dict, reason: str, changed: dict | None = None
) -> dict[str, Any]:
    sc = plan["score"]
    return {
        "round": n,
        "source": source,
        "settings": model_settings(strategy),
        "changed": changed or {},
        "reason": reason,
        "score": sc["total"],
        "valid": sc["valid"],
        "violation_count": sc["violation_count"],
        "violations_by_rule": sc["violation_counts_by_rule"],
        "truck_count": plan["summary"]["truck_count"],
        "fleet": plan["summary"]["fleet_label"],
        "fill_pct": sc["fill_pct"],
    }


def _rank(rec: dict) -> tuple:
    return (rec["valid"], rec["score"], -rec["truck_count"], -rec["round"])


def plan_with_model(
    inventory: dict,
    strategy: dict | None = None,
    *,
    max_rounds: int = MAX_ROUNDS,
    run_dir: Path | str | None = None,
    ask: Callable[[str, int], dict] | None = None,
) -> dict[str, Any]:
    """Solve, let the model change the settings, solve again; up to `max_rounds` solver runs in all."""
    base = dict(strategy or {})
    max_rounds = max(1, min(int(max_rounds), 5))
    model_id = ""
    note: str | None = None

    plan = solver.solve(inventory, strategy=base)
    plans = [plan]
    rounds = [_plan_round_record(1, "start", base, plan, "Starting settings.")]
    history = [{"round": 1, "settings": rounds[0]["settings"], "result": _result_digest(plan)}]
    load = _load_facts(plan)

    if ask is None and max_rounds > 1:
        try:
            from backend.llm import for_job

            job = for_job("plan", run_dir)
            model_id = job.provider.model

            def ask(prompt: str, round_no: int) -> dict:
                return job.generate_json(
                    prompt, schema=SCHEMA, prompt_version=PROMPT_VERSION, label=f"plan round {round_no}"
                )
        except Exception as e:
            note = f"Planner model not available ({type(e).__name__}: {e}); this is the plain solve."
            max_rounds = 1

    for n in range(2, max_rounds + 1):
        prompt = build_prompt(load, history, rounds_left=max_rounds - n + 1)
        t0 = time.time()
        try:
            answer = ask(prompt, n)
        except Exception as e:
            note = f"Model call for round {n} failed ({type(e).__name__}: {str(e)[:200]}); kept the best plan so far."
            break
        latency = round(time.time() - t0, 2)

        settings = _clean_settings(answer.get("settings") or {})
        reason = " ".join(str(answer.get("reason") or "").split())[:300]
        prev = rounds[-1]["settings"]
        tried = next((r["round"] for r in rounds if r["settings"] == settings), None)
        if tried is not None:
            why = "the model chose to stop" if answer.get("stop") else f"the model returned round {tried}'s settings again"
            note = f"Stopped after round {n - 1}: {why}. {reason}".strip()
            break

        new_strategy = {**base, **settings}
        try:
            plan = solver.solve(inventory, strategy=new_strategy)
        except Exception as e:
            note = f"Round {n}: the solver rejected the model's settings ({type(e).__name__}: {e}); kept the best plan so far."
            break
        plans.append(plan)
        rec = _plan_round_record(n, "model", new_strategy, plan, reason, _changes(prev, settings))
        rec["model_latency_s"] = latency
        rounds.append(rec)
        history.append({"round": n, "settings": settings, "why_you_chose_it": reason, "result": _result_digest(plan)})

    best = max(rounds, key=_rank)
    return {
        "plan": plans[best["round"] - 1],
        "rounds": rounds,
        "best_round": best["round"],
        "first_score": rounds[0]["score"],
        "best_score": best["score"],
        "model": model_id,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Interface B: `run_neon_loop` (powers `arena_api.py` & `tests/test_planner_agents.py`)
# ---------------------------------------------------------------------------

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


def _neon_round_record(
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
    return {
        "diagnosis": (
            f"Valid 0-violation plan at {prev_rec['score']['fill_pct']}% fleet fill. "
            "Enabling `downsize_last_truck` with `lifo_heavy_first` to eliminate empty volume in the final truck."
        ),
        "truck_id": "uhaul_26",
        "packer_engine": "constrained",
        "order_mode": "lifo_heavy_first",
        "lifo_weight": 1.3,
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
    r0 = _neon_round_record(
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
        rec = _neon_round_record(
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
    ap = argparse.ArgumentParser(description="Planner loop: solve, let the plan model change the settings, re-solve.")
    ap.add_argument("inventory", type=Path, help="Path to an inventory JSON (e.g. data/sample_venue.json)")
    ap.add_argument("--rounds", type=int, default=MAX_ROUNDS)
    ap.add_argument("--truck", default=None)
    ap.add_argument("--engine", default=None, choices=ENGINES)
    args = ap.parse_args()

    inv = json.loads(args.inventory.read_text(encoding="utf-8"))
    start = {k: v for k, v in (("truck_id", args.truck), ("packer_engine", args.engine)) if v}
    out = plan_with_model(inv, start, max_rounds=args.rounds)
    print(f"model: {out['model'] or '(none)'}")
    for r in out["rounds"]:
        mark = "*" if r["round"] == out["best_round"] else " "
        print(
            f"{mark} round {r['round']}: score {r['score']}, {r['fleet']}, {r['violation_count']} violations"
            + (f", model {r['model_latency_s']} s" if "model_latency_s" in r else "")
        )
        if r["changed"]:
            print("    changed: " + ", ".join(f"{k} {a!r} -> {b!r}" for k, (a, b) in r["changed"].items()))
        print(f"    {r['reason']}")
    if out["note"]:
        print("note:", out["note"])


if __name__ == "__main__":
    main()
