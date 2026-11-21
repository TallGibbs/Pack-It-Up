"""Model provider layer. Code asks for a job, not a model:

    from backend.llm import for_job
    data = for_job("perceive").generate_json(prompt, media=[m], schema=SCHEMA, prompt_version="perceive_v1")

Shared here, whatever the provider: config lookup (models.toml + MODEL_<JOB> env
override), response cache, JSON-schema validation with one retry, the call log,
the video-to-frames fallback, and the decide() fallback.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import threading
import time
import tomllib
from pathlib import Path

import jsonschema

from .base import Media, Provider, ProviderError, Usage
from . import media as media_utils

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(__file__).with_name("models.toml")
CACHE_DIR = ROOT / ".cache" / "llm"
GLOBAL_LOG = ROOT / ".cache" / "calls.jsonl"
FAILURES = ROOT / "FAILURES.md"

_log_lock = threading.Lock()
_env_loaded = False


class LLMError(RuntimeError):
    """A job failed after its retry. Already logged to the call log and FAILURES.md."""


def _load_env() -> None:
    global _env_loaded
    if _env_loaded:
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    _env_loaded = True


def load_config() -> dict:
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def _make_provider(spec: str) -> Provider:
    provider, _, model = spec.partition(":")
    if provider == "gemini":
        from .gemini import GeminiProvider
        return GeminiProvider(model)
    # if provider == "claude": from .claude import ClaudeProvider  (later)
    raise ValueError(f"unknown provider {provider!r} in {spec!r}")


def for_job(name: str, run_dir: Path | str | None = None) -> "Job":
    """The configured provider for a job. MODEL_<NAME> env var overrides models.toml."""
    _load_env()
    cfg = load_config()
    jobs = cfg.get("jobs", {})
    if name not in jobs:
        raise KeyError(f"job {name!r} not in {CONFIG_PATH.name}")
    settings = {**cfg.get("defaults", {}), **jobs[name]}
    spec = os.environ.get(f"MODEL_{name.upper()}") or settings.pop("model")
    settings.pop("model", None)
    provider = _make_provider(spec)
    # Testing switch: MODEL_PERCEIVE_DISABLE=video_in,audio_in makes a capable model act like one that
    # can't watch or hear, so the frame-sampling and transcription fallbacks can be exercised today.
    disabled = os.environ.get(f"MODEL_{name.upper()}_DISABLE") or ",".join(settings.pop("disable", []))
    if disabled:
        provider.capabilities = set(provider.capabilities) - {c.strip() for c in disabled.split(",")}
    return Job(name, spec, provider, settings, Path(run_dir) if run_dir else None)


TRANSCRIPT_SCHEMA = {
    "type": "object", "required": ["segments"],
    "properties": {"segments": {"type": "array", "items": {
        "type": "object", "required": ["start_s", "end_s", "text", "speaker"],
        "properties": {"start_s": {"type": "number", "minimum": 0}, "end_s": {"type": "number", "minimum": 0},
                       "text": {"type": "string"},
                       "speaker": {"type": "string", "enum": ["narrator", "background"],
                                   "description": "narrator = the person filming, close to the microphone"}}}}},
}
TRANSCRIBE_PROMPT = ("Transcribe the speech in this audio with timestamps in seconds. Mark each segment's speaker as "
                     "`narrator` (the person recording, close to the microphone, describing the room) or `background` "
                     "(other people nearby, announcements, music). Return an empty list if nobody speaks.")


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _append_failure(what: str, inp: str, change: str = "Job failed after retry; see calls.jsonl") -> None:
    t = _dt.datetime.now().strftime("%H:%M")
    line = f"| {t} | {inp} | {what.replace('|', '/').replace(chr(10), ' ')[:300]} | {change} |\n"
    with _log_lock, open(FAILURES, "a", encoding="utf-8") as f:
        f.write(line)


class Job:
    def __init__(self, name: str, spec: str, provider: Provider, settings: dict, run_dir: Path | None):
        self.name = name
        self.spec = spec
        self.provider = provider
        self.settings = settings
        self.run_dir = run_dir

    def __repr__(self) -> str:
        return f"Job({self.name} -> {self.spec})"

    # ---------- logging / cache ----------
    def _log(self, **entry) -> None:
        rec = {"ts": _dt.datetime.now().isoformat(timespec="seconds"), "job": self.name,
               "provider": self.provider.name, "model": self.provider.model, **entry}
        line = json.dumps(rec) + "\n"
        targets = [GLOBAL_LOG] + ([self.run_dir / "calls.jsonl"] if self.run_dir else [])
        with _log_lock:
            for p in targets:
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "a", encoding="utf-8") as f:
                    f.write(line)

    def _key(self, kind: str, prompt: str, media: list[Media], prompt_version: str, extra=None) -> str:
        settings = {k: v for k, v in self.settings.items() if k not in ("timeout_s", "retries")}
        return _sha({"job": self.name, "kind": kind, "model": self.spec, "pv": prompt_version,
                     "caps": sorted(self.provider.capabilities),
                     "key_profile": os.environ.get("GEMINI_KEY_PROFILE", "").upper() or None,
                     "prompt": _sha(prompt), "media": [m.cache_token() for m in media],
                     "settings": settings, "extra": extra})

    def _cache_get(self, key: str):
        p = CACHE_DIR / f"{key}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))["value"]
        return None

    def _cache_put(self, key: str, value) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_DIR / f"{key}.{threading.get_ident()}.tmp"
        tmp.write_text(json.dumps({"value": value}), encoding="utf-8")
        os.replace(tmp, CACHE_DIR / f"{key}.json")

    # ---------- media adaptation ----------
    def _transcribe_clip(self, m: Media) -> str:
        """Fallback for a model that can't hear: transcribe the soundtrack with the `transcribe` job."""
        if not media_utils.has_audio(m.path):
            return ""
        wav = media_utils.extract_audio(m.path, CACHE_DIR / "audio" / f"{m.sha256[:16]}.wav")
        audio = Media(wav, "audio", "audio/wav", media_utils.sha256_file(wav), m.start_s, m.end_s)
        tr = for_job("transcribe", self.run_dir).generate_json(TRANSCRIBE_PROMPT, media=[audio], schema=TRANSCRIPT_SCHEMA,
                                                                prompt_version="transcribe_v1", label=m.path.name)
        lines = [f"[{s['start_s']:.1f}-{s['end_s']:.1f} s, {s['speaker']}] {s['text']}" for s in tr["segments"]]
        return (f"\n\nSoundtrack transcript of {m.path.name} (made separately because you receive no audio; "
                f"timestamps in seconds):\n" + ("\n".join(lines) if lines else "(no speech)"))

    def _adapt_media(self, prompt: str, media: list[Media]) -> tuple[str, list[Media], str | None]:
        """If the provider can't hear, transcribe each clip first; if it can't take video, send sampled frames."""
        caps = self.provider.capabilities
        notes = []
        videos = [m for m in media if m.kind == "video"]
        if videos and not {"video_in", "audio_in"} <= caps:
            for m in videos:
                text = self._transcribe_clip(m)
                if text:
                    prompt += text
                    notes.append(f"transcribed {m.path.name}")
        if "video_in" in caps or not videos:
            return prompt, media, ("; ".join(notes) or None)
        out: list[Media] = []
        fps = float(self.settings.get("video_fps", 2))
        for m in media:
            if m.kind != "video":
                out.append(m)
                continue
            frames = media_utils.sample_frames(m.path, CACHE_DIR / "frames" / m.sha256, fps=fps, max_frames=60,
                                               start_s=m.start_s, end_s=m.end_s)
            for t, p in frames:
                out.append(Media(p, "image", "image/jpeg", f"{m.sha256}@{t}", caption=f"[{m.path.name} frame at t={t:.2f} s]"))
            notes.append(f"{m.path.name}: {len(frames)} frames at {fps} fps")
        prompt += ("\n\nThe video was supplied as still frames; each frame is labelled with its timestamp. "
                   "Use those timestamps for timestamp_s.")
        return prompt, out, "; ".join(notes)

    # ---------- jobs ----------
    def _run(self, kind: str, prompt: str, media: list[Media], prompt_version: str, call, validate=None,
             extra_key=None, label: str | None = None):
        media = list(media or [])
        key = self._key(kind, prompt, media, prompt_version, extra_key)
        files = label or ",".join(m.path.name for m in media)
        cached = self._cache_get(key)
        if cached is not None:
            self._log(kind=kind, prompt_version=prompt_version, file=files, cache="hit", valid=True, latency_s=0.0)
            return cached
        p_prompt, p_media, adapt_note = self._adapt_media(prompt, media)
        attempts = int(self.settings.get("retries", 1)) + 1
        last_err = None
        for attempt in range(1, attempts + 1):
            t0 = time.time()
            usage = Usage()
            try:
                value, usage = call(p_prompt, p_media)
                if validate:
                    validate(value)
                self._log(kind=kind, prompt_version=prompt_version, file=files, cache="miss", valid=True,
                          latency_s=round(time.time() - t0, 2), tokens_in=usage.tokens_in, tokens_out=usage.tokens_out,
                          attempt=attempt, media_mode=adapt_note, **usage.extra)
                self._cache_put(key, value)
                return value
            except (jsonschema.ValidationError, ValueError) as e:
                last_err = e
                msg = e.message if isinstance(e, jsonschema.ValidationError) else str(e)
                self._log(kind=kind, prompt_version=prompt_version, file=files, cache="miss", valid=False,
                          latency_s=round(time.time() - t0, 2), attempt=attempt, error=msg[:300])
                p_prompt = (prompt if adapt_note is None else p_prompt) + (
                    f"\n\nYour previous answer failed validation: {msg[:500]}\nReturn JSON that matches the schema exactly.")
            except ProviderError as e:
                last_err = e
                self._log(kind=kind, prompt_version=prompt_version, file=files, cache="miss", valid=False,
                          latency_s=round(time.time() - t0, 2), attempt=attempt, error=str(e)[:300])
                if "GEMINI_API_KEY" in str(e):
                    break
        _append_failure(f"{self.name} ({self.spec}) failed: {last_err}", files)
        raise LLMError(f"{self.name} failed on {files}: {last_err}") from last_err

    def generate_text(self, prompt: str, media: list[Media] | None = None, prompt_version: str = "",
                      label: str | None = None) -> str:
        return self._run("text", prompt, media or [], prompt_version,
                         lambda p, m: self.provider.generate_text(p, m, self.settings), label=label)

    def generate_json(self, prompt: str, media: list[Media] | None = None, schema: dict | None = None,
                      prompt_version: str = "", label: str | None = None) -> dict:
        assert schema is not None, "generate_json needs a schema"
        validator = jsonschema.Draft202012Validator(schema)

        def validate(value):
            err = jsonschema.exceptions.best_match(validator.iter_errors(value))
            if err is not None:
                raise err

        return self._run("json", prompt, media or [], prompt_version,
                         lambda p, m: self.provider.generate_json(p, m, schema, self.settings),
                         validate=validate, extra_key=_sha(schema), label=label)

    def decide(self, question: str, media: list[Media] | None = None, options: list[str] | None = None,
               criteria: dict[str, str] | None = None, label: str | None = None) -> dict:
        """-> {"answer", "confidence", "rationale", "via"}. Native Decisions API if the provider has it,
        else a structured generate_json call whose answer is an enum of the options."""
        options = list(options or (criteria or {}).keys())
        assert len(options) >= 2, "decide needs at least two options"
        schema = {"type": "object", "required": ["answer", "confidence", "rationale"],
                  "properties": {"answer": {"type": "string", "enum": options},
                                 "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                                 "rationale": {"type": "string"}}}
        validator = jsonschema.Draft202012Validator(schema)

        def validate(value):
            err = jsonschema.exceptions.best_match(validator.iter_errors(value))
            if err is not None:
                raise err

        if "decide_native" in self.provider.capabilities and not os.environ.get("DECIDE_FORCE_FALLBACK"):
            settings = {**self.settings, "criteria": criteria or {o: o for o in options}}
            try:
                out = self._run("decide_native", question, media or [], "decide_native_v1",
                                lambda p, m: self.provider.decide(p, m, options, settings),
                                validate=validate, extra_key=settings["criteria"], label=label)
                return {**out, "via": "decisions_api"}
            except LLMError:
                pass  # fall through to the generic path; logged already
        crit = criteria or {}
        prompt = (f"{question}\n\nAnswer with exactly one of these options:\n" +
                  "\n".join(f"- {o}" + (f": {crit[o]}" if crit.get(o) and crit[o] != o else "") for o in options) +
                  "\nGive your confidence (0-1) and a one-sentence rationale.")
        # The Decisions model may not do generate_json, so the fallback runs as its own job if configured.
        fb = self
        if self.name != "decide_fallback" and "decide_fallback" in load_config().get("jobs", {}):
            fb = for_job("decide_fallback", self.run_dir)
        out = fb._run("decide_fallback", prompt, media or [], "decide_fallback_v1",
                      lambda p, m: fb.provider.generate_json(p, m, schema, fb.settings),
                      validate=validate, extra_key=_sha(schema), label=label)
        return {**out, "via": "generate_json_fallback"}

    def generate_image(self, prompt: str, refs: list[Media] | None = None, label: str | None = None) -> bytes:
        import base64
        b64 = self._run("image", prompt, refs or [], "",
                        lambda p, m: (lambda r: (base64.b64encode(r[0]).decode(), r[1]))(
                            self.provider.generate_image(p, m, self.settings)), label=label)
        return base64.b64decode(b64)


def media_from_path(path: Path | str, sha256: str | None = None, start_s=None, end_s=None) -> Media:
    """Build a Media from a file on disk (kind and mime from the extension)."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext in media_utils.IMAGE_EXT:
        kind, mime = "image", media_utils.IMAGE_EXT[ext]
    elif ext in media_utils.VIDEO_EXT:
        kind, mime = "video", media_utils.VIDEO_EXT[ext]
    else:
        raise ValueError(f"unsupported media type: {path.name}")
    return Media(path, kind, mime, sha256 or media_utils.sha256_file(path), start_s, end_s)


__all__ = ["for_job", "Job", "Media", "LLMError", "ProviderError", "media_from_path", "load_config"]
