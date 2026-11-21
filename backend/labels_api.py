"""FastAPI routes for Stage B10 Offline QR Box Labels & Stretch A6 Photo Box Matcher.

Mount in `backend/app.py`:
    from backend.labels_api import router as labels_router
    app.include_router(labels_router)

Routes:
  GET  /labels/{run_id}                 JSON bundle of all box labels + inline SVG QRs
  GET  /labels/{run_id}/{box_id}/qr.png High-contrast PNG QR code for a single box
  POST /labels/{run_id}/identify        Upload box photo -> Hydrogen + Decision 1 match
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from backend import labels
from backend.ingest.common import run_dir

router = APIRouter(tags=["labels"])


@router.get("/labels/{run_id}")
def get_labels(run_id: str, include_furniture: bool = Query(False)) -> dict[str, Any]:
    try:
        return labels.labels_for_run(run_id, include_furniture_tags=include_furniture)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/labels/{run_id}/{box_id}/qr.png")
def get_label_qr_png(run_id: str, box_id: str, include_furniture: bool = Query(True)) -> Response:
    try:
        bundle = labels.labels_for_run(run_id, include_furniture_tags=include_furniture)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))

    match = next(
        (b for b in bundle["labels"] if b["box_id"] == box_id or b["short_name"].lower() == box_id.lower()),
        None,
    )
    if match is None:
        raise HTTPException(404, f"no box {box_id!r} in run {run_id!r}")
    png = labels.qr_png_bytes(match["qr_text"])
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=3600"})


@router.post("/labels/{run_id}/identify")
async def post_identify_box(
    run_id: str,
    file: UploadFile = File(...),
    hint: str = Form(""),
) -> dict[str, Any]:
    try:
        bundle = labels.labels_for_run(run_id, include_furniture_tags=False)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(400, "uploaded photo is empty")

    rd = None
    if run_id not in ("sample_venue", "sample", "mock-demo"):
        try:
            cand = run_dir(run_id)
            if cand.exists():
                rd = cand
        except ValueError:
            pass

    try:
        return labels.identify_box_from_photo(
            raw_bytes,
            file.content_type or "image/jpeg",
            bundle["labels"],
            run_dir_path=rd,
            hint_text=hint,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
