"""Track A HTTP routes. Mounted by backend/app.py.

POST /upload                          multipart files + room (+ run_id to add to that run) -> {run_id}
GET  /runs/{run_id}                   rooms, stage status per file, then inventory and questions
GET  /inventory/{run_id}              inventory.json
POST /answer/{run_id}                 {question_id, answer} -> updated inventory
PATCH /inventory/{run_id}/items/{id}  {quantity?, disposition?, catalog_id?} -> updated inventory
POST /inventory/{run_id}/items        {room, catalog_id, quantity, label?} or {room, label, dims_in, quantity}
                                      -> updated inventory, with the added item marked source "user_added"
GET  /catalog                         items the "Add an item" list offers: {items: [{id, name, category, dims_in}]}
GET  /media/{run_id}/{file_hash}/crop?box=ymin,xmin,ymax,xmax&t=4.0  -> JPEG crop
GET  /media/{run_id}/{file_hash}/audio?start=2.5&end=3.8           -> MP3 of a quote
"""
from __future__ import annotations

import shutil
import threading
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from backend import catalog
from backend.llm import media as mu

from . import gaps
from .common import new_run_id, read_json, run_dir, slug
from .intake import ACCEPTED, intake
from .pipeline import begin_pipeline, end_pipeline, rebuild, run_lock, run_pipeline

router = APIRouter(tags=["ingest"])

# One upload at a time per run: intake reads, changes and rewrites manifest.json. Separate from
# run_lock, which rebuild() can hold for many seconds while questions are being answered.
_intake_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


def _rd(run_id: str) -> Path:
    try:
        rd = run_dir(run_id)
    except ValueError:
        raise HTTPException(400, "bad run id")
    if not rd.exists():
        raise HTTPException(404, f"no run {run_id}")
    return rd


# A plain `def`, not `async def`: copying, hashing and audio extraction block, and FastAPI runs a
# plain route in a worker thread, so one phone's large clip doesn't freeze everyone else's polling.
@router.post("/upload")
def upload(files: list[UploadFile] = File(...), room: str = Form("room_1"), run_id: str | None = Form(None)):
    run_id = run_id or new_run_id(room)
    try:
        rd = run_dir(run_id)
    except ValueError:
        raise HTTPException(400, "bad run id")
    up = rd / "uploads"
    room_id = slug(room or "room_1")  # the id intake() files this room under, whatever name it was first given
    begin_pipeline(run_id)  # before intake, so a pipeline ending meanwhile can't mark the run done
    try:
        with _intake_locks[run_id]:
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
    except BaseException:
        end_pipeline(run_id)
        raise
    threading.Thread(target=run_pipeline, args=(run_id, room_id), kwargs={"counted": True}, daemon=True).start()
    return {"run_id": run_id, "room_id": room_id, "files": [f["name"] for f in manifest["files"] if f["room_id"] == room_id],
            "skipped": manifest["skipped"]}


@router.get("/runs/{run_id}")
def run_status(run_id: str):
    rd = _rd(run_id)
    status = read_json(rd / "status.json", {})
    manifest = read_json(rd / "manifest.json") or {}
    # rooms: [{id, name}] in upload order, so a page can rebuild its room cards before any inventory exists
    out = {"run_id": run_id, "rooms": manifest.get("rooms", []), "status": status}
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
    with run_lock(run_id):  # store and rebuild as one step, so two edits at once can't lose one
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
    with run_lock(run_id):
        try:
            gaps.edit_item(run_id, item_id, body)
        except KeyError:
            raise HTTPException(404, f"no item {item_id}")
        except ValueError as e:
            raise HTTPException(400, str(e))
        return rebuild(run_id)


@router.post("/inventory/{run_id}/items")
def add_item(run_id: str, body: dict):
    """Add something the camera didn't see. See gaps.add_item for the body."""
    _rd(run_id)
    with run_lock(run_id):
        try:
            gaps.add_item(run_id, body)
        except KeyError:
            raise HTTPException(404, f"no room {body.get('room')!r} in this run's inventory yet")
        except ValueError as e:
            raise HTTPException(400, str(e))
        return rebuild(run_id)


@router.get("/catalog")
def get_catalog():
    """What the review page's "Add an item" list offers: every catalog row but the boxes."""
    return {"items": [{"id": r["catalog_id"], "name": r["name"], "category": r["category"],
                       "dims_in": [r["length_in"], r["width_in"], r["height_in"]]}
                      for r in catalog.load().values() if r.get("category") != "box"]}


@router.get("/media/{run_id}/{file_hash}/audio")
def audio(run_id: str, file_hash: str, start: float = Query(..., ge=0), end: float = Query(...)):
    """MP3 of a clip's soundtrack between start and end seconds, to replay a narrator's quote."""
    rd = _rd(run_id)
    manifest = read_json(rd / "manifest.json") or {"files": []}
    entry = next((f for f in manifest["files"] if f["sha256"].startswith(file_hash) and len(file_hash) >= 8), None)
    if entry is None or entry["kind"] != "video" or not entry.get("has_audio"):
        raise HTTPException(404, "no clip with audio for that hash in this run")
    if not 0 < end - start <= 30:
        raise HTTPException(400, "end must be after start, at most 30 s later")
    return Response(mu.audio_clip(rd / entry["path"], start, end), media_type="audio/mpeg")


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
