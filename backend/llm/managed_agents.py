"""Managed Agents (`antigravity-preview-09-2026`) and Track B `plan` job helpers.

Lives inside `backend/llm/` so no file outside `backend/llm/` imports a model SDK,
and avoids touching `backend/llm/__init__.py` or `gemini.py` while parallel sessions
work in their own branches.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from . import CACHE_DIR, GLOBAL_LOG, Job, LLMError, _append_failure, _load_env, _log_lock, for_job, load_config
from .base import ProviderError
from .gemini import GeminiProvider, _get_client, key_var

DEFAULT_PLAN_SPEC = "gemini:gemini-4-neon"
DEFAULT_PLAN_FALLBACK_SPEC = "gemini:gemini-4-argon"
DEFAULT_MANAGED_AGENT = "antigravity-preview-09-2026"
DEFAULT_MANAGED_AGENT_MODEL = "gemini-4-neon"


def has_api_key() -> bool:
    """Return True if the active Gemini API key env var is populated."""
    _load_env()
    return bool(os.environ.get(key_var()))


def plan_job(name: str = "plan", run_dir: Path | str | None = None) -> Job:
    """Return configured `Job` for `plan` (or `plan_fallback`), even if `models.toml` hasn't merged it yet."""
    _load_env()
    cfg = load_config()
    if name in cfg.get("jobs", {}):
        return for_job(name, run_dir=run_dir)

    default_spec = DEFAULT_PLAN_FALLBACK_SPEC if "fallback" in name else DEFAULT_PLAN_SPEC
    spec = os.environ.get(f"MODEL_{name.upper()}") or default_spec
    provider_name, _, model_id = spec.partition(":")
    if provider_name != "gemini":
        raise ValueError(f"unsupported provider {provider_name!r} in {spec!r}")
    settings = {**cfg.get("defaults", {}), "thinking": "medium"}
    return Job(name, spec, GeminiProvider(model_id), settings, Path(run_dir) if run_dir else None)


def _sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _log_agent_call(run_dir: Path | None, **entry: Any) -> None:
    rec = {"ts": _dt.datetime.now().isoformat(timespec="seconds"), **entry}
    line = json.dumps(rec) + "\n"
    targets = [GLOBAL_LOG] + ([run_dir / "calls.jsonl"] if run_dir else [])
    with _log_lock:
        for p in targets:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(line)


def run_managed_agent(
    prompt: str,
    *,
    run_dir: Path | str | None = None,
    label: str = "managed_agent",
    agent_id: str | None = None,
    agent_model: str | None = None,
    timeout_s: float | None = None,
    poll_interval_s: float = 2.0,
) -> dict[str, Any]:
    """Run a Gemini Managed Agent (`antigravity-preview-09-2026`) in a remote Linux sandbox (`v1beta`).

    Uses `background=True` and `environment="remote"` via the Interactions API and polls
    until completion, caching and logging in the same format as `backend/llm/__init__.py`.
    """
    _load_env()
    cfg = load_config()
    job_cfg = dict(cfg.get("jobs", {}).get("managed_agent", {}))
    defaults = dict(cfg.get("defaults", {}))

    raw_spec = os.environ.get("MODEL_MANAGED_AGENT") or job_cfg.get("model") or f"gemini:{DEFAULT_MANAGED_AGENT}"
    _, _, default_agent = raw_spec.partition(":")
    agent = agent_id or default_agent or DEFAULT_MANAGED_AGENT
    underlying_model = (
        agent_model
        or os.environ.get("MODEL_MANAGED_AGENT_MODEL")
        or job_cfg.get("agent_model")
        or DEFAULT_MANAGED_AGENT_MODEL
    )
    api_version = str(job_cfg.get("api_version") or "v1beta")
    max_wait = float(timeout_s or job_cfg.get("timeout_s") or max(150.0, float(defaults.get("timeout_s", 90))))
    rd = Path(run_dir) if run_dir else None

    cache_key = _sha({
        "job": "managed_agent",
        "agent": agent,
        "agent_model": underlying_model,
        "api_version": api_version,
        "prompt": _sha(prompt),
    })
    cache_path = CACHE_DIR / f"{cache_key}.json"
    if cache_path.exists():
        cached_val = json.loads(cache_path.read_text(encoding="utf-8"))["value"]
        _log_agent_call(
            rd,
            job="managed_agent",
            provider="gemini",
            model=agent,
            agent_model=underlying_model,
            kind="managed_agent",
            file=label,
            cache="hit",
            valid=True,
            latency_s=0.0,
        )
        return cached_val

    t0 = time.time()
    try:
        client = _get_client()
        create_kwargs: dict[str, Any] = {
            "agent": agent,
            "input": prompt,
            "environment": "remote",
            "background": True,
            "api_version": api_version,
        }
        if agent.startswith("antigravity"):
            create_kwargs["agent_config"] = {
                "type": "antigravity",
                "model": underlying_model,
            }

        interaction = client.interactions.create(**create_kwargs)
        inter_id = getattr(interaction, "id", None)
        status = getattr(interaction, "status", None)

        while status not in ("completed", "failed", "cancelled"):
            if time.time() - t0 > max_wait:
                raise ProviderError(f"Managed agent {agent} ({inter_id}) timed out after {max_wait:.0f}s (status={status})")
            time.sleep(poll_interval_s)
            interaction = client.interactions.get(inter_id, api_version=api_version)
            status = getattr(interaction, "status", None)

        if status != "completed":
            err_detail = getattr(interaction, "error", None) or status
            raise ProviderError(f"Managed agent {agent} ended with status={status}: {err_detail}")

        output_text = getattr(interaction, "output_text", None) or ""
        env_id = getattr(interaction, "environment_id", None)
        usage_obj = getattr(interaction, "usage", None)
        tokens_in = getattr(usage_obj, "total_input_tokens", None) if usage_obj else None
        tokens_out = getattr(usage_obj, "total_output_tokens", None) if usage_obj else None

        result = {
            "output_text": output_text,
            "interaction_id": inter_id,
            "environment_id": env_id,
            "agent": agent,
            "agent_model": underlying_model,
            "status": status,
        }
        latency = round(time.time() - t0, 2)
        _log_agent_call(
            rd,
            job="managed_agent",
            provider="gemini",
            model=agent,
            agent_model=underlying_model,
            kind="managed_agent",
            interaction_id=inter_id,
            environment_id=env_id,
            file=label,
            cache="miss",
            valid=True,
            latency_s=latency,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_DIR / f"{cache_key}.{threading.get_ident()}.tmp"
        tmp.write_text(json.dumps({"value": result}), encoding="utf-8")
        os.replace(tmp, cache_path)
        return result
    except Exception as exc:
        latency = round(time.time() - t0, 2)
        msg = str(exc)
        _log_agent_call(
            rd,
            job="managed_agent",
            provider="gemini",
            model=agent,
            agent_model=underlying_model,
            kind="managed_agent",
            file=label,
            cache="miss",
            valid=False,
            latency_s=latency,
            error=msg[:300],
        )
        _append_failure(f"managed_agent ({agent}/{underlying_model}) failed: {msg}", label)
        raise LLMError(f"managed_agent failed on {label}: {msg}") from exc
