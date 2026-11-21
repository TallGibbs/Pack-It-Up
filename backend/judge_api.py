"""FastAPI routes for the two separate Final Judge steps.

Mount in `backend/app.py`:
    from backend.judge_api import router as judge_router
    app.include_router(judge_router)

Routes (kept strictly separate per George's design decision):
  POST /judge/plan              inline `{placement?, inventory?}` -> Step 1 Move Plan Judge
  POST /judge/plan/{run_id}     judges `runs/<run_id>` move plan  -> writes `judge_plan.json`
  POST /judge/rubric            repo + optional `{plan_judgment?}` -> Step 2 Hackathon Rubric Judge
  POST /judge/rubric/{run_id}   judges `runs/<run_id>` + repo     -> writes `judge_rubric.json`
  GET  /judge/{run_id}          returns stored `judge_plan` and `judge_rubric` if present
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from backend import judge_plan, judge_rubric, solver
from backend.ingest.common import read_json, run_dir

router = APIRouter(tags=["judge"])


def _rd(run_id: str) -> Path:
    try:
        rd = run_dir(run_id)
    except ValueError:
        raise HTTPException(400, "bad run id")
    if not rd.exists():
        raise HTTPException(404, f"no run {run_id}")
    return rd


@router.post("/judge/plan")
def post_judge_plan_inline(body: dict[str, Any] = Body(...)):
    placement = body.get("placement")
    inventory = body.get("inventory")
    if placement is None:
        if inventory is None:
            raise HTTPException(400, "body must provide 'placement' or 'inventory'")
        placement = solver.solve(inventory)
    return judge_plan.judge_move_plan(placement, inventory=inventory)


@router.post("/judge/plan/{run_id}")
def post_judge_plan_run(run_id: str):
    if run_id not in ("sample_venue", "sample", "mock-demo"):
        _rd(run_id)
    try:
        return judge_plan.judge_run_plan(run_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/judge/rubric")
def post_judge_rubric_inline(body: dict[str, Any] | None = Body(default=None)):
    body = body or {}
    return judge_rubric.judge_hackathon_rubric(plan_judgment=body.get("plan_judgment"))


@router.post("/judge/rubric/{run_id}")
def post_judge_rubric_run(run_id: str):
    if run_id in ("sample_venue", "sample", "mock-demo"):
        return judge_rubric.judge_hackathon_rubric(run_id=run_id, rd=None, plan_judgment=None)
    rd = _rd(run_id)
    plan_judgment = read_json(rd / "judge_plan.json")
    return judge_rubric.judge_hackathon_rubric(run_id=run_id, rd=rd, plan_judgment=plan_judgment)


@router.get("/judge/{run_id}")
def get_judge_results(run_id: str):
    rd = _rd(run_id)
    return {
        "run_id": run_id,
        "move_plan_judge": read_json(rd / "judge_plan.json"),
        "hackathon_rubric_judge": read_json(rd / "judge_rubric.json"),
    }
