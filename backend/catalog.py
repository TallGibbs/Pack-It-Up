"""Catalog lookup for items, trucks, and Penn Station destination stores/zones.

Owned by Track B (George). Keeps `load()` and `get()` backwards-compatible with
Track A's `resolve.py` (in particular, `row["weight_lb"]` stays `None` when the
CSV leaves it blank so `resolve.py` uses its material density table, while
`lookup()` and `estimate_weight_lb()` compute the 7 lb/cu ft fallback).
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CATALOG_PATH = DATA_DIR / "item_catalog.csv"
TRUCKS_PATH = DATA_DIR / "trucks.csv"
PENN_ZONES_PATH = DATA_DIR / "penn_zones.csv"

DEFAULT_LB_PER_CUFT = 7.0

_ITEM_NUM = {"length_in", "width_in", "height_in", "weight_lb"}
_TRUCK_NUM = {
    "length_in", "width_in", "height_in", "max_weight_lb",
    "door_width_in", "door_height_in", "deck_height_in",
}
_ZONE_NUM = {
    "length_in", "width_in", "height_in",
    "door_width_in", "door_height_in", "max_weight_lb",
}


def _yes(val: object) -> bool:
    return str(val or "").strip().lower() in ("yes", "true", "1")


def volume_cuft(length_in: float, width_in: float, height_in: float) -> float:
    """Cubic feet from dimensions in inches."""
    return round((length_in * width_in * height_in) / 1728.0, 2)


def estimate_weight_lb(
    item_or_dims: str | dict | list[float] | tuple[float, float, float],
    lb_per_cuft: float = DEFAULT_LB_PER_CUFT,
) -> float:
    """Return explicit catalog weight if present, else 7 lb per cubic foot."""
    if isinstance(item_or_dims, str):
        row = get(item_or_dims)
        if row is None:
            raise KeyError(f"unknown catalog_id: {item_or_dims!r}")
        item_or_dims = row
    if isinstance(item_or_dims, dict):
        if item_or_dims.get("weight_lb") is not None:
            return round(float(item_or_dims["weight_lb"]), 1)
        l, w, h = item_or_dims["length_in"], item_or_dims["width_in"], item_or_dims["height_in"]
    else:
        l, w, h = item_or_dims
    return round((l * w * h / 1728.0) * lb_per_cuft, 1)


@lru_cache(maxsize=1)
def load() -> dict[str, dict]:
    """Load item_catalog.csv keyed by catalog_id (Track A compatible)."""
    rows: dict[str, dict] = {}
    with open(CATALOG_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            row: dict = {}
            for k, v in r.items():
                v = (v or "").strip()
                row[k] = (float(v) if v else None) if k in _ITEM_NUM else v
            dims = [row["length_in"], row["width_in"], row["height_in"]]
            vol = volume_cuft(*dims)
            row["dims_in"] = dims
            row["volume_cuft"] = vol
            row["est_weight_lb"] = (
                round(float(row["weight_lb"]), 1)
                if row.get("weight_lb") is not None
                else round(vol * DEFAULT_LB_PER_CUFT, 1)
            )
            rows[row["catalog_id"]] = row
    return rows


def get(catalog_id: str) -> dict | None:
    """Raw catalog row (keeps weight_lb=None when CSV has none, for Track A resolve.py)."""
    return load().get(catalog_id)


def lookup(catalog_id: str) -> dict | None:
    """Normalized Track B item lookup with dims_in, volume_cuft, weight_lb, and bool flags."""
    row = get(catalog_id)
    if row is None:
        return None
    return {
        "catalog_id": row["catalog_id"],
        "name": row["name"],
        "category": row["category"],
        "dims_in": list(row["dims_in"]),
        "length_in": row["length_in"],
        "width_in": row["width_in"],
        "height_in": row["height_in"],
        "volume_cuft": row["volume_cuft"],
        "weight_lb": row["est_weight_lb"],
        "stackable": row.get("stackable_on_top") or "no",
        "must_stay_upright": _yes(row.get("must_stay_upright")),
        "load_on_edge": _yes(row.get("load_on_edge")),
        "fragile": _yes(row.get("fragile")),
        "two_person": _yes(row.get("two_person")),
    }


@lru_cache(maxsize=1)
def load_trucks() -> dict[str, dict]:
    """Load trucks.csv keyed by truck_id."""
    trucks: dict[str, dict] = {}
    with open(TRUCKS_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            row: dict = {}
            for k, v in r.items():
                v = (v or "").strip()
                row[k] = float(v) if k in _TRUCK_NUM else v
            dims = [row["length_in"], row["width_in"], row["height_in"]]
            row["dims_in"] = dims
            row["door_in"] = [row["door_width_in"], row["door_height_in"]]
            row["volume_cuft"] = volume_cuft(*dims)
            trucks[row["truck_id"]] = row
    return trucks


def get_truck(truck_id: str) -> dict | None:
    return load_trucks().get(truck_id)


def list_trucks() -> list[dict]:
    """Return trucks ordered from smallest to largest cargo volume."""
    return sorted(load_trucks().values(), key=lambda t: t["volume_cuft"])


@lru_cache(maxsize=1)
def load_penn_zones() -> dict[str, dict]:
    """Load Penn Station destination stores/zones keyed by zone_id."""
    zones: dict[str, dict] = {}
    with open(PENN_ZONES_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            row: dict = {}
            for k, v in r.items():
                v = (v or "").strip()
                if k in _ZONE_NUM:
                    row[k] = float(v)
                elif k == "dock_stop":
                    row[k] = int(v)
                elif k in ("categories", "keywords"):
                    row[k] = [x.strip().lower() for x in v.split(";") if x.strip()]
                else:
                    row[k] = v
            dims = [row["length_in"], row["width_in"], row["height_in"]]
            row["dims_in"] = dims
            row["door_in"] = [row["door_width_in"], row["door_height_in"]]
            row["volume_cuft"] = volume_cuft(*dims)
            row["floor_sqft"] = round((row["length_in"] * row["width_in"]) / 144.0, 1)
            zones[row["zone_id"]] = row
    return zones


def get_penn_zone(zone_id: str) -> dict | None:
    return load_penn_zones().get(zone_id)


def list_penn_zones() -> list[dict]:
    """Return Penn Station destination zones ordered by dock_stop (1 = unloaded first)."""
    return sorted(load_penn_zones().values(), key=lambda z: z["dock_stop"])
