"""Read-only routes for frontend/models.html.

GET /analysis/runs              -> every run with call and question counts
GET /analysis/runs/{run_id}     -> jobs, Decisions API answers, per-file perception, call timeline
GET /analysis/summary           -> the same job and decision totals across all runs
GET /analysis/trends            -> one row per run, oldest first: speed, confidence, answers kept

GET /analysis/databricks        -> is the Databricks copy on, when it last ran, its last error's type
GET /analysis/databricks/summary -> totals per model, read back from the Databricks tables (kept a minute)

Runs whose folder was deleted stay in the database, marked `archived`.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.ingest.common import run_dir

from . import databricks, store

router = APIRouter(prefix="/analysis", tags=["analysis"])
databricks.start_background()  # copies runs to Databricks every minute, only if .env has its settings


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


@router.get("/trends")
def trends():
    return {"runs": store.trends()}


@router.get("/databricks")
def databricks_status():
    return databricks.public_status()


@router.get("/databricks/summary")
def databricks_summary():
    return databricks.summary()
