"""Final Judge Step 2: Hackathon Rubric Judge (`backend/judge_rubric.py`).

Separate post-run evaluation step (run *after* Step 1 `backend/judge_plan.py`)
that audits Pack It Up against the official Cerebral Valley × Google DeepMind
**Gemini 4 NYC Hackathon** rules and judging rubric:

  1. Hard Eligibility & Compliance Gates (`noul` yes/no):
     - At least two Gemini 4 models (`gemini-4-carbon`, `gemini-4-neon`,
       `gemini-4-argon`, or `gemini-4-hydrogen`) with distinct clear jobs +
       the Gemini Decisions API (`gemini-decision-1`), and zero legacy
       `gemini-1.5/2.0/2.5` models.
     - Problem Statement Two (Element 119) & anti-project compliance: multimodal
       video/audio/photo input and 3D/generated output, not a text-only chatbot,
       plain image analyzer, or stat dashboard, with clear `README.md` disclosure.
     - Real proof beyond the happy-path demo (`verify.py` + `judge_plan.py`
       self-check, `FAILURES.md` engineering log, and `eval/` scoring/baselines).
  2. Official Four-Criterion Rubric (`score` 0..4 ordered levels):
     - `live_demo`                (Round 1: 35%, Round 2 Finals: 25%)
     - `proof_it_works`           (Round 1: 25%, Round 2 Finals: 25%)
     - `creativity`               (Round 1: 20%, Round 2 Finals: 25%)
     - `gemini_and_decisions_use` (Round 1: 20%, Round 2 Finals: 25%)
  3. Submission Readiness Routing (`choice` with explicit `"other"` catch-all) +
     Gemini 4 (`judge_escalate`) pre-5PM gap checklist and live Q&A prep.

No model SDK is imported here; all model calls go through `backend.llm.for_job()`.

CLI:
    python -m backend.judge_rubric
    python -m backend.judge_rubric --run <run_id>
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from backend.ingest.common import read_json, run_dir, write_json
from backend.llm import LLMError, for_job, load_config

ROOT = Path(__file__).resolve().parents[1]

ROUND_1_WEIGHTS: dict[str, float] = {
    "live_demo": 0.35,
    "proof_it_works": 0.25,
    "creativity": 0.20,
    "gemini_and_decisions_use": 0.20,
}

ROUND_2_WEIGHTS: dict[str, float] = {
    "live_demo": 0.25,
    "proof_it_works": 0.25,
    "creativity": 0.25,
    "gemini_and_decisions_use": 0.25,
}

GEMINI_4_REASONING_MODELS = {
    "gemini-4-carbon",
    "gemini-4-neon",
    "gemini-4-argon",
    "gemini-4-hydrogen",
}

DEPRECATED_PREFIXES = ("gemini-2.5", "gemini-2.0", "gemini-1.5")

HACKATHON_RUBRIC_QUESTIONS: dict[str, dict] = {
    "meets_model_and_decisions_rule": {
        "type": "noul",
        "instructions": (
            "Does this system configure and use at least two distinct Gemini 4 models "
            "(Carbon, Neon, Argon, or Hydrogen) with clear separate jobs PLUS the Gemini "
            "Decisions API (`gemini-decision-1`), with zero deprecated gemini-1.5/2.0/2.5 models?"
        ),
    },
    "avoids_anti_project_disqualifiers": {
        "type": "noul",
        "instructions": (
            "Does this project clearly avoid the hackathon's banned anti-projects (not a text-only "
            "chatbot, Streamlit app, standalone image analyzer, or dashboard-first app) and disclose "
            "what was built at the event vs brought in?"
        ),
    },
    "has_verified_proof_beyond_demo": {
        "type": "noul",
        "instructions": (
            "Is there concrete verification evidence beyond a happy-path demo: a physics/rule verifier "
            "plus Move Plan Judge checking output, an honest FAILURES.md log, and evaluation scripts/counts?"
        ),
    },
    "live_demo": {
        "type": "score",
        "instructions": (
            "Live Demo (35% Round 1 / 25% Round 2): Does it work live on real, unrehearsed inputs "
            "(phone room capture -> inventory & live question -> verified 3D truck & Penn Station plan "
            "with interactive edit/re-solve) within the 3-minute judging window?"
        ),
        "criteria": [
            "Slides, static mockups, or broken pipeline that cannot process real inputs.",
            "Partial pipeline works in CLI only; phone upload or packing view missing.",
            "End-to-end backend works on real photos/clips, but live 3D view or edit re-solve is incomplete.",
            "Working live phone-to-truck flow on unrehearsed venue media with interactive question and re-solve.",
            "Battle-tested <3 min live phone capture -> Decisions question -> 3D trucks & Penn Station unload + tunnel fallback.",
        ],
    },
    "proof_it_works": {
        "type": "score",
        "instructions": (
            "Proof It Works (25% Round 1 / 25% Round 2): Is there real evidence beyond the demo, such as "
            "a test against a baseline, an honest look at where it fails, and a plan the agent checks its own output against?"
        ),
        "criteria": [
            "No verification, no failure log, and no evaluation on unprepared inputs.",
            "Basic sanity checks or unit tests only, without baseline comparison or real failure log.",
            "Has physics verifier + Move Plan Judge and real FAILURES.md log, but baseline/eval table is still partial.",
            "Has deterministic 3D verifier + Move Plan Judge, hand-counted unprepared venue eval, and detailed FAILURES.md.",
            "Complete proof suite: verifier + Judge loop, single-call & bedroom-rule baselines in RESULTS.md, hand-counts, and FAILURES.md.",
        ],
    },
    "creativity": {
        "type": "score",
        "instructions": (
            "Creativity (20% Round 1 / 25% Round 2): Does it take on a hard physical problem others avoid, "
            "and go beyond a text interface in a way that matters?"
        ),
        "criteria": [
            "Generic text wrapper or standard CRUD/dashboard application.",
            "Multimodal room inventory list without physical 3D packing or destination constraints.",
            "Computes 3D truck packing from room media, going beyond text.",
            "Combines handheld video + spoken narration with 3D fleet packing and Penn Station multi-store LIFO dock routing.",
            "Full multimodal physical workflow: narrated room video in -> verified 3D fleet, Penn Station store routing, offline QR box labels, and arrival render out.",
        ],
    },
    "gemini_and_decisions_use": {
        "type": "score",
        "instructions": (
            "Gemini 4 & Decisions API Use (20% Round 1 / 25% Round 2): How well does the system use at least "
            "two Gemini 4 models (each with a clear job) and the Decisions API across reasoning, speed, and multimodality?"
        ),
        "criteria": [
            "Uses only one model, retired model IDs, or omits the Decisions API.",
            "Uses two Gemini 4 models loosely, or only trivial text Decisions API calls.",
            "Clear split: Hydrogen for video+audio perception and Decisions API for multimodal gap questions, plus a second Gemini 4 model configured.",
            "Hydrogen perceives video+audio, Neon/Carbon plans & escalates, and Decisions API handles both multimodal gap routing and single-pass noul/choice/score judging.",
            "Full toolkit mastery: Hydrogen parallel video+speech, Decisions API calibrated choice/noul/score gates, Neon planning loop, Managed Agents sandboxes, and Nano Banana 2.1.",
        ],
    },
    "submission_status": {
        "type": "choice",
        "instructions": "What is the overall hackathon submission readiness status right now?",
        "criteria": {
            "stage_ready": "Meets all rules and scores strongly across all 4 criteria; ready to record video and pitch.",
            "close_gaps_before_5pm": "Compliant architecture and core works, but specific build/eval items remain before 5:00 PM.",
            "compliance_risk": "Missing a mandatory hackathon rule (2+ Gemini 4 models, Decisions API, disclosure, or anti-project boundary).",
            "other": "Insufficient repository or run evidence to grade.",
        },
    },
}

COACH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["headline", "pre_5pm_checklist", "judge_qa_prep", "pitch_highlights"],
    "properties": {
        "headline": {"type": "string"},
        "pre_5pm_checklist": {"type": "array", "items": {"type": "string"}},
        "judge_qa_prep": {"type": "array", "items": {"type": "string"}},
        "pitch_highlights": {"type": "array", "items": {"type": "string"}},
    },
}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def collect_hackathon_evidence(
    *,
    repo_root: Path = ROOT,
    run_id: str | None = None,
    rd: Path | None = None,
    plan_judgment: dict | None = None,
) -> dict[str, Any]:
    """Inspect repo files, `models.toml`, `calls.jsonl`, `eval/`, `FAILURES.md`, and Step 1 output."""
    if rd is None and run_id:
        try:
            cand = run_dir(run_id)
            if cand.exists():
                rd = cand
        except ValueError:
            rd = None

    cfg = load_config()
    jobs_cfg = cfg.get("jobs") or {}
    configured_models: dict[str, str] = {}
    gemini4_configured: set[str] = set()
    deprecated_configured: list[str] = []
    uses_decisions_configured = False

    for jname, jspec in jobs_cfg.items():
        raw_m = str(jspec.get("model") or "")
        _, _, mid = raw_m.partition(":")
        model_id = mid or raw_m
        configured_models[jname] = model_id
        if model_id in GEMINI_4_REASONING_MODELS:
            gemini4_configured.add(model_id)
        if model_id == "gemini-decision-1":
            uses_decisions_configured = True
        if model_id.startswith(DEPRECATED_PREFIXES):
            deprecated_configured.append(f"{jname}:{model_id}")

    # Call logs (global + run-specific if present)
    calls = _read_jsonl(repo_root / ".cache" / "calls.jsonl")
    if rd is not None:
        run_calls = _read_jsonl(rd / "calls.jsonl")
        seen_ts = {(c.get("ts"), c.get("job"), c.get("file")) for c in calls}
        for rc in run_calls:
            k = (rc.get("ts"), rc.get("job"), rc.get("file"))
            if k not in seen_ts:
                calls.append(rc)

    exercised_models = sorted({str(c.get("model")) for c in calls if c.get("model")})
    exercised_jobs = sorted({str(c.get("job")) for c in calls if c.get("job")})
    decisions_calls = sum(1 for c in calls if c.get("model") == "gemini-decision-1" or str(c.get("kind", "")).startswith("decide"))

    # Failures log
    failures_path = repo_root / "FAILURES.md"
    failure_rows = 0
    if failures_path.exists():
        for ln in failures_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if ln.startswith("|") and not ln.startswith("| Time") and not ln.startswith("|---"):
                failure_rows += 1

    # README disclosure check
    readme_text = (repo_root / "README.md").read_text(encoding="utf-8", errors="replace") if (repo_root / "README.md").exists() else ""
    has_readme_disclosure = ("What was built at the event" in readme_text) and ("Brought in" in readme_text)

    # Check built modules across Track A, Track B, Frontend, and Eval
    components = {
        "ingest_pipeline": (repo_root / "backend" / "ingest" / "pipeline.py").exists(),
        "decisions_gaps": (repo_root / "backend" / "ingest" / "gaps.py").exists(),
        "expand": (repo_root / "backend" / "expand.py").exists(),
        "solver_3d": (repo_root / "backend" / "solver.py").exists(),
        "verifier_3d": (repo_root / "backend" / "verify.py").exists(),
        "move_plan_judge": (repo_root / "backend" / "judge_plan.py").exists(),
        "neon_planner_loop": (repo_root / "backend" / "planner.py").exists(),
        "managed_agents": (repo_root / "backend" / "agents.py").exists(),
        "arrival_render": (repo_root / "backend" / "render.py").exists(),
        "qr_box_labels": (repo_root / "backend" / "labels.py").exists(),
        "phone_capture_ui": (repo_root / "frontend" / "capture.html").exists(),
        "review_ui": (repo_root / "frontend" / "review.html").exists(),
        "threejs_3d_view": (repo_root / "frontend" / "index.html").exists(),
        "hand_count_eval": (repo_root / "eval" / "score_inventory.py").exists() and (repo_root / "eval" / "hand_counts" / "malin.json").exists(),
        "results_table": (repo_root / "eval" / "RESULTS.md").exists(),
        "baseline_eval": any((repo_root / "eval").glob("baseline*.py")) if (repo_root / "eval").exists() else False,
    }

    # Check Step 1 Move Plan Judge output if available
    if plan_judgment is None and rd is not None:
        plan_judgment = read_json(rd / "judge_plan.json")

    reqs_text = (repo_root / "requirements.txt").read_text(encoding="utf-8", errors="replace").lower() if (repo_root / "requirements.txt").exists() else ""
    uses_streamlit = "streamlit" in reqs_text

    return {
        "run_id": run_id,
        "configured_models": configured_models,
        "distinct_gemini4_models_configured": sorted(gemini4_configured),
        "uses_decisions_api_configured": uses_decisions_configured,
        "deprecated_models_configured": deprecated_configured,
        "logged_call_count": len(calls),
        "decisions_call_count": decisions_calls,
        "exercised_models": exercised_models,
        "exercised_jobs": exercised_jobs,
        "failures_logged_count": failure_rows,
        "has_readme_disclosure": has_readme_disclosure,
        "uses_streamlit": uses_streamlit,
        "components": components,
        "has_step1_plan_judgment": plan_judgment is not None,
        "step1_summary": (
            {
                "approved": plan_judgment.get("approved"),
                "recommended_action": plan_judgment.get("recommended_action"),
                "judge_score_100": plan_judgment.get("judge_score_100"),
                "verifier_score_100": plan_judgment.get("verifier_score_100"),
            }
            if isinstance(plan_judgment, dict)
            else None
        ),
    }


def _format_evidence_prompt(ev: dict[str, Any]) -> str:
    comp = ev["components"]
    built = [k for k, v in comp.items() if v]
    missing = [k for k, v in comp.items() if not v]
    lines = [
        "=== PACK IT UP: GEMINI 4 NYC HACKATHON RUBRIC AUDIT ===",
        "Problem Statement: Problem Statement Two — Element 119 (multimodal video/audio/photo in, verified 3D truck + Penn Station store plan + QR labels + arrival visual out).",
        f"Configured jobs -> models: {json.dumps(ev['configured_models'])}",
        f"Distinct Gemini 4 reasoning models configured ({len(ev['distinct_gemini4_models_configured'])}): {ev['distinct_gemini4_models_configured']}",
        f"Decisions API (`gemini-decision-1`) configured: {ev['uses_decisions_api_configured']}",
        f"Deprecated models configured: {ev['deprecated_models_configured'] or 'none'}",
        f"Uses banned Streamlit: {ev['uses_streamlit']}",
        f"README event-work & brought-in disclosure present: {ev['has_readme_disclosure']}",
        f"Engineering failures logged in FAILURES.md: {ev['failures_logged_count']}",
        f"Recorded model calls in calls.jsonl: {ev['logged_call_count']} (Decisions API calls={ev['decisions_call_count']}, models={ev['exercised_models']})",
        f"Built components ({len(built)}/{len(comp)}): {built}",
        f"Remaining components before 5:00 PM ({len(missing)}): {missing}",
        f"Step 1 Move Plan Judge result attached: {json.dumps(ev['step1_summary'])}",
    ]
    return "\n".join(lines)


def _deterministic_rubric_answers(ev: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Evidence-grounded deterministic scoring used only when GEMINI_API_KEY is unset locally."""
    c = ev["components"]
    two_g4 = len(ev["distinct_gemini4_models_configured"]) >= 2 and ev["uses_decisions_api_configured"] and not ev["deprecated_models_configured"]
    no_anti = (not ev["uses_streamlit"]) and ev["has_readme_disclosure"] and c["solver_3d"] and c["verifier_3d"]
    has_proof = c["verifier_3d"] and c["move_plan_judge"] and ev["failures_logged_count"] >= 5 and c["hand_count_eval"]

    # 0..4 scores grounded strictly in which pieces are already built in the repo
    demo_sc = 1.5
    if c["ingest_pipeline"] and c["phone_capture_ui"] and c["review_ui"]:
        demo_sc += 1.0
    if c["solver_3d"] and c["verifier_3d"]:
        demo_sc += 0.6
    if c["threejs_3d_view"]:
        demo_sc += 0.7
    if ev["has_step1_plan_judgment"]:
        demo_sc += 0.2

    proof_sc = 1.0
    if c["verifier_3d"] and c["move_plan_judge"]:
        proof_sc += 1.3
    if ev["failures_logged_count"] >= 5:
        proof_sc += 0.7
    if c["hand_count_eval"]:
        proof_sc += 0.4
    if c["baseline_eval"] and c["results_table"]:
        proof_sc += 0.6

    creat_sc = 2.4
    if c["solver_3d"] and c["expand"]:
        creat_sc += 0.7
    if c["threejs_3d_view"]:
        creat_sc += 0.4
    if c["qr_box_labels"]:
        creat_sc += 0.3
    if c["arrival_render"]:
        creat_sc += 0.2

    models_sc = 2.0 if two_g4 else 0.8
    if c["decisions_gaps"] and c["move_plan_judge"]:
        models_sc += 0.9
    if c["neon_planner_loop"]:
        models_sc += 0.5
    if c["managed_agents"]:
        models_sc += 0.4
    if c["arrival_render"]:
        models_sc += 0.2

    def _mk_score(val: float, crit: list[str]) -> dict[str, Any]:
        max_s = len(crit) - 1
        vc = round(max(0.0, min(float(max_s), val)), 4)
        idx = int(round(vc))
        probs = {str(i): (0.80 if i == idx else round(0.20 / max_s, 4)) for i in range(len(crit))}
        return {
            "type": "score",
            "score": vc,
            "max_score": max_s,
            "normalized": round(vc / max_s, 4),
            "probabilities": probs,
            "legend": {str(i): desc for i, desc in enumerate(crit)},
            "confidence": 0.80,
        }

    missing_core = [
        k for k in ("threejs_3d_view", "neon_planner_loop", "baseline_eval", "results_table") if not c.get(k)
    ]
    if not (two_g4 and no_anti):
        status = "compliance_risk"
    elif missing_core:
        status = "close_gaps_before_5pm"
    else:
        status = "stage_ready"

    return {
        "meets_model_and_decisions_rule": {
            "type": "noul",
            "noul": 0.95 if two_g4 else 0.10,
            "answer": two_g4,
            "confidence": 0.95 if two_g4 else 0.90,
        },
        "avoids_anti_project_disqualifiers": {
            "type": "noul",
            "noul": 0.94 if no_anti else 0.15,
            "answer": no_anti,
            "confidence": 0.94 if no_anti else 0.85,
        },
        "has_verified_proof_beyond_demo": {
            "type": "noul",
            "noul": 0.92 if has_proof else 0.35,
            "answer": has_proof,
            "confidence": 0.92 if has_proof else 0.65,
        },
        "live_demo": _mk_score(demo_sc, HACKATHON_RUBRIC_QUESTIONS["live_demo"]["criteria"]),
        "proof_it_works": _mk_score(proof_sc, HACKATHON_RUBRIC_QUESTIONS["proof_it_works"]["criteria"]),
        "creativity": _mk_score(creat_sc, HACKATHON_RUBRIC_QUESTIONS["creativity"]["criteria"]),
        "gemini_and_decisions_use": _mk_score(models_sc, HACKATHON_RUBRIC_QUESTIONS["gemini_and_decisions_use"]["criteria"]),
        "submission_status": {
            "type": "choice",
            "choice": status,
            "probabilities": {
                k: (0.82 if k == status else round(0.18 / 3, 4))
                for k in HACKATHON_RUBRIC_QUESTIONS["submission_status"]["criteria"]
            },
            "confidence": 0.82,
        },
    }


def _deterministic_coaching(ev: dict[str, Any], r1_score: float) -> dict[str, Any]:
    c = ev["components"]
    checklist: list[str] = []
    if not c["threejs_3d_view"]:
        checklist.append("Finish `frontend/index.html` Three.js 3D truck & Penn Station storefront playback wired to `?run_id=`.")
    if not c["neon_planner_loop"]:
        checklist.append("Add `backend/planner.py` (Gemini 4 Neon strategy loop) so Neon actively repairs violations on screen.")
    if not c["managed_agents"]:
        checklist.append("Add `backend/agents.py` (Antigravity Managed Agent parallel sandboxes) to qualify for the $5,000 Managed Agents prize.")
    if not (c["baseline_eval"] and c["results_table"]):
        checklist.append("Run single-call LLM packing baseline vs solver+verifier and write `eval/RESULTS.md` (worth 25% in Round 1).")
    if not c["qr_box_labels"]:
        checklist.append("Add `backend/labels.py` self-contained offline QR box labels so a judge's phone can scan a box live.")
    if not c["arrival_render"]:
        checklist.append("Add `backend/render.py` (`gemini-nano-banana-2.1`) illustrative Penn Station arrival image with badge.")
    if not checklist:
        checklist.append("Record the 1-minute submission video by 4:30 PM and rehearse the 3-minute live room film -> pack flow twice.")

    return {
        "headline": f"Current Round 1 projection: {r1_score}/100 ({sum(c.values())}/{len(c)} build milestones present).",
        "pre_5pm_checklist": checklist,
        "judge_qa_prep": [
            "What was built today vs brought in? -> Point to git commit history since 10:30 AM and README 'Brought in' section (`item_catalog.csv`, Penn Station reference media).",
            "Why multiple Gemini 4 models + Decisions API? -> Hydrogen watches video+audio fast in parallel; Decisions API (`gemini-decision-1`) runs zero-output-token calibrated gap questions & final rubric gates; Neon handles multi-constraint packing strategy & escalations.",
            "How do you know the 3D load works? -> Deterministic physics verifier (`verify.py`: >=75% base support, 3D overlap, upright/edge rules, 40-60% CoG, Penn Station doorway clearances) + Move Plan Judge.",
        ],
        "pitch_highlights": [
            "Lead with the packed 3D truck fleet and Penn Station store unload sequence, never a static dashboard.",
            "Narrate one fact aloud while filming ('these chairs stack' or 'the plants stay') so judges see audio update the plan.",
            "Invite a judge at 2:00 to toggle an item or switch truck size and watch verifier + Move Plan Judge re-check live.",
        ],
        "via": "deterministic_evidence_fallback",
    }


def _weighted_100(answers: dict[str, dict], weights: dict[str, float]) -> float:
    total = 0.0
    for k, w in weights.items():
        total += w * float(answers[k]["normalized"]) * 100.0
    return round(total, 1)


def judge_hackathon_rubric(
    *,
    repo_root: Path = ROOT,
    run_id: str | None = None,
    rd: Path | None = None,
    plan_judgment: dict | None = None,
    allow_offline_fallback: bool = True,
) -> dict[str, Any]:
    """Run Final Judge Step 2: evaluate project & run against the Cerebral Valley Hackathon rubric."""
    if rd is None and run_id:
        rd = run_dir(run_id)

    evidence = collect_hackathon_evidence(
        repo_root=repo_root,
        run_id=run_id,
        rd=rd,
        plan_judgment=plan_judgment,
    )
    prompt_text = _format_evidence_prompt(evidence)

    via = "decisions_api"
    try:
        batch = for_job("judge", run_dir=rd).decide_batch(
            prompt_text,
            questions=HACKATHON_RUBRIC_QUESTIONS,
            media=[],
            prompt_version="judge_hackathon_rubric_v1",
            label=f"judge_rubric:{run_id or 'repo'}",
        )
        answers = batch["answers"]
        via = batch["via"]
    except LLMError:
        if not allow_offline_fallback:
            raise
        answers = _deterministic_rubric_answers(evidence)
        via = "deterministic_evidence_fallback"

    r1_score = _weighted_100(answers, ROUND_1_WEIGHTS)
    r2_score = _weighted_100(answers, ROUND_2_WEIGHTS)

    gates = {
        "meets_model_and_decisions_rule": answers["meets_model_and_decisions_rule"],
        "avoids_anti_project_disqualifiers": answers["avoids_anti_project_disqualifiers"],
        "has_verified_proof_beyond_demo": answers["has_verified_proof_beyond_demo"],
    }
    criteria = {
        k: {
            **answers[k],
            "round_1_weight": ROUND_1_WEIGHTS[k],
            "round_2_weight": ROUND_2_WEIGHTS[k],
            "weighted_points_round_1": round(answers[k]["normalized"] * 100.0 * ROUND_1_WEIGHTS[k], 1),
            "weighted_points_round_2": round(answers[k]["normalized"] * 100.0 * ROUND_2_WEIGHTS[k], 1),
        }
        for k in ROUND_1_WEIGHTS
    }
    status_ans = answers["submission_status"]

    needs_coaching = (
        status_ans["choice"] != "stage_ready"
        or status_ans["confidence"] < 0.75
        or any(not g["answer"] for g in gates.values())
        or any(criteria[k]["score"] < 3.2 for k in criteria)
    )

    if via == "deterministic_evidence_fallback":
        coaching = _deterministic_coaching(evidence, r1_score)
    elif needs_coaching:
        coach_prompt = (
            "You are advising the Pack It Up team at the Gemini 4 NYC Hackathon before the 5:00 PM deadline.\n"
            "Based ONLY on the repository/run evidence and calibrated rubric scores below, return:\n"
            "1) a crisp one-line headline,\n"
            "2) prioritized concrete build/eval items to finish before 5:00 PM,\n"
            "3) three sharp answers to likely judge Q&A questions,\n"
            "4) three live-demo pitch highlights.\n\n"
            f"{prompt_text}\n\n"
            f"Calibrated rubric answers:\n{json.dumps(answers, indent=2)}"
        )
        try:
            coach_raw = for_job("judge_escalate", run_dir=rd).generate_json(
                coach_prompt,
                media=[],
                schema=COACH_SCHEMA,
                prompt_version="judge_rubric_coach_v1",
                label=f"judge_rubric_coach:{run_id or 'repo'}",
            )
            coaching = {**coach_raw, "via": for_job("judge_escalate", run_dir=rd).spec}
        except LLMError:
            if not allow_offline_fallback:
                raise
            coaching = _deterministic_coaching(evidence, r1_score)
    else:
        coaching = _deterministic_coaching(evidence, r1_score)

    eligible = (
        gates["meets_model_and_decisions_rule"]["answer"]
        and gates["avoids_anti_project_disqualifiers"]["answer"]
    )

    result: dict[str, Any] = {
        "step": "hackathon_rubric_judge",
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "run_id": run_id,
        "eligible": eligible,
        "submission_status": status_ans["choice"],
        "round_1_score_100": r1_score,
        "round_2_score_100": r2_score,
        "via": via,
        "compliance_gates": gates,
        "criteria": criteria,
        "routing": status_ans,
        "coaching": coaching,
        "evidence": evidence,
    }

    if rd is not None and rd.exists():
        write_json(rd / "judge_rubric.json", result)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Final Judge Step 2: audit run & repo against the Hackathon Judging Rubric.")
    ap.add_argument("--run", dest="run_id", default=None, help="Optional run_id under runs/ (reads judge_plan.json if present)")
    ap.add_argument("--plan-judgment", type=Path, default=None, help="Optional path to Step 1 judge_plan.json")
    ap.add_argument("--out", type=Path, default=None, help="Optional path to write judge_rubric JSON")
    ap.add_argument("--strict-online", action="store_true", help="Fail instead of falling back when GEMINI_API_KEY is unset")
    args = ap.parse_args()

    pj = json.loads(args.plan_judgment.read_text(encoding="utf-8")) if args.plan_judgment else None
    res = judge_hackathon_rubric(
        run_id=args.run_id,
        plan_judgment=pj,
        allow_offline_fallback=not args.strict_online,
    )

    print(
        f"[Hackathon Rubric Judge] eligible={res['eligible']} status={res['submission_status']} "
        f"round_1={res['round_1_score_100']}/100 round_2={res['round_2_score_100']}/100 via={res['via']}"
    )
    for k, c in res["criteria"].items():
        print(
            f"  - {k} (R1 {int(c['round_1_weight']*100)}%): {c['score']:.2f}/{c['max_score']} "
            f"-> {c['weighted_points_round_1']}/{int(c['round_1_weight']*100)} pts (conf={c['confidence']:.2f})"
        )
    print("  Top pre-5PM action items:")
    for item in res["coaching"]["pre_5pm_checklist"][:4]:
        print(f"    * {item}")
    if args.out:
        args.out.write_text(json.dumps(res, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
