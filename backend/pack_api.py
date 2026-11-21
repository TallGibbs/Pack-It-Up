"""Track B HTTP routes: 3D truck + Penn Station store packing, verification & video stills.

Mounted by `backend/app.py` alongside Track A's `ingest_router`.

Routes:
  GET  /trucks                           Available U-Haul trucks and Penn Station store zones
  POST /solve                            {run_id?, inventory?, strategy?, extra_items?} -> placement JSON
  GET  /solve/{run_id}                   Convenience GET solve for a run_id (or 'sample_venue' / 'mock-demo')
  GET  /destination-media                Available destination photos/clips in data/NYPenn/
  GET  /destination-media/{slot}/still   JPEG video frame / photo still for destination room/zone
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from backend import catalog, solver
from backend.ingest.common import read_json, run_dir, write_json
from backend.llm import media as mu

router = APIRouter(tags=["pack"])

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_VENUE_PATH = REPO_ROOT / "data" / "sample_venue.json"
MOCK_INV_PATH = REPO_ROOT / "frontend" / "mock" / "inventory.json"
NYPENN_DIR = REPO_ROOT / "data" / "NYPenn"


def _list_nypenn_files() -> list[Path]:
    if not NYPENN_DIR.exists():
        return []
    allowed = set(mu.IMAGE_EXT) | set(mu.VIDEO_EXT)
    return sorted(
        p for p in NYPENN_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in allowed
    )


def _compute_dest_corner(pos_in: list[float], size_in: list[float], zone_dims: list[float]) -> str:
    """Human-readable room corner/wall label inside `[L, W, H]` destination room."""
    L = max(1.0, float(zone_dims[0]))
    W = max(1.0, float(zone_dims[1]))
    cx = (float(pos_in[0]) + 0.5 * float(size_in[0])) / L  # 0 = back wall, 1 = front doorway wall
    cy = (float(pos_in[1]) + 0.5 * float(size_in[1])) / W  # 0 = left wall, 1 = right wall

    depth_lbl = "Back" if cx < 0.36 else ("Front" if cx > 0.66 else "Mid")
    side_lbl = "Left" if cy < 0.36 else ("Right" if cy > 0.64 else "Center")

    if depth_lbl == "Mid" and side_lbl == "Center":
        return "Center Floor"
    if depth_lbl == "Mid":
        return f"{side_lbl} Wall"
    if side_lbl == "Center":
        return "Back Wall" if depth_lbl == "Back" else "Front Entrance"
    return f"{depth_lbl}-{side_lbl} Corner"


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


def _enrich_media_and_corners(rid: str, inv: dict[str, Any], plan: dict[str, Any]) -> None:
    """Attach source video evidence, room stills, truck source->dest links, and room corners."""
    manifest_by_name: dict[str, dict[str, Any]] = {}
    if rid not in ("inline", "sample_venue", "mock-demo"):
        try:
            rd = run_dir(rid)
            manifest = read_json(rd / "manifest.json") or {}
            for f in manifest.get("files", []):
                if f.get("name"):
                    manifest_by_name[f["name"]] = f
        except Exception:
            pass

    # Map file name -> sha256/kind from either manifest or item evidence
    file_meta: dict[str, dict[str, Any]] = {}
    for name, mf in manifest_by_name.items():
        file_meta[name] = {"sha256": mf.get("sha256"), "kind": mf.get("kind")}

    for rb in inv.get("rooms", []):
        for it in rb.get("items", []):
            ev = it.get("evidence") or {}
            src = ev.get("source")
            if src and ev.get("sha256") and src not in file_meta:
                file_meta[src] = {"sha256": ev.get("sha256"), "kind": ev.get("kind")}

    def _norm_ev(ev: dict[str, Any] | None, fallback_files: list[str]) -> dict[str, Any] | None:
        if not ev and not fallback_files:
            return None
        out = dict(ev or {})
        src = out.get("source") or (fallback_files[0] if fallback_files else None)
        if not src:
            return None
        out["source"] = src
        fm = file_meta.get(src) or {}
        if not out.get("sha256") and fm.get("sha256"):
            out["sha256"] = fm["sha256"]
        if not out.get("kind"):
            ext = Path(src).suffix.lower()
            out["kind"] = fm.get("kind") or ("video" if ext in mu.VIDEO_EXT else "image")
        if out["kind"] == "video" and out.get("timestamp_s") is None:
            out["timestamp_s"] = 2.5
        return out

    source_ev_by_id: dict[str, dict[str, Any]] = {}
    room_stills: list[dict[str, Any]] = []

    for r_idx, rb in enumerate(inv.get("rooms", []), start=1):
        r_meta = rb.get("room") or {}
        room_id = r_meta.get("id") or f"room_{r_idx}"
        room_name = r_meta.get("name") or room_id
        r_files = list(rb.get("files") or [])

        best_room_ev: dict[str, Any] | None = None
        sample_boxes: list[dict[str, Any]] = []

        for it in rb.get("items", []):
            nev = _norm_ev(it.get("evidence"), r_files)
            if nev:
                source_ev_by_id[it["id"]] = nev
                if best_room_ev is None or (nev.get("kind") == "video" and best_room_ev.get("kind") != "video"):
                    best_room_ev = nev
                if nev.get("box_2d") and len(sample_boxes) < 4:
                    sample_boxes.append({"label": it.get("label", ""), "box_2d": nev["box_2d"]})

        for c in rb.get("containers", []):
            cid = c.get("id")
            nev = _norm_ev(c.get("evidence"), c.get("seen_in") or r_files)
            if cid and nev:
                source_ev_by_id[cid] = nev

        if best_room_ev is None and r_files:
            best_room_ev = _norm_ev({"source": r_files[0]}, r_files)

        room_stills.append({
            "room_id": room_id,
            "room_name": room_name,
            "files": r_files,
            "evidence": best_room_ev,
            "sample_detections": sample_boxes,
        })

    room_still_by_id = {rs["room_id"]: rs for rs in room_stills}

    # Check if real Penn Station destination media exists in data/NYPenn/
    nypenn_files = _list_nypenn_files()

    # Map piece_id -> destination corner from zones[]
    piece_corner_map: dict[str, str] = {}
    for z_idx, z in enumerate(plan.get("zones", [])):
        z_dims = z.get("dims_in") or [180.0, 120.0, 96.0]
        if nypenn_files:
            chosen_file = nypenn_files[z_idx % len(nypenn_files)]
            is_vid = chosen_file.suffix.lower() in mu.VIDEO_EXT
            t_sec = round(1.0 + (z_idx * 1.7) % 6.0, 1) if is_vid else None
            q = f"?t={t_sec}&size=640" if t_sec is not None else "?size=640"
            z["dest_still"] = {
                "url": f"/destination-media/{z_idx % len(nypenn_files)}/still{q}",
                "source": chosen_file.name,
                "kind": "video" if is_vid else "image",
                "timestamp_s": t_sec,
            }
        else:
            z["dest_still"] = None

        corner_counts: dict[str, int] = {}
        src_rooms_in_zone: dict[str, int] = {}
        for zit in z.get("items", []):
            corner = _compute_dest_corner(zit.get("pos_in") or [0, 0, 0], zit.get("size_in") or [18, 18, 16], z_dims)
            zit["dest_corner"] = corner
            piece_corner_map[zit.get("piece_id", zit["id"])] = corner
            corner_counts[corner] = corner_counts.get(corner, 0) + 1
            rid_it = zit.get("room_id") or "room_1"
            src_rooms_in_zone[rid_it] = src_rooms_in_zone.get(rid_it, 0) + 1
            ev = source_ev_by_id.get(zit.get("source_id", ""))
            if ev:
                zit["evidence"] = ev

        z["corners_summary"] = [
            {"corner": k, "count": n}
            for k, n in sorted(corner_counts.items(), key=lambda kv: -kv[1])
        ]
        z["sourced_from_rooms"] = [
            {
                "room_id": rk,
                "room_name": (room_still_by_id.get(rk) or {}).get("room_name", rk),
                "count": rn,
                "evidence": (room_still_by_id.get(rk) or {}).get("evidence"),
            }
            for rk, rn in sorted(src_rooms_in_zone.items(), key=lambda kv: -kv[1])
        ]

    zone_by_id = {z["zone_id"]: z for z in plan.get("zones", [])}

    # Enrich trucks[].items[] and build per-truck source_rooms & dest_zones summaries
    for t in plan.get("trucks", []):
        src_tally: dict[str, dict[str, Any]] = {}
        dst_tally: dict[str, dict[str, Any]] = {}
        for it in t.get("items", []):
            ev = source_ev_by_id.get(it.get("source_id", ""))
            if ev:
                it["evidence"] = ev
            corner = piece_corner_map.get(it.get("piece_id", it["id"])) or "Center Floor"
            it["dest_corner"] = corner

            rm_id = it.get("room_id") or "room_1"
            rm_entry = src_tally.setdefault(rm_id, {
                "room_id": rm_id,
                "room_name": it.get("room_name") or rm_id,
                "item_count": 0,
                "box_count": 0,
                "weight_lb": 0.0,
                "evidence": (room_still_by_id.get(rm_id) or {}).get("evidence") or ev,
                "sample_detections": (room_still_by_id.get(rm_id) or {}).get("sample_detections") or [],
            })
            rm_entry["item_count"] += 1
            if it.get("is_box"):
                rm_entry["box_count"] += 1
            rm_entry["weight_lb"] = round(rm_entry["weight_lb"] + float(it.get("weight_lb") or 0), 1)

            zid = it.get("dest_zone") or "penn_concourse"
            z_obj = zone_by_id.get(zid) or {}
            dz_entry = dst_tally.setdefault(zid, {
                "zone_id": zid,
                "name": it.get("dest_zone_name") or z_obj.get("name") or zid,
                "dock_stop": it.get("dock_stop") or z_obj.get("dock_stop") or 6,
                "item_count": 0,
                "corners": {},
                "dest_still": z_obj.get("dest_still"),
            })
            dz_entry["item_count"] += 1
            dz_entry["corners"][corner] = dz_entry["corners"].get(corner, 0) + 1

        t["source_rooms"] = sorted(src_tally.values(), key=lambda x: -x["item_count"])
        t["dest_zones"] = sorted(dst_tally.values(), key=lambda x: x["dock_stop"])

    plan["room_stills"] = room_stills


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


@router.get("/destination-media")
def list_destination_media() -> dict[str, Any]:
    files = _list_nypenn_files()
    return {
        "count": len(files),
        "files": [
            {
                "slot": idx,
                "name": p.name,
                "kind": "video" if p.suffix.lower() in mu.VIDEO_EXT else "image",
                "still_url": f"/destination-media/{idx}/still",
            }
            for idx, p in enumerate(files)
        ],
    }


@router.get("/destination-media/{slot}/still")
def get_destination_still(
    slot: int,
    t: float | None = Query(1.5, ge=0),
    size: int = Query(640, ge=64, le=1920),
) -> Response:
    files = _list_nypenn_files()
    if not files:
        raise HTTPException(404, "no media files in data/NYPenn")
    chosen = files[slot % len(files)]
    kind = "video" if chosen.suffix.lower() in mu.VIDEO_EXT else "image"
    jpg = mu.crop_jpeg(chosen, kind, None, t if kind == "video" else None, max_side=size)
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


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
    _enrich_media_and_corners(rid, inv_to_solve, plan)

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
