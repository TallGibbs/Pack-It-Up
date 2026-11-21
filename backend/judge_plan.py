"""Final Judge Step 1: Move Plan Judge (`backend/judge_plan.py`).

Product-facing final quality & safety gate run at the end of the packing pipeline
(separate from Step 2 `backend/judge_rubric.py`, which scores hackathon rubric readiness).

Follows the official Gemini 4 Hackathon Builder Guide pattern ("Route, gate and score
with the Gemini Decisions API"):
  1. Evaluates the solved truck fleet, Penn Station multi-store LIFO unload plan,
     deterministic `verify` checks, user spoken/edited dispositions, and optional
     illustrative arrival render in ONE forward pass with `gemini-decision-1`
     (`for_job("judge").decide_batch(...)`, zero output tokens) across all three
     Decisions API question types:
       - `noul`: binary safety/completeness/visual-consistency gates
       - `score`: 0..4 ordered rubrics for load safety, Penn Station LIFO routing,
         and mover readiness
       - `choice`: dispatch routing (`approve_dispatch`, `ask_user_open_questions`,
         `replan_solver`, `other`)
  2. Checks calibrated `confidence` (< 0.75) and hazard `noul` (> 0.50); escalates
     flagged or uncertain plans to `for_job("judge_escalate")` (Gemini 4 Neon / Carbon)
     for root-cause diagnosis and a concrete `recommended_strategy_patch` that
     `solver.solve()` can apply directly.

No model SDK is imported here; all model calls go through `backend.llm.for_job()`.

CLI:
    python -m backend.judge_plan data/sample_venue.json
    python -m backend.judge_plan --run <run_id>
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from backend import solver, verify
from backend.ingest.common import read_json, run_dir, write_json
from backend.llm import LLMError, Media, for_job, media_from_path

CONFIDENCE_THRESHOLD = 0.75
HAZARD_NOUL_THRESHOLD = 0.50

BASE_MOVE_PLAN_QUESTIONS: dict[str, dict] = {
    "has_safety_or_damage_risk": {
        "type": "noul",
        "instructions": (
            "Does this move plan contain any physical loading hazard, fragile-crushing risk, "
            "unsupported elevated item (<75% base support), tipped upright item, overweight or "
            "unbalanced truck, unplaced item, or Penn Station doorway/store overflow violation?"
        ),
    },
    "respects_user_instructions": {
        "type": "noul",
        "instructions": (
            "Does the packed truck manifest faithfully include movable keep/undecided items while "
            "excluding items marked stays, trash, sell, or donate, and honoring spoken instructions?"
        ),
    },
    "load_safety_score": {
        "type": "score",
        "instructions": "Rate the physical safety, stacking stability, and weight balance of the truck load.",
        "criteria": [
            "Unsafe or invalid load: severe overlaps, out-of-bounds items, crushed fragile items, or unplaced pieces.",
            "Major stability or orientation flaws: upright items tipped, <75% base support, or severe truck imbalance.",
            "Borderline load: fits in trucks with minor warnings or tight weight/support margins.",
            "Solid mover-grade load: zero physics violations, safe left-right CoG, and protected fragile items.",
            "Exemplary load: zero violations, strong base support, balanced CoG near 50%, and efficient truck fill.",
        ],
    },
    "penn_routing_lifo_score": {
        "type": "score",
        "instructions": (
            "Rate the Penn Station multi-store destination routing, doorway clearances, and "
            "reverse-order LIFO dock-stop unloading sequence."
        ),
        "criteria": [
            "Broken destination plan: doorway clearance failures, store weight/fit overflows, or single-hall dumping.",
            "Weak routing: poor store distribution or severe LIFO dock-stop inversions blocking early stops.",
            "Acceptable routing: items clear store doorways with moderate LIFO stop alignment.",
            "Strong routing: 3+ Penn Station storefronts stocked cleanly with high LIFO unload alignment.",
            "Optimal dock-to-store plan: all storefronts stocked within doorway/floor limits and clean LIFO unload order.",
        ],
    },
    "mover_readiness_score": {
        "type": "score",
        "instructions": (
            "Rate how actionable and complete this move plan is for a real moving crew right now "
            "(fleet sizing, step-by-step load/unload sequence, box contents, and resolved inventory unknowns)."
        ),
        "criteria": [
            "Not actionable: missing truck assignments, unplaced items, or major unresolved blockers.",
            "Incomplete: basic truck assignment exists, but multiple high-volume unknowns or rule errors remain.",
            "Usable draft: clear fleet and load sequence, though open container/count questions could shift box counts.",
            "Crew-ready plan: verified fleet, numbered load/unload steps, store assignments, and manageable unknowns.",
            "Turnkey dispatch plan: 100% placed, 0 violations, clear two-person/fragile callouts, and settled inventory.",
        ],
    },
    "dispatch_action": {
        "type": "choice",
        "instructions": "Which workflow action should handle this move plan next?",
        "criteria": {
            "approve_dispatch": "Plan is physically valid, safe, and ready for truck loading and QR label printing.",
            "ask_user_open_questions": (
                "Truck physics pass, but open high-volume inventory questions or closed containers should be confirmed."
            ),
            "replan_solver": (
                "Physical violations, unplaced items, truck imbalance, or store routing issues require re-solving."
            ),
            "other": "Plan data is incomplete, contradictory, or requires manual inspection.",
        },
    },
}

VISUAL_RENDER_QUESTION: dict[str, Any] = {
    "type": "noul",
    "instructions": (
        "Does the attached illustrative arrival image plausibly reflect the moved furniture/equipment "
        "at the destination space without contradicting the inventory?"
    ),
}

ESCALATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["verdict", "summary", "blocking_issues", "mover_notes", "recommended_strategy_patch"],
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["approve_dispatch", "approve_with_caution", "ask_user_open_questions", "replan_solver"],
        },
        "summary": {"type": "string"},
        "blocking_issues": {"type": "array", "items": {"type": "string"}},
        "mover_notes": {"type": "array", "items": {"type": "string"}},
        "recommended_strategy_patch": {
            "type": "object",
            "required": ["truck_id", "order_mode", "downsize_last_truck"],
            "properties": {
                "truck_id": {"type": "string", "enum": ["uhaul_10", "uhaul_15", "uhaul_20", "uhaul_26"]},
                "order_mode": {
                    "type": "string",
                    "enum": ["lifo_heavy_first", "zone_strict_lifo", "heavy_first", "volume_first", "fragile_last"],
                },
                "downsize_last_truck": {"type": "boolean"},
            },
        },
    },
}


def summarize_move_plan_context(
    placement: dict,
    inventory: dict | None = None,
    verify_report: dict | None = None,
    has_arrival_image: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Build a compact, traceable ground-truth digest of the move plan for the Judge."""
    vrep = verify_report or placement.get("score") or verify.verify(placement)
    summary = placement.get("summary") or {}
    trucks = placement.get("trucks") or []
    zones = placement.get("zones") or []
    unplaced = placement.get("unplaced") or []

    open_questions: list[dict] = []
    unknown_containers: list[str] = []
    spoken_quotes: list[str] = []
    excluded_items: list[str] = []
    expected_movable_units = 0

    if inventory:
        for q in inventory.get("questions") or []:
            if q.get("status") == "open":
                open_questions.append(q)
        for r in inventory.get("rooms") or []:
            rname = (r.get("room") or {}).get("name") or "room"
            for it in r.get("items") or []:
                disp = (it.get("disposition") or "undecided").lower()
                qty = int(it.get("quantity") or 0)
                if disp in ("stays", "trash", "sell", "donate", "removed"):
                    excluded_items.append(f"{it.get('label')} x{qty} ({disp})")
                else:
                    expected_movable_units += qty
                for sf in it.get("set_by_speech") or []:
                    if sf.get("quote"):
                        spoken_quotes.append(f"\"{sf['quote']}\" -> {it.get('label')} ({sf.get('field')})")
            for c in r.get("containers") or []:
                if c.get("contents_unknown") or c.get("fullness") == "not_visible":
                    unknown_containers.append(f"{rname}: {c.get('label')}")

    lines: list[str] = [
        "=== PACK IT UP: FINAL MOVE PLAN INSPECTION ===",
        f"Fleet: {summary.get('fleet_label', f'{len(trucks)} truck(s)')}",
        (
            f"Placed pieces: {summary.get('total_items', sum(len(t.get('items', [])) for t in trucks))} "
            f"({summary.get('furniture_count', '?')} furniture + {summary.get('box_count', '?')} boxes), "
            f"Unplaced: {len(unplaced)}"
        ),
        (
            f"Verifier score: {vrep.get('total', 0)}/100 | valid={vrep.get('valid')} | "
            f"fill={vrep.get('fill_pct', 0)}% | balance_cog_y={vrep.get('balance_pct', 50)}% "
            f"(safe 40%-60%) | lifo_score={vrep.get('lifo_score', 0)}/10 | "
            f"zone_coverage={vrep.get('zone_coverage_pct', 0)}% | violations={vrep.get('violation_count', 0)}"
        ),
    ]

    if trucks:
        lines.append("\n--- Trucks ---")
        for t in trucks:
            t_items = t.get("items") or []
            two_p = sum(1 for it in t_items if it.get("two_person"))
            frag = sum(1 for it in t_items if it.get("fragile"))
            first_lbl = t_items[0].get("label") if t_items else "none"
            last_lbl = t_items[-1].get("label") if t_items else "none"
            lines.append(
                f"Truck {t.get('index', 0)} ({t.get('truck_id')}): {len(t_items)} items, "
                f"{t.get('weight_lb', 0)}/{t.get('max_weight_lb', 0)} lb, fill={t.get('fill_pct', 0)}%, "
                f"fragile={frag}, two_person={two_p}, first_loaded={first_lbl!r}, last_loaded={last_lbl!r}"
            )

    if zones:
        lines.append("\n--- Penn Station Destination Stores (Dock Unload Order) ---")
        for z in zones:
            lines.append(
                f"Stop {z.get('dock_stop')} {z.get('zone_id')} ({z.get('name')}): "
                f"{z.get('item_count', len(z.get('items', [])))} items, "
                f"weight={z.get('weight_lb', 0)}/{z.get('max_weight_lb', 0)} lb, "
                f"floor={z.get('floor_pct', 0)}%, door={z.get('door_in')}"
            )

    if unplaced:
        lines.append("\n--- Unplaced Items ---")
        for u in unplaced[:10]:
            lines.append(f"- {u.get('id')} ({u.get('label')}): {u.get('reason')}")

    if vrep.get("violations"):
        lines.append(f"\n--- Rule Violations ({len(vrep['violations'])}) ---")
        for v in vrep["violations"][:12]:
            lines.append(f"- [{v.get('rule')}] {v.get('detail')}")

    if inventory is not None:
        lines.append("\n--- Inventory & User Instructions ---")
        lines.append(f"Expected movable furniture units (keep/undecided): {expected_movable_units}")
        lines.append(f"Excluded non-moving lines (stays/trash/sell/donate): {len(excluded_items)}")
        if excluded_items:
            lines.append("  Excluded: " + "; ".join(excluded_items[:8]))
        if spoken_quotes:
            lines.append("  Spoken instructions applied: " + "; ".join(spoken_quotes[:6]))
        lines.append(
            f"Open user questions: {len(open_questions)} "
            f"(high-volume >=8 cu ft: {sum(1 for q in open_questions if float(q.get('volume_at_stake') or 0) >= 8.0)})"
        )
        if unknown_containers:
            lines.append("  Closed containers assumed empty pending user confirmation: " + "; ".join(unknown_containers[:6]))

    lines.append(f"\nArrival render attached: {has_arrival_image}")

    facts = {
        "verify_valid": bool(vrep.get("valid")),
        "verifier_score": float(vrep.get("total", 0.0)),
        "violation_count": int(vrep.get("violation_count", 0)),
        "violations_by_rule": dict(vrep.get("violation_counts_by_rule") or {}),
        "unplaced_count": len(unplaced),
        "truck_count": len(trucks),
        "open_question_count": len(open_questions),
        "high_stake_open_questions": sum(
            1 for q in open_questions if float(q.get("volume_at_stake") or 0.0) >= 8.0 or q.get("always_show")
        ),
        "unknown_container_count": len(unknown_containers),
        "has_arrival_image": has_arrival_image,
    }
    return "\n".join(lines), facts


def _deterministic_plan_answers(
    facts: dict[str, Any],
    verify_report: dict[str, Any],
    include_visual: bool,
) -> dict[str, dict[str, Any]]:
    """Transparent rule-derived fallback used only when no API key is configured locally."""
    has_risk = (not facts["verify_valid"]) or facts["unplaced_count"] > 0
    p_risk = 0.92 if has_risk else 0.06

    v_total = float(verify_report.get("total", 0.0))
    lifo = float(verify_report.get("lifo_score", 0.0))
    zone_cov = float(verify_report.get("zone_coverage_pct", 0.0))

    if has_risk:
        safety_lvl = max(0.0, min(2.0, v_total / 40.0))
    elif v_total >= 85.0:
        safety_lvl = 3.8
    else:
        safety_lvl = 3.2

    zone_err = any(
        r in (facts["violations_by_rule"] or {})
        for r in ("zone_door_clearance", "zone_fit", "zone_overlap", "zone_overweight", "zone_distribution")
    )
    if zone_err:
        routing_lvl = 1.0
    else:
        routing_lvl = round(min(4.0, 2.0 + (lifo / 10.0) * 1.2 + (zone_cov / 100.0) * 0.8), 2)

    if has_risk:
        readiness_lvl = 1.0
        choice = "replan_solver"
    elif facts["high_stake_open_questions"] > 0:
        readiness_lvl = 2.9
        choice = "ask_user_open_questions"
    else:
        readiness_lvl = 3.8
        choice = "approve_dispatch"

    def _mk_score(val: float, crit: list[str]) -> dict[str, Any]:
        max_s = len(crit) - 1
        val_c = round(max(0.0, min(float(max_s), val)), 4)
        idx = int(round(val_c))
        probs = {str(i): (0.82 if i == idx else round(0.18 / max_s, 4)) for i in range(len(crit))}
        return {
            "type": "score",
            "score": val_c,
            "max_score": max_s,
            "normalized": round(val_c / max_s, 4),
            "probabilities": probs,
            "legend": {str(i): c for i, c in enumerate(crit)},
            "confidence": 0.82,
        }

    answers: dict[str, dict[str, Any]] = {
        "has_safety_or_damage_risk": {
            "type": "noul",
            "noul": p_risk,
            "answer": p_risk >= 0.5,
            "confidence": round(max(p_risk, 1.0 - p_risk), 4),
        },
        "respects_user_instructions": {
            "type": "noul",
            "noul": 0.94,
            "answer": True,
            "confidence": 0.94,
        },
        "load_safety_score": _mk_score(safety_lvl, BASE_MOVE_PLAN_QUESTIONS["load_safety_score"]["criteria"]),
        "penn_routing_lifo_score": _mk_score(routing_lvl, BASE_MOVE_PLAN_QUESTIONS["penn_routing_lifo_score"]["criteria"]),
        "mover_readiness_score": _mk_score(readiness_lvl, BASE_MOVE_PLAN_QUESTIONS["mover_readiness_score"]["criteria"]),
        "dispatch_action": {
            "type": "choice",
            "choice": choice,
            "probabilities": {
                k: (0.84 if k == choice else round(0.16 / 3, 4))
                for k in BASE_MOVE_PLAN_QUESTIONS["dispatch_action"]["criteria"]
            },
            "confidence": 0.84,
        },
    }
    if include_visual:
        answers["visual_render_matches_plan"] = {
            "type": "noul",
            "noul": 0.88,
            "answer": True,
            "confidence": 0.88,
        }
    return answers


def _deterministic_escalation(placement: dict, facts: dict[str, Any], verify_report: dict[str, Any]) -> dict[str, Any]:
    """Rule-based strategy repair recommendation when escalation runs without a live API key."""
    rules = facts.get("violations_by_rule") or {}
    cur_strat = placement.get("strategy") or {}
    cur_truck = str(cur_strat.get("truck_id") or "uhaul_26")

    next_truck = cur_truck
    if "unplaced_item" in rules or "fit" in rules or "truck_overweight" in rules:
        next_truck = "uhaul_26"

    if any(r in rules for r in ("fragile_crushed", "light_only_on_top", "no_stack")):
        order_mode = "fragile_last"
    elif float(verify_report.get("lifo_score", 10.0)) < 7.0:
        order_mode = "zone_strict_lifo"
    else:
        order_mode = "lifo_heavy_first"

    blocking = [v["detail"] for v in (verify_report.get("violations") or [])[:6]]
    if not facts["verify_valid"]:
        verdict = "replan_solver"
        summary = f"Plan has {facts['violation_count']} rule violation(s); re-run solver with {next_truck} and {order_mode}."
    elif facts["high_stake_open_questions"] > 0:
        verdict = "ask_user_open_questions"
        summary = (
            f"Physics checks pass ({verify_report.get('total')}/100), but "
            f"{facts['high_stake_open_questions']} high-impact inventory question(s) remain open."
        )
    else:
        verdict = "approve_dispatch"
        summary = f"All mover safety, balance, and Penn Station store checks pass ({verify_report.get('total')}/100)."

    mover_notes: list[str] = []
    all_items = [it for t in placement.get("trucks", []) for it in t.get("items", [])]
    two_person_cnt = sum(1 for it in all_items if it.get("two_person"))
    fragile_cnt = sum(1 for it in all_items if it.get("fragile"))
    if two_person_cnt:
        mover_notes.append(f"{two_person_cnt} piece(s) require a two-person lift (>50 lb or bulky furniture).")
    if fragile_cnt:
        mover_notes.append(f"{fragile_cnt} fragile piece(s)/boxes packed; pad and strap before departure.")
    mover_notes.append("Use a commercial/truck-height navigation route (avoid parkways) en route to NY Penn Station.")

    return {
        "verdict": verdict,
        "summary": summary,
        "blocking_issues": blocking,
        "mover_notes": mover_notes,
        "recommended_strategy_patch": {
            "truck_id": next_truck,
            "order_mode": order_mode,
            "downsize_last_truck": True,
        },
        "via": "deterministic_rule_fallback",
    }


def _collect_run_media(rd: Path | None, arrival_image: Path | None) -> tuple[list[Media], bool]:
    media: list[Media] = []
    has_arrival = False
    candidates: list[Path] = []
    if arrival_image and Path(arrival_image).exists():
        candidates.append(Path(arrival_image))
    elif rd is not None:
        for name in ("arrival.png", "arrival.jpg", "arrival.jpeg", "arrival.webp"):
            p = rd / name
            if p.exists():
                candidates.append(p)
                break
    for p in candidates:
        try:
            m = media_from_path(p)
            m.caption = f"Illustrative Penn Station arrival render ({p.name})"
            media.append(m)
            has_arrival = True
        except ValueError:
            pass

    if rd is not None and (rd / "crops").is_dir():
        for crop_path in sorted((rd / "crops").glob("*.jpg"))[:2]:
            try:
                cm = media_from_path(crop_path)
                cm.caption = f"Source room item crop ({crop_path.name})"
                media.append(cm)
            except ValueError:
                pass
    return media, has_arrival


def judge_move_plan(
    placement: dict,
    inventory: dict | None = None,
    *,
    arrival_image: Path | str | None = None,
    run_id: str | None = None,
    rd: Path | None = None,
    allow_offline_fallback: bool = True,
) -> dict[str, Any]:
    """Run Final Judge Step 1 on a solved packing plan.

    Evaluates safety, completeness, Penn Station LIFO store routing, and optional
    arrival visuals with `gemini-decision-1` (`noul` + `choice` + `score`), and
    escalates low-confidence or flagged plans to Gemini 4 (`judge_escalate`).
    """
    if rd is None and run_id:
        rd = run_dir(run_id)

    verify_report = verify.verify(placement)
    placement["score"] = verify_report

    media, has_arrival = _collect_run_media(rd, Path(arrival_image) if arrival_image else None)
    context_text, facts = summarize_move_plan_context(
        placement,
        inventory=inventory,
        verify_report=verify_report,
        has_arrival_image=has_arrival,
    )

    questions = dict(BASE_MOVE_PLAN_QUESTIONS)
    if has_arrival:
        questions["visual_render_matches_plan"] = dict(VISUAL_RENDER_QUESTION)

    via = "decisions_api"
    try:
        batch = for_job("judge", run_dir=rd).decide_batch(
            context_text,
            questions=questions,
            media=media,
            prompt_version="judge_move_plan_v1",
            label=f"judge_plan:{run_id or 'inline'}",
        )
        answers = batch["answers"]
        via = batch["via"]
    except LLMError:
        if not allow_offline_fallback:
            raise
        answers = _deterministic_plan_answers(facts, verify_report, include_visual=has_arrival)
        via = "deterministic_rule_fallback"

    hazard = answers["has_safety_or_damage_risk"]
    respects = answers["respects_user_instructions"]
    route = answers["dispatch_action"]
    safety_sc = answers["load_safety_score"]
    routing_sc = answers["penn_routing_lifo_score"]
    readiness_sc = answers["mover_readiness_score"]

    score_confs = [safety_sc["confidence"], routing_sc["confidence"], readiness_sc["confidence"]]
    escalation_reasons: list[str] = []
    if route["confidence"] < CONFIDENCE_THRESHOLD:
        escalation_reasons.append(f"dispatch_action confidence {route['confidence']:.2f} < {CONFIDENCE_THRESHOLD}")
    if hazard["noul"] > HAZARD_NOUL_THRESHOLD:
        escalation_reasons.append(f"has_safety_or_damage_risk P(yes)={hazard['noul']:.2f} > {HAZARD_NOUL_THRESHOLD}")
    if not respects["answer"]:
        escalation_reasons.append(f"respects_user_instructions P(yes)={respects['noul']:.2f} < 0.50")
    if not facts["verify_valid"]:
        escalation_reasons.append(f"deterministic verifier reported {facts['violation_count']} violation(s)")
    if min(score_confs) < 0.65:
        escalation_reasons.append(f"rubric confidence {min(score_confs):.2f} < 0.65")

    needs_escalation = len(escalation_reasons) > 0
    escalation: dict[str, Any] | None = None

    if needs_escalation:
        if via == "deterministic_rule_fallback":
            escalation = _deterministic_escalation(placement, facts, verify_report)
        else:
            esc_prompt = (
                "You are the senior Move Plan Judge escalating a flagged or uncertain truck packing plan.\n"
                "Review the deterministic verifier metrics, Penn Station store routing, and Gemini Decision 1 "
                "calibrated scores below. Identify concrete blocking issues, practical mover notes, and the best "
                "`recommended_strategy_patch` for `solver.solve()`.\n\n"
                f"Escalation triggers: {', '.join(escalation_reasons)}\n\n"
                f"{context_text}\n\n"
                f"Decisions API answers:\n{json.dumps(answers, indent=2)}"
            )
            try:
                esc_out = for_job("judge_escalate", run_dir=rd).generate_json(
                    esc_prompt,
                    media=media,
                    schema=ESCALATION_SCHEMA,
                    prompt_version="judge_plan_escalate_v1",
                    label=f"judge_plan_escalate:{run_id or 'inline'}",
                )
                escalation = {**esc_out, "via": for_job("judge_escalate", run_dir=rd).spec}
            except LLMError:
                if not allow_offline_fallback:
                    raise
                escalation = _deterministic_escalation(placement, facts, verify_report)

    # Overall 0-100 Move Plan Judge score combining the three calibrated 0..4 rubrics (weighted 45/30/25)
    rubric_100 = round(
        (
            0.45 * safety_sc["normalized"]
            + 0.30 * routing_sc["normalized"]
            + 0.25 * readiness_sc["normalized"]
        )
        * 100.0,
        1,
    )

    final_action = escalation["verdict"] if escalation else route["choice"]
    approved = (
        final_action in ("approve_dispatch", "approve_with_caution")
        and facts["verify_valid"]
        and hazard["noul"] <= HAZARD_NOUL_THRESHOLD
    )

    result: dict[str, Any] = {
        "step": "move_plan_judge",
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "run_id": run_id,
        "approved": approved,
        "recommended_action": final_action,
        "judge_score_100": rubric_100,
        "verifier_score_100": verify_report["total"],
        "via": via,
        "gates": {
            "has_safety_or_damage_risk": hazard,
            "respects_user_instructions": respects,
            **(
                {"visual_render_matches_plan": answers["visual_render_matches_plan"]}
                if "visual_render_matches_plan" in answers
                else {}
            ),
        },
        "rubrics": {
            "load_safety": safety_sc,
            "penn_routing_lifo": routing_sc,
            "mover_readiness": readiness_sc,
        },
        "routing": route,
        "escalated": needs_escalation,
        "escalation_reasons": escalation_reasons,
        "escalation": escalation,
        "facts": facts,
    }

    if rd is not None:
        write_json(rd / "judge_plan.json", result)
    return result


def judge_run_plan(run_id: str, *, allow_offline_fallback: bool = True) -> dict[str, Any]:
    """Load `runs/<run_id>/inventory.json` (or `sample_venue` / `mock-demo`) and run Step 1."""
    repo_root = Path(__file__).resolve().parents[1]
    rid = (run_id or "").strip()
    if rid in ("sample_venue", "sample"):
        sample_path = repo_root / "data" / "sample_venue.json"
        if not sample_path.exists():
            raise FileNotFoundError(f"sample_venue.json not found: {sample_path}")
        inv = json.loads(sample_path.read_text(encoding="utf-8"))
        return judge_move_plan(
            solver.solve(inv),
            inventory=inv,
            run_id="sample_venue",
            rd=None,
            allow_offline_fallback=allow_offline_fallback,
        )
    if rid == "mock-demo":
        mock_path = repo_root / "frontend" / "mock" / "inventory.json"
        if not mock_path.exists():
            raise FileNotFoundError(f"mock inventory not found: {mock_path}")
        inv = json.loads(mock_path.read_text(encoding="utf-8"))
        return judge_move_plan(
            solver.solve(inv),
            inventory=inv,
            run_id="mock-demo",
            rd=None,
            allow_offline_fallback=allow_offline_fallback,
        )

    rd = run_dir(rid)
    if not rd.exists():
        raise FileNotFoundError(f"run folder not found: {rd}")
    inv = read_json(rd / "inventory.json")
    placement = read_json(rd / "placement.json")
    if placement is None:
        if inv is None:
            raise ValueError(f"run {rid!r} has neither placement.json nor inventory.json")
        placement = solver.solve(inv)
        write_json(rd / "placement.json", placement)
    return judge_move_plan(
        placement,
        inventory=inv,
        run_id=rid,
        rd=rd,
        allow_offline_fallback=allow_offline_fallback,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Final Judge Step 1: evaluate a solved Pack It Up move plan.")
    ap.add_argument("inventory", nargs="?", type=Path, default=None, help="Optional inventory_v2 JSON to solve & judge")
    ap.add_argument("--run", dest="run_id", default=None, help="Existing run_id under runs/")
    ap.add_argument("--placement", type=Path, default=None, help="Pre-computed placement JSON")
    ap.add_argument("--arrival-image", type=Path, default=None, help="Optional arrival render image")
    ap.add_argument("--out", type=Path, default=None, help="Optional path to save judge_plan JSON")
    ap.add_argument("--strict-online", action="store_true", help="Fail instead of falling back when GEMINI_API_KEY is unset")
    args = ap.parse_args()

    if args.run_id:
        res = judge_run_plan(args.run_id, allow_offline_fallback=not args.strict_online)
    else:
        inv = json.loads(args.inventory.read_text(encoding="utf-8")) if args.inventory else None
        if args.placement:
            plan = json.loads(args.placement.read_text(encoding="utf-8"))
        elif inv is not None:
            plan = solver.solve(inv)
        else:
            ap.error("Provide an inventory JSON, --placement, or --run <run_id>")
            return
        res = judge_move_plan(
            plan,
            inventory=inv,
            arrival_image=args.arrival_image,
            allow_offline_fallback=not args.strict_online,
        )

    print(
        f"[Move Plan Judge] approved={res['approved']} action={res['recommended_action']} "
        f"judge_score={res['judge_score_100']}/100 verifier={res['verifier_score_100']}/100 "
        f"via={res['via']} escalated={res['escalated']}"
    )
    for name, r in res["rubrics"].items():
        print(f"  - {name}: {r['score']:.2f}/{r['max_score']} (conf={r['confidence']:.2f})")
    if res["escalation"]:
        print(f"  Escalation ({res['escalation']['via']}): {res['escalation']['summary']}")
    if args.out:
        args.out.write_text(json.dumps(res, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
