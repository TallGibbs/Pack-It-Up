"""FastAPI routes for real-time Point A -> Point B truck route tips & city parking (`backend/route_guide.py`).

Mounted by `backend/app.py`:
  GET  /route/presets   Quick-fill origin/destination presets & supported phone nav apps
  GET  /route/brief     Convenience GET endpoint for live route brief
  POST /route/brief     Full POST endpoint accepting `{run_id?, plan?, origin, destination, truck_id?, nav_app?, refresh?}`
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend import route_guide, solver
from backend.ingest.common import read_json, run_dir

router = APIRouter(prefix="/route", tags=["route"])

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_VENUE_PATH = REPO_ROOT / "data" / "sample_venue.json"
MOCK_INV_PATH = REPO_ROOT / "frontend" / "mock" / "inventory.json"


def _load_plan_context(run_id: str | None, inline_plan: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, Path | None]:
    if isinstance(inline_plan, dict) and inline_plan.get("trucks"):
        rid = (run_id or "").strip()
        rd = None
        if rid and rid not in ("inline", "sample_venue", "sample", "mock-demo"):
            try:
                cand = run_dir(rid)
                if cand.exists():
                    rd = cand
            except ValueError:
                pass
        return inline_plan, rd

    rid = (run_id or "sample_venue").strip()
    if rid in ("", "sample_venue", "sample"):
        if SAMPLE_VENUE_PATH.exists():
            inv = json.loads(SAMPLE_VENUE_PATH.read_text(encoding="utf-8"))
            return solver.solve(inv), None
        return None, None

    if rid == "mock-demo":
        if MOCK_INV_PATH.exists():
            inv = json.loads(MOCK_INV_PATH.read_text(encoding="utf-8"))
            return solver.solve(inv), None
        return None, None

    try:
        rd = run_dir(rid)
    except ValueError:
        raise HTTPException(400, "bad run id")
    if not rd.exists():
        return None, None

    saved_plan = read_json(rd / "placement.json")
    if saved_plan:
        return saved_plan, rd
    inv = read_json(rd / "inventory.json")
    if inv:
        return solver.solve(inv), rd
    return None, rd


@router.get("/presets")
def get_route_presets() -> dict[str, Any]:
    return {
        "default_origin": route_guide.DEFAULT_ORIGIN,
        "default_destination": route_guide.DEFAULT_DESTINATION,
        "places": [
            {"label": p["label"], "neighborhood": p.get("neighborhood") or p["city"], "state": p["state"]}
            for p in route_guide.KNOWN_PLACES
        ],
        "nav_apps": [
            {"id": k, "name": v["name"], "has_native_truck_mode": v["has_native_truck_mode"], "badge": v["badge"]}
            for k, v in route_guide.NAV_APP_PROFILES.items()
        ],
    }


@router.post("/brief")
def post_route_brief(body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = body or {}
    plan, rd = _load_plan_context(payload.get("run_id"), inline_plan=payload.get("plan"))
    refresh = bool(payload.get("refresh", False))
    use_llm = bool(payload.get("use_llm", True))
    client = route_guide.LiveRouteDataClient(use_cache=not refresh)

    return route_guide.build_route_brief(
        origin=payload.get("origin"),
        destination=payload.get("destination"),
        plan=plan,
        truck_id=payload.get("truck_id"),
        nav_app=str(payload.get("nav_app") or "google_maps"),
        run_dir=rd,
        client=client,
        use_llm=use_llm,
    )


@router.get("/brief")
def get_route_brief(
    origin: str = Query(route_guide.DEFAULT_ORIGIN),
    destination: str = Query(route_guide.DEFAULT_DESTINATION),
    run_id: str = Query("sample_venue"),
    truck_id: str | None = Query(None),
    nav_app: str = Query("google_maps"),
    refresh: bool = Query(False),
    use_llm: bool = Query(True),
) -> dict[str, Any]:
    return post_route_brief({
        "origin": origin,
        "destination": destination,
        "run_id": run_id,
        "truck_id": truck_id,
        "nav_app": nav_app,
        "refresh": refresh,
        "use_llm": use_llm,
    })
