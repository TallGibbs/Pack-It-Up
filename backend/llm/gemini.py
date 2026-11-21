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
    capabilities = {"image_in", "video_in", "audio_in", "json_schema", "decide_native", "image_out", "audio_out", "video_out"}

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
            lvl = settings["thinking"]
            # Builder Guide rule: Gemini 4 Neon and Hydrogen reject `minimal` thinking level.
            if lvl == "minimal" and any(m in self.model for m in ("gemini-4-neon", "gemini-4-hydrogen")):
                lvl = "low"
            cfg["thinking_config"] = types.ThinkingConfig(thinking_level=_THINKING[lvl])
        if settings.get("media_resolution"):
            cfg["media_resolution"] = _RES[settings["media_resolution"]]
        if settings.get("temperature") is not None:
            cfg["temperature"] = settings["temperature"]
        http_opts: dict = {}
        if settings.get("timeout_s"):
            http_opts["timeout"] = int(settings["timeout_s"] * 1000)
        if settings.get("api_version"):
            http_opts["api_version"] = settings["api_version"]
        if http_opts:
            cfg["http_options"] = types.HttpOptions(**http_opts)
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

    def decide_batch(
        self, input_text: str, media: list[Media], questions: dict[str, dict], settings: dict
    ) -> tuple[dict, Usage]:
        """Native Decisions API batch call: evaluates noul, choice, and score questions in one pass."""
        inputs: list[dict] = []
        for m in media:
            if m.caption:
                inputs.append({"type": "text", "text": m.caption})
            if m.kind == "image":
                inputs.append({
                    "type": "image",
                    "mime_type": m.mime,
                    "data": base64.b64encode(Path(m.path).read_bytes()).decode(),
                })
            elif m.kind == "audio":
                inputs.append({
                    "type": "audio",
                    "mime_type": m.mime,
                    "data": base64.b64encode(Path(m.path).read_bytes()).decode(),
                })
            else:
                f = self.upload_video(m)
                inputs.append({"type": "video", "mime_type": f.mime_type or m.mime, "uri": f.uri})
        if input_text:
            inputs.append({"type": "text", "text": input_text})
        if not inputs:
            inputs.append({"type": "text", "text": "(no input)"})

        api_questions: dict[str, dict] = {}
        for qid, q in questions.items():
            qtype = q["type"]
            if qtype == "noul":
                entry: dict = {"type": "noul", "instructions": q["instructions"]}
                if q.get("criteria"):
                    entry["criteria"] = dict(q["criteria"])
                api_questions[qid] = entry
            elif qtype == "choice":
                api_questions[qid] = {
                    "type": "choice",
                    "instructions": q["instructions"],
                    "criteria": dict(q["criteria"]),
                }
            elif qtype == "score":
                api_questions[qid] = {
                    "type": "score",
                    "instructions": q["instructions"],
                    "criteria": list(q["criteria"]),
                }
            else:
                raise ValueError(f"unsupported decision question type {qtype!r} for {qid!r}")

        model = self.model if self.model.startswith("models/") else f"models/{self.model}"
        extra = {"api_version": settings["api_version"]} if settings.get("api_version") else {}
        try:
            resp = _get_client().decisions.create(
                model=model,
                input=inputs,
                questions=api_questions,
                timeout=settings.get("timeout_s", 90),
                **extra,
            )
        except Exception as e:
            raise ProviderError(f"Decisions API {type(e).__name__}: {e}") from e

        raw_answers = resp.answers or {}
        parsed: dict[str, dict] = {}
        for qid, q in questions.items():
            ans = raw_answers.get(qid)
            if ans is None:
                raise ProviderError(f"Decisions API returned no answer for {qid!r}: {resp!r}"[:500])
            qtype = q["type"]
            if qtype == "noul":
                noul_val = getattr(ans, "noul", None)
                if noul_val is None:
                    raise ProviderError(f"Decisions API missing noul value for {qid!r}: {ans!r}"[:500])
                p_yes = float(noul_val)
                parsed[qid] = {
                    "type": "noul",
                    "noul": round(p_yes, 4),
                    "answer": p_yes >= 0.5,
                    "confidence": round(float(ans.confidence), 4),
                }
            elif qtype == "choice":
                choice_val = getattr(ans, "choice", None)
                if choice_val is None:
                    raise ProviderError(f"Decisions API missing choice value for {qid!r}: {ans!r}"[:500])
                parsed[qid] = {
                    "type": "choice",
                    "choice": str(choice_val),
                    "probabilities": {str(k): round(float(v), 4) for k, v in (ans.probabilities or {}).items()},
                    "confidence": round(float(ans.confidence), 4),
                }
            elif qtype == "score":
                score_val = getattr(ans, "score", None)
                if score_val is None:
                    raise ProviderError(f"Decisions API missing score value for {qid!r}: {ans!r}"[:500])
                crit = list(q["criteria"])
                max_lvl = max(1, len(crit) - 1)
                sc = float(score_val)
                raw_legend = getattr(ans, "legend", None) or {str(i): c for i, c in enumerate(crit)}
                parsed[qid] = {
                    "type": "score",
                    "score": round(sc, 4),
                    "max_score": max_lvl,
                    "normalized": round(sc / max_lvl, 4),
                    "probabilities": {str(k): round(float(v), 4) for k, v in (ans.probabilities or {}).items()},
                    "legend": {str(k): str(v) for k, v in raw_legend.items()},
                    "confidence": round(float(ans.confidence), 4),
                }

        usage = Usage()
        u = getattr(resp, "usage", None)
        if u is not None:
            usage = Usage(
                tokens_in=getattr(u, "total_input_tokens", None),
                tokens_out=getattr(u, "total_output_tokens", None),
            )
        return {"answers": parsed}, usage

    def generate_image(self, prompt: str, refs: list[Media], settings: dict) -> tuple[bytes, Usage]:
        """Generate an image via Interactions API (Nano Banana 2.1) with generate_content fallback."""
        client = _get_client()
        inputs: list[dict] = []
        for m in refs[:14]:
            if m.caption:
                inputs.append({"type": "text", "text": m.caption})
            if m.kind == "image":
                inputs.append({
                    "type": "image",
                    "mime_type": m.mime,
                    "data": base64.b64encode(Path(m.path).read_bytes()).decode(),
                })
            elif m.kind == "video":
                f = self.upload_video(m)
                inputs.append({"type": "video", "mime_type": f.mime_type or m.mime, "uri": f.uri})
        inputs.append({"type": "text", "text": prompt})

        try:
            interaction = client.interactions.create(
                model=self.model,
                input=inputs if len(inputs) > 1 else prompt,
            )
            out_img = getattr(interaction, "output_image", None)
            if out_img and getattr(out_img, "data", None):
                raw = out_img.data
                img_bytes = base64.b64decode(raw) if isinstance(raw, str) else bytes(raw)
                u = getattr(interaction, "usage", None)
                usage = Usage(
                    tokens_in=getattr(u, "total_input_tokens", None) if u else None,
                    tokens_out=getattr(u, "total_output_tokens", None) if u else None,
                )
                return img_bytes, usage
            for step in getattr(interaction, "steps", None) or []:
                if getattr(step, "type", None) == "model_output":
                    for c in getattr(step, "content", None) or []:
                        if getattr(c, "type", None) == "image" and getattr(c, "data", None):
                            raw = c.data
                            return (base64.b64decode(raw) if isinstance(raw, str) else bytes(raw)), Usage()
        except Exception:
            pass

        resp = self._generate(prompt, refs, settings, response_modalities=["IMAGE", "TEXT"])
        for cand in resp.candidates or []:
            for part in (cand.content.parts if cand.content else []) or []:
                if part.inline_data and part.inline_data.data:
                    raw = part.inline_data.data
                    return (base64.b64decode(raw) if isinstance(raw, str) else bytes(raw)), _usage(resp)
        raise ProviderError("no image in response")

    # ---------- speech and video (submission video build + Vinny/ARIA crew radio + Omni arrival clip) ----------
    def _client_for(self, settings: dict) -> genai.Client:
        """A client on the job's api_version (TTS and video use the Interactions API on v1beta)."""
        if not settings.get("api_version"):
            return _get_client()
        _get_client()  # checks the key is set
        return genai.Client(api_key=os.environ[key_var()],
                            http_options={"api_version": settings["api_version"],
                                          "timeout": int(float(settings.get("timeout_s", 90)) * 1000)})

    def speak(self, text: str, settings: dict) -> tuple[bytes, Usage]:
        """Text to speech: one WAV (24 kHz mono 16-bit). `style` goes in speech_metadata, never in the text."""
        content = {"type": "text", "text": text}
        if settings.get("style"):
            content["annotations"] = [{"type": "speech_metadata", "style": settings["style"]}]
        try:
            r = self._client_for(settings).interactions.create(
                model=self.model, input=[{"type": "user_input", "content": [content]}],
                response_format={"type": "audio"},
                generation_config={"speech_config": [{"voice": settings.get("voice", "Charon")}]},
                store=False)
        except Exception as e:  # noqa: BLE001 - surface every SDK error the same way
            raise ProviderError(f"speak: {e}") from e
        audio = getattr(r, "output_audio", None)
        if not audio or not audio.data:
            raise ProviderError("speak: no audio in response")
        data = audio.data if isinstance(audio.data, bytes) else base64.b64decode(audio.data)
        return data, Usage()

    def generate_speech(
        self, turns: list[dict], speakers: list[dict], settings: dict
    ) -> tuple[bytes, Usage]:
        """Synthesize single- or multi-speaker 24kHz WAV via Gemini 3.8 TTS Interactions API."""
        var = key_var()
        if not os.environ.get(var):
            raise ProviderError(f"{var} is not set; add it to .env")
        api_ver = settings.get("api_version", "v1beta")
        timeout_ms = int(settings.get("timeout_s", 45)) * 1000
        tts_client = genai.Client(
            api_key=os.environ[var],
            http_options=types.HttpOptions(api_version=api_ver, timeout=timeout_ms),
        )
        content: list[dict] = []
        multi = len(speakers) > 1
        for t in turns:
            ann: dict[str, str] = {"type": "speech_metadata"}
            if multi and t.get("speaker"):
                ann["speaker"] = str(t["speaker"])
            if t.get("style"):
                ann["style"] = str(t["style"])
            content.append({
                "type": "text",
                "text": str(t["text"]),
                "annotations": [ann],
            })

        if multi:
            speech_cfg: dict | list = {
                "speakers": [{"speaker": s["speaker"], "voice": s["voice"]} for s in speakers]
            }
        else:
            voice = speakers[0]["voice"] if speakers else "Puck"
            speech_cfg = [{"voice": voice}]

        models_to_try = [self.model]
        if self.model == "gemini-3.8-flash-tts":
            models_to_try.append("gemini-3.8-flash-lite-tts")

        last_err: Exception | None = None
        for mdl in models_to_try:
            try:
                interaction = tts_client.interactions.create(
                    model=mdl,
                    input=[{"type": "user_input", "content": content}],
                    response_format={"type": "audio"},
                    generation_config={"speech_config": speech_cfg},
                )
                out_aud = getattr(interaction, "output_audio", None)
                if out_aud and getattr(out_aud, "data", None):
                    raw = out_aud.data
                    wav_bytes = base64.b64decode(raw) if isinstance(raw, str) else bytes(raw)
                    u = getattr(interaction, "usage", None)
                    usage = Usage(
                        tokens_in=getattr(u, "total_input_tokens", None) if u else None,
                        tokens_out=getattr(u, "total_output_tokens", None) if u else None,
                    )
                    return wav_bytes, usage
                for step in getattr(interaction, "steps", None) or []:
                    if getattr(step, "type", None) == "model_output":
                        for c in getattr(step, "content", None) or []:
                            if getattr(c, "type", None) == "audio" and getattr(c, "data", None):
                                raw = c.data
                                return (base64.b64decode(raw) if isinstance(raw, str) else bytes(raw)), Usage()
                raise ProviderError(f"TTS model {mdl} returned no audio block")
            except Exception as e:
                last_err = e
                continue
        raise ProviderError(f"TTS {type(last_err).__name__}: {last_err}") from last_err

    def generate_video(
        self,
        prompt: str,
        settings: dict,
        first_frame: Media | None = None,
        last_frame: Media | None = None,
        refs: list[Media] | None = None,
    ) -> tuple[bytes, Usage]:
        """Generate MP4 video (text-to-video or first+last frame transitions) via Gemini Omni 1.2 Flash."""
        vid_client = self._client_for({**settings, "api_version": settings.get("api_version", "v1beta"), "timeout_s": settings.get("timeout_s", 300)})

        def _norm_uri(uri: str) -> str:
            import re as _re
            m_id = _re.search(r"files/([a-zA-Z0-9\-_]+)", uri or "")
            if m_id:
                return f"https://generativelanguage.googleapis.com/files/{m_id.group(1)}"
            return uri

        input_parts: list[dict] = []
        f1_uri: str | None = None
        f1_mime: str | None = None
        if first_frame is not None:
            f1 = self.upload_video(first_frame)
            f1_uri = _norm_uri(f1.uri)
            f1_mime = f1.mime_type or first_frame.mime
            input_parts.append({"type": "image", "uri": f1_uri, "mime_type": f1_mime})

        if last_frame is not None:
            if first_frame is not None and last_frame.sha256 == first_frame.sha256 and f1_uri:
                input_parts.append({"type": "image", "uri": f1_uri, "mime_type": f1_mime})
            else:
                f2 = self.upload_video(last_frame)
                input_parts.append({
                    "type": "image",
                    "uri": _norm_uri(f2.uri),
                    "mime_type": f2.mime_type or last_frame.mime,
                })

        for r in (refs or [])[:6]:
            rf = self.upload_video(r)
            input_parts.append({
                "type": "image" if r.kind == "image" else "video",
                "uri": _norm_uri(rf.uri),
                "mime_type": rf.mime_type or r.mime,
            })

        prompt_text = (prompt or "").strip()
        low = prompt_text.lower()
        if first_frame is not None and last_frame is not None:
            if "starting frame" not in low and "first frame" not in low:
                sep = "" if prompt_text.endswith((".", "!", "?")) else "."
                prompt_text = f"{prompt_text}{sep} Use the first image as the starting frame and the second image as the final frame."
        elif first_frame is not None:
            if "starting frame" not in low and "first frame" not in low:
                sep = "" if prompt_text.endswith((".", "!", "?")) else "."
                prompt_text = f"{prompt_text}{sep} Use this image as the starting frame."

        input_parts.append({"type": "text", "text": prompt_text})

        raw_dur = settings.get("duration") or (f"{int(settings['duration_s'])}s" if settings.get("duration_s") else "6s")
        duration = str(raw_dur)
        if not duration.endswith("s"):
            duration = f"{int(float(duration))}s"
        video_cfg: dict[str, str] = {
            "type": "video",
            "delivery": "uri",
            "aspect_ratio": str(settings.get("aspect_ratio", "16:9")),
            "duration": duration,
            "resolution": str(settings.get("resolution", "720p")),
        }

        try:
            interaction = vid_client.interactions.create(
                model=self.model,
                input=input_parts,
                response_format=video_cfg,
            )
            out_vid = getattr(interaction, "output_video", None)
            vid_uri = getattr(out_vid, "uri", None) if out_vid else None
            if not vid_uri:
                for step in getattr(interaction, "steps", None) or []:
                    if getattr(step, "type", None) == "model_output":
                        for c in getattr(step, "content", None) or []:
                            if getattr(c, "type", None) == "video" and getattr(c, "uri", None):
                                vid_uri = c.uri
                                break
            if not vid_uri:
                raise ProviderError(f"generate_video: no video in response (status {getattr(interaction, 'status', '?')})")
            video_bytes = vid_client.files.download(file=vid_uri)
            u = getattr(interaction, "usage", None)
            usage = Usage(
                tokens_in=getattr(u, "total_input_tokens", None) if u else None,
                tokens_out=getattr(u, "total_output_tokens", None) if u else None,
            )
            return bytes(video_bytes), usage
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"generate_video: {e}") from e
