"""Provider interface and the Media type.

Everything outside backend/llm/ talks to models through `for_job()` in
backend/llm/__init__.py. Adapters (gemini.py today, claude.py later) implement
the Provider protocol below and nothing else.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol


@dataclass
class Media:
    path: Path
    kind: Literal["image", "video", "audio"]
    mime: str
    sha256: str
    start_s: float | None = None  # optional clip window
    end_s: float | None = None
    # Free-form caption put next to the media in the prompt, e.g. "frame at 4.0 s".
    caption: str | None = None

    def cache_token(self) -> str:
        return f"{self.sha256}:{self.start_s}:{self.end_s}"


@dataclass
class Usage:
    tokens_in: int | None = None
    tokens_out: int | None = None
    extra: dict = field(default_factory=dict)


class ProviderError(RuntimeError):
    """A provider call failed (network, quota, rejected input)."""


class Provider(Protocol):
    name: str
    model: str
    capabilities: set[str]  # {"image_in", "video_in", "audio_in", "json_schema", "decide_native", "image_out"}

    def generate_json(self, prompt: str, media: list[Media], schema: dict, settings: dict) -> tuple[dict, Usage]: ...

    def generate_text(self, prompt: str, media: list[Media], settings: dict) -> tuple[str, Usage]: ...

    def decide(self, question: str, media: list[Media], options: list[str], settings: dict) -> tuple[dict, Usage]: ...

    def decide_batch(
        self, input_text: str, media: list[Media], questions: dict[str, dict], settings: dict
    ) -> tuple[dict, Usage]: ...

    def generate_image(self, prompt: str, refs: list[Media], settings: dict) -> tuple[bytes, Usage]: ...
