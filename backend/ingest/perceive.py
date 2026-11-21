"""Stage 2: perceive. One `perceive` model call per photo or clip, in parallel.

Writes runs/<run_id>/perception/<file>.json for each file.
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from backend import catalog
from backend.llm import LLMError, Media, for_job

from .common import read_json, run_dir, update_status, write_json
from .schemas import PERCEPTION_SCHEMA

PROMPT_VERSION = "perceive_v1"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / f"{PROMPT_VERSION}.md"
MAX_PARALLEL = 6


def _fmt(v) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


def catalog_table() -> str:
    rows = [r for r in catalog.load().values() if r.get("category") != "box"]
    return "\n".join(f"{r['catalog_id']} | {r['name']} | {_fmt(r['length_in'])}x{_fmt(r['width_in'])}x{_fmt(r['height_in'])}"
                     for r in rows)


def build_prompt(entry: dict) -> str:
    tpl = PROMPT_PATH.read_text(encoding="utf-8")
    if entry["kind"] == "video":
        media_desc = f"a {entry.get('duration_s') or 0:.0f}-second video walking through one room"
        video_rule = ("This is a video: the camera may pass the same item more than once. Count each physical item once "
                      "across the whole clip.")
        frame_word = "video frame"
        ts_rule = " `timestamp_s` is the time in seconds where the item is clearest."
    else:
        media_desc = "a photo of one room"
        video_rule = "Count only what is in this photo."
        frame_word = "image"
        ts_rule = " Leave out `timestamp_s` for a photo."
    return (tpl.replace("{media_desc}", media_desc).replace("{catalog}", catalog_table())
            .replace("{video_rule}", video_rule).replace("{frame_word}", frame_word)
            .replace("{timestamp_rule}", ts_rule))


def clean_label(label: str) -> str:
    """Keep labels short: the model sometimes leaks its reasoning into them."""
    label = " ".join(label.split()).rstrip(".")
    if len(label) > 60:
        label = re.split(r"\s*\(|\s-\s|;", label)[0].strip() or label[:60]
    return label[:80]


def media_for(rd: Path, entry: dict) -> Media:
    return Media(rd / entry["path"], entry["kind"], entry["mime"], entry["sha256"])


def perceive_file(run_id: str, entry: dict, job_name: str = "perceive") -> dict:
    rd = run_dir(run_id)
    name = entry["name"]
    update_status(rd, files={name: {"perceive": "running"}})
    t0 = time.time()
    job = for_job(job_name, run_dir=rd)
    try:
        out = job.generate_json(build_prompt(entry), media=[media_for(rd, entry)], schema=PERCEPTION_SCHEMA,
                                prompt_version=PROMPT_VERSION, label=name)
    except LLMError as e:
        update_status(rd, files={name: {"perceive": "failed", "error": str(e)[:300]}}, error=f"perceive {name}: {e}")
        raise
    known = catalog.load()
    for it in out["items"]:
        it["label"] = clean_label(it["label"])
        if it["catalog_id"] != "unknown" and it["catalog_id"] not in known:
            it.setdefault("notes", f"model gave unknown catalog id {it['catalog_id']!r}")
            it["catalog_id"] = "unknown"
        if entry["kind"] == "image":
            it["evidence"].pop("timestamp_s", None)
    result = {"file": name, "sha256": entry["sha256"], "kind": entry["kind"], "room_id": entry["room_id"],
              "model": job.spec, "prompt_version": PROMPT_VERSION, **out}
    write_json(rd / "perception" / f"{name}.json", result)
    update_status(rd, files={name: {"perceive": "done", "items": len(out["items"]),
                                    "seconds": round(time.time() - t0, 1)}})
    return result


def perceive_all(run_id: str, room_id: str | None = None, job_name: str = "perceive",
                 on_file_done=None) -> list[dict]:
    """Perceive every file in the manifest (optionally one room). Clips go first: their upload is the slow part."""
    rd = run_dir(run_id)
    manifest = read_json(rd / "manifest.json")
    entries = [f for f in manifest["files"] if room_id is None or f["room_id"] == room_id]
    entries.sort(key=lambda f: f["kind"] != "video")
    update_status(rd, stage="perceive")
    results, failed = [], []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futs = {pool.submit(perceive_file, run_id, e, job_name): e for e in entries}
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except LLMError:
                failed.append(futs[fut]["name"])
                continue
            if on_file_done:
                try:
                    on_file_done(results[-1])
                except Exception as e:  # a partial rebuild must not stop the run
                    update_status(rd, error=f"partial rebuild after {results[-1]['file']}: {e}")
    update_status(rd, stage="perceive_done", perceive_failed=failed)
    return sorted(results, key=lambda r: r["file"])
