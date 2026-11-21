"""backend/llm/media.py: frames from clips. No model calls; ffmpeg makes its own one-second test clip."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from backend.llm import media


@pytest.fixture()
def clip(tmp_path: Path) -> Path:
    out = tmp_path / "one_second.mp4"
    subprocess.run(
        [media.FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10",
         "-pix_fmt", "yuv420p", str(out)],
        check=True, capture_output=True,
    )
    return out


def test_frame_inside_the_clip(clip: Path) -> None:
    img = media.frame_at(clip, 0.5)
    assert img.size == (320, 240)


def test_frame_past_the_end_gives_the_last_frame_not_an_error(clip: Path) -> None:
    # The truck page asked for stills at 2.7 s and 4.4 s of clips 2.67 s and 4.10 s long (FAILURES.md 15:15).
    img = media.frame_at(clip, 5.0)
    assert img.size == (320, 240)


def test_crop_jpeg_past_the_end_is_a_jpeg(clip: Path) -> None:
    jpg = media.crop_jpeg(clip, "video", None, 5.0, max_side=160)
    assert jpg[:2] == b"\xff\xd8"
