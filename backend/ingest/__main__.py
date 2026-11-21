"""CLI: python -m backend.ingest data/Inputs/Malin --room "Malin lounge"

Writes runs/<run_id>/ and prints the run id and a summary table.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .common import new_run_id
from .intake import collect_folder, intake


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.ingest")
    ap.add_argument("folder", type=Path, help="folder of photos and clips for one room")
    ap.add_argument("--room", help="room name (default: folder name)")
    ap.add_argument("--run-id", help="add to an existing run (multi-room move)")
    ap.add_argument("--until", default="intake", choices=["intake"], help="stop after this stage")
    args = ap.parse_args(argv)

    files = collect_folder(args.folder)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
