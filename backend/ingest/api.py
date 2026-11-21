"""Track A HTTP routes. Mounted by backend/app.py.

POST /upload                          multipart files + room (+ run_id to add a room) -> {run_id}
GET  /runs/{run_id}                   stage status per file, then inventory and questions
GET  /inventory/{run_id}              inventory.json
POST /answer/{run_id}                 {question_id, answer} -> updated inventory
PATCH /inventory/{run_id}/items/{id}  {quantity?, disposition?, catalog_id?} -> updated inventory
GET  /media/{run_id}/{file_hash}/crop?box=ymin,xmin,ymax,xmax&t=4.0  -> JPEG crop
"""
from __future__ import annotations

import shutil
import threading
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from backend.llm import media as mu

from . import gaps
from .common import new_run_id, read_json, run_dir
from .intake import ACCEPTED, intake
from .pipeline import rebuild, run_pipeline

router = APIRouter(tags=["ingest"])


def _rd(run_id: str) -> Path:
    try:
        rd = run_dir(run_id)
    except ValueError:
        raise HTTPException(400, "bad run id")
    if not rd.exists():
        raise HTTPException(404, f"no run {run_id}")
    return rd


@router.post("/upload")
async def upload(files: list[UploadFile] = File(...), room: str = Form("room_1"), run_id: str | None = Form(None)):
    run_id = run_id or new_run_id(room)
    try:
        rd = run_dir(run_id)
    except ValueError:
        raise HTTPException(400, "bad run id")
    up = rd / "uploads"
    up.mkdir(parents=True, exist_ok=True)
    paths, names = [], {}
    for f in files:
        name = Path(f.filename or "upload").name
        if Path(name).suffix.lower() not in ACCEPTED:
            continue
        dst = up / name
        with open(dst, "wb") as out:
            shutil.copyfileobj(f.file, out)
        paths.append(dst)
        names[dst] = name
    if not paths:
        raise HTTPException(400, f"no accepted media; accepted types: {sorted(ACCEPTED)}")
    manifest = intake(paths, room, run_id, names)
    room_id = next(r["id"] for r in manifest["rooms"] if r["name"] == room)
    threading.Thread(target=run_pipeline, args=(run_id, room_id), daemon=True).start()
    return {"run_id": run_id, "room_id": room_id, "files": [f["name"] for f in manifest["files"] if f["room_id"] == room_id],
            "skipped": manifest["skipped"]}


@router.get("/runs/{run_id}")
def run_status(run_id: str):
    rd = _rd(run_id)
    status = read_json(rd / "status.json", {})
    out = {"run_id": run_id, "status": status}
    inv = read_json(rd / "inventory.json")
    if inv is not None:
        out["inventory"] = inv
        out["partial"] = status.get("stage") != "done"
        out["questions"] = [q for q in inv.get("questions", []) if q.get("status") == "open"]
    return out


@router.get("/inventory/{run_id}")
def get_inventory(run_id: str):
    inv = read_json(_rd(run_id) / "inventory.json")
    if inv is None:
        raise HTTPException(409, "inventory not ready yet; poll GET /runs/{run_id}")
    return inv


@router.post("/answer/{run_id}")
def answer(run_id: str, body: dict):
    _rd(run_id)
    qid, ans = body.get("question_id"), body.get("answer")
    if not qid or ans is None:
        raise HTTPException(400, "body needs question_id and answer")
    try:
        gaps.answer_question(run_id, qid, ans, source="user")
    except KeyError:
        raise HTTPException(404, f"no question {qid}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return rebuild(run_id)


@router.patch("/inventory/{run_id}/items/{item_id}")
def patch_item(run_id: str, item_id: str, body: dict):
    _rd(run_id)
    try:
        gaps.edit_item(run_id, item_id, body)
    except KeyError:
        raise HTTPException(404, f"no item {item_id}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return rebuild(run_id)


@router.get("/media/{run_id}/{file_hash}/crop")
def crop(run_id: str, file_hash: str, box: str | None = Query(None), t: float | None = Query(None),
         size: int = Query(512, ge=64, le=2048)):
    rd = _rd(run_id)
    manifest = read_json(rd / "manifest.json") or {"files": []}
    entry = next((f for f in manifest["files"] if f["sha256"].startswith(file_hash) and len(file_hash) >= 8), None)
    if entry is None:
        raise HTTPException(404, "no such file in this run")
    box_2d = None
    if box:
        try:
            box_2d = [int(float(v)) for v in box.split(",")]
            assert len(box_2d) == 4
        except Exception:
            raise HTTPException(400, "box must be ymin,xmin,ymax,xmax on a 0-1000 scale")
    jpg = mu.crop_jpeg(rd / entry["path"], entry["kind"], box_2d, t, max_side=size)
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})
