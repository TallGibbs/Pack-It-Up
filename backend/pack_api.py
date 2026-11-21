"""Track B HTTP routes: 3D truck + Penn Station store packing & verification.

Mounted by `backend/app.py` alongside Track A's `ingest_router`.

Routes:
  GET  /trucks             Available U-Haul trucks and Penn Station store zones
  POST /solve              {run_id?, inventory?, strategy?, extra_items?} -> placement JSON
  GET  /solve/{run_id}     Convenience GET solve for a run_id (or 'sample_venue' / 'mock-demo')
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend import catalog, solver
from backend.ingest.common import read_json, run_dir, write_json

router = APIRouter(tags=["pack"])

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_VENUE_PATH = REPO_ROOT / "data" / "sample_venue.json"
MOCK_INV_PATH = REPO_ROOT / "frontend" / "mock" / "inventory.json"


def _load_inventory_for_run(run_id: str | None) -> tuple[str, dict[str, Any]]:
    rid = (run_id or "sample_venue").strip()
    if rid in ("", "sample_venue", "sample"):
        if not SAMPLE_VENUE_PATH.exists():
            raise HTTPException(404, "sample_venue.json not found")
        return "sample_venue", json.loads(SAMPLE_VENUE_PATH.read_text(encoding="utf-8"))

    if rid == "mock-demo":
        if not MOCK_INV_PATH.exists():
            raise HTTPException(404, "frontend/mock/inventory.json not found")
        return "mock-demo", json.loads(MOCK_INV_PATH.read_text(encoding="utf-8"))

    try:
        rd = run_dir(rid)
    except ValueError:
        raise HTTPException(400, "bad run id")
    if not rd.exists():
        raise HTTPException(404, f"no run {rid}")

    inv = read_json(rd / "inventory.json")
    if inv is None:
        raise HTTPException(409, "inventory not ready yet; poll GET /runs/{run_id}")
    return rid, inv


def _inject_extra_items(inv: dict[str, Any], extra_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a deep copy of `inv` with judge what-if items appended."""
    if not extra_items:
        return inv
    cloned = copy.deepcopy(inv)
    rooms = cloned.setdefault("rooms", [])
    if not rooms:
        rooms.append({
            "room": {"id": "judge_room", "name": "Judge What-If"},
            "files": [],
            "items": [],
            "containers": [],
            "fixtures": [],
            "left_out": {"fixtures": 0, "personal_belongings": 0, "personal_belonging_kinds": {}},
        })
    target_items = rooms[0].setdefault("items", [])
    for idx, raw in enumerate(extra_items, start=1):
        cid = str(raw.get("catalog_id") or "unknown")
        cat = catalog.lookup(cid) if cid != "unknown" else None
        dims = raw.get("dims_in") or (cat["dims_in"] if cat else [36, 24, 36])
        vol = catalog.volume_cuft(float(dims[0]), float(dims[1]), float(dims[2]))
        wt = float(raw.get("weight_lb") or (cat["weight_lb"] if cat else round(vol * 7.0, 1)))
        qty = max(1, int(raw.get("quantity") or 1))
        target_items.append({
            "id": str(raw.get("id") or f"judge_extra_{idx:02d}"),
            "label": str(raw.get("label") or (cat["name"] if cat else "Added item")),
            "catalog_id": cid,
            "quantity": qty,
            "stack_count": int(raw.get("stack_count") or 1),
            "confidence": 1.0,
            "move_class": "movable",
            "size": {
                "dims_in": [float(dims[0]), float(dims[1]), float(dims[2])],
                "size_source": "user",
                "volume_cuft_each": vol,
                "volume_cuft_total": round(vol * qty, 2),
                "weight_lb_each": wt,
                "weight_lb_total": round(wt * qty, 1),
                "weight_source": "user",
                "material": str(raw.get("material") or "mixed"),
            },
            "fragile": bool(raw.get("fragile") if "fragile" in raw else (cat["fragile"] if cat else False)),
            "must_stay_upright": bool(
                raw.get("must_stay_upright")
                if "must_stay_upright" in raw
                else (cat["must_stay_upright"] if cat else False)
            ),
            "load_on_edge": bool(
                raw.get("load_on_edge") if "load_on_edge" in raw else (cat["load_on_edge"] if cat else False)
            ),
            "disassemble": bool(raw.get("disassemble", False)),
            "two_person": bool(
                raw.get("two_person") if "two_person" in raw else (cat["two_person"] if cat else wt > 50.0)
            ),
            "stackable": str(raw.get("stackable") or (cat["stackable"] if cat else "no")),
            "disposition": "keep",
            "heard_only": False,
            "evidence": {},
        })
    return cloned


@router.get("/trucks")
def get_trucks_and_zones() -> dict[str, Any]:
    return {
        "trucks": catalog.list_trucks(),
        "zones": catalog.list_penn_zones(),
    }


@router.post("/solve")
def post_solve(body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = body or {}
    strategy = dict(payload.get("strategy") or {})
    extra_items = list(payload.get("extra_items") or [])

    if isinstance(payload.get("inventory"), dict):
        inv = payload["inventory"]
        rid = str(payload.get("run_id") or inv.get("run_id") or "inline")
    else:
        rid, inv = _load_inventory_for_run(payload.get("run_id"))

    inv_to_solve = _inject_extra_items(inv, extra_items)
    try:
        plan = solver.solve(inv_to_solve, strategy=strategy)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    plan["run_id"] = rid
    plan["rooms"] = [
        {
            "id": (r.get("room") or {}).get("id") or f"room_{i+1}",
            "name": (r.get("room") or {}).get("name") or f"Room {i+1}",
        }
        for i, r in enumerate(inv_to_solve.get("rooms", []))
    ]

    # Persist placement.json for real runs when not running a transient what-if injection.
    if not extra_items and rid not in ("inline", "sample_venue", "mock-demo"):
        try:
            rd = run_dir(rid)
            if rd.exists():
                write_json(rd / "placement.json", plan)
        except Exception:
            pass

    return plan


@router.get("/solve/{run_id}")
def get_solve(
    run_id: str,
    truck_id: str = Query("uhaul_26"),
    packer_engine: str = Query("constrained"),
    order_mode: str = Query("lifo_heavy_first"),
    downsize_last_truck: bool = Query(False),
) -> dict[str, Any]:
    return post_solve({
        "run_id": run_id,
        "strategy": {
            "truck_id": truck_id,
            "packer_engine": packer_engine,
            "order_mode": order_mode,
            "downsize_last_truck": downsize_last_truck,
        },
    })
