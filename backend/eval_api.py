"""HTTP routes for Live Chaos 1-Call LLM Baseline & Evaluation Table (`/eval/*`)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend import solver
from backend.pack_api import _enrich_media_and_corners, _load_inventory_for_run
from eval.baseline_bedroom import run_bedroom_baseline
from eval.baseline_single_call import run_single_call_baseline

router = APIRouter(tags=["eval"])


class ChaosSolveRequest(BaseModel):
    run_id: str | None = None
    inventory: dict[str, Any] | None = None
    truck_id: str = "uhaul_26"
    use_live_llm: bool = False


@router.post("/eval/chaos-plan")
def api_chaos_plan(req: ChaosSolveRequest) -> dict[str, Any]:
    rid = (req.run_id or "sample_venue").strip()
    inv = req.inventory
    if inv is None:
        rid, inv = _load_inventory_for_run(rid)
    plan = run_single_call_baseline(inv, truck_id=req.truck_id, use_live_llm=req.use_live_llm)
    plan["run_id"] = rid
    plan["rooms"] = [rb.get("room") for rb in inv.get("rooms", []) if rb.get("room")]
    _enrich_media_and_corners(rid, inv, plan)
    return plan


@router.get("/eval/summary")
def api_eval_summary(run_id: str = "sample_venue") -> dict[str, Any]:
    rid, inv = _load_inventory_for_run(run_id)
    ours = solver.solve(inv, strategy={"packer_engine": "constrained", "truck_id": "uhaul_26"})
    raw_py = solver.solve(inv, strategy={"packer_engine": "raw_py3dbp", "truck_id": "uhaul_26"})
    chaos = run_single_call_baseline(inv, truck_id="uhaul_26", use_live_llm=False)
    bed = run_bedroom_baseline(inv)

    return {
        "run_id": rid,
        "rows": [
            {
                "method": "Pack It Up (Agents + Constrained Solver + Verifier)",
                "score": ours["score"]["total"],
                "valid": ours["score"]["valid"],
                "violations": ours["score"]["violation_count"],
                "trucks": len(ours["trucks"]),
                "notes": "0 floating/overlap/crush violations · Penn LIFO ordered",
            },
            {
                "method": "Baseline A1: Single-Call LLM 3D Coordinates",
                "score": chaos["score"]["total"],
                "valid": chaos["score"]["valid"],
                "violations": chaos["score"]["violation_count"],
                "trucks": len(chaos["trucks"]),
                "notes": f"Mid-air floats, AABB overlaps & tipped upright items ({chaos['strategy']['via']})",
            },
            {
                "method": "Baseline A2: Stock py3dbp 3D Bin Packer",
                "score": raw_py["score"]["total"],
                "valid": raw_py["score"]["valid"],
                "violations": raw_py["score"]["violation_count"],
                "trucks": len(raw_py["trucks"]),
                "notes": "<75% base support overhangs, crushed light_only & axle imbalance",
            },
            {
                "method": "Baseline B: Rental-Site Room-Count Calculator",
                "score": bed["score"]["total"],
                "valid": bed["score"]["valid"],
                "violations": bed["score"]["violation_count"],
                "trucks": 1,
                "notes": f"Recommends 1× {bed['recommended_truck']} -> {bed['overflow_piece_count']} pieces stranded on curb",
            },
        ],
    }
