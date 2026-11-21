"""Read-only routes for frontend/models.html.

GET /analysis/runs              -> every run with call and question counts
GET /analysis/runs/{run_id}     -> jobs, Decisions API answers, per-file perception, call timeline
GET /analysis/summary           -> the same job and decision totals across all runs
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.ingest.common import run_dir

from . import store

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/runs")
def runs():
    return {"runs": store.list_runs()}


@router.get("/runs/{run_id}")
def run(run_id: str):
    try:
        run_dir(run_id)  # validates the id's characters
    except ValueError as e:
        raise HTTPException(400, str(e))
    out = store.run_summary(run_id)
    if out is None:
        raise HTTPException(404, f"no run {run_id}")
    return out


@router.get("/summary")
def summary():
    return store.overall()
