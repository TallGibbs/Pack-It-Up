"""CLI: python -m backend.ingest data/Inputs/Malin --room "Malin lounge"

Writes runs/<run_id>/ and prints the run id and a summary table.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .common import new_run_id, run_dir
from .intake import collect_folder, intake
from .merge import merge
from .perceive import perceive_all
from .pipeline import run_pipeline


def print_summary(inv: dict) -> None:
    for room in inv["rooms"]:
        print(f"\n{room['room']['name']}  ({len(room['files'])} files)")
        print(f"  {'item':<44} {'qty':>3}  {'size source':<16} {'dims in':<17} {'cu ft':>6} {'lb':>6}  weight src")
        for it in room["items"]:
            s = it["size"]
            dims = "x".join(f"{d:g}" for d in s["dims_in"])
            print(f"  {it['label'][:44]:<44} {it['quantity']:>3}  {s['size_source']:<16} {dims:<17} "
                  f"{s['volume_cuft_total']:>6.1f} {s['weight_lb_total']:>6.0f}  {s['weight_source']}")
        for c in room["containers"]:
            print(f"  [container] {c['label'][:40]:<40} {c['kind']:<14} {c['fullness']:<12} {c.get('est_volume_cuft', '')}")
        t, lo = room["totals"], room["left_out"]
        print(f"  TOTAL {t['item_count']} items in {t['item_lines']} lines, {t['volume_cuft']} cu ft, {t['weight_lb']:.0f} lb"
              f" (+{t['boxed_volume_cuft']} cu ft boxed). Left out: {lo['fixtures']} fixtures,"
              f" {lo['personal_belongings']} personal belongings")
    if inv.get("questions"):
        print(f"\n{len(inv['questions'])} questions; see questions.json")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.ingest")
    ap.add_argument("folder", type=Path, help="folder of photos and clips for one room")
    ap.add_argument("--room", help="room name (default: folder name)")
    ap.add_argument("--run-id", help="add to an existing run (multi-room move)")
    ap.add_argument("--until", default="resolve", choices=["intake", "perceive", "merge", "resolve"], help="stop after this stage")
    ap.add_argument("--no-questions", action="store_true", help="skip stage 5 (no decide calls)")
    ap.add_argument("--include", help="comma-separated file names to use from the folder (default: all)")
    args = ap.parse_args(argv)

    files = collect_folder(args.folder)
    if args.include:
        wanted = {n.strip().lower() for n in args.include.split(",")}
        files = [f for f in files if f.name.lower() in wanted]
    if not files:
        print(f"no accepted media in {args.folder}", file=sys.stderr)
        return 1
    run_id = args.run_id or new_run_id(args.room or args.folder.name)
    manifest = intake(files, args.room or args.folder.name, run_id)
    print(f"run_id: {run_id}")
    for f in manifest["files"]:
        extra = f"{f['duration_s']:.1f}s {f.get('codec')}" if f["kind"] == "video" else f"{f['width']}x{f['height']}"
        print(f"  {f['name']:<16} {f['kind']:<6} {f['bytes'] / 1e6:5.1f} MB  {extra}  {f['sha256'][:12]}")
    for s in manifest["skipped"]:
        print(f"  skipped {s['name']}: {s['reason']}")
    if args.until == "intake":
        return 0
    if args.until == "perceive":
        perceive_all(run_id)
        return 0
    if args.until == "merge":
        perceive_all(run_id)
        merge(run_id)
        return 0
    inv = run_pipeline(run_id, questions=not args.no_questions)
    print_summary(inv)
    print(f"\nrun folder: {run_dir(run_id)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
