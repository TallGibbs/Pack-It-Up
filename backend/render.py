"""B9 Element 119 Media-Out: Nano Banana 2.1 Arrival Render + Gemini Omni 1.2 Flash Time-Lapse.

1. `render_arrival()` (`gemini-nano-banana-2.1` via `for_job("image")`):
   - Uses real Penn Station / Moynihan media in `data/NYPenn/` when present; otherwise
     generates & caches a clean 16:9 empty architectural concourse reference frame.
   - Crops up to 5 recognizable items from `runs/<run_id>` (`box_2d`) when available.
   - Fuses the empty Penn Station frame + item crops + solved manifest to render the
     packed items staged inside Penn Station, always marked `illustrative: True`.
2. `start_timelapse_job()` / `render_timelapse()` (`gemini-omni-1.2-flash` via `for_job("video")`):
   - Interpolates between `first_frame` (empty Penn Station) and `last_frame` (Nano Banana 2.1
     staged arrival render) to produce a 6-second 720p 16:9 architectural hyper-lapse MP4.
"""
from __future__ import annotations

import hashlib
import io
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from backend import solver
from backend.ingest.common import read_json, run_dir
from backend.llm import LLMError, Media, for_job, media as mu

ROOT = Path(__file__).resolve().parents[1]
NYPENN_DIR = ROOT / "data" / "NYPenn"
RENDER_DIR = ROOT / ".cache" / "renders"

_JOBS_LOCK = threading.Lock()
_VIDEO_JOBS: dict[str, dict[str, Any]] = {}

EMPTY_PENN_PROMPT = (
    "Wide-angle 16:9 architectural photograph inside Moynihan Train Hall at New York Penn Station. "
    "Sunlight streams through the iconic vaulted steel-and-glass skylight onto polished light-gray "
    "terrazzo concourse floors and a clean, empty open-front limestone retail lounge bay in the foreground. "
    "Unoccupied foreground floor ready for furniture installation, crisp natural daylight, realistic "
    "architectural photography, no text overlays."
)


def _normalize_16x9_png(raw_bytes_or_path: bytes | Path, out_path: Path, size: tuple[int, int] = (1280, 720)) -> Media:
    """Normalize an image to exact 16:9 RGB PNG on disk so Omni Flash keyframes match 1:1."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(raw_bytes_or_path, Path):
        im = mu.load_image(raw_bytes_or_path)
    else:
        im = Image.open(io.BytesIO(raw_bytes_or_path))
        im = ImageOps.exif_transpose(im).convert("RGB")
    fitted = ImageOps.fit(im, size, method=Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    fitted.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    tmp = out_path.with_suffix(f".{threading.get_ident()}.tmp")
    tmp.write_bytes(png_bytes)
    tmp.replace(out_path)
    return Media(out_path, "image", "image/png", hashlib.sha256(png_bytes).hexdigest())


def ensure_empty_penn_frame(rd: Path | None = None) -> tuple[Media, str]:
    """Return `(Media, source_kind)` for Frame 1 (empty Penn Station concourse/bay)."""
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    if NYPENN_DIR.exists():
        allowed = set(mu.IMAGE_EXT) | set(mu.VIDEO_EXT)
        files = sorted(p for p in NYPENN_DIR.iterdir() if p.is_file() and p.suffix.lower() in allowed)
        if files:
            src = files[0]
            h = mu.sha256_file(src)[:16]
            out_png = RENDER_DIR / f"penn_real_before_{h}.png"
            if out_png.exists() and out_png.stat().st_size > 500:
                return Media(out_png, "image", "image/png", mu.sha256_file(out_png)), f"nypenn_media:{src.name}"
            if src.suffix.lower() in mu.VIDEO_EXT:
                dur = mu.video_info(src).get("duration_s") or 4.0
                jpg_tmp = RENDER_DIR / f"penn_frame_{h}.jpg"
                mu.frame_at(src, min(2.0, dur * 0.35)).save(jpg_tmp, "JPEG", quality=90)
                return _normalize_16x9_png(jpg_tmp, out_png), f"nypenn_video:{src.name}"
            return _normalize_16x9_png(src, out_png), f"nypenn_photo:{src.name}"

    cached_base = RENDER_DIR / "penn_moynihan_empty_16x9.png"
    if cached_base.exists() and cached_base.stat().st_size > 1000:
        return (
            Media(cached_base, "image", "image/png", mu.sha256_file(cached_base)),
            "generated_moynihan_base",
        )

    raw_png = for_job("image", rd).generate_image(
        EMPTY_PENN_PROMPT,
        refs=[],
        label="penn_empty_concourse_base",
    )
    return _normalize_16x9_png(raw_png, cached_base), "generated_moynihan_base"


def collect_source_item_crops(run_id: str | None, inv: dict[str, Any], max_crops: int = 5) -> list[Media]:
    """Extract up to `max_crops` item bounding-box crops from `runs/<run_id>` photos/clips."""
    if not run_id or run_id in ("sample_venue", "sample", "mock-demo", "inline"):
        return []
    try:
        rd = run_dir(run_id)
    except ValueError:
        return []
    if not rd.exists():
        return []

    manifest = read_json(rd / "manifest.json") or {}
    path_by_name: dict[str, Path] = {}
    for f in manifest.get("files", []):
        if f.get("name") and f.get("path"):
            p = Path(f["path"])
            if not p.is_absolute():
                p = ROOT / p
            if p.exists():
                path_by_name[f["name"]] = p

    crops: list[Media] = []
    seen_labels: set[str] = set()
    crop_dir = RENDER_DIR / "crops"
    crop_dir.mkdir(parents=True, exist_ok=True)

    for rb in inv.get("rooms", []):
        for it in rb.get("items", []):
            if len(crops) >= max_crops:
                break
            if it.get("disposition") in ("stays", "trash", "sell", "donate"):
                continue
            lbl = str(it.get("label") or "").strip()
            if not lbl or lbl.lower() in seen_labels:
                continue
            ev = it.get("evidence") or {}
            src_name = ev.get("source")
            box = ev.get("box_2d")
            src_path = path_by_name.get(src_name) if src_name else None
            if not src_path or not box or len(box) != 4:
                continue
            try:
                key = hashlib.sha256(f"{src_path}:{box}:{ev.get('timestamp_s')}".encode()).hexdigest()[:16]
                out_crop = crop_dir / f"crop_{key}.jpg"
                if not out_crop.exists():
                    if src_path.suffix.lower() in mu.VIDEO_EXT:
                        src_img = mu.frame_at(src_path, float(ev.get("timestamp_s") or 1.5))
                    else:
                        src_img = mu.load_image(src_path)
                    mu.crop_box(src_img, box).save(out_crop, "JPEG", quality=90)
                crops.append(
                    Media(
                        out_crop,
                        "image",
                        "image/jpeg",
                        mu.sha256_file(out_crop),
                        caption=f"Reference item crop from filmed room: {lbl}",
                    )
                )
                seen_labels.add(lbl.lower())
            except Exception:
                continue
    return crops


def _summarize_manifest_for_render(plan: dict[str, Any]) -> tuple[str, list[str]]:
    """Summarize the top furniture & box counts from the solved plan for Nano Banana 2.1."""
    trucks = plan.get("trucks") or []
    all_items = [it for t in trucks for it in (t.get("items") or [])]
    furniture_counts: dict[str, int] = {}
    box_count = 0
    for it in all_items:
        if it.get("is_box"):
            box_count += 1
        else:
            lbl = str(it.get("label") or "furniture piece").split("(")[0].strip()
            furniture_counts[lbl] = furniture_counts.get(lbl, 0) + 1

    top_pieces = sorted(furniture_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    bullet_phrases = [
        f"{cnt}× {name}" if cnt > 1 else name
        for name, cnt in top_pieces
    ]
    if box_count:
        bullet_phrases.append(
            f"{box_count} plain brown corrugated moving boxes with blank unadorned vertical sides and a small white shipping sticker flat on the horizontal top lid only"
        )
    if not bullet_phrases:
        bullet_phrases = [
            "bespoke communal work tables and lounge sofas",
            "ergonomic task chairs and bar stools",
            "65-inch presentation monitors on rolling stands",
            "plain brown corrugated moving boxes with blank unadorned vertical sides and a small white sticker flat on the top lid",
        ]
    return ", ".join(bullet_phrases), bullet_phrases


def render_arrival(
    run_id: str | None = None,
    plan: dict[str, Any] | None = None,
    inventory: dict[str, Any] | None = None,
    zone_focus: str | None = None,
) -> dict[str, Any]:
    """Generate Before + After Penn Station arrival frames with Nano Banana 2.1 (`for_job('image')`)."""
    t0 = time.time()
    rd: Path | None = None
    if run_id and run_id not in ("sample_venue", "sample", "mock-demo", "inline"):
        try:
            cand = run_dir(run_id)
            if cand.exists():
                rd = cand
        except ValueError:
            rd = None

    if inventory is None:
        if rd and (rd / "inventory.json").exists():
            inventory = read_json(rd / "inventory.json")
        else:
            inventory = json.loads((ROOT / "data" / "sample_venue.json").read_text(encoding="utf-8"))

    if plan is None:
        plan = solver.solve(inventory)

    before_media, before_source = ensure_empty_penn_frame(rd)
    before_media.caption = (
        "Reference Image 1 (STARTING SPACE): Empty Moynihan Train Hall / NY Penn Station concourse bay. "
        "Keep this exact camera angle, perspective, vaulted skylight, columns, walls, and floor."
    )

    crops = collect_source_item_crops(run_id, inventory, max_crops=5)
    manifest_str, highlights = _summarize_manifest_for_render(plan)
    zone_clause = f" staged for the {zone_focus} zone" if zone_focus else ""

    arrival_prompt = (
        "Edit Reference Image 1 (the empty Moynihan Train Hall / NY Penn Station concourse bay) so that "
        "the exact same architectural space, camera position, focal length, skylight, columns, and floor "
        f"are now freshly unpacked and staged{zone_clause} with this moved venue inventory: {manifest_str}. "
        + (
            "Match the colors, textures, and silhouettes of the attached Reference item crops from the filmed source room. "
            if crops
            else ""
        )
        + "Arrange the sofas, communal tables, chairs, monitors, and a neat low cluster of plain kraft cardboard "
        "moving boxes (every vertical side wall of every box must be 100% blank plain brown cardboard with zero stickers on the sides; "
        "place small white shipping stickers flat on the horizontal top lids only) "
        "into an inviting, photorealistic coworking & retail showcase under natural skylight daylight. "
        "Photorealistic architectural photography, 16:9, no text watermarks."
    )

    key_hash = hashlib.sha256(
        json.dumps(
            {
                "before": before_media.sha256,
                "crops": [c.sha256 for c in crops],
                "prompt": arrival_prompt,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:20]

    after_name = f"penn_arrival_after_{key_hash}.png"
    after_path = RENDER_DIR / after_name
    before_name = before_media.path.name

    img_job = for_job("image", rd)
    cached = after_path.exists() and after_path.stat().st_size > 1000
    if not cached:
        raw_after = img_job.generate_image(
            arrival_prompt,
            refs=[before_media, *crops],
            label="penn_arrival_render",
        )
        _normalize_16x9_png(raw_after, after_path)

    return {
        "ok": True,
        "illustrative": True,
        "badge": "Illustrative render · 3D view is the physics-verified plan",
        "cached": cached,
        "before_asset": before_name,
        "after_asset": after_name,
        "before_url": f"/render/asset/{before_name}",
        "after_url": f"/render/asset/{after_name}",
        "before_source": before_source,
        "item_crops_used": len(crops),
        "highlights": highlights,
        "timelapse_key": key_hash,
        "model": img_job.provider.model,
        "latency_s": round(time.time() - t0, 2),
    }


def render_timelapse_sync(
    before_asset: str,
    after_asset: str,
    run_id: str | None = None,
    duration_s: int = 6,
) -> dict[str, Any]:
    """Run Gemini Omni 1.2 Flash (`gemini-omni-1.2-flash`) first->last frame transition MP4."""
    t0 = time.time()
    before_path = (RENDER_DIR / Path(before_asset).name).resolve()
    after_path = (RENDER_DIR / Path(after_asset).name).resolve()
    if not before_path.exists() or not after_path.exists():
        raise FileNotFoundError("Arrival keyframes not found; run POST /render/arrival first.")

    f1 = Media(before_path, "image", "image/png", mu.sha256_file(before_path))
    f2 = Media(after_path, "image", "image/png", mu.sha256_file(after_path))

    dur_clamped = max(4, min(10, int(duration_s)))
    tl_hash = hashlib.sha256(f"{f1.sha256}:{f2.sha256}:{dur_clamped}s".encode()).hexdigest()[:20]
    mp4_name = f"penn_timelapse_{tl_hash}.mp4"
    mp4_path = RENDER_DIR / mp4_name

    rd: Path | None = None
    if run_id and run_id not in ("sample_venue", "sample", "mock-demo", "inline"):
        try:
            cand = run_dir(run_id)
            if cand.exists():
                rd = cand
        except ValueError:
            rd = None

    vid_job = for_job("video", rd)
    if mp4_path.exists() and mp4_path.stat().st_size > 2000:
        return {
            "ok": True,
            "cached": True,
            "video_asset": mp4_name,
            "video_url": f"/render/asset/{mp4_name}",
            "duration_s": dur_clamped,
            "model": vid_job.provider.model,
            "latency_s": 0.0,
        }

    prompt = (
        "Locked-off tripod architectural time-lapse inside Moynihan Train Hall at New York Penn Station. "
        "Fast-moving professional movers wheel dollies and hand-trucks into the empty concourse bay, "
        "setting down plain brown moving cartons (white labels flat on top lids only, blank cardboard sides) and smoothly placing "
        "tables, sofas, chairs, and monitors into their exact final positions as warm daylight shifts "
        "gently across the terrazzo floor. Single continuous locked-camera hyper-lapse transition."
    )
    mp4_bytes = vid_job.generate_video(
        prompt=prompt,
        first_frame=f1,
        last_frame=f2,
        duration=f"{dur_clamped}s",
        aspect_ratio="16:9",
        resolution="720p",
        prompt_version="omni_penn_timelapse_v1",
        label="penn_omni_timelapse",
    )
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    tmp = RENDER_DIR / f"{mp4_name}.tmp"
    tmp.write_bytes(mp4_bytes)
    tmp.replace(mp4_path)

    return {
        "ok": True,
        "cached": False,
        "video_asset": mp4_name,
        "video_url": f"/render/asset/{mp4_name}",
        "duration_s": dur_clamped,
        "size_bytes": len(mp4_bytes),
        "model": vid_job.provider.model,
        "latency_s": round(time.time() - t0, 2),
    }


def start_timelapse_job(
    before_asset: str,
    after_asset: str,
    run_id: str | None = None,
    duration_s: int = 6,
) -> dict[str, Any]:
    """Launch (or reuse cached) async Gemini Omni 1.2 Flash time-lapse job so HTTP never times out."""
    before_path = (RENDER_DIR / Path(before_asset).name).resolve()
    after_path = (RENDER_DIR / Path(after_asset).name).resolve()
    if not before_path.exists() or not after_path.exists():
        raise FileNotFoundError("Arrival keyframes not found; run POST /render/arrival first.")

    dur_clamped = max(4, min(10, int(duration_s)))
    tl_hash = hashlib.sha256(
        f"{mu.sha256_file(before_path)}:{mu.sha256_file(after_path)}:{dur_clamped}s".encode()
    ).hexdigest()[:20]
    mp4_name = f"penn_timelapse_{tl_hash}.mp4"
    mp4_path = RENDER_DIR / mp4_name
    if mp4_path.exists() and mp4_path.stat().st_size > 2000:
        return {
            "job_id": f"cached_{tl_hash}",
            "status": "completed",
            "cached": True,
            "video_asset": mp4_name,
            "video_url": f"/render/asset/{mp4_name}",
            "duration_s": dur_clamped,
            "model": "gemini-omni-1.2-flash",
            "elapsed_s": 0.0,
        }

    # Reuse an in-flight job for the exact same keyframe pair if already running
    with _JOBS_LOCK:
        for existing in _VIDEO_JOBS.values():
            if existing.get("tl_hash") == tl_hash and existing.get("status") == "running":
                return {
                    **existing,
                    "elapsed_s": round(time.time() - existing["started_at"], 1),
                }

        job_id = f"omni_{uuid.uuid4().hex[:10]}"
        rec: dict[str, Any] = {
            "job_id": job_id,
            "tl_hash": tl_hash,
            "status": "running",
            "started_at": time.time(),
            "duration_s": dur_clamped,
            "model": "gemini-omni-1.2-flash",
            "video_url": None,
            "error": None,
        }
        _VIDEO_JOBS[job_id] = rec

    def _worker() -> None:
        try:
            res = render_timelapse_sync(
                before_asset=before_asset,
                after_asset=after_asset,
                run_id=run_id,
                duration_s=dur_clamped,
            )
            with _JOBS_LOCK:
                rec["status"] = "completed"
                rec["video_url"] = res["video_url"]
                rec["video_asset"] = res["video_asset"]
                rec["latency_s"] = res.get("latency_s")
        except Exception as e:
            with _JOBS_LOCK:
                rec["status"] = "failed"
                rec["error"] = str(e)[:400]

    threading.Thread(target=_worker, daemon=True).start()
    return {**rec, "elapsed_s": 0.0}


def get_timelapse_job(job_id: str) -> dict[str, Any] | None:
    with _JOBS_LOCK:
        rec = _VIDEO_JOBS.get(job_id)
        if not rec:
            return None
        out = dict(rec)
    out["elapsed_s"] = round(time.time() - out["started_at"], 1)
    return out
