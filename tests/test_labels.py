"""Tests for Stage B10 (Offline Self-Contained QR Box Labels) and Stretch A6 (Photo Box Matcher)."""
from __future__ import annotations

import ast
import io
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

import backend.llm as llm_mod
from backend import labels, labels_api, solver
from backend.llm.base import Usage
from backend.llm.gemini import GeminiProvider

ROOT = Path(__file__).resolve().parents[1]


def _isolate_llm(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(llm_mod, "CACHE_DIR", tmp_path / "cache_llm")
    monkeypatch.setattr(llm_mod, "GLOBAL_LOG", tmp_path / "calls.jsonl")
    monkeypatch.setattr(llm_mod, "FAILURES", tmp_path / "FAILURES.md")


def test_no_sdk_imports_in_labels_modules() -> None:
    """AGENTS.md rule: no file outside backend/llm/ imports google-genai."""
    for rel in ("backend/labels.py", "backend/labels_api.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("google"), f"{rel} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("google"), f"{rel} imports from {node.module}"


def test_b10_qr_encoder_versions_and_manifest_bounds() -> None:
    # Short Version 1 payload (21x21)
    m1 = labels.encode_qr_matrix("Main 1")
    assert len(m1) == 21 and len(m1[0]) == 21

    # Version 10 payload (>230 bytes -> 57x57 with 16-bit count & 2 RS block groups)
    long_payload = "PACK IT UP · " + (" Vase x3, Books x12," * 12)
    assert 235 <= len(long_payload.encode("utf-8")) <= 270
    m10 = labels.encode_qr_matrix(long_payload)
    assert len(m10) == 57 and len(m10[0]) == 57

    svg = labels.qr_svg("Lounge 2")
    assert svg.startswith("<svg ") and "viewBox=" in svg and "<path d=" in svg

    png = labels.qr_png_bytes("Lounge 2", scale=6)
    img = Image.open(io.BytesIO(png))
    assert img.size == ((21 + 8) * 6, (21 + 8) * 6)

    # Manifest formatter caps oversized contents cleanly and never emits http:// links
    huge_box = {
        "short_name": "Lounge 4",
        "fragile": True,
        "must_stay_upright": True,
        "two_person": False,
        "room_name": "Malin Lounge",
        "dock_stop": 2,
        "dest_zone_name": "Trackside Espresso & Cafe Storefront",
        "truck_index": 0,
        "load_seq": 14,
        "unload_seq": 38,
        "weight_lb": 35.0,
        "contents": ", ".join(f"espresso cup set #{i}" for i in range(40)),
    }
    manifest = labels.format_qr_manifest(huge_box)
    assert len(manifest.encode("utf-8")) <= labels.MAX_QR_BYTES
    assert "Lounge 4" in manifest
    assert "FRAGILE" in manifest
    assert "Stop 2" in manifest
    assert "http" not in manifest.lower()


def test_b10_sample_venue_labels_bundle() -> None:
    sample = json.loads((ROOT / "data" / "sample_venue.json").read_text(encoding="utf-8"))
    plan = solver.solve(sample, strategy={"downsize_last_truck": True})
    bundle = labels.build_labels(plan, run_id="sample_venue")

    assert bundle["box_count"] == 42
    assert bundle["count"] == 42
    short_names = [b["short_name"] for b in bundle["labels"]]
    assert len(set(short_names)) == 42  # every box gets a distinct marker short name

    stops = [b["dock_stop"] for b in bundle["labels"]]
    assert stops == sorted(stops)  # ordered by Penn Station dock stop 1..6

    for b in bundle["labels"]:
        assert b["qr_bytes_len"] <= labels.MAX_QR_BYTES
        assert b["qr_svg"].startswith("<svg ")
        assert b["short_name"] in b["qr_text"]


def test_a6_identify_box_from_photo_with_decisions_api_and_other_catchall(monkeypatch, tmp_path: Path) -> None:
    _isolate_llm(monkeypatch, tmp_path)

    mock_inv = json.loads((ROOT / "frontend" / "mock" / "inventory.json").read_text(encoding="utf-8"))
    plan = solver.solve(mock_inv)
    bundle = labels.build_labels(plan, run_id="mock-demo")
    target = bundle["labels"][0]

    img = Image.new("RGB", (120, 90), (210, 180, 140))
    ImageDraw.Draw(img).text((10, 35), target["short_name"], fill=(10, 10, 10))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    photo_bytes = buf.getvalue()

    # 1. Hydrogen perceives marker text + dent; Decision 1 matches target box_id
    monkeypatch.setattr(
        GeminiProvider,
        "generate_json",
        lambda self, prompt, media, schema, settings: (
            {
                "written_text": target["short_name"],
                "tape_or_color": target["color_name"],
                "size_guess": "medium",
                "visible_contents": "",
                "damaged": True,
                "damage_note": "Minor corner crease on top flap",
            },
            Usage(tokens_in=280, tokens_out=32),
        ),
    )
    monkeypatch.setattr(
        GeminiProvider,
        "decide",
        lambda self, question, media, options, settings: (
            {
                "answer": target["box_id"],
                "confidence": 0.91,
                "rationale": "Exact short_name match",
                "probabilities": {target["box_id"]: 0.91, "other": 0.09},
            },
            Usage(tokens_in=340, tokens_out=0),
        ),
    )

    res = labels.identify_box_from_photo(photo_bytes, "image/jpeg", bundle["labels"], run_dir_path=tmp_path)
    assert res["matched"] is True
    assert res["box_id"] == target["box_id"]
    assert res["confidence"] == 0.91
    assert res["observation"]["damaged"] is True
    assert res["box"]["short_name"] == target["short_name"]

    # 2. Decision 1 answers "other" -> matched=False
    img2 = Image.new("RGB", (120, 90), (90, 90, 90))
    buf2 = io.BytesIO()
    img2.save(buf2, format="JPEG")
    monkeypatch.setattr(
        GeminiProvider,
        "decide",
        lambda self, question, media, options, settings: (
            {
                "answer": "other",
                "confidence": 0.84,
                "rationale": "Unmarked box",
                "probabilities": {"other": 0.84},
            },
            Usage(tokens_in=340, tokens_out=0),
        ),
    )
    res_none = labels.identify_box_from_photo(buf2.getvalue(), "image/jpeg", bundle["labels"], run_dir_path=tmp_path)
    assert res_none["matched"] is False
    assert res_none["box"] is None


def test_labels_api_endpoints(monkeypatch, tmp_path: Path) -> None:
    _isolate_llm(monkeypatch, tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(llm_mod, "_env_loaded", True)
    monkeypatch.setattr("backend.llm.gemini._client", None)

    app = FastAPI()
    app.include_router(labels_api.router)
    client = TestClient(app)

    r = client.get("/labels/mock-demo")
    assert r.status_code == 200
    data = r.json()
    assert data["box_count"] >= 2
    first = data["labels"][0]

    r_png = client.get(f"/labels/mock-demo/{first['box_id']}/qr.png")
    assert r_png.status_code == 200
    assert r_png.headers["content-type"] == "image/png"
    assert len(r_png.content) > 200

    img_buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 175, 135)).save(img_buf, format="JPEG")
    r_id = client.post(
        "/labels/mock-demo/identify",
        data={"hint": first["short_name"]},
        files={"file": ("box.jpg", img_buf.getvalue(), "image/jpeg")},
    )
    assert r_id.status_code == 200
    out = r_id.json()
    assert out["matched"] is True
    assert out["box"]["box_id"] == first["box_id"]
