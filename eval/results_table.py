"""Build eval/RESULTS.md from the moves in runs/.

    python eval/results_table.py           # no model calls
    python eval/results_table.py --neon    # first run the Neon planner loop on one move per set of footage (model calls)

Every move that has an inventory.json is packed twice, by the stock py3dbp packer and by our
solver, and both plans are scored by the same checker (backend/verify.py). The other tables: the
Neon planner's rounds (eval/neon_rounds.json, written by --neon), the truck a rental site's
bedroom rule would pick against the smallest truck that fits, the inventory against the
in-person count of the venue lounge, and the Decisions API grading.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

from backend import solver  # noqa: E402
from backend.ingest.common import RUNS_DIR  # noqa: E402
import score_inventory  # noqa: E402

OUT = ROOT / "eval" / "RESULTS.md"
NEON = ROOT / "eval" / "neon_rounds.json"
HAND = ROOT / "eval" / "hand_counts" / "malin.json"
GRADING = ROOT / "eval" / "grading" / "malin_decisions_1109.md"

# U-Haul's own guidance, read from uhaul.com/Truck-Rentals/ on Nov 21 2026: home size and cargo volume.
RULE_OF_THUMB = {
    "uhaul_10": ("10 ft", "studio to 1 bedroom apartment", 402),
    "uhaul_15": ("15 ft", "1 bedroom home to 2 bedroom apartment", 764),
    "uhaul_20": ("20 ft", "2 bedroom home to 3 bedroom apartment", 1016),
    "uhaul_26": ("26 ft", "3 to 4 bedroom home", 1682),
}
SIZES = ["uhaul_10", "uhaul_15", "uhaul_20", "uhaul_26"]


def truck_for_rooms(n_rooms: int) -> str:
    """The rental-site rule, with each filmed room counted as a bedroom (our assumption)."""
    return SIZES[min(max(n_rooms, 1), 4) - 1]


def load_moves() -> list[dict]:
    moves = []
    for rd in sorted(RUNS_DIR.iterdir()):
        inv_path = rd / "inventory.json"
        if not inv_path.exists():
            continue
        inv = json.loads(inv_path.read_text(encoding="utf-8"))
        man = json.loads((rd / "manifest.json").read_text(encoding="utf-8")) if (rd / "manifest.json").exists() else {}
        files = sorted(str(f.get("name", "")).lower() for f in man.get("files", []))
        m = re.match(r"\d{8}-(\d{2})(\d{2})(\d{2})", rd.name)
        moves.append({
            "dir": rd, "inv": inv, "files": files,
            "id": "".join(m.groups()) if m else rd.name, "time": f"{m[1]}:{m[2]}" if m else "",
            "rooms": [r["room"]["name"] for r in inv.get("rooms", [])],
        })
    # Letter each distinct set of footage, so repeat runs of the same files are visible.
    letters: dict[tuple, str] = {}
    for mv in moves:
        key = tuple(mv["files"])
        letters.setdefault(key, chr(ord("A") + len(letters)) if len(letters) < 26 else f"S{len(letters)}")
        mv["set"] = letters[key]
    return moves


def pack(inv: dict, **strategy) -> dict:
    plan = solver.solve(inv, strategy=strategy)
    s, sc = plan["summary"], plan["score"]
    return {"trucks": s["truck_count"], "pieces": s["total_items"], "unplaced": s["unplaced_count"],
            "cuft": s["total_volume_cuft"], "violations": sc["violation_count"], "valid": sc["valid"],
            "score": sc["total"], "by_rule": dict(sc["violation_counts_by_rule"])}


def smallest_fit(inv: dict, ours: dict) -> str:
    """The smallest single truck our solver fills with nothing left over and no extra violations."""
    for tid in SIZES:
        p = pack(inv, truck_id=tid)
        if p["trucks"] == 1 and p["unplaced"] == 0 and p["violations"] <= ours["violations"]:
            return f"1 × {RULE_OF_THUMB[tid][0]}"
    return f"{ours['trucks']} × 26 ft"


def run_neon(moves: list[dict]) -> None:
    from backend import planner

    latest = {}
    for mv in moves:
        latest[mv["set"]] = mv  # moves are in time order, so the last one of each set stays
    out = {}
    for mv in latest.values():
        res = planner.plan_with_model(mv["inv"], {}, run_dir=None)
        res.pop("plan", None)
        out[f"{mv['id']}-{mv['set']}"] = res  # move id and set letter; the folder name can hold a person's name
        print(f"  neon {mv['id']}: {res.get('first_score')} -> {res.get('best_score')} ({len(res.get('rounds', []))} rounds) {res.get('note') or ''}")
    NEON.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def ft(text) -> str:
    """uhaul_26 -> 26 ft, in fleet labels and settings."""
    return re.sub(r"uhaul_(\d+)", lambda m: m.group(1) + " ft", str(text))


def build(moves: list[dict]) -> str:
    L: list[str] = []
    n = len(moves)
    n_sets = len({mv["set"] for mv in moves})
    for mv in moves:
        mv["stock"] = pack(mv["inv"], packer_engine="raw_py3dbp")
        mv["ours"] = pack(mv["inv"])

    L += ["# Results", "",
          f"Built by `python eval/results_table.py` on {datetime.now():%b %d %Y at %H:%M} from the {n} moves in `runs/` that have an inventory. "
          "Do not edit by hand; run the script again.", "",
          f"**The test set.** Every move on the demo laptop: photos and clips uploaded today, Nov 21 2026, while we built and tested. "
          f"Most are rooms at the hackathon venue; we did not record where each was filmed. "
          f"The {n} moves come from {n_sets} different sets of files: moves with the same letter under \"Set\" are repeat runs of the same footage "
          "(prompt changes during the build, or a file sent twice), so they are not independent. Where a line says \"one per set\", it counts only "
          "the latest move of each set.", ""]

    # ---- 1. Packing ----
    stock_valid = sum(mv["stock"]["valid"] for mv in moves)
    ours_valid = sum(mv["ours"]["valid"] for mv in moves)
    stock_v = sum(mv["stock"]["violations"] for mv in moves)
    ours_v = sum(mv["ours"]["violations"] for mv in moves)
    latest = list({mv["set"]: mv for mv in moves}.values())  # moves are in time order
    k = len(latest)
    rules = Counter()
    for mv in moves:
        rules.update(mv["stock"]["by_rule"])
    ours_rules = Counter()
    for mv in moves:
        ours_rules.update(mv["ours"]["by_rule"])
    L += ["## 1. Packing: a stock packer against ours, scored by the same checker", "",
          "The baseline is `py3dbp`, an open-source 3D bin packer, used as it comes (`packer_engine=\"raw_py3dbp\"`). "
          "Ours is the solver in `backend/solver.py`. Both plans go through `backend/verify.py`, which checks fit and payload, overlap, "
          "support under each piece, upright and on-edge rules, stacking and fragile rules, left/right balance and the doorways at the destination.", "",
          "| | Stock packer | Ours |", "|---|---|---|",
          f"| Plans with no rule broken | {stock_valid} of {n} | {ours_valid} of {n} |",
          f"| The same, one per set | {sum(mv['stock']['valid'] for mv in latest)} of {k} | {sum(mv['ours']['valid'] for mv in latest)} of {k} |",
          f"| Rules broken, all moves | {stock_v} | {ours_v} |",
          f"| Rules broken per move, mean | {stock_v / n:.1f} | {ours_v / n:.1f} |", "",
          "Rules the stock packer broke: " + ", ".join(f"{k} {v}" for k, v in rules.most_common()) + ".",
          ("Rules ours broke: " + ", ".join(f"{k} {v}" for k, v in ours_rules.most_common()) + "." if ours_rules else "Ours broke none."), "",
          "| Move | Set | Rooms | Pieces | Load (cu ft) | Stock: trucks | Stock: rules broken | Ours: trucks | Ours: rules broken | Ours: score |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for mv in moves:
        s, o = mv["stock"], mv["ours"]
        L.append(f"| {mv['id']} | {mv['set']} | {len(mv['rooms'])} | {o['pieces']} | {o['cuft']:.0f} | {s['trucks']} | {s['violations']} | "
                 f"{o['trucks']} | {o['violations']} | {o['score']} |")
    L += ["", "The stock packer always reports one truck because it stacks without the rules; the load does not travel that way. "
              "Trucks are U-Haul 26 ft.", ""]

    # ---- 2. Neon ----
    L += ["## 2. The Neon planner loop", ""]
    if NEON.exists():
        neon = json.loads(NEON.read_text(encoding="utf-8"))
        better = sum(1 for r in neon.values() if (r.get("best_score") or 0) > (r.get("first_score") or 0))
        fewer = sum(1 for r in neon.values() if r["rounds"] and
                    next(x for x in r["rounds"] if x["round"] == r["best_round"])["truck_count"] < r["rounds"][0]["truck_count"])
        L += [f"`gemini-4-neon` reads the checker's score and broken rules and changes the solver's settings, for up to three solver runs; "
              f"the best round with no rule broken is kept. Run on the latest move of each set of footage ({len(neon)} moves): "
              f"the score went up on {better} and the start was already best on {len(neon) - better}; the truck count went down on {fewer}. "
              "The score is the checker's own (fill, unload order, balance), so a higher score with smaller trucks means a tighter load, "
              "not a cheaper one.", "",
              "| Move | Start | Start score | Kept round | Kept | Kept score | Settings changed from the round before |",
              "|---|---|---|---|---|---|---|"]
        for key, r in neon.items():
            if not r.get("rounds"):
                continue
            first = r["rounds"][0]
            best = next(x for x in r["rounds"] if x["round"] == r["best_round"])
            changed = ft("; ".join(f"{k}: {a} → {b}" for k, (a, b) in (best.get("changed") or {}).items())) or "nothing (the start was best)"
            L.append(f"| {key[:6]} | {ft(first['fleet'])} | {first['score']} | {r['best_round']} of {len(r['rounds'])} | {ft(best['fleet'])} | {best['score']} | {changed} |")
        notes = [f"{k[:6]}: {r['note']}" for k, r in neon.items() if r.get("note")]
        if notes:
            L += ["", "Notes from the loop: " + " ".join(notes)]
        L += [""]
    else:
        L += ["Not run yet. `python eval/results_table.py --neon` runs it on one move per set of footage.", ""]

    # ---- 3. Rule of thumb ----
    L += ["## 3. Truck size: the rental site's bedroom rule against the smallest truck that fits", "",
          "How people pick a truck today: U-Haul's site names a truck by home size "
          "(" + "; ".join(f"{v[0]}: {v[1]}, {v[2]:,} cu ft" for v in RULE_OF_THUMB.values()) + "; "
          "[uhaul.com/Truck-Rentals](https://www.uhaul.com/Truck-Rentals/), read Nov 21 2026). "
          "We count each filmed room as a bedroom, which is our assumption and is generous to the rule. "
          "\"Trucks of that size needed\" is our solver packing the move into that truck size, checked. "
          "\"Smallest that fits\" is the smallest single U-Haul our solver fills with nothing left over.", "",
          "| Move | Set | Rooms | Rule picks | Load (cu ft) | Trucks of that size needed | Smallest that fits | Rule was |",
          "|---|---|---|---|---|---|---|---|"]
    verdicts, verdicts_latest = Counter(), Counter()
    for mv in moves:
        tid = truck_for_rooms(len(mv["rooms"]))
        need = pack(mv["inv"], truck_id=tid)["trucks"]
        fit = smallest_fit(mv["inv"], mv["ours"])
        rule_label = f"1 × {RULE_OF_THUMB[tid][0]}"
        if need > 1:
            verdict = "too small"
        elif fit == rule_label:
            verdict = "right"
        else:
            verdict = "bigger than needed"
        verdicts[verdict] += 1
        if any(mv is x for x in latest):
            verdicts_latest[verdict] += 1
        L.append(f"| {mv['id']} | {mv['set']} | {len(mv['rooms'])} | {rule_label} | {mv['ours']['cuft']:.0f} | {need} | {fit} | {verdict} |")
    L += ["", f"Over the {n} moves the rule's truck was " + ", ".join(f"{a} on {b}" for a, b in verdicts.most_common()) + "; "
              f"one per set ({k}), " + ", ".join(f"{a} on {b}" for a, b in verdicts_latest.most_common()) + ". "
              "Most of these are venue rooms (a lounge, a workspace, a conference room), not bedrooms, so this shows that a room count "
              "says little about a load; it is not a test of the rule on homes.", ""]

    # ---- 4. Inventory ----
    hand = json.loads(HAND.read_text(encoding="utf-8"))
    hand_files = sorted(f.lower() for f in hand.get("files", []))
    rows = []
    for mv in moves:
        if mv["files"] == hand_files:
            rows.append((mv, score_inventory.score(mv["inv"], hand)["summary"]))
    L += ["## 4. Inventory against a count made in person", "",
          f"The venue lounge was counted in person by Chris ({hand_files and len(hand_files)} files of footage, "
          f"{rows[0][1]['hand_units'] if rows else '?'} movable things; `eval/hand_counts/malin.json`). The count includes things that are in the room "
          "but hidden or out of frame, so 100% is not reachable from this footage. Each row is one run of the same footage; "
          "the prompt changed between runs. Scored by `eval/score_inventory.py`.", "",
          "| Move | Found | Missed | Counted twice | Recall | Precision |", "|---|---|---|---|---|---|"]
    for mv, s in rows:
        L.append(f"| {mv['id']} | {s['found']} of {s['hand_units']} | {s['missed']} | {s['double_counted']} | {s['recall_pct']}% | {s['precision_pct']}% |")
    if rows:
        rec = [s["recall_pct"] for _, s in rows]
        pre = [s["precision_pct"] for _, s in rows]
        L += ["", f"Recall {min(rec)}% to {max(rec)}%, precision {min(pre)}% to {max(pre)}% over {len(rows)} runs. "
                  "One room only: this is a first reading, not a measured accuracy."]
    L += [""]

    # ---- 5. Decisions API ----
    heads = [ln[3:].strip() for ln in GRADING.read_text(encoding="utf-8").splitlines()
             if ln.startswith("## Applied automatically") or ln.startswith("## Suggested only")]
    L += ["## 5. Decisions API answers, graded in person", "",
          "The questions the pipeline raised about the venue lounge, answered by `gemini-decision-1` and graded by Chris against the room "
          "([grading/malin_decisions_1109.md](grading/malin_decisions_1109.md)):", ""]
    L += [f"- {h}" for h in heads]
    L += ["", "So the confidence separated the answers that could be applied from the ones a person should see. Nine graded answers, one room.", ""]

    # ---- Limits ----
    L += ["## What these tables do not show", "",
          "- Homes. Most moves are venue rooms.",
          "- Independent samples. Repeat runs of the same footage are separate rows in tables 1 and 3; the \"one per set\" lines count each set once.",
          "- A neutral checker. The rules are ours and the stock packer was not built for them; the table shows what a packer without the rules does, not that it is a bad packer.",
          "- A checker that stood still. At 15:30 on Nov 21 we changed one rule: a move under 30 pieces now needs two stocked Penn Station stores, not three (`zone_distribution`, FAILURES.md 15:17). Before that change, 2 of our 24 plans broke it (moves 115436 and 124056, 17 and 14 pieces). The plans did not change; the rule did.",
          "- Table 2 after that change. The Neon rounds in `eval/neon_rounds.json` were scored before it, so move 124056 shows 67.7 there and 79.7 in table 1. Run `--neon` again to refresh them.",
          "- A single-model-call baseline (one model asked for the whole plan with coordinates). Not built.",
          "- Whether the sizes are right. Item sizes are model estimates or catalog values; nobody measured the furniture.", ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--neon", action="store_true", help="run the Neon planner loop on one move per set of footage first (model calls)")
    args = ap.parse_args()
    moves = load_moves()
    if args.neon:
        run_neon(moves)
    OUT.write_text(build(moves), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)} from {len(moves)} moves")


if __name__ == "__main__":
    main()
