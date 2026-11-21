"""FastAPI routes for the Shopify / shop.dev Commerce Bonus Track (`backend/commerce.py`).

Mounted by `backend/app.py`:
  GET  /commerce/kit/{run_id}   Build live Move Supply Kit + Shop Pay checkouts + Haul-vs-Replace comps
  POST /commerce/kit            Same, accepting inline `inventory` / `plan` / `extra_items` / `state`
  POST /commerce/agent          Conversational Gemini 4 + mcp.shop.com Shopping Agent turn
  POST /commerce/search         Direct Shop.dev global catalog search (`mcp.shop.com/search_catalog`)
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend import catalog, commerce, solver
from backend.ingest.common import read_json, run_dir, write_json

router = APIRouter(prefix="/commerce", tags=["commerce"])

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_VENUE_PATH = REPO_ROOT / "data" / "sample_venue.json"
MOCK_INV_PATH = REPO_ROOT / "frontend" / "mock" / "inventory.json"


def _resolve_run_context(
    run_id: str | None,
    inline_inv: dict[str, Any] | None = None,
    inline_plan: dict[str, Any] | None = None,
    extra_items: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any] | None, Path | None]:
    """Load `(rid, inventory, plan, rd_path)` for `sample_venue`, `mock-demo`, inline JSON, or real `run_id`."""
    if isinstance(inline_inv, dict):
        rid = str(run_id or inline_inv.get("run_id") or "inline")
        inv = copy.deepcopy(inline_inv)
        rd = None
    else:
        rid = (run_id or "sample_venue").strip()
        if rid in ("", "sample_venue", "sample"):
            if not SAMPLE_VENUE_PATH.exists():
                raise HTTPException(404, "sample_venue.json not found")
            inv = json.loads(SAMPLE_VENUE_PATH.read_text(encoding="utf-8"))
            rd = None
            rid = "sample_venue"
        elif rid == "mock-demo":
            if not MOCK_INV_PATH.exists():
                raise HTTPException(404, "frontend/mock/inventory.json not found")
            inv = json.loads(MOCK_INV_PATH.read_text(encoding="utf-8"))
            rd = None
        else:
            try:
                rd = run_dir(rid)
            except ValueError:
                raise HTTPException(400, "bad run id")
            if not rd.exists():
                raise HTTPException(404, f"no run {rid}")
            loaded = read_json(rd / "inventory.json")
            if loaded is None:
                raise HTTPException(409, "inventory not ready yet; poll GET /runs/{run_id}")
            inv = loaded

    if extra_items:
        rooms = inv.setdefault("rooms", [])
        if not rooms:
            rooms.append({"room": {"id": "judge_room", "name": "Judge What-If"}, "items": [], "containers": []})
        t_items = rooms[0].setdefault("items", [])
        for idx, raw in enumerate(extra_items, start=1):
            cid = str(raw.get("catalog_id") or "unknown")
            cat = catalog.lookup(cid) if cid != "unknown" else None
            dims = raw.get("dims_in") or (cat["dims_in"] if cat else [36, 24, 36])
            vol = catalog.volume_cuft(float(dims[0]), float(dims[1]), float(dims[2]))
            wt = float(raw.get("weight_lb") or (cat["weight_lb"] if cat else round(vol * 7.0, 1)))
            qty = max(1, int(raw.get("quantity") or 1))
            t_items.append({
                "id": str(raw.get("id") or f"judge_extra_{idx:02d}"),
                "label": str(raw.get("label") or (cat["name"] if cat else "Added item")),
                "catalog_id": cid,
                "quantity": qty,
                "stack_count": int(raw.get("stack_count") or 1),
                "size": {
                    "dims_in": [float(dims[0]), float(dims[1]), float(dims[2])],
                    "volume_cuft_each": vol,
                    "volume_cuft_total": round(vol * qty, 2),
                    "weight_lb_each": wt,
                    "weight_lb_total": round(wt * qty, 1),
                },
                "fragile": bool(raw.get("fragile") if "fragile" in raw else (cat["fragile"] if cat else False)),
                "two_person": bool(raw.get("two_person") if "two_person" in raw else (cat["two_person"] if cat else wt > 50.0)),
                "disposition": "keep",
            })

    plan = inline_plan
    if plan is None and rd is not None and not extra_items:
        plan = read_json(rd / "placement.json")
    if plan is None:
        try:
            plan = solver.solve(inv)
        except Exception:
            plan = None

    return rid, inv, plan, rd


def _dest_from_postal(postal_code: str | None, region: str | None = None) -> dict[str, str]:
    pc = (postal_code or "10001").strip() or "10001"
    reg = (region or ("NY" if pc.startswith("1") else "NY")).strip() or "NY"
    return {"country": "US", "region": reg, "postal_code": pc, "currency": "USD"}


@router.post("/kit")
def post_commerce_kit(body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = body or {}
    rid, inv, plan, rd = _resolve_run_context(
        payload.get("run_id"),
        inline_inv=payload.get("inventory"),
        inline_plan=payload.get("plan"),
        extra_items=payload.get("extra_items"),
    )
    state = dict(payload.get("state") or {})
    tier = str(payload.get("tier") or state.get("tier") or "standard")
    dest = _dest_from_postal(payload.get("postal_code"), payload.get("region"))
    verify_dec = bool(payload.get("verify_with_decisions", True))
    include_comps = bool(payload.get("include_comps", True))

    kit = commerce.build_move_kit(
        inv,
        plan,
        destination=dest,
        tier=tier,
        verify_with_decisions=verify_dec,
        max_budget_cents=state.get("max_budget_cents"),
        custom_additions=state.get("custom_additions"),
        excluded_ids=set(state.get("excluded_ids") or []),
        qty_overrides=state.get("qty_overrides"),
        query_overrides=state.get("query_overrides"),
        run_dir=rd,
    )
    comps = commerce.discover_item_comps(inv, destination=dest, run_dir=rd) if include_comps else []

    out = {
        "run_id": rid,
        "kit": kit,
        "item_comps": comps,
        "state": {
            "tier": kit["tier"],
            "custom_additions": list(state.get("custom_additions") or []),
            "excluded_ids": list(state.get("excluded_ids") or []),
            "qty_overrides": dict(state.get("qty_overrides") or {}),
            "query_overrides": dict(state.get("query_overrides") or {}),
            "max_budget_cents": state.get("max_budget_cents"),
            "known_shops": [c["shop_domain"] for c in kit["merchant_carts"]],
        },
    }

    if rd is not None and rd.exists() and not payload.get("extra_items"):
        try:
            write_json(rd / "commerce_kit.json", out)
        except Exception:
            pass

    return out


@router.get("/kit/{run_id}")
def get_commerce_kit(
    run_id: str,
    tier: str = Query("standard"),
    postal_code: str = Query("10001"),
    verify: bool = Query(True),
    include_comps: bool = Query(True),
) -> dict[str, Any]:
    return post_commerce_kit({
        "run_id": run_id,
        "tier": tier,
        "postal_code": postal_code,
        "verify_with_decisions": verify,
        "include_comps": include_comps,
    })


@router.post("/agent")
def post_commerce_agent(body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = body or {}
    msg = str(payload.get("message") or "").strip()
    if not msg:
        raise HTTPException(400, "message is required")

    rid, inv, plan, rd = _resolve_run_context(
        payload.get("run_id"),
        inline_inv=payload.get("inventory"),
        inline_plan=payload.get("plan"),
        extra_items=payload.get("extra_items"),
    )
    dest = _dest_from_postal(payload.get("postal_code"), payload.get("region"))
    res = commerce.run_shopping_agent(
        msg,
        inv,
        plan,
        current_state=payload.get("state"),
        destination=dest,
        run_dir=rd,
    )
    return {"run_id": rid, **res}


@router.post("/search")
def post_commerce_search(body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = body or {}
    q = str(payload.get("query") or "").strip()
    if not q:
        raise HTTPException(400, "query is required")
    dest = _dest_from_postal(payload.get("postal_code"), payload.get("region"))
    max_usd = payload.get("max_price_usd")
    max_cents = int(round(float(max_usd) * 100)) if max_usd is not None else None
    limit = max(1, min(12, int(payload.get("limit") or 6)))

    client = commerce.ShopMCPClient()
    try:
        res = client.search_catalog(q, destination=dest, max_price_cents=max_cents, limit=limit)
    except commerce.ShopMCPError as exc:
        raise HTTPException(502, str(exc))

    need_stub = {"qty_needed": max(1, int(payload.get("qty") or 1)), "default_unit_est_cents": 1500}
    offers = commerce._normalize_catalog_offers(res.get("products") or [], need_stub)
    return {
        "query": q,
        "destination": dest,
        "offers": offers,
        "next": res.get("next") or [],
    }
