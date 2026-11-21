"""Score a run's inventory.json against a hand count.

    python eval/score_inventory.py runs/<run_id> eval/hand_counts/malin.json [--json out.json]

Reports per hand-counted item: found, missed, double counted (inventory has more
than the hand count); inventory items that match nothing (extra), and fixtures or
personal belongings wrongly included. Matching is by catalog id, then by keyword
in the label. Also a size check: the model's own estimate against the catalog
dimensions, as percent error, for catalog-matched items.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKIP_DISPOSITIONS = {"trash", "sell", "donate", "stays", "removed"}


def _has(label: str, words: list[str]) -> bool:
    low = label.lower()
    return any(re.search(rf"\b{re.escape(w.lower())}", low) for w in words)


def load_inventory(path: Path) -> dict:
    if path.is_dir():
        path = path / "inventory.json"
    return json.loads(path.read_text(encoding="utf-8"))


def score(inv: dict, hand: dict) -> dict:
    items = [dict(i, _room=r["room"]["name"]) for r in inv["rooms"] for i in r["items"]
             if i.get("disposition") not in SKIP_DISPOSITIONS]
    assigned: dict[int, str] = {}
    entries = hand["movable"]

    # Pass 1: catalog id equals the hand-count key.
    for e in entries:
        for idx, it in enumerate(items):
            if idx not in assigned and it["catalog_id"] == e["key"]:
                assigned[idx] = e["key"]
    # Pass 2: keyword in label. Entries with more specific (longer) keywords go first,
    # so "table" for the second table is tried after "coffee table" and "communal".
    for e in sorted(entries, key=lambda e: -max(len(w) for w in e["match"])):
        for idx, it in enumerate(items):
            if idx not in assigned and _has(it["label"], e["match"]):  # any line no catalog entry claimed
                assigned[idx] = e["key"]
    # Pass 3: optional items (neither missed nor extra).
    for o in hand.get("optional", []):
        for idx, it in enumerate(items):
            if idx not in assigned and _has(it["label"], o["match"]):
                assigned[idx] = "optional:" + o["key"]

    rows = []
    for e in entries:
        got = [items[i] for i, k in assigned.items() if k == e["key"]]
        n = sum(i["quantity"] for i in got)
        dims_check = None
        if e.get("dims_in") and got:
            d = got[0]["size"]["dims_in"]  # [length, width, height]
            exp = e["dims_in"]
            dims_check = {"inventory_dims_in": d, "expected": exp,
                          "height_pct_error": round(100 * (d[2] - exp["height"]) / exp["height"], 1) if exp.get("height") else None,
                          "width_ok": (d[0] >= exp["width_min"]) if exp.get("width_min") else None}
        rows.append({"key": e["key"], "label": e["label"], "verified": e.get("verified", "photos"), "dims_check": dims_check,
                     "hand": e["quantity"], "inventory": n,
                     "found": min(n, e["quantity"]), "missed": max(0, e["quantity"] - n),
                     "double_counted": max(0, n - e["quantity"]),
                     "matched_lines": [f"{i['label']} x{i['quantity']} ({i['catalog_id']})" for i in got]})

    fixture_words = [w for f in hand.get("fixtures", []) for w in f.lower().split() if len(w) > 3]
    extras, wrong_fixture, wrong_personal = [], [], []
    personal_words = ["backpack", "bag", "laptop", "coat", "jacket", "bottle", "cup", "phone", "food"]
    for idx, it in enumerate(items):
        if idx in assigned:
            continue
        rec = f"{it['label']} x{it['quantity']} ({it['catalog_id']})"
        if _has(it["label"], personal_words):
            wrong_personal.append(rec)
        elif _has(it["label"], ["built-in", "built in", "wall-mounted", "mounted", "sconce", "pendant", "extinguisher",
                                "exit sign", "camera", "track light"]):
            wrong_fixture.append(rec)
        else:
            extras.append(rec)

    hand_total = sum(e["quantity"] for e in entries)
    found = sum(r["found"] for r in rows)
    inv_total = sum(i["quantity"] for idx, i in enumerate(items) if not str(assigned.get(idx, "")).startswith("optional:"))

    # Size check: model estimate vs catalog dims for catalog-matched items.
    sizes = []
    for it in items:
        s = it["size"]
        v, c = s.get("vision_dims_in"), s.get("catalog_dims_in")
        # Catalog rows for a packed form (rolled rug, disassembled frame) aren't comparable with what the camera sees.
        if any(w in it["catalog_id"] for w in ("rolled", "disassembled", "folded")):
            continue
        if v and c:
            pct = [round(100 * (v[k] - c[k]) / c[k], 1) for k in range(3)]
            vol_pct = round(100 * ((v[0] * v[1] * v[2]) / (c[0] * c[1] * c[2]) - 1), 1)
            sizes.append({"label": it["label"], "catalog_id": it["catalog_id"], "vision_dims_in": v,
                          "catalog_dims_in": c, "pct_error_lwh": pct, "pct_error_volume": vol_pct,
                          "size_source": s["size_source"]})
    mae = (round(sum(abs(p) for s in sizes for p in s["pct_error_lwh"]) / (3 * len(sizes)), 1) if sizes else None)

    return {
        "run_id": inv.get("run_id"), "hand_count": hand.get("room"),
        "inventory_files": sorted({f for r in inv["rooms"] for f in r.get("files", [])}),
        "hand_files": hand.get("files", []),
        "rows": rows,
        "summary": {"hand_units": hand_total, "inventory_units": inv_total, "found": found,
                    "missed": sum(r["missed"] for r in rows), "double_counted": sum(r["double_counted"] for r in rows),
                    "extra_lines": len(extras), "fixtures_wrongly_included": len(wrong_fixture),
                    "personal_wrongly_included": len(wrong_personal),
                    "recall_pct": round(100 * found / hand_total, 1) if hand_total else None,
                    "precision_pct": round(100 * found / inv_total, 1) if inv_total else None},
        "extras": extras, "fixtures_wrongly_included": wrong_fixture, "personal_wrongly_included": wrong_personal,
        "size_check": {"items": sizes, "mean_abs_pct_error_per_dim": mae},
    }


def print_report(res: dict) -> None:
    print(f"Run {res['run_id']} vs hand count '{res['hand_count']}'")
    if set(res["inventory_files"]) != set(res["hand_files"]):
        print(f"  note: inventory files {res['inventory_files']} differ from hand-count files {res['hand_files']}")
    print(f"\n  {'hand-counted item':<44} {'hand':>4} {'inv':>4} {'found':>5} {'missed':>6} {'double':>6}  checked")
    for r in res["rows"]:
        print(f"  {r['label'][:44]:<44} {r['hand']:>4} {r['inventory']:>4} {r['found']:>5} {r['missed']:>6} "
              f"{r['double_counted']:>6}  {r['verified'].replace('_', ' ')}")
    for r in res["rows"]:
        if r.get("dims_check"):
            dc = r["dims_check"]
            print(f"  size vs in person, {r['key']}: inventory {dc['inventory_dims_in']} in; expected {dc['expected']}; "
                  f"height error {dc['height_pct_error']}%, width at least expected: {dc['width_ok']}")
    s = res["summary"]
    print(f"\n  FOUND {s['found']} of {s['hand_units']} hand-counted units (recall {s['recall_pct']}%), "
          f"MISSED {s['missed']}, DOUBLE COUNTED {s['double_counted']}; "
          f"inventory has {s['inventory_units']} units (precision {s['precision_pct']}%)")
    print(f"  Extra lines not in the hand count: {s['extra_lines']} {res['extras']}")
    print(f"  Fixtures wrongly included: {s['fixtures_wrongly_included']} {res['fixtures_wrongly_included']}")
    print(f"  Personal belongings wrongly included: {s['personal_wrongly_included']} {res['personal_wrongly_included']}")
    sc = res["size_check"]
    if sc["items"]:
        print(f"\n  Size check: model estimate vs catalog (percent error L/W/H, volume)")
        for it in sc["items"]:
            print(f"    {it['label'][:36]:<36} {str(it['vision_dims_in']):<20} vs {str(it['catalog_dims_in']):<20} "
                  f"{it['pct_error_lwh']}  vol {it['pct_error_volume']:+}%")
        print(f"    mean absolute error per dimension: {sc['mean_abs_pct_error_per_dim']}%")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path, help="run folder or inventory.json")
    ap.add_argument("hand", type=Path, help="hand count JSON")
    ap.add_argument("--json", type=Path, help="also write the result here")
    args = ap.parse_args(argv)
    res = score(load_inventory(args.run), json.loads(args.hand.read_text(encoding="utf-8")))
    print_report(res)
    if args.json:
        args.json.write_text(json.dumps(res, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
