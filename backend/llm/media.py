"""Media helpers: frame sampling, crops, duration, transcode.

Uses the ffmpeg binary that ships with imageio-ffmpeg, so nobody installs
anything. No model SDK here.
"""
from __future__ import annotations

import hashlib
import io
import subprocess
import warnings
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageOps

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

IMAGE_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
             ".heic": "image/heic", ".heif": "image/heif"}
VIDEO_EXT = {".mp4": "video/mp4", ".mov": "video/quicktime", ".m4v": "video/mp4"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def video_info(path: Path) -> dict:
    """Duration (s), fps, size and codec as reported by ffmpeg."""
    with warnings.catch_warnings():  # rotated phone clips warn about frame size; harmless here
        warnings.simplefilter("ignore")
        gen = imageio_ffmpeg.read_frames(str(path))
        try:
            meta = next(gen)
        finally:
            gen.close()
    return {
        "duration_s": meta.get("duration"),
        "fps": meta.get("fps"),
        "size": list(meta.get("size") or []),
        "codec": meta.get("codec"),
        "rotate": meta.get("rotate"),
        "has_audio": has_audio(path),
    }


def has_audio(path: Path) -> bool:
    """True if ffmpeg reports an audio stream."""
    err = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True).stderr.decode("utf-8", "replace")
    return any("Stream #" in line and "Audio:" in line for line in err.splitlines())


def extract_audio(path: Path, out_path: Path) -> Path:
    """Soundtrack as 16 kHz mono WAV, for the transcription fallback and quote playback."""
    if out_path.exists():
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp.wav")
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", str(tmp)], check=True, capture_output=True)
    tmp.replace(out_path)
    return out_path


def audio_clip(path: Path, start_s: float, end_s: float) -> bytes:
    """A short MP3 of [start_s, end_s] from a clip's soundtrack, for replaying a quote."""
    cmd = [FFMPEG, "-v", "error", "-ss", f"{max(0, start_s):.2f}", "-to", f"{end_s:.2f}", "-i", str(path),
           "-vn", "-ac", "1", "-c:a", "libmp3lame", "-q:a", "5", "-f", "mp3", "-"]
    return subprocess.run(cmd, capture_output=True, check=True).stdout


def frame_at(path: Path, t: float, max_side: int = 1280) -> Image.Image:
    """One frame of a video at time t (seconds), as a PIL image."""
    cmd = [FFMPEG, "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(path), "-frames:v", "1",
           "-vf", f"scale='min({max_side},iw)':-2", "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "-"]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    if not out:  # t past the end: take the last frame
        cmd[cmd.index("-ss") + 1] = "0"
        cmd[3:3] = ["-sseof", "-0.5"]
        out = subprocess.run(cmd, capture_output=True, check=True).stdout
    return Image.open(io.BytesIO(out)).convert("RGB")


def sample_frames(path: Path, out_dir: Path, fps: float = 2.0, max_frames: int = 60,
                  start_s: float | None = None, end_s: float | None = None) -> list[tuple[float, Path]]:
    """Write JPEG frames sampled at `fps` (capped at max_frames) and return (timestamp, path) pairs."""
    info = video_info(path)
    dur = info["duration_s"] or 0
    t0 = start_s or 0.0
    t1 = min(end_s, dur) if end_s else dur
    span = max(t1 - t0, 0.1)
    n = max(1, min(max_frames, int(span * fps)))
    step = span / n
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i in range(n):
        t = round(t0 + i * step, 2)
        p = out_dir / f"frame_{t:07.2f}.jpg"
        if not p.exists():
            frame_at(path, t).save(p, "JPEG", quality=85)
        frames.append((t, p))
    return frames


def transcode_720p(path: Path, out_path: Path) -> Path:
    """H.264 MP4 at 720p, for providers that reject the original (e.g. HEVC)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [FFMPEG, "-v", "error", "-y", "-i", str(path), "-vf", "scale=-2:'min(720,ih)'",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-movflags", "+faststart",
           str(out_path)]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def load_image(path: Path) -> Image.Image:
    img = Image.open(path)
    return ImageOps.exif_transpose(img).convert("RGB")


def crop_box(img: Image.Image, box_2d: list[int] | None, pad: float = 0.04) -> Image.Image:
    """Crop with a [ymin, xmin, ymax, xmax] box on a 0-1000 scale, padded a little."""
    if not box_2d or len(box_2d) != 4:
        return img
    w, h = img.size
    ymin, xmin, ymax, xmax = [max(0, min(1000, int(v))) for v in box_2d]
    if ymax <= ymin or xmax <= xmin:
        return img
    py, px = pad * 1000, pad * 1000
    left = max(0, (xmin - px) / 1000 * w)
    top = max(0, (ymin - py) / 1000 * h)
    right = min(w, (xmax + px) / 1000 * w)
    bottom = min(h, (ymax + py) / 1000 * h)
    return img.crop((int(left), int(top), int(right), int(bottom)))


def crop_jpeg(path: Path, kind: str, box_2d: list[int] | None = None, t: float | None = None,
              max_side: int = 512) -> bytes:
    """JPEG bytes of a crop from a photo, or from the clip frame at t."""
    img = frame_at(path, t or 0.0) if kind == "video" else load_image(path)
    img = crop_box(img, box_2d)
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()
