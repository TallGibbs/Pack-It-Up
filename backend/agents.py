"""Stage B7: Competing Managed Agents arena (`agents.py`).

Launches 4 parallel packing agents with distinct strategic mandates:
  1. `agent_baseline`   — Naive Volume Packer (raw single-hall baseline anchor)
  2. `agent_structural` — Heavy-First Structural Mover (floor stability & L/R balance)
  3. `agent_penn_lifo`  — Penn Station Store & Dock Specialist (doorway routing + LIFO stops)
  4. `agent_fleet_opt`  — Right-Sized Hybrid Fleet Optimizer (mixed truck downsizing + stacking)

Execution modes (`mode`):
  - `"managed_agent"`: Runs each strategy agent inside Google's remote Linux sandbox
    via `antigravity-preview-09-2026` (`environment="remote"`, `background=True`,
    `agent_config={"type": "antigravity", "model": "gemini-4-neon"}`), where the agent
    writes & executes Python in its sandbox to optimize strategy parameters, then our
    host runs `solver.solve()` + `verify.verify()` to produce the exact 3D placement.
  - `"neon_fast"`: Parallel Gemini 4 Neon (`for_job("plan")`) structured strategy agents.
  - `"local"`: Fast in-process parallel sandbox workers (fallback when offline or key-less).
  - `"auto"` (default): Uses `"managed_agent"` when `GEMINI_API_KEY` is set (unless
    `MANAGED_AGENTS_FAST=1` selects `"neon_fast"`), with per-agent automatic fallback
    so a live stage demo never stalls.

Also maintains an in-memory background race registry (`start_agent_race` / `get_agent_race`)
so the UI can poll live per-agent progress as each worker finishes.

CLI:
    python -m backend.agents data/sample_venue.json
"""
from __future__ import annotations

import argparse
import concurrent.futures
import copy
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from backend import catalog, planner, solver
from backend.llm import LLMError
from backend.llm.managed_agents import has_api_key, plan_job, run_managed_agent

AGENT_SPECS: list[dict[str, Any]] = [
    {
        "agent_id": "agent_baseline",
        "name": "Agent 1 · Naive Volume Baseline",
        "persona": "Fast unguided volume-first bin-packer that packs into standard trucks without mover physics.",
        "fallback_strategy": {
            "truck_id": "uhaul_26",
            "packer_engine": "raw_py3dbp",
            "order_mode": "volume_first",
            "lifo_weight": 0.0,
            "downsize_last_truck": False,
            "allow_all_rotations": True,
            "force_single_zone": "penn_concourse",
        },
        "prefer_local_baseline": True,
    },
    {
        "agent_id": "agent_structural",
        "name": "Agent 2 · Heavy-First Structural",
        "persona": (
            "Conservative structural mover: enforces >=75% base support, upright & on-edge orientation, "
            "and heavy-before-light center-of-gravity stability across uniform 26-ft trucks."
        ),
        "fallback_strategy": {
            "truck_id": "uhaul_26",
            "packer_engine": "constrained",
            "order_mode": "heavy_first",
            "lifo_weight": 0.4,
            "downsize_last_truck": False,
            "allow_all_rotations": False,
        },
    },
    {
        "agent_id": "agent_penn_lifo",
        "name": "Agent 3 · Penn Station Store & LIFO",
        "persona": (
            "NY Penn Station dock logistics specialist: distributes cargo across all 6 Penn Station storefronts "
            "respecting doorway clearances and loads trucks in strict reverse dock-stop order (stop 6 -> stop 1)."
        ),
        "fallback_strategy": {
            "truck_id": "uhaul_26",
            "packer_engine": "constrained",
            "order_mode": "lifo_heavy_first",
            "lifo_weight": 1.5,
            "downsize_last_truck": False,
            "allow_all_rotations": False,
        },
    },
    {
        "agent_id": "agent_fleet_opt",
        "name": "Agent 4 · Right-Sized Hybrid Fleet",
        "persona": (
            "Fleet utilization & dock optimizer: pairs strict Penn Station store LIFO sequencing with mixed "
            "U-Haul downsizing (`downsize_last_truck=true`) to maximize cubic-foot fill with 0 violations."
        ),
        "fallback_strategy": {
            "truck_id": "uhaul_26",
            "packer_engine": "constrained",
            "order_mode": "zone_strict_lifo",
            "lifo_weight": 1.8,
            "downsize_last_truck": True,
            "allow_all_rotations": False,
        },
    },
]

_RACES: dict[str, dict[str, Any]] = {}
_RACES_LOCK = threading.Lock()


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    candidates = list(reversed(fenced))
    brace_match = re.search(r"(\{[^{}]*\"truck_id\"[^{}]*\})", text, flags=re.DOTALL)
    if brace_match:
        candidates.insert(0, brace_match.group(1))
    candidates.append(text.strip())
    for raw in candidates:
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and "truck_id" in obj:
                return obj
        except Exception:
            continue
    return None


def _build_managed_agent_prompt(spec: dict[str, Any], inv_summary: dict[str, Any]) -> str:
    trucks = [
        {"truck_id": t["truck_id"], "dims_in": t["dims_in"], "volume_cuft": t["volume_cuft"], "max_weight_lb": t["max_weight_lb"]}
        for t in catalog.list_trucks()
    ]
    zones = [
        {"zone_id": z["zone_id"], "dock_stop": z["dock_stop"], "door_in": z["door_in"], "floor_sqft": z["floor_sqft"]}
        for z in catalog.list_penn_zones()
    ]
    return (
        f"You are **{spec['name']}** competing in the Pack It Up strategy arena.\n"
        f"Your mandate: {spec['persona']}\n\n"
        f"Move inventory summary:\n{json.dumps(inv_summary, indent=2)}\n\n"
        f"U-Haul fleet specs: {json.dumps(trucks)}\n"
        f"Penn Station store zones: {json.dumps(zones)}\n\n"
        "Task inside your Linux sandbox:\n"
        "1. Write and run a quick Python script (`evaluate.py`) that checks truck ceiling clearance against "
        "`tallest_upright_in`, estimates how many trucks are needed at ~48% realistic furniture packing density, "
        "and chooses optimal settings for your mandate.\n"
        "2. Output ONLY a single JSON object (no markdown prose after it) with these exact keys:\n"
        '{"diagnosis": "...", "truck_id": "uhaul_van|uhaul_10|uhaul_15|uhaul_20|uhaul_26", '
        '"packer_engine": "constrained|raw_py3dbp", '
        '"order_mode": "lifo_heavy_first|zone_strict_lifo|heavy_first|volume_first|fragile_last", '
        '"lifo_weight": 0.0-3.0, "downsize_last_truck": true|false, '
        '"allow_all_rotations": true|false, "multi_store_routing": true|false}'
    )


def _sanitize_strategy(raw: dict[str, Any], default_strat: dict[str, Any]) -> tuple[dict[str, Any], str]:
    truck_id = str(raw.get("truck_id") or default_strat.get("truck_id") or "uhaul_26")
    if truck_id not in planner.TRUCK_IDS:
        truck_id = "uhaul_26"
    engine = str(raw.get("packer_engine") or default_strat.get("packer_engine") or "constrained")
    if engine not in planner.PACKER_ENGINES:
        engine = "constrained"
    order_mode = str(raw.get("order_mode") or default_strat.get("order_mode") or "lifo_heavy_first")
    if order_mode not in planner.ORDER_MODES:
        order_mode = "lifo_heavy_first"
    try:
        lifo_wt = max(0.0, min(3.0, float(raw.get("lifo_weight", default_strat.get("lifo_weight", 1.0)))))
    except Exception:
        lifo_wt = 1.0

    strat: dict[str, Any] = {
        "truck_id": truck_id,
        "packer_engine": engine,
        "order_mode": order_mode,
        "lifo_weight": round(lifo_wt, 2),
        "downsize_last_truck": bool(raw.get("downsize_last_truck", default_strat.get("downsize_last_truck", False))),
        "allow_all_rotations": bool(raw.get("allow_all_rotations", default_strat.get("allow_all_rotations", False))),
    }
    if not raw.get("multi_store_routing", "force_single_zone" not in default_strat):
        strat["force_single_zone"] = "penn_concourse"
    diag = str(raw.get("diagnosis") or "").strip()
    return strat, diag


def _run_one_agent(
    spec: dict[str, Any],
    inventory: dict[str, Any],
    inv_summary: dict[str, Any],
    *,
    mode: str,
    run_dir: Path | None,
) -> dict[str, Any]:
    t0 = time.time()
    aid = spec["agent_id"]
    fallback_strat = copy.deepcopy(spec["fallback_strategy"])
    chosen_strat = fallback_strat
    rationale = spec["persona"]
    via = "local_sandbox"
    interaction_id: str | None = None
    environment_id: str | None = None

    effective_mode = mode
    if effective_mode == "auto":
        if not has_api_key():
            effective_mode = "local"
        elif os.environ.get("MANAGED_AGENTS_FAST") == "1":
            effective_mode = "neon_fast"
        else:
            effective_mode = "managed_agent"

    # Agent 1 intentionally anchors the raw unguided baseline so judges see the contrast.
    if spec.get("prefer_local_baseline"):
        effective_mode = "local"

    if effective_mode == "managed_agent" and has_api_key():
        prompt = _build_managed_agent_prompt(spec, inv_summary)
        try:
            ma_res = run_managed_agent(
                prompt,
                run_dir=run_dir,
                label=aid,
                timeout_s=95.0,
            )
            interaction_id = ma_res.get("interaction_id")
            environment_id = ma_res.get("environment_id")
            parsed = _extract_json_object(ma_res.get("output_text", ""))
            if parsed:
                chosen_strat, diag = _sanitize_strategy(parsed, fallback_strat)
                if diag:
                    rationale = diag
                via = f"managed_agent:{ma_res.get('agent')}({ma_res.get('agent_model')})"
            else:
                effective_mode = "neon_fast"
        except LLMError:
            effective_mode = "neon_fast"

    if effective_mode == "neon_fast" and has_api_key():
        prompt = _build_managed_agent_prompt(spec, inv_summary)
        try:
            job = plan_job("plan", run_dir=run_dir)
            parsed = job.generate_json(
                prompt,
                schema=planner.NEON_ROUND_SCHEMA,
                prompt_version="agent_arena_v1",
                label=aid,
            )
            chosen_strat, diag = _sanitize_strategy(parsed, fallback_strat)
            if diag:
                rationale = diag
            via = job.spec
        except LLMError:
            chosen_strat = fallback_strat
            via = "local_sandbox_fallback"

    placement = solver.solve(inventory, strategy=chosen_strat)
    elapsed = round(time.time() - t0, 2)
    sc = placement["score"]
    sm = placement["summary"]

    return {
        "agent_id": aid,
        "name": spec["name"],
        "persona": spec["persona"],
        "status": "completed",
        "via": via,
        "interaction_id": interaction_id,
        "environment_id": environment_id,
        "elapsed_s": elapsed,
        "rationale": rationale,
        "strategy": chosen_strat,
        "fleet_label": sm["fleet_label"],
        "truck_count": sm["truck_count"],
        "zones_stocked": sm["zones_stocked"],
        "score": {
            "total": sc["total"],
            "valid": sc["valid"],
            "fill_pct": sc["fill_pct"],
            "balance_pct": sc["balance_pct"],
            "lifo_score": sc["lifo_score"],
            "violation_count": sc["violation_count"],
            "violation_counts_by_rule": sc["violation_counts_by_rule"],
        },
        "placement": placement,
    }


def _agent_rank(entry: dict[str, Any]) -> tuple[int, float, float]:
    sc = entry.get("score") or {}
    return (1 if sc.get("valid") else 0, float(sc.get("total") or 0.0), float(sc.get("fill_pct") or 0.0))


def run_competing_agents(
    inventory: dict[str, Any],
    *,
    mode: str = "auto",
    run_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Run all 4 competing strategy agents in parallel and return the verified winner."""
    rd = Path(run_dir) if run_dir else None
    inv_summary = planner.summarize_inventory(inventory)

    results_by_id: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(AGENT_SPECS)) as pool:
        futs = {
            pool.submit(_run_one_agent, spec, inventory, inv_summary, mode=mode, run_dir=rd): spec["agent_id"]
            for spec in AGENT_SPECS
        }
        for fut in concurrent.futures.as_completed(futs):
            aid = futs[fut]
            results_by_id[aid] = fut.result()

    ordered_agents = [results_by_id[s["agent_id"]] for s in AGENT_SPECS]
    winner_entry = max(ordered_agents, key=_agent_rank)
    winner_plan = copy.deepcopy(winner_entry["placement"])

    public_agents = []
    for a in ordered_agents:
        row = {k: v for k, v in a.items() if k != "placement"}
        row["is_winner"] = a["agent_id"] == winner_entry["agent_id"]
        public_agents.append(row)

    winner_plan["agent_arena"] = {
        "winner_agent_id": winner_entry["agent_id"],
        "winner_name": winner_entry["name"],
        "agents": public_agents,
    }
    return {
        "status": "completed",
        "completed_count": len(public_agents),
        "total_count": len(public_agents),
        "winner_agent_id": winner_entry["agent_id"],
        "winner_name": winner_entry["name"],
        "agents": public_agents,
        "winner": winner_plan,
    }


def start_agent_race(
    inventory: dict[str, Any],
    *,
    run_id: str = "sample_venue",
    mode: str = "auto",
    run_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Launch the 4 competing agents asynchronously so the UI can poll each run as it finishes."""
    job_id = f"race_{uuid.uuid4().hex[:10]}"
    rd = Path(run_dir) if run_dir else None
    inv_copy = copy.deepcopy(inventory)
    inv_summary = planner.summarize_inventory(inv_copy)

    initial_agents = [
        {
            "agent_id": s["agent_id"],
            "name": s["name"],
            "persona": s["persona"],
            "status": "running",
            "via": None,
            "elapsed_s": None,
            "rationale": s["persona"],
            "fleet_label": None,
            "score": None,
            "is_winner": False,
        }
        for s in AGENT_SPECS
    ]
    race_state: dict[str, Any] = {
        "job_id": job_id,
        "run_id": run_id,
        "status": "running",
        "started_at": time.time(),
        "completed_count": 0,
        "total_count": len(AGENT_SPECS),
        "winner_agent_id": None,
        "winner_name": None,
        "agents": initial_agents,
        "_placements": {},
        "winner": None,
    }
    with _RACES_LOCK:
        _RACES[job_id] = race_state

    def _worker(idx: int, spec: dict[str, Any]) -> None:
        try:
            res = _run_one_agent(spec, inv_copy, inv_summary, mode=mode, run_dir=rd)
        except Exception as exc:
            res = {
                "agent_id": spec["agent_id"],
                "name": spec["name"],
                "persona": spec["persona"],
                "status": "failed",
                "via": "error",
                "elapsed_s": 0.0,
                "rationale": f"Failed: {exc}",
                "fleet_label": "—",
                "score": {"total": 0.0, "valid": False, "fill_pct": 0.0, "violation_count": 1},
                "placement": None,
            }

        with _RACES_LOCK:
            st = _RACES[job_id]
            pub = {k: v for k, v in res.items() if k != "placement"}
            pub["is_winner"] = False
            st["agents"][idx] = pub
            if res.get("placement") is not None:
                st["_placements"][spec["agent_id"]] = res["placement"]
            st["completed_count"] = sum(1 for a in st["agents"] if a["status"] in ("completed", "failed"))

            if st["completed_count"] >= st["total_count"]:
                completed = [a for a in st["agents"] if a["status"] == "completed" and a["agent_id"] in st["_placements"]]
                if completed:
                    best = max(completed, key=_agent_rank)
                    for a in st["agents"]:
                        a["is_winner"] = a["agent_id"] == best["agent_id"]
                    win_plan = copy.deepcopy(st["_placements"][best["agent_id"]])
                    win_plan["run_id"] = run_id
                    win_plan["agent_arena"] = {
                        "winner_agent_id": best["agent_id"],
                        "winner_name": best["name"],
                        "agents": copy.deepcopy(st["agents"]),
                    }
                    st["winner_agent_id"] = best["agent_id"]
                    st["winner_name"] = best["name"]
                    st["winner"] = win_plan
                    st["status"] = "completed"
                else:
                    st["status"] = "failed"

    for idx, spec in enumerate(AGENT_SPECS):
        threading.Thread(target=_worker, args=(idx, spec), daemon=True).start()

    return get_agent_race(job_id)  # type: ignore[return-value]


def get_agent_race(job_id: str) -> dict[str, Any] | None:
    """Return a JSON-safe snapshot of a background agent race."""
    with _RACES_LOCK:
        st = _RACES.get(job_id)
        if st is None:
            return None
        return {
            "job_id": st["job_id"],
            "run_id": st["run_id"],
            "status": st["status"],
            "completed_count": st["completed_count"],
            "total_count": st["total_count"],
            "winner_agent_id": st["winner_agent_id"],
            "winner_name": st["winner_name"],
            "agents": copy.deepcopy(st["agents"]),
            "winner": copy.deepcopy(st["winner"]),
        }


def main() -> None:
    ap = argparse.ArgumentParser(description="Run B7 competing packing agents.")
    ap.add_argument("inventory", type=Path, help="Path to inventory_v2 JSON (e.g. data/sample_venue.json)")
    ap.add_argument("--mode", default="auto", choices=["auto", "managed_agent", "neon_fast", "local"])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    inv = json.loads(args.inventory.read_text(encoding="utf-8"))
    res = run_competing_agents(inv, mode=args.mode)
    print(f"Winner: {res['winner_name']} ({res['winner_agent_id']})")
    for a in res["agents"]:
        sc = a["score"]
        star = "★ WINNER" if a["is_winner"] else "        "
        print(
            f"  {star} {a['name']:36s} | via={a['via']:22s} | fleet={a['fleet_label']:26s} "
            f"| score={sc['total']:5.1f} valid={str(sc['valid']):5s} fill={sc['fill_pct']:4.1f}% viol={sc['violation_count']}"
        )
    if args.out:
        args.out.write_text(json.dumps(res, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
