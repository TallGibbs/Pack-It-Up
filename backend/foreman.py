"""Vinny the NYC Mover + ARIA Physics Verifier: 15-second crew radio briefing.

Uses Gemini 3.8 Flash TTS (`for_job("tts")`) multi-speaker synthesis with
turn-level `speech_metadata` acting styles and inline vocal tags (`<laugh>`,
`<short pause>`) grounded in the exact solved truck fleet, Penn Station LIFO
dock stops, axle balance, and fragile/two-person handling rules.
"""
from __future__ import annotations

import hashlib
import io
import json
import time
import wave
from pathlib import Path
from typing import Any

from backend import solver
from backend.llm import LLMError, for_job

ROOT = Path(__file__).resolve().parents[1]
RENDER_ASSET_DIR = ROOT / ".cache" / "renders"

SPEAKERS = [
    {"speaker": "Vinny", "voice": "Puck"},
    {"speaker": "ARIA", "voice": "Kore"},
]


def _clean_item_name(label: str) -> str:
    raw = (label or "heavy piece").split("(")[0].split("—")[0].strip()
    # Strip trailing multiplier like "x10" for natural speech
    parts = raw.split()
    if parts and parts[-1].lower().startswith("x") and parts[-1][1:].isdigit():
        cnt = parts[-1][1:]
        base = " ".join(parts[:-1])
        return f"stack of {cnt} {base}"
    return raw[:42]


def build_foreman_dialogue(plan: dict[str, Any]) -> dict[str, Any]:
    """Build a tight ~15-second (~38-44 word) 3-turn NYC mover radio script from a solved plan."""
    trucks = plan.get("trucks") or []
    score_block = plan.get("score") or {}
    summary = plan.get("summary") or {}
    violations = score_block.get("violations") or []

    truck_count = len(trucks) or int(summary.get("truck_count") or 1)
    first_truck_name = (trucks[0].get("name") if trucks else "U-Haul 26-foot") or "U-Haul 26-foot"
    feet = "twenty-six-foot" if "26" in first_truck_name else (
        "twenty-foot" if "20" in first_truck_name else (
            "fifteen-foot" if "15" in first_truck_name else "ten-foot"
        )
    )
    fleet_phrase = (
        f"one {feet} truck" if truck_count == 1 else f"{truck_count} {feet} trucks"
    )

    all_items = [it for t in trucks for it in (t.get("items") or [])]
    total_pcs = len(all_items) or int(summary.get("placed_items") or 0)

    # Pick signature heavy cab-wall item and delicate/upright item
    heavy_item = None
    fragile_item = None
    stop1_zone = "Stop One Kiosk"
    for it in all_items:
        if not it.get("is_box"):
            if heavy_item is None or float(it.get("weight_lb") or 0) > float(heavy_item.get("weight_lb") or 0):
                heavy_item = it
            if (it.get("fragile") or it.get("must_stay_upright")) and fragile_item is None:
                fragile_item = it
        if int(it.get("dock_stop") or 99) == 1 and it.get("dest_zone_name"):
            stop1_zone = str(it["dest_zone_name"]).replace("Concourse ", "").replace("Storefront", "").strip()

    heavy_lbl = _clean_item_name(heavy_item["label"]) if heavy_item else "communal table"
    fragile_lbl = _clean_item_name(fragile_item["label"]) if fragile_item else "glass monitor"

    bal_pct = 50
    if trucks:
        lr = (trucks[0].get("metrics") or {}).get("left_weight_ratio")
        if isinstance(lr, (int, float)):
            bal_pct = int(round(float(lr) * 100))
        elif isinstance(score_block.get("left_right_ratio"), (int, float)):
            bal_pct = int(round(float(score_block["left_right_ratio"]) * 100))

    if len(violations) == 0:
        turns = [
            {
                "speaker": "Vinny",
                "style": "gruff, rapid-fire, energetic Brooklyn NYC moving boss on a walkie-talkie, speaking fast",
                "text": (
                    f"Yo crew! {fleet_phrase.capitalize()} to Penn Station — {total_pcs} pieces, zero violations! "
                    f"Pin that {heavy_lbl} cab-wall first, baby the {fragile_lbl}!"
                ),
            },
            {
                "speaker": "ARIA",
                "style": "crisp, brisk, confident physics load engineer, fast pace",
                "text": (
                    f"Axle balance {bal_pct} percent. {stop1_zone} rides last at the rear door for instant unload."
                ),
            },
            {
                "speaker": "Vinny",
                "style": "upbeat, fast NYC crew boss",
                "text": "<laugh> Beautiful! Skip the FDR — Thirty-First Street dock, roll out!",
            },
        ]
    else:
        v_cnt = len(violations)
        turns = [
            {
                "speaker": "Vinny",
                "style": "alarmed, rapid-fire Brooklyn NYC moving boss on a walkie-talkie, speaking fast",
                "text": (
                    f"Whoa, hold the ramp! {v_cnt} physics violations — boxes floating in mid-air "
                    f"and crushing the {fragile_lbl}!"
                ),
            },
            {
                "speaker": "ARIA",
                "style": "urgent, brisk physics load engineer, fast pace",
                "text": (
                    f"Load rejected. Switch back to Pack It Up Verified before hitting a Midtown pothole."
                ),
            },
            {
                "speaker": "Vinny",
                "style": "gruff, fast NYC crew boss",
                "text": "Nobody touches the brakes till we re-pack this right!",
            },
        ]

    transcript = " ".join(f"{t['speaker']}: {t['text']}" for t in turns)
    return {
        "turns": turns,
        "speakers": SPEAKERS,
        "transcript": transcript,
        "violation_count": len(violations),
        "truck_count": truck_count,
        "piece_count": total_pcs,
    }


def _wav_duration_seconds(wav_bytes: bytes) -> float:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or 24000
            return round(frames / float(rate), 2)
    except Exception:
        # 24kHz 16-bit mono WAV ~ 48,000 bytes/sec
        return round(max(1.0, (len(wav_bytes) - 44) / 48000.0), 2)


def generate_foreman_briefing(
    plan: dict[str, Any] | None = None,
    inventory: dict[str, Any] | None = None,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    """Synthesize (or serve cached) 15s Vinny + ARIA crew radio WAV via Gemini 3.8 Flash TTS."""
    if plan is None:
        if inventory is None:
            sample = json.loads((ROOT / "data" / "sample_venue.json").read_text(encoding="utf-8"))
            plan = solver.solve(sample)
        else:
            plan = solver.solve(inventory)

    dialogue = build_foreman_dialogue(plan)
    RENDER_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(
        json.dumps({"turns": dialogue["turns"], "speakers": dialogue["speakers"]}, sort_keys=True).encode()
    ).hexdigest()[:20]
    wav_name = f"vinny_foreman_{digest}.wav"
    wav_path = RENDER_ASSET_DIR / wav_name

    t0 = time.time()
    cached = wav_path.exists() and wav_path.stat().st_size > 200
    job = for_job("tts", run_dir)
    if cached:
        wav_bytes = wav_path.read_bytes()
    else:
        try:
            wav_bytes = job.generate_speech(
                turns=dialogue["turns"],
                speakers=dialogue["speakers"],
                prompt_version="vinny_foreman_v1",
                label="vinny_foreman_radio",
            )
            tmp = RENDER_ASSET_DIR / f"{wav_name}.tmp"
            tmp.write_bytes(wav_bytes)
            tmp.replace(wav_path)
        except LLMError as e:
            return {
                "ok": False,
                "fallback_browser_tts": True,
                "error": str(e),
                "turns": dialogue["turns"],
                "speakers": dialogue["speakers"],
                "transcript": dialogue["transcript"],
                "model": job.provider.model,
            }

    dur_s = _wav_duration_seconds(wav_bytes)
    return {
        "ok": True,
        "cached": cached,
        "asset_name": wav_name,
        "audio_url": f"/render/asset/{wav_name}",
        "duration_s": dur_s,
        "size_bytes": len(wav_bytes),
        "turns": dialogue["turns"],
        "speakers": dialogue["speakers"],
        "transcript": dialogue["transcript"],
        "model": job.provider.model,
        "latency_s": round(time.time() - t0, 2),
    }
