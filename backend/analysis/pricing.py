"""Estimate what model calls cost, from the token counts in the call log and `prices.toml`.

An estimate at Google's list prices, not a bill:
- Cached calls replay a saved answer, log no tokens and so cost nothing here.
- A failed attempt logs no tokens; if Google billed it, it is missing from the total.
- Google's own discount for repeated input (implicit caching) is not in the log, so repeated input is
  counted at the full rate.
- An event or free-tier key may not be charged at all.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

PRICES_PATH = Path(__file__).with_name("prices.toml")
_cache: tuple[float, dict] | None = None


def table() -> dict:
    """prices.toml, re-read when the file changes so a price edit needs no restart."""
    global _cache
    try:
        mtime = PRICES_PATH.stat().st_mtime
        if _cache is None or _cache[0] != mtime:
            _cache = (mtime, tomllib.loads(PRICES_PATH.read_text(encoding="utf-8")))
        return _cache[1]
    except (OSError, tomllib.TOMLDecodeError):
        return {"models": {}}


def cost_usd(model: str | None, tokens_in, tokens_out, thoughts=0) -> float | None:
    """Dollars for these tokens on this model, or None when the model has no price on file."""
    p = table().get("models", {}).get(model or "")
    if p is None:
        return None
    return ((tokens_in or 0) * float(p.get("input", 0)) + ((tokens_out or 0) + (thoughts or 0)) * float(p.get("output", 0))) / 1e6


def summarize(rows: list[dict]) -> dict:
    """Total and per-model cost for rows that each have model, calls, live_calls, tokens_in, tokens_out and thoughts.
    Rows for the same model (one per job) are added together."""
    t = table()
    by_model: dict[str, dict] = {}
    for r in rows:
        m = by_model.setdefault(r["model"], {"model": r["model"], "calls": 0, "live_calls": 0, "tokens_in": 0,
                                             "tokens_out": 0, "thoughts": 0})
        for k in ("calls", "live_calls", "tokens_in", "tokens_out", "thoughts"):
            m[k] += r.get(k) or 0
    out, total, unpriced = [], 0.0, []
    for m in by_model.values():
        price = t.get("models", {}).get(m["model"])
        m["price_in"] = None if price is None else float(price.get("input", 0))
        m["price_out"] = None if price is None else float(price.get("output", 0))
        c = cost_usd(m["model"], m["tokens_in"], m["tokens_out"], m["thoughts"])
        m["cost_usd"] = None if c is None else round(c, 4)
        if c is None:
            if m["tokens_in"] or m["tokens_out"]:
                unpriced.append(m["model"])
        else:
            total += c
        out.append(m)
    out.sort(key=lambda m: (-(m["cost_usd"] or 0), m["model"] or ""))
    return {"total_usd": round(total, 4), "by_model": out, "unpriced": sorted(unpriced),
            "source": t.get("source"), "as_of": t.get("as_of")}
