"""Gemini adapter: the only file that imports google-genai.

Photos go inline as bytes. Clips go through the Files API and we wait until the
file is ACTIVE. Uploaded file names are cached by sha256 for the session.
`decide()` uses the native Decisions API (client.decisions.create).
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from pathlib import Path

from google import genai
from google.genai import types

from .base import Media, ProviderError, Usage

_THINKING = {"minimal": "MINIMAL", "low": "LOW", "medium": "MEDIUM", "high": "HIGH", "xhigh": "XHIGH"}
_RES = {"low": "MEDIA_RESOLUTION_LOW", "medium": "MEDIA_RESOLUTION_MEDIUM", "high": "MEDIA_RESOLUTION_HIGH"}

_client: genai.Client | None = None
_client_lock = threading.Lock()
_uploaded: dict[str, types.File] = {}  # sha256 -> active File
_upload_locks: dict[str, threading.Lock] = {}


def key_var() -> str:
    """Which .env variable holds the key: GEMINI_API_KEY by default, GEMINI_API_KEY_<PROFILE> when
    GEMINI_KEY_PROFILE is set (e.g. PERSONAL for your own AI Studio key next to the event key)."""
    profile = os.environ.get("GEMINI_KEY_PROFILE", "").strip().upper()
    return f"GEMINI_API_KEY_{profile}" if profile else "GEMINI_API_KEY"


def _get_client() -> genai.Client:
    global _client
    with _client_lock:
        if _client is None:
            var = key_var()
            if not os.environ.get(var):
                raise ProviderError(f"{var} is not set; add it to .env")
            _client = genai.Client(api_key=os.environ[var])
        return _client


def _usage(resp) -> Usage:
    um = getattr(resp, "usage_metadata", None)
    if not um:
        return Usage()
    return Usage(tokens_in=getattr(um, "prompt_token_count", None),
                 tokens_out=getattr(um, "candidates_token_count", None),
                 extra={"thoughts": getattr(um, "thoughts_token_count", None)})


class GeminiProvider:
    name = "gemini"
    capabilities = {"image_in", "video_in", "audio_in", "json_schema", "decide_native", "image_out"}

    def __init__(self, model: str):
        self.model = model

    # ---------- media ----------
    def upload_video(self, m: Media, timeout_s: float = 180) -> types.File:
        lock = _upload_locks.setdefault(m.sha256, threading.Lock())
        with lock:
            f = _uploaded.get(m.sha256)
            if f is not None:
                return f
            client = _get_client()
            f = client.files.upload(file=str(m.path), config={"mime_type": m.mime, "display_name": m.path.name})
            t0 = time.time()
            while f.state and f.state.name == "PROCESSING":
                if time.time() - t0 > timeout_s:
                    raise ProviderError(f"video {m.path.name} still processing after {timeout_s}s")
                time.sleep(1.5)
                f = client.files.get(name=f.name)
            if f.state and f.state.name == "FAILED":
                raise ProviderError(f"Files API could not process {m.path.name}: {f.error}")
            _uploaded[m.sha256] = f
            return f

    def _parts(self, prompt: str, media: list[Media], settings: dict) -> list:
        parts: list = []
        for m in media:
            if m.caption:
                parts.append(types.Part.from_text(text=m.caption))
            if m.kind in ("image", "audio"):  # short soundtracks go inline like photos
                parts.append(types.Part.from_bytes(data=Path(m.path).read_bytes(), mime_type=m.mime))
            else:  # video: Gemini hears the soundtrack along with the frames
                f = self.upload_video(m)
                vm = {}
                if settings.get("video_fps"):
                    vm["fps"] = float(settings["video_fps"])
                if m.start_s is not None:
                    vm["start_offset"] = f"{m.start_s:.1f}s"
                if m.end_s is not None:
                    vm["end_offset"] = f"{m.end_s:.1f}s"
                parts.append(types.Part(file_data=types.FileData(file_uri=f.uri, mime_type=f.mime_type or m.mime),
                                        video_metadata=types.VideoMetadata(**vm) if vm else None))
        parts.append(types.Part.from_text(text=prompt))
        return parts

    def _config(self, settings: dict, **extra) -> types.GenerateContentConfig:
        cfg: dict = dict(extra)
        if settings.get("thinking"):
            cfg["thinking_config"] = types.ThinkingConfig(thinking_level=_THINKING[settings["thinking"]])
        if settings.get("media_resolution"):
            cfg["media_resolution"] = _RES[settings["media_resolution"]]
        if settings.get("temperature") is not None:
            cfg["temperature"] = settings["temperature"]
        if settings.get("timeout_s"):
            cfg["http_options"] = types.HttpOptions(timeout=int(settings["timeout_s"] * 1000))
        return types.GenerateContentConfig(**cfg)

    def _generate(self, prompt, media, settings, **cfg):
        try:
            return _get_client().models.generate_content(
                model=self.model, contents=self._parts(prompt, media, settings), config=self._config(settings, **cfg))
        except ProviderError:
            raise
        except Exception as e:  # SDK raises several error classes; normalise
            raise ProviderError(f"{type(e).__name__}: {e}") from e

    # ---------- interface ----------
    def generate_text(self, prompt: str, media: list[Media], settings: dict) -> tuple[str, Usage]:
        resp = self._generate(prompt, media, settings)
        return resp.text or "", _usage(resp)

    def generate_json(self, prompt: str, media: list[Media], schema: dict, settings: dict) -> tuple[dict, Usage]:
        resp = self._generate(prompt, media, settings,
                              response_mime_type="application/json", response_json_schema=schema)
        text = resp.text or ""
        try:
            return json.loads(text), _usage(resp)
        except json.JSONDecodeError as e:
            # Shared code treats this like a validation failure and retries.
            raise ValueError(f"response is not JSON ({e}); first 200 chars: {text[:200]!r}") from e

    def decide(self, question: str, media: list[Media], options: list[str], settings: dict) -> tuple[dict, Usage]:
        """Native Decisions API: one choice question over `options`."""
        inputs: list[dict] = []
        for m in media:
            if m.caption:
                inputs.append({"type": "text", "text": m.caption})
            if m.kind == "image":
                inputs.append({"type": "image", "mime_type": m.mime,
                               "data": base64.b64encode(Path(m.path).read_bytes()).decode()})
            else:
                f = self.upload_video(m)
                inputs.append({"type": "video", "mime_type": f.mime_type or m.mime, "uri": f.uri})
        if not inputs:
            inputs.append({"type": "text", "text": "(no media)"})
        criteria = settings.get("criteria") or {o: o for o in options}
        model = self.model if self.model.startswith("models/") else f"models/{self.model}"
        extra = {"api_version": settings["api_version"]} if settings.get("api_version") else {}
        try:
            resp = _get_client().decisions.create(
                model=model, input=inputs,
                questions={"q": {"type": "choice", "instructions": question, "criteria": criteria}},
                timeout=settings.get("timeout_s", 90), **extra)
        except Exception as e:
            raise ProviderError(f"Decisions API {type(e).__name__}: {e}") from e
        ans = (resp.answers or {}).get("q")
        if ans is None or getattr(ans, "choice", None) is None:
            raise ProviderError(f"Decisions API returned no answer: {resp!r}"[:500])
        usage = Usage()
        u = getattr(resp, "usage", None)
        if u is not None:
            usage = Usage(tokens_in=getattr(u, "total_input_tokens", None),
                          tokens_out=getattr(u, "total_output_tokens", None))
        return {"answer": ans.choice, "confidence": float(ans.confidence),
                "rationale": "Decisions API calibrated probabilities: " +
                             json.dumps({k: round(v, 3) for k, v in (ans.probabilities or {}).items()}),
                "probabilities": dict(ans.probabilities or {})}, usage

    def generate_image(self, prompt: str, refs: list[Media], settings: dict) -> tuple[bytes, Usage]:
        resp = self._generate(prompt, refs, settings, response_modalities=["IMAGE", "TEXT"])
        for cand in resp.candidates or []:
            for part in (cand.content.parts if cand.content else []) or []:
                if part.inline_data and part.inline_data.data:
                    return part.inline_data.data, _usage(resp)
        raise ProviderError("no image in response")
