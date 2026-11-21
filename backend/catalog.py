"""Item catalog lookup. Owned by Track B (George): extend this, don't rewrite it.

Track A created it with only load() and get() so resolve.py can run.
Columns: catalog_id, name, category, length_in, width_in, height_in,
stackable_on_top (yes/no/light_only), must_stay_upright, load_on_edge,
fragile, two_person (yes/no), and an optional weight_lb.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "item_catalog.csv"
_NUM = {"length_in", "width_in", "height_in", "weight_lb"}


@lru_cache(maxsize=1)
def load() -> dict[str, dict]:
    rows: dict[str, dict] = {}
    with open(CATALOG_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            row = {}
            for k, v in r.items():
                v = (v or "").strip()
                row[k] = (float(v) if v else None) if k in _NUM else v
            rows[row["catalog_id"]] = row
    return rows


def get(catalog_id: str) -> dict | None:
    return load().get(catalog_id)
