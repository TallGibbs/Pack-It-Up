"""Tests for deleting uploaded media from a run on the Film page."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app
from backend.ingest import common
from backend.ingest.common import write_json
from backend.ingest.intake import intake
from backend.ingest.pipeline import rebuild


def _fake_perception(file_name: str, sha: str, room_id: str, label: str, catalog_id: str, qty: int = 1) -> dict:
    return {
        "file": file_name,
        "sha256": sha,
        "kind": "image",
        "room_id": room_id,
        "model": "gemini:test",
        "prompt_version": "perceive_v3",
        "room_guess": "living room",
        "scale_refs": ["door (80 in)"],
        "items": [
            {
                "label": label,
                "catalog_id": catalog_id,
                "seat_class": "none",
                "quantity": qty,
                "stack_count": 1,
                "move_class": "movable",
                "est_dims_in": [36, 36, 36],
                "dims_basis": "door",
                "material": "upholstered",
                "est_weight_lb": 75,
                "fragile": False,
                "must_stay_upright": False,
                "disassemble": False,
                "two_person": False,
                "stackable": False,
                "partially_visible": False,
                "confidence": 0.9,
                "heard_only": False,
                "evidence": {"box_2d": [100, 100, 500, 500]},
            }
        ],
        "containers": [],
        "uncertain": [],
        "transcript": [],
        "spoken_facts": [],
    }


def _make_jpeg(path: Path, color: tuple[int, int, int]) -> Path:
    from PIL import Image

    img = Image.new("RGB", (64, 64), color)
    img.save(path, "JPEG")
    return path


def test_delete_one_of_two_uploaded_files_rebuilds_inventory(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "RUNS_DIR", tmp_path / "runs")
    src = tmp_path / "src"
    src.mkdir()
    p1 = _make_jpeg(src / "good.jpg", (200, 40, 40))
    p2 = _make_jpeg(src / "mistake.jpg", (40, 40, 200))

    run_id = "20261121-161000-test-a1b2c3"
    manifest = intake([p1, p2], "Living Room", run_id)
    rd = common.run_dir(run_id)
    by_name = {f["name"]: f for f in manifest["files"]}

    write_json(
        rd / "perception" / "good.jpg.json",
        _fake_perception("good.jpg", by_name["good.jpg"]["sha256"], "living_room", "3-seat sofa", "sofa_3seat", 1),
    )
    write_json(
        rd / "perception" / "mistake.jpg.json",
        _fake_perception("mistake.jpg", by_name["mistake.jpg"]["sha256"], "living_room", "dining table", "dining_table_6", 1),
    )
    common.update_status(
        rd,
        stage="done",
        files={
            "good.jpg": {"perceive": "done", "items": 1, "seconds": 2.0},
            "mistake.jpg": {"perceive": "done", "items": 1, "seconds": 2.1},
        },
    )
    inv0 = rebuild(run_id)
    assert inv0["totals"]["item_count"] == 2

    client = TestClient(app)
    res = client.delete(f"/runs/{run_id}/files/mistake.jpg")
    assert res.status_code == 200
    body = res.json()
    assert "mistake.jpg" not in body["status"]["files"]
    assert "good.jpg" in body["status"]["files"]
    assert body["inventory"]["totals"]["item_count"] == 1
    labels = [it["label"] for it in body["inventory"]["rooms"][0]["items"]]
    assert labels == ["3-seat sofa"]
    assert not (rd / "perception" / "mistake.jpg.json").exists()
    assert not (rd / by_name["mistake.jpg"]["path"]).exists()

    # Deleting a missing file returns 404; bad names are rejected.
    assert client.delete(f"/runs/{run_id}/files/mistake.jpg").status_code == 404
    assert client.delete(f"/runs/{run_id}/files/..").status_code in (400, 404, 405)
    assert client.delete(f"/runs/{run_id}/files/%2E%2E").status_code in (400, 404, 405)

    # Deleting the last remaining file resets the move cleanly so the user can re-upload.
    res2 = client.delete(f"/runs/{run_id}/files/good.jpg")
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["rooms"] == []
    assert body2["status"]["files"] == {}
    assert body2["status"]["stage"] == "created"
    assert "inventory" not in body2
    assert not (rd / "inventory.json").exists()
