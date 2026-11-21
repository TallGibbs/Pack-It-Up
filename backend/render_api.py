"""HTTP routes for Element 119 Media-Out & Vinny NYC Foreman TTS (`render.py` + `foreman.py`).

Routes:
  POST /render                       Generate Nano Banana 2.1 Before/After Penn Station arrival render
  POST /render/arrival               Same as POST /render
  POST /render/timelapse/start       Launch (or serve cached) Gemini Omni 1.2 Flash 6s time-lapse MP4
  GET  /render/timelapse/{job_id}    Poll Omni Flash video transition status
  POST /render/foreman               Synthesize 15s Vinny + ARIA multi-speaker crew radio WAV
  GET  /render/asset/{filename}      Serve generated PNG / WAV / MP4 media assets
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend import foreman, render, solver
from backend.ingest.common import run_dir
from backend.pack_api import _load_inventory_for_run

router = APIRouter(tags=["render"])

_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
}


class RenderArrivalRequest(BaseModel):
    run_id: str | None = None
    plan: dict[str, Any] | None = None
    inventory: dict[str, Any] | None = None
    zone_focus: str | None = None


class TimelapseStartRequest(BaseModel):
    before_asset: str
    after_asset: str
    run_id: str | None = None
    duration_s: int = 6


class ForemanBriefRequest(BaseModel):
    run_id: str | None = None
    plan: dict[str, Any] | None = None
    inventory: dict[str, Any] | None = None


@router.post("/render")
@router.post("/render/arrival")
def api_render_arrival(req: RenderArrivalRequest) -> dict[str, Any]:
    inv = req.inventory
    rid = (req.run_id or "sample_venue").strip()
    if inv is None and req.plan is None:
        rid, inv = _load_inventory_for_run(rid)
    try:
        return render.render_arrival(
            run_id=rid,
            plan=req.plan,
            inventory=inv,
            zone_focus=req.zone_focus,
        )
    except Exception as e:
        raise HTTPException(500, f"Arrival render failed: {e}") from e


@router.post("/render/timelapse/start")
def api_timelapse_start(req: TimelapseStartRequest) -> dict[str, Any]:
    try:
        return render.start_timelapse_job(
            before_asset=req.before_asset,
            after_asset=req.after_asset,
            run_id=req.run_id,
            duration_s=req.duration_s,
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Timelapse start failed: {e}") from e


@router.get("/render/timelapse/{job_id}")
def api_timelapse_status(job_id: str) -> dict[str, Any]:
    st = render.get_timelapse_job(job_id)
    if st is None:
        raise HTTPException(404, f"Unknown timelapse job {job_id}")
    return st


@router.post("/render/foreman")
def api_foreman_briefing(req: ForemanBriefRequest) -> dict[str, Any]:
    rid = (req.run_id or "sample_venue").strip()
    rd: Path | None = None
    if rid not in ("", "sample_venue", "sample", "mock-demo", "inline"):
        try:
            cand = run_dir(rid)
            if cand.exists():
                rd = cand
        except ValueError:
            rd = None

    plan = req.plan
    inv = req.inventory
    if plan is None:
        if inv is None:
            rid, inv = _load_inventory_for_run(rid)
        plan = solver.solve(inv)
    return foreman.generate_foreman_briefing(plan=plan, inventory=inv, run_dir=rd)


@router.get("/render/asset/{filename}")
def api_render_asset(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        raise HTTPException(400, "Invalid asset filename")
    path = (render.RENDER_DIR / safe_name).resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(404, f"Asset {safe_name} not found")
    mime = _MIME_BY_EXT.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "public, max-age=3600"})
