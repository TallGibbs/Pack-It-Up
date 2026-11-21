"""Stage 1: intake. No model call.

Accepts photos and clips (extension matched case-insensitively), hashes each
file, normalises photos (EXIF rotation, HEIC to JPEG, long side at most 2048 px),
reads clip durations, and writes runs/<run_id>/manifest.json.
"""
from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

from PIL import Image, ImageOps

from backend.llm import media as mu

from .common import read_json, run_dir, scrub, slug, update_status, write_json

ACCEPTED = set(mu.IMAGE_EXT) | set(mu.VIDEO_EXT)
MAX_SIDE = 2048

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:  # HEIC then fails per file, loudly
    pillow_heif = None


def _normalise_photo(src: Path, dst_dir: Path, sha: str) -> tuple[Path, dict]:
    img = Image.open(src)
    orientation = img.getexif().get(0x0112, 1)
    w, h = img.size
    ext = src.suffix.lower()
    needs = ext in (".heic", ".heif") or orientation not in (0, 1) or max(w, h) > MAX_SIDE
    if not needs:
        dst = dst_dir / f"{sha[:16]}{ext}"
        if not dst.exists():
            shutil.copyfile(src, dst)
        return dst, {"width": w, "height": h, "normalised": False}
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    dst = dst_dir / f"{sha[:16]}.jpg"
    img.save(dst, "JPEG", quality=90)
    return dst, {"width": img.size[0], "height": img.size[1], "normalised": True,
                 "original_size": [w, h], "exif_orientation": orientation}


def intake(paths: list[Path], room_name: str | None, run_id: str, original_names: dict[Path, str] | None = None) -> dict:
    """Add files to the run's manifest under one room. Calling again with another room makes a multi-room move."""
    rd = run_dir(run_id)
    media_dir = rd / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    manifest = read_json(rd / "manifest.json") or {
        "run_id": run_id, "created": dt.datetime.now().isoformat(timespec="seconds"), "rooms": [], "files": [], "skipped": []}

    room_name = room_name or "room_1"
    room_id = slug(room_name)
    if not any(r["id"] == room_id for r in manifest["rooms"]):
        manifest["rooms"].append({"id": room_id, "name": room_name})
    known = {(f["sha256"], f["room_id"]) for f in manifest["files"]}

    for src in sorted(paths, key=lambda p: p.name.lower()):
        name = (original_names or {}).get(src, src.name)
        ext = Path(name).suffix.lower()
        if ext not in ACCEPTED:
            if not name.startswith("."):
                manifest["skipped"].append({"name": name, "reason": f"unsupported type {ext or '(none)'}"})
            continue
        sha = mu.sha256_file(src)
        if (sha, room_id) in known:
            continue
        entry = {"name": name, "sha256": sha, "room_id": room_id, "bytes": src.stat().st_size,
                 "original_path": str(src)}
        try:
            if ext in mu.IMAGE_EXT:
                dst, info = _normalise_photo(src, media_dir, sha)
                entry.update(kind="image", mime="image/jpeg" if dst.suffix == ".jpg" else mu.IMAGE_EXT[ext], **info)
            else:
                dst = media_dir / f"{sha[:16]}{ext}"
                if not dst.exists():
                    shutil.copyfile(src, dst)
                info = mu.video_info(dst)
                entry.update(kind="video", mime=mu.VIDEO_EXT[ext], duration_s=info["duration_s"], fps=info["fps"],
                             width=(info["size"] or [None, None])[0], height=(info["size"] or [None, None])[1],
                             codec=info["codec"], has_audio=info["has_audio"])
                if info["has_audio"]:  # for the transcription fallback and quote playback
                    wav = mu.extract_audio(dst, rd / "audio" / f"{sha[:16]}.wav")
                    entry["audio_path"] = str(wav.relative_to(rd)).replace("\\", "/")
            entry["path"] = str(dst.relative_to(rd)).replace("\\", "/")
        except Exception as e:  # one bad file must not sink the run
            manifest["skipped"].append({"name": name, "reason": scrub(f"{type(e).__name__}: {e}")})
            update_status(rd, error=f"intake {name}: {e}")
            continue
        manifest["files"].append(entry)
        known.add((sha, room_id))
        update_status(rd, files={name: {"room_id": room_id, "kind": entry["kind"], "intake": "done"}})

    write_json(rd / "manifest.json", manifest)
    update_status(rd, stage="intake_done")
    return manifest


def collect_folder(folder: Path) -> list[Path]:
    return [p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() in ACCEPTED]
