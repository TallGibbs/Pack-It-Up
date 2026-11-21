"""Stage B6 + B7 HTTP router: Gemini 4 Neon planning loop & Competing Managed Agents arena.

Kept in its own router module (`arena_api.py`) so parallel Track B sessions editing
`pack_api.py` or `commerce_api.py` merge with zero conflicts. Mount in `backend/app.py`:
    from backend.arena_api import router as arena_router
    app.include_router(arena_router)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from backend import agents, pack_api, planner
from backend.ingest.common import run_dir, write_json

router = APIRouter(tags=["arena"])


def _attach_metadata(plan: dict[str, Any], rid: str, inv: dict[str, Any]) -> None:
    plan["run_id"] = rid
    plan["rooms"] = [
        {
            "id": (r.get("room") or {}).get("id") or f"room_{i+1}",
            "name": (r.get("room") or {}).get("name") or f"Room {i+1}",
        }
        for i, r in enumerate(inv.get("rooms", []))
    ]
    enrich = getattr(pack_api, "_enrich_media_and_corners", None)
    if callable(enrich):
        try:
            enrich(rid, inv, plan)
        except Exception:
            pass


@router.post("/plan")
def post_plan(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run B6 Gemini 4 Neon iterative planning loop (up to 3 rounds) and return progression + winner."""
    payload = body or {}
    extra_items = list(payload.get("extra_items") or [])
    max_rounds = int(payload.get("max_rounds") or 3)
    initial_strategy = payload.get("initial_strategy")

    if isinstance(payload.get("inventory"), dict):
        inv = payload["inventory"]
        rid = str(payload.get("run_id") or inv.get("run_id") or "inline")
    else:
        rid, inv = pack_api._load_inventory_for_run(payload.get("run_id"))

    inv_to_solve = pack_api._inject_extra_items(inv, extra_items)
    rd: Path | None = None
    if rid not in ("inline", "sample_venue", "mock-demo"):
        try:
            cand_rd = run_dir(rid)
            if cand_rd.exists():
                rd = cand_rd
        except ValueError:
            pass

    res = planner.run_neon_loop(
        inv_to_solve,
        initial_strategy=initial_strategy,
        max_rounds=max_rounds,
        run_dir=rd,
    )
    _attach_metadata(res["winner"], rid, inv_to_solve)
    res["run_id"] = rid

    if not extra_items and rd is not None:
        try:
            write_json(rd / "placement.json", res["winner"])
        except Exception:
            pass
    return res


@router.post("/agents/start")
def post_agents_start(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Start B7 competing Managed Agents in background threads; poll `GET /agents/{job_id}`."""
    payload = body or {}
    extra_items = list(payload.get("extra_items") or [])
    mode = str(payload.get("mode") or "auto")

    if isinstance(payload.get("inventory"), dict):
        inv = payload["inventory"]
        rid = str(payload.get("run_id") or inv.get("run_id") or "inline")
    else:
        rid, inv = pack_api._load_inventory_for_run(payload.get("run_id"))

    inv_to_solve = pack_api._inject_extra_items(inv, extra_items)
    rd: Path | None = None
    if rid not in ("inline", "sample_venue", "mock-demo"):
        try:
            cand_rd = run_dir(rid)
            if cand_rd.exists():
                rd = cand_rd
        except ValueError:
            pass

    snap = agents.start_agent_race(inv_to_solve, run_id=rid, mode=mode, run_dir=rd)
    if snap.get("winner"):
        _attach_metadata(snap["winner"], rid, inv_to_solve)
    return snap


@router.get("/agents/{job_id}")
def get_agents_status(job_id: str) -> dict[str, Any]:
    """Poll live progress of a B7 competing agents race."""
    snap = agents.get_agent_race(job_id)
    if snap is None:
        raise HTTPException(404, f"no agent race {job_id}")
    rid = snap.get("run_id") or "sample_venue"
    if snap.get("winner") and "rooms" not in snap["winner"]:
        try:
            _, inv = pack_api._load_inventory_for_run(rid)
            _attach_metadata(snap["winner"], rid, inv)
        except Exception:
            snap["winner"]["run_id"] = rid
            snap["winner"]["rooms"] = []
        if rid not in ("inline", "sample_venue", "mock-demo"):
            try:
                rd = run_dir(rid)
                if rd.exists():
                    write_json(rd / "placement.json", snap["winner"])
            except Exception:
                pass
    return snap
