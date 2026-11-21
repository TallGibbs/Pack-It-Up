"""Stage 2: perceive. One `perceive` model call per photo or clip, in parallel.

Writes runs/<run_id>/perception/<file>.json for each file.
"""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from backend import catalog
from backend.llm import LLMError, Media, for_job

from .common import read_json, run_dir, update_status, write_json
from .schemas import PERCEPTION_SCHEMA, SEAT_CLASS_CATALOG

PROMPT_VERSION = "perceive_v3"
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
            .replace("{timestamp_rule}", ts_rule).replace("{audio_rules}", audio_rules(entry)))


AUDIO_RULES_CLIP = """Listen to the soundtrack as well as watching the frames.

- `transcript`: every stretch of speech, with start and end times in seconds. Mark `speaker` as `narrator` for the person filming (closest to the microphone, talking about this room) and `background` for anyone else: people talking nearby, announcements, music, phone calls.
- `spoken_facts`: only from the narrator, and only for things said that change what has to be moved or how. Ignore background speech completely, even if it mentions furniture. General commentary ("this is the lounge", "let's take inventory") is not a fact.
  - `kind`: `disposition` (keep, sell, donate, trash), `not_moving` (stays behind or belongs to someone else: set `disposition: stays`), `contents` (what is inside or on it and how full: set `contents` and `fullness`), `count` (set `count`), `fragile`, `size` (set `size_in` in inches and `size_dim`), `identity` (what something really is: set `label` and the closest `catalog_id`), `unfilmed_item` (named but never on camera), `other`.
  - `quote`: the narrator's exact words. `timestamp_s`: when they were said. `value`: a short normalised summary.
  - `refers_to`: `item:<n>` or `container:<n>`, the 0-based index into your own `items` or `containers` list. When the narrator says "this one" or "that shelf", link to what is on screen at that moment. Use `none` only when nothing fits.
- An item the narrator names that never appears on camera ("there's a piano in the back room") goes into `items` with `heard_only: true`, `confidence` reflecting how clearly it was said, `est_dims_in` from typical sizes, and an `unfilmed_item` fact pointing at it. Every other item has `heard_only: false`.
- Speech never deletes an item: an item the narrator says is staying is still listed, with a `not_moving` fact.
- If nobody speaks, or only background voices, return empty `transcript` and `spoken_facts` lists."""

AUDIO_RULES_PHOTO = ("This is a photo: there is no audio. Return empty `transcript` and `spoken_facts` lists and set "
                     "`heard_only: false` on every item.")


def audio_rules(entry: dict) -> str:
    if entry["kind"] == "video" and entry.get("has_audio", True):
        return AUDIO_RULES_CLIP
    if entry["kind"] == "video":
        return "This clip has no soundtrack. " + AUDIO_RULES_PHOTO.split(": there is no audio. ")[1]
    return AUDIO_RULES_PHOTO


def parse_ref(ref: str | None) -> tuple[str, int] | None:
    """'item:3' -> ('item', 3); anything else -> None."""
    m = re.fullmatch(r"\s*(item|container)\s*[:#]?\s*(\d+)\s*", str(ref or ""))
    return (m.group(1), int(m.group(2))) if m else None


def check_facts(out: dict, entry: dict) -> list[dict]:
    """Keep only narrator facts from clips, with a quote and a reference that exists (or none)."""
    if entry["kind"] != "video":
        return []
    kept = []
    for f in out.get("spoken_facts", []):
        if not f.get("quote", "").strip():
            continue
        ref = parse_ref(f.get("refers_to"))
        if ref:
            kind, idx = ref
            pool = out["items"] if kind == "item" else out.get("containers", [])
            if idx >= len(pool):
                f["refers_to"], f["ref_error"] = "none", f"index {idx} out of range"
        else:
            f["refers_to"] = "none"
        kept.append(f)
    return kept


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
        # Upholstered seating is grouped and sized by seat count: the class decides the catalog row.
        sc = it.get("seat_class", "none")
        if sc in SEAT_CLASS_CATALOG and not (sc == "single_seat" and it["catalog_id"] == "recliner"):
            it["catalog_id"] = SEAT_CLASS_CATALOG[sc]
        if it["catalog_id"] != "unknown" and it["catalog_id"] not in known:
            it.setdefault("notes", f"model gave unknown catalog id {it['catalog_id']!r}")
            it["catalog_id"] = "unknown"
        if entry["kind"] == "image":
            it["evidence"].pop("timestamp_s", None)
    out["spoken_facts"] = check_facts(out, entry)
    if entry["kind"] != "video":
        out["transcript"] = []
    result = {"file": name, "sha256": entry["sha256"], "kind": entry["kind"], "room_id": entry["room_id"],
              "model": job.spec, "prompt_version": PROMPT_VERSION, **out}
    write_json(rd / "perception" / f"{name}.json", result)
    if entry["kind"] == "video":  # git-ignored with the run: transcripts can hold bystanders' words
        write_json(rd / "transcripts" / f"{name}.json", {"file": name, "has_audio": entry.get("has_audio"),
                                                          "transcript": out["transcript"],
                                                          "spoken_facts": out["spoken_facts"]})
    update_status(rd, files={name: {"perceive": "done", "items": len(out["items"]),
                                    "seconds": round(time.time() - t0, 1)}})
    return result


# Files a pipeline in this process is reading right now, per run. See perceive_all(only_new=True).
_reading: dict[str, set[str]] = defaultdict(set)
_reading_guard = threading.Lock()


def perceive_all(run_id: str, room_id: str | None = None, job_name: str = "perceive",
                 on_file_done=None, only_new: bool = False) -> list[dict]:
    """Perceive every file in the manifest (optionally one room). Clips go first: their upload is the slow part.

    `only_new` is for the upload route. Each upload to a room starts its own pipeline, and without it
    a second upload (three photos after a clip, or a retry) read the room's earlier files again: a
    second model call for a clip still being watched, and finished rows going back to "looking".
    With it, a file already read, or being read by another pipeline, is left alone.
    """
    rd = run_dir(run_id)
    manifest = read_json(rd / "manifest.json")
    entries = [f for f in manifest["files"] if room_id is None or f["room_id"] == room_id]
    if only_new:
        with _reading_guard:
            seen = (read_json(rd / "status.json", {}) or {}).get("files", {})
            entries = [f for f in entries if f["name"] not in _reading[run_id]
                       and not (seen.get(f["name"], {}).get("perceive") == "done"
                                and (rd / "perception" / f"{f['name']}.json").exists())]
            _reading[run_id].update(f["name"] for f in entries)
    entries.sort(key=lambda f: f["kind"] != "video")
    update_status(rd, stage="perceive")
    results, failed = [], []
    try:
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
    finally:
        if only_new:
            with _reading_guard:
                _reading[run_id].difference_update(f["name"] for f in entries)
    update_status(rd, stage="perceive_done", perceive_failed=failed)
    return sorted(results, key=lambda r: r["file"])
