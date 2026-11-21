"""Tests for Vinny NYC Foreman TTS (`foreman.py`), Element 119 Media-Out (`render.py`),
and Chaos 1-Call LLM / Bedroom Baselines (`eval/` + `eval_api.py`).
"""
from __future__ import annotations

import io
import json
import struct
import wave
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from backend import foreman, labels, render, solver
from backend.app import app
from eval.baseline_bedroom import run_bedroom_baseline
from eval.baseline_single_call import run_single_call_baseline

ROOT = Path(__file__).resolve().parents[1]


def _make_dummy_wav(duration_s: float = 14.8, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    n_frames = int(duration_s * rate)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack("<h", 0) * n_frames)
    return buf.getvalue()


def _make_dummy_png(color: tuple[int, int, int] = (40, 90, 160)) -> bytes:
    im = Image.new("RGB", (640, 360), color=color)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_foreman_dialogue_verified_vs_violating():
    sample = json.loads((ROOT / "data" / "sample_venue.json").read_text(encoding="utf-8"))
    verified_plan = solver.solve(sample)
    d_ok = foreman.build_foreman_dialogue(verified_plan)
    assert d_ok["violation_count"] == 0
    assert len(d_ok["turns"]) == 3
    assert d_ok["turns"][0]["speaker"] == "Vinny"
    assert d_ok["turns"][1]["speaker"] == "ARIA"
    assert "zero violations" in d_ok["turns"][0]["text"].lower()

    chaos_plan = run_single_call_baseline(sample, use_live_llm=False)
    assert chaos_plan["score"]["violation_count"] > 0
    d_bad = foreman.build_foreman_dialogue(chaos_plan)
    assert d_bad["violation_count"] > 0
    assert "violations" in d_bad["turns"][0]["text"].lower()


def test_foreman_api_with_mocked_tts(monkeypatch, tmp_path):
    monkeypatch.setattr(foreman, "RENDER_ASSET_DIR", tmp_path)
    monkeypatch.setattr(render, "RENDER_DIR", tmp_path)

    class DummyTTSJob:
        class provider:
            model = "gemini-3.8-flash-tts"

        def generate_speech(self, turns, speakers, prompt_version="tts_v1", label=None):
            assert len(turns) == 3
            assert len(speakers) == 2
            return _make_dummy_wav(15.0)

    monkeypatch.setattr(foreman, "for_job", lambda name, rd=None: DummyTTSJob())
    client = TestClient(app)
    resp = client.post("/render/foreman", json={"run_id": "sample_venue"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert 14.0 <= body["duration_s"] <= 16.0
    assert body["audio_url"].startswith("/render/asset/")

    wav_resp = client.get(body["audio_url"])
    assert wav_resp.status_code == 200
    assert wav_resp.headers["content-type"].startswith("audio/wav")


def test_render_arrival_and_timelapse_routes(monkeypatch, tmp_path):
    monkeypatch.setattr(render, "RENDER_DIR", tmp_path)
    monkeypatch.setattr(render, "NYPENN_DIR", tmp_path / "empty_nypenn")

    class DummyMediaJob:
        def __init__(self, model_name: str):
            self.provider = type("P", (), {"model": model_name})()

        def generate_image(self, prompt, refs=None, label=None):
            return _make_dummy_png((120, 150, 200) if refs else (80, 100, 120))

        def generate_video(self, prompt, first_frame=None, last_frame=None, **kwargs):
            assert first_frame is not None and last_frame is not None
            return b"\x00\x00\x00\x18ftypmp42" + (b"\x00" * 4096)

    monkeypatch.setattr(
        render,
        "for_job",
        lambda name, rd=None: DummyMediaJob(
            "gemini-nano-banana-2.1" if name == "image" else "gemini-omni-1.2-flash"
        ),
    )

    client = TestClient(app)
    r1 = client.post("/render/arrival", json={"run_id": "sample_venue"})
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["ok"] is True
    assert b1["illustrative"] is True
    assert (tmp_path / b1["before_asset"]).exists()
    assert (tmp_path / b1["after_asset"]).exists()

    # Sync timelapse render verification
    sync_out = render.render_timelapse_sync(b1["before_asset"], b1["after_asset"], duration_s=6)
    assert sync_out["ok"] is True
    assert sync_out["video_url"].startswith("/render/asset/")

    # Cached job pickup via HTTP
    r2 = client.post(
        "/render/timelapse/start",
        json={"before_asset": b1["before_asset"], "after_asset": b1["after_asset"], "duration_s": 6},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "completed"


def test_eval_chaos_and_summary_routes():
    client = TestClient(app)
    c_resp = client.post("/eval/chaos-plan", json={"run_id": "sample_venue", "use_live_llm": False})
    assert c_resp.status_code == 200
    c_plan = c_resp.json()
    assert c_plan["score"]["valid"] is False
    assert c_plan["score"]["violation_count"] > 10

    s_resp = client.get("/eval/summary?run_id=sample_venue")
    assert s_resp.status_code == 200
    rows = s_resp.json()["rows"]
    assert len(rows) == 4
    assert rows[0]["violations"] == 0
    assert rows[1]["violations"] > 0

    sample = json.loads((ROOT / "data" / "sample_venue.json").read_text(encoding="utf-8"))
    bed = run_bedroom_baseline(sample)
    assert bed["overflow_piece_count"] > 0

    solved = solver.solve(sample)
    box_labels = labels.extract_box_labels(solved)
    assert len(box_labels) > 0
    assert all(b["placement_surface"] == "top" and "MOUNT:TOP-FLAPS" in b["qr_payload"] for b in box_labels)
