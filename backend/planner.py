"""Stage B6: the planner loop. A Gemini 4 model reads the checker's result and changes the solver's settings.

Round 1 is the solver with the settings it was given. For each later round the model (job `plan` in
`backend/llm/models.toml`, Neon today) gets the load, the truck table, and every round so far: settings,
score, violations by rule, and how full each truck is. It never sees the placement list. It returns a new
set of settings and one sentence on why; the solver runs again and `verify.py` scores the result. The model
proposes, the checker decides: the plan kept is the highest-scoring one with no violations.

    from backend import planner
    out = planner.plan_with_model(inventory)          # {"plan", "rounds", "best_round", "model", "note"}

Run from the CLI (one real model call per extra round):
    python -m backend.planner data/sample_venue.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable

from backend import catalog, solver

MAX_ROUNDS = 3
PROMPT_VERSION = "plan_v1"

ORDER_MODES = ["lifo_heavy_first", "heavy_first", "volume_first", "fragile_last", "zone_strict_lifo"]
ENGINES = ["constrained", "raw_py3dbp"]

# The settings the model may change, with the solver's defaults. Anything else in a strategy
# (what-if items, zone overrides) stays as the caller set it.
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
                "truck_id": {"type": "string", "enum": ["uhaul_10", "uhaul_15", "uhaul_20", "uhaul_26"]},
                "truck_sequence": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["uhaul_10", "uhaul_15", "uhaul_20", "uhaul_26"]},
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
    """What is being moved, in a few numbers. Taken from the solved plan, so it matches what the solver saw."""
    items = [it for t in plan.get("trucks", []) for it in t.get("items", [])]
    dims = [it.get("orig_dims_in") or it["size_in"] for it in items] + [u["dims_in"] for u in plan.get("unplaced", []) if u.get("dims_in")]
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
    """The part of a solved plan the model reads: score, violations by rule, a few details, truck fill."""
    sc = plan["score"]
    trucks = [
        {"truck_id": t["truck_id"], "pieces": len(t["items"]), "fill_pct": t["fill_pct"],
         "weight_lb": t["weight_lb"], "max_weight_lb": t["max_weight_lb"]}
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
    # A nearly empty last truck is the usual waste; say what is in it so the model can reason about why.
    if len(plan.get("trucks", [])) > 1 and len(plan["trucks"][-1]["items"]) <= 6:
        out["last_truck_pieces"] = [
            {"label": str(it["label"])[:60], "dims_in": it.get("orig_dims_in"), "weight_lb": it["weight_lb"],
             "must_stay_upright": it["must_stay_upright"], "load_on_edge": it["load_on_edge"],
             "stackable": it["stackable"]}
            for it in plan["trucks"][-1]["items"]
        ]
    if plan.get("unplaced"):
        out["unplaced_examples"] = [f"{u['label']}: {u.get('reason', '')}"[:200] for u in plan["unplaced"][:5]]
    return out


def build_prompt(load: dict, history: list[dict], rounds_left: int) -> str:
    trucks = [
        {"truck_id": t["truck_id"], "inside_in": t["dims_in"], "volume_cuft": round(t["volume_cuft"]),
         "max_weight_lb": t["max_weight_lb"]}
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


def _round_record(n: int, source: str, strategy: dict, plan: dict, reason: str, changed: dict | None = None) -> dict[str, Any]:
    sc = plan["score"]
    return {
        "round": n,
        "source": source,  # "start" = the settings the caller gave; "model" = the model's settings
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
    """Higher is better: no violations first, then the checker's score, then fewer trucks, then the earlier round."""
    return (rec["valid"], rec["score"], -rec["truck_count"], -rec["round"])


def plan_with_model(
    inventory: dict,
    strategy: dict | None = None,
    *,
    max_rounds: int = MAX_ROUNDS,
    run_dir: Path | str | None = None,
    ask: Callable[[str, int], dict] | None = None,
) -> dict[str, Any]:
    """Solve, let the model change the settings, solve again; up to `max_rounds` solver runs in all.

    Returns {"plan": best plan, "rounds": [...], "best_round": n, "model": id, "note": str | None}.
    A failed model call ends the loop and is reported in `note`; the best plan so far is still returned,
    so with no model at all this is the plain solve. `ask(prompt, round_no) -> dict` replaces the model in tests.
    """
    base = dict(strategy or {})
    max_rounds = max(1, min(int(max_rounds), 5))
    model_id = ""
    note: str | None = None

    plan = solver.solve(inventory, strategy=base)  # a ValueError here (bad truck_id) is the caller's to handle
    plans = [plan]
    rounds = [_round_record(1, "start", base, plan, "Starting settings.")]
    history = [{"round": 1, "settings": rounds[0]["settings"], "result": _result_digest(plan)}]
    load = _load_facts(plan)

    if ask is None and max_rounds > 1:
        try:
            from backend.llm import for_job  # the only door to a model; see AGENTS.md
            job = for_job("plan", run_dir)
            model_id = job.provider.model

            def ask(prompt: str, round_no: int) -> dict:
                return job.generate_json(prompt, schema=SCHEMA, prompt_version=PROMPT_VERSION,
                                         label=f"plan round {round_no}")
        except Exception as e:  # missing job or key: the plain solve still stands
            note = f"Planner model not available ({type(e).__name__}: {e}); this is the plain solve."
            max_rounds = 1

    for n in range(2, max_rounds + 1):
        prompt = build_prompt(load, history, rounds_left=max_rounds - n + 1)
        t0 = time.time()
        try:
            answer = ask(prompt, n)
        except Exception as e:  # LLMError is already in the call log and FAILURES.md
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
        rec = _round_record(n, "model", new_strategy, plan, reason, _changes(prev, settings))
        rec["model_latency_s"] = latency  # close to 0 means the answer came from the response cache
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
        print(f"{mark} round {r['round']}: score {r['score']}, {r['fleet']}, {r['violation_count']} violations"
              + (f", model {r['model_latency_s']} s" if "model_latency_s" in r else ""))
        if r["changed"]:
            print("    changed: " + ", ".join(f"{k} {a!r} -> {b!r}" for k, (a, b) in r["changed"].items()))
        print(f"    {r['reason']}")
    if out["note"]:
        print("note:", out["note"])


if __name__ == "__main__":
    main()
