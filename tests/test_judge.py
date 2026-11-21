"""Tests for multi-question Decisions API (`decide_batch`) and the two separate Final Judge steps:
  - Step 1: `backend/judge_plan.py` (Move Plan Judge)
  - Step 2: `backend/judge_rubric.py` (Hackathon Rubric Judge)
  - HTTP router: `backend/judge_api.py`
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

import backend.ingest.common as ingest_common
import backend.llm as llm_mod
from backend import judge_api, judge_plan, judge_rubric, solver
from backend.llm.base import Usage
from backend.llm.gemini import GeminiProvider

ROOT = Path(__file__).resolve().parents[1]


def _isolate_llm_cache(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(llm_mod, "CACHE_DIR", tmp_path / "cache_llm")
    monkeypatch.setattr(llm_mod, "GLOBAL_LOG", tmp_path / "calls.jsonl")
    monkeypatch.setattr(llm_mod, "FAILURES", tmp_path / "FAILURES.md")


def test_no_sdk_imports_outside_backend_llm() -> None:
    """AGENTS.md rule: no file outside backend/llm/ imports google-genai."""
    for rel in ("backend/judge_plan.py", "backend/judge_rubric.py", "backend/judge_api.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("google"), f"{rel} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("google"), f"{rel} imports from {node.module}"


def test_gemini_config_clamps_minimal_thinking_on_neon_and_hydrogen() -> None:
    """Builder Guide rule: Neon and Hydrogen reject `minimal` thinking with a validation error."""
    neon = GeminiProvider("gemini-4-neon")
    cfg_neon = neon._config({"thinking": "minimal"})
    assert str(cfg_neon.thinking_config.thinking_level).endswith("LOW")

    hydro = GeminiProvider("gemini-4-hydrogen")
    cfg_hydro = hydro._config({"thinking": "minimal"})
    assert str(cfg_hydro.thinking_config.thinking_level).endswith("LOW")

    carbon = GeminiProvider("gemini-4-carbon")
    cfg_carbon = carbon._config({"thinking": "minimal"})
    assert str(cfg_carbon.thinking_config.thinking_level).endswith("MINIMAL")


def test_decide_batch_native_and_structured_fallback(monkeypatch, tmp_path: Path) -> None:
    _isolate_llm_cache(monkeypatch, tmp_path)

    img_path = tmp_path / "arrival.png"
    Image.new("RGB", (32, 32), color=(40, 90, 140)).save(img_path)
    media = [llm_mod.media_from_path(img_path)]
    media[0].caption = "Arrival render preview"

    captured_call: dict = {}

    class FakeDecisions:
        def create(self, **kwargs):
            captured_call.update(kwargs)
            return SimpleNamespace(
                answers={
                    "has_risk": SimpleNamespace(type="noul", noul=0.08, confidence=0.92),
                    "route_to": SimpleNamespace(
                        type="choice",
                        choice="approve_dispatch",
                        probabilities={"approve_dispatch": 0.88, "replan_solver": 0.08, "other": 0.04},
                        confidence=0.88,
                    ),
                    "quality": SimpleNamespace(
                        type="score",
                        score=2.7,
                        probabilities={"0": 0.02, "1": 0.06, "2": 0.12, "3": 0.80},
                        legend={"0": "bad", "1": "weak", "2": "good", "3": "great"},
                        confidence=0.80,
                    ),
                },
                usage=SimpleNamespace(total_input_tokens=412, total_output_tokens=0),
            )

    monkeypatch.setattr("backend.llm.gemini._get_client", lambda: SimpleNamespace(decisions=FakeDecisions()))

    questions = {
        "has_risk": {"type": "noul", "instructions": "Any hazard?"},
        "route_to": {
            "type": "choice",
            "instructions": "Which route?",
            "criteria": {"approve_dispatch": "Safe", "replan_solver": "Unsafe", "other": "Unreadable"},
        },
        "quality": {
            "type": "score",
            "instructions": "Rate quality.",
            "criteria": ["bad", "weak", "good", "great"],
        },
    }

    out = llm_mod.for_job("judge").decide_batch("Shared inspection text", questions=questions, media=media)
    assert out["via"] == "decisions_api"
    assert captured_call["model"] == "models/gemini-decision-1"
    assert captured_call["api_version"] == "v1alpha"
    assert any(b.get("type") == "image" for b in captured_call["input"])
    assert any(b.get("type") == "text" and "Shared inspection text" in b.get("text", "") for b in captured_call["input"])

    ans = out["answers"]
    assert ans["has_risk"]["noul"] == 0.08 and ans["has_risk"]["answer"] is False
    assert ans["route_to"]["choice"] == "approve_dispatch"
    assert ans["quality"]["score"] == 2.7 and ans["quality"]["max_score"] == 3 and ans["quality"]["normalized"] == 0.9

    # Test structured JSON fallback path when DECIDE_FORCE_FALLBACK=1
    monkeypatch.setenv("DECIDE_FORCE_FALLBACK", "1")
    monkeypatch.setattr(
        GeminiProvider,
        "generate_json",
        lambda self, prompt, media, schema, settings: (
            {
                "answers": {
                    "has_risk": {"noul": 0.72, "confidence": 0.81},
                    "route_to": {"choice": "replan_solver", "confidence": 0.79},
                    "quality": {"score": 1.2, "confidence": 0.77},
                }
            },
            Usage(tokens_in=300, tokens_out=45),
        ),
    )
    fb_out = llm_mod.for_job("judge").decide_batch("Fallback check", questions=questions, media=[])
    assert fb_out["via"] == "generate_json_fallback"
    assert fb_out["answers"]["has_risk"]["answer"] is True
    assert fb_out["answers"]["route_to"]["choice"] == "replan_solver"
    assert fb_out["answers"]["quality"]["score"] == 1.2


def test_step1_move_plan_judge_valid_vs_broken_and_escalation(monkeypatch, tmp_path: Path) -> None:
    _isolate_llm_cache(monkeypatch, tmp_path)

    sample = json.loads((ROOT / "data" / "sample_venue.json").read_text(encoding="utf-8"))
    valid_plan = solver.solve(sample)

    arrival_img = tmp_path / "arrival.png"
    Image.new("RGB", (48, 48), color=(100, 120, 140)).save(arrival_img)

    # 1. High-confidence Decisions API pass on valid plan + arrival render -> approved without escalation
    def fake_high_conf_batch(self, input_text, media, questions, settings):
        assert "visual_render_matches_plan" in questions
        return (
            {
                "answers": {
                    "has_safety_or_damage_risk": {"type": "noul", "noul": 0.04, "answer": False, "confidence": 0.96},
                    "respects_user_instructions": {"type": "noul", "noul": 0.95, "answer": True, "confidence": 0.95},
                    "visual_render_matches_plan": {"type": "noul", "noul": 0.91, "answer": True, "confidence": 0.91},
                    "load_safety_score": {
                        "type": "score", "score": 3.8, "max_score": 4, "normalized": 0.95,
                        "probabilities": {"4": 0.85, "3": 0.15}, "legend": {}, "confidence": 0.85,
                    },
                    "penn_routing_lifo_score": {
                        "type": "score", "score": 3.6, "max_score": 4, "normalized": 0.90,
                        "probabilities": {"4": 0.70, "3": 0.30}, "legend": {}, "confidence": 0.78,
                    },
                    "mover_readiness_score": {
                        "type": "score", "score": 3.6, "max_score": 4, "normalized": 0.90,
                        "probabilities": {"4": 0.72, "3": 0.28}, "legend": {}, "confidence": 0.80,
                    },
                    "dispatch_action": {
                        "type": "choice",
                        "choice": "approve_dispatch",
                        "probabilities": {"approve_dispatch": 0.89, "ask_user_open_questions": 0.07, "replan_solver": 0.03, "other": 0.01},
                        "confidence": 0.89,
                    },
                }
            },
            Usage(tokens_in=850, tokens_out=0),
        )

    monkeypatch.setattr(GeminiProvider, "decide_batch", fake_high_conf_batch)
    res_ok = judge_plan.judge_move_plan(valid_plan, inventory=sample, arrival_image=arrival_img)
    assert res_ok["step"] == "move_plan_judge"
    assert res_ok["via"] == "decisions_api"
    assert res_ok["approved"] is True
    assert res_ok["escalated"] is False
    assert res_ok["recommended_action"] == "approve_dispatch"
    assert "visual_render_matches_plan" in res_ok["gates"]
    assert res_ok["judge_score_100"] >= 90.0

    # 2. Broken plan (10-ft truck leaves 3 upright items unplaced) -> triggers Neon escalation + working strategy patch
    broken_plan = solver.solve(sample, strategy={"truck_id": "uhaul_10"})
    assert broken_plan["score"]["valid"] is False

    def fake_flagged_batch(self, input_text, media, questions, settings):
        return (
            {
                "answers": {
                    "has_safety_or_damage_risk": {"type": "noul", "noul": 0.93, "answer": True, "confidence": 0.93},
                    "respects_user_instructions": {"type": "noul", "noul": 0.40, "answer": False, "confidence": 0.60},
                    "load_safety_score": {
                        "type": "score", "score": 0.8, "max_score": 4, "normalized": 0.20,
                        "probabilities": {"1": 0.80, "0": 0.20}, "legend": {}, "confidence": 0.80,
                    },
                    "penn_routing_lifo_score": {
                        "type": "score", "score": 2.0, "max_score": 4, "normalized": 0.50,
                        "probabilities": {"2": 0.70, "1": 0.30}, "legend": {}, "confidence": 0.70,
                    },
                    "mover_readiness_score": {
                        "type": "score", "score": 0.6, "max_score": 4, "normalized": 0.15,
                        "probabilities": {"1": 0.60, "0": 0.40}, "legend": {}, "confidence": 0.75,
                    },
                    "dispatch_action": {
                        "type": "choice",
                        "choice": "replan_solver",
                        "probabilities": {"replan_solver": 0.68, "approve_dispatch": 0.10, "ask_user_open_questions": 0.12, "other": 0.10},
                        "confidence": 0.68,
                    },
                }
            },
            Usage(tokens_in=900, tokens_out=0),
        )

    monkeypatch.setattr(GeminiProvider, "decide_batch", fake_flagged_batch)
    monkeypatch.setattr(
        GeminiProvider,
        "generate_json",
        lambda self, prompt, media, schema, settings: (
            {
                "verdict": "replan_solver",
                "summary": "Three tall items exceed uhaul_10 ceiling; switch fleet to uhaul_26 with lifo_heavy_first.",
                "blocking_issues": ["3 upright items unplaced in uhaul_10"],
                "mover_notes": ["Use 26-ft truck for 75-in mobile whiteboards and tall shelving."],
                "recommended_strategy_patch": {
                    "truck_id": "uhaul_26",
                    "order_mode": "lifo_heavy_first",
                    "downsize_last_truck": True,
                },
            },
            Usage(tokens_in=1100, tokens_out=120),
        ),
    )

    res_bad = judge_plan.judge_move_plan(broken_plan, inventory=sample)
    assert res_bad["approved"] is False
    assert res_bad["escalated"] is True
    assert res_bad["recommended_action"] == "replan_solver"
    assert res_bad["escalation"]["via"] == "gemini:gemini-4-neon"

    # Applying the Judge's recommended_strategy_patch repairs the broken plan to 0 violations
    repaired = solver.solve(sample, strategy=res_bad["escalation"]["recommended_strategy_patch"])
    assert repaired["score"]["valid"] is True
    assert repaired["unplaced"] == []


def test_step2_hackathon_rubric_judge_weights_and_separation(monkeypatch, tmp_path: Path) -> None:
    _isolate_llm_cache(monkeypatch, tmp_path)

    ev = judge_rubric.collect_hackathon_evidence(repo_root=ROOT)
    assert len(ev["distinct_gemini4_models_configured"]) >= 2
    assert ev["uses_decisions_api_configured"] is True
    assert ev["deprecated_models_configured"] == []
    assert ev["has_readme_disclosure"] is True
    assert ev["failures_logged_count"] >= 10

    def fake_rubric_batch(self, input_text, media, questions, settings):
        return (
            {
                "answers": {
                    "meets_model_and_decisions_rule": {"type": "noul", "noul": 0.97, "answer": True, "confidence": 0.97},
                    "avoids_anti_project_disqualifiers": {"type": "noul", "noul": 0.95, "answer": True, "confidence": 0.95},
                    "has_verified_proof_beyond_demo": {"type": "noul", "noul": 0.90, "answer": True, "confidence": 0.90},
                    # Deliberately asymmetric scores to verify Round 1 (35/25/20/20) != Round 2 (25/25/25/25):
                    # live_demo=4.0 (100%), proof=3.0 (75%), creativity=2.0 (50%), models=3.0 (75%)
                    # R1 = 35 + 18.75 + 10 + 15 = 78.8; R2 = 25 + 18.75 + 12.5 + 18.75 = 75.0
                    "live_demo": {
                        "type": "score", "score": 4.0, "max_score": 4, "normalized": 1.0,
                        "probabilities": {"4": 0.90}, "legend": {}, "confidence": 0.90,
                    },
                    "proof_it_works": {
                        "type": "score", "score": 3.0, "max_score": 4, "normalized": 0.75,
                        "probabilities": {"3": 0.85}, "legend": {}, "confidence": 0.85,
                    },
                    "creativity": {
                        "type": "score", "score": 2.0, "max_score": 4, "normalized": 0.50,
                        "probabilities": {"2": 0.80}, "legend": {}, "confidence": 0.80,
                    },
                    "gemini_and_decisions_use": {
                        "type": "score", "score": 3.0, "max_score": 4, "normalized": 0.75,
                        "probabilities": {"3": 0.88}, "legend": {}, "confidence": 0.88,
                    },
                    "submission_status": {
                        "type": "choice",
                        "choice": "close_gaps_before_5pm",
                        "probabilities": {"close_gaps_before_5pm": 0.82, "stage_ready": 0.14, "compliance_risk": 0.02, "other": 0.02},
                        "confidence": 0.82,
                    },
                }
            },
            Usage(tokens_in=720, tokens_out=0),
        )

    monkeypatch.setattr(GeminiProvider, "decide_batch", fake_rubric_batch)
    monkeypatch.setattr(
        GeminiProvider,
        "generate_json",
        lambda self, prompt, media, schema, settings: (
            {
                "headline": "Strong Round 1 demo lead; finish QR labels and baseline table before 5:00 PM.",
                "pre_5pm_checklist": ["Write eval/RESULTS.md baseline comparison", "Add QR labels print view"],
                "judge_qa_prep": ["Explain Hydrogen vs Neon vs Decisions API split"],
                "pitch_highlights": ["Show live phone room upload into 3D Penn Station trucks"],
            },
            Usage(tokens_in=800, tokens_out=95),
        ),
    )

    step1_stub = {"approved": True, "recommended_action": "approve_dispatch", "judge_score_100": 92.5, "verifier_score_100": 94.0}
    res = judge_rubric.judge_hackathon_rubric(repo_root=ROOT, plan_judgment=step1_stub)
    assert res["step"] == "hackathon_rubric_judge"
    assert res["eligible"] is True
    assert res["round_1_score_100"] == 78.8
    assert res["round_2_score_100"] == 75.0
    assert res["evidence"]["has_step1_plan_judgment"] is True
    assert res["evidence"]["components"]["pitch_cue_cards"] is True
    assert len(res["presenter_cards"]["chris"]) == 3
    assert len(res["presenter_cards"]["george"]) == 3
    assert len(res["coaching"]["pre_5pm_checklist"]) >= 1


def test_judge_api_separate_routes_and_offline_fallback(monkeypatch, tmp_path: Path) -> None:
    _isolate_llm_cache(monkeypatch, tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(llm_mod, "_env_loaded", True)
    monkeypatch.setattr(ingest_common, "RUNS_DIR", tmp_path / "runs")

    rid = "20261121-123000-malin_test"
    rd = tmp_path / "runs" / rid
    rd.mkdir(parents=True)
    mock_inv = json.loads((ROOT / "frontend" / "mock" / "inventory.json").read_text(encoding="utf-8"))
    (rd / "inventory.json").write_text(json.dumps(mock_inv), encoding="utf-8")

    app = FastAPI()
    app.include_router(judge_api.router)
    client = TestClient(app)

    # Step 1 only: writes judge_plan.json, does NOT write judge_rubric.json
    r1 = client.post(f"/judge/plan/{rid}")
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["step"] == "move_plan_judge"
    assert body1["via"] == "deterministic_rule_fallback"
    assert (rd / "judge_plan.json").exists()
    assert not (rd / "judge_rubric.json").exists()

    # Step 2 only: reads Step 1 judge_plan.json and writes judge_rubric.json separately
    r2 = client.post(f"/judge/rubric/{rid}")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["step"] == "hackathon_rubric_judge"
    assert body2["evidence"]["has_step1_plan_judgment"] is True
    assert (rd / "judge_rubric.json").exists()

    # GET /judge/{run_id} returns both separate step artifacts
    r_both = client.get(f"/judge/{rid}")
    assert r_both.status_code == 200
    both = r_both.json()
    assert both["move_plan_judge"]["step"] == "move_plan_judge"
    assert both["hackathon_rubric_judge"]["step"] == "hackathon_rubric_judge"

    # Special built-in demo run_ids (`sample_venue` and `mock-demo`) also work out-of-the-box
    r_sample = client.post("/judge/plan/sample_venue")
    assert r_sample.status_code == 200
    assert r_sample.json()["approved"] is True
    r_sample_rubric = client.post("/judge/rubric/sample_venue")
    assert r_sample_rubric.status_code == 200
    assert r_sample_rubric.json()["eligible"] is True

