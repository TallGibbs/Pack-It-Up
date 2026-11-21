"""Stage B3: 3D multi-truck fleet solver + Penn Station store/zone packer.

Uses `py3dbp` (`Bin`, `Item`, `Packer`) for bin/item modelling and raw baseline
packing (`packer_engine="raw_py3dbp"`), and defaults to a physics-constrained
extreme-point packer (`packer_engine="constrained"`) that enforces:
  - >= 75% base support (`min_support`)
  - `must_stay_upright` and `load_on_edge` orientation rules
  - `stackable` (`yes`, `no`, `light_only`) and fragile protection
  - Left-right weight balance across truck width (`40%-60%`)
  - LIFO loading by Penn Station `dock_stop` (deepest concourse loaded first near
    cab `x=0`; stop 1 near loading dock loaded last near rear door `x=L`)
  - 3D placement inside each Penn Station destination storefront (`zones[]`).

Run from CLI:
    python -m backend.solver data/sample_venue.json
"""
from __future__ import annotations

import argparse
import heapq
import json
from pathlib import Path
from typing import Any

from py3dbp import Bin as Py3Bin, Item as Py3Item, Packer as Py3Packer

from backend import catalog, verify
from backend.expand import can_pass_door, expand_inventory

EPS = 1e-4
MAX_REACH_SETBACK_IN = 24.0


def valid_orientations(piece: dict, *, allow_all_rotations: bool = False) -> list[tuple[float, float, float]]:
    """Return legal `(dx, dy, dz)` orientations for `piece`."""
    l, w, h = [float(v) for v in piece["dims_in"]]
    all_perms = [
        (l, w, h),
        (w, l, h),
        (l, h, w),
        (h, l, w),
        (w, h, l),
        (h, w, l),
    ]
    seen: set[tuple[float, float, float]] = set()
    uniq: list[tuple[float, float, float]] = []
    for p in all_perms:
        key = (round(p[0], 3), round(p[1], 3), round(p[2], 3))
        if key not in seen:
            seen.add(key)
            uniq.append(p)

    must_upright = bool(piece.get("must_stay_upright"))
    on_edge = bool(piece.get("load_on_edge"))
    min_d, max_d = min(l, w, h), max(l, w, h)

    filtered: list[tuple[float, float, float]] = []
    for dx, dy, dz in uniq:
        if must_upright and abs(dz - h) > 0.2:
            continue
        if on_edge and max_d > min_d * 1.5 and abs(dz - min_d) <= 0.2:
            continue
        if not must_upright and not on_edge and not allow_all_rotations and abs(dz - h) > 0.2:
            continue
        filtered.append((dx, dy, dz))

    return filtered or [(l, w, h)]


def _support_tier(piece: dict) -> int:
    """0 = floor/structural base, 1 = medium/light_only, 2 = top-layer non-stackable/fragile."""
    st = str(piece.get("stackable", "no")).lower()
    h = float(piece["dims_in"][2])
    if st == "yes":
        return 0
    # Tall non-stackable items (> 45 in) cannot stack on furniture anyway; claim floor footprint early.
    if h >= 45.0 or piece.get("load_on_edge"):
        return 0
    if st == "light_only" and not piece.get("fragile"):
        return 1
    return 2


def sort_pieces(pieces: list[dict], strategy: dict) -> list[dict]:
    """Order pieces according to strategy (`lifo_heavy_first`, `heavy_first`, `volume_first`, `zone_strict_lifo`, `fragile_last`)."""
    mode = str(strategy.get("order_mode") or "lifo_heavy_first")
    lifo_wt = float(strategy.get("lifo_weight", 1.0))

    if mode == "heavy_first":
        return sorted(pieces, key=lambda p: (_support_tier(p), -p["weight_lb"], -p["volume_cuft"]))
    if mode == "volume_first":
        return sorted(pieces, key=lambda p: (_support_tier(p), -p["volume_cuft"], -p["weight_lb"]))
    if mode == "fragile_last":
        return sorted(pieces, key=lambda p: (bool(p.get("fragile")), _support_tier(p), -p["weight_lb"], -p["volume_cuft"]))
    if mode == "zone_strict_lifo":
        return sorted(
            pieces,
            key=lambda p: (-int(p.get("dock_stop") or 6), _support_tier(p), -p["weight_lb"], -p["volume_cuft"]),
        )

    # Default `lifo_heavy_first`: structural bases & tall pieces go down first while
    # deeper Penn Station dock stops (stop 6 -> stop 1) bias toward the front of the truck.
    def _key(p: dict) -> tuple:
        stop = int(p.get("dock_stop") or 6)
        tier = _support_tier(p)
        priority = stop * 45.0 * lifo_wt + p["weight_lb"] * 1.2 + p["volume_cuft"] * 2.5
        return (tier, -priority, -p["weight_lb"])

    return sorted(pieces, key=_key)


def _overlaps_3d(
    x1: float, y1: float, z1: float, x2: float, y2: float, z2: float,
    placed_boxes: list[tuple[float, float, float, float, float, float]],
) -> bool:
    for bx1, by1, bz1, bx2, by2, bz2 in placed_boxes:
        if x2 <= bx1 + EPS or bx2 <= x1 + EPS:
            continue
        if y2 <= by1 + EPS or by2 <= y1 + EPS:
            continue
        if z2 <= bz1 + EPS or bz2 <= z1 + EPS:
            continue
        return True
    return False


def _check_support_and_stacking(
    x1: float,
    y1: float,
    z1: float,
    dx: float,
    dy: float,
    dz: float,
    wt: float,
    piece_stackable: str,
    piece_fragile: bool,
    placed: list[dict],
    placed_boxes: list[tuple[float, float, float, float, float, float]],
    placed_stand_x: list[float],
    *,
    L: float,
    W: float,
    enforce_shake: bool = True,
    min_support: float,
    light_max_lb: float,
) -> tuple[bool, float]:
    x2, y2, z2 = x1 + dx, y1 + dy, z1 + dz

    # Guard against sliding a `no_stack` / `light_only` / `fragile` item directly underneath
    # the overhanging bottom face (`bz1 == z2`) of an already-placed item above it, or extending
    # `x2` so far past `above`'s front face `bx2` that `above` becomes unreachable without climbing.
    for i, above in enumerate(placed):
        bx1, by1, bz1, bx2, by2, _ = placed_boxes[i]
        if bz1 + EPS < z2:
            continue
        if min(x2, bx2) - max(x1, bx1) <= EPS or min(y2, by2) - max(y1, by1) <= EPS:
            continue
        if x2 - bx2 > MAX_REACH_SETBACK_IN + EPS:
            return False, x2
        if abs(bz1 - z2) <= verify.SUPPORT_Z_TOL:
            if piece_stackable == "no":
                return False, x2
            if (piece_stackable == "light_only" or piece_fragile) and above["weight_lb"] > light_max_lb + EPS:
                return False, x2

    if z1 <= EPS:
        return True, x2

    sup_area = 0.0
    req_stand_x = x2
    col_dx, col_dy = dx, dy
    for i, sup in enumerate(placed):
        bx1, by1, bz1, bx2, by2, bz2 = placed_boxes[i]
        ox = min(x2, bx2) - max(x1, bx1)
        if ox <= EPS:
            continue
        oy = min(y2, by2) - max(y1, by1)
        if oy <= EPS:
            continue
        if bz2 <= z1 + verify.SUPPORT_Z_TOL and placed_stand_x[i] > req_stand_x:
            req_stand_x = placed_stand_x[i]
        if abs(bz2 - z1) > 0.05:
            continue
        bstack = sup["stackable"]
        if bstack == "no":
            return False, req_stand_x
        if (bstack == "light_only" or sup.get("fragile")) and wt > light_max_lb + EPS:
            return False, req_stand_x
        col_dx = max(col_dx, bx2 - bx1)
        col_dy = max(col_dy, by2 - by1)
        # Placed items in a valid truck are pairwise non-overlapping, so top faces at height z1 are disjoint.
        sup_area += ox * oy

    if req_stand_x - x2 > MAX_REACH_SETBACK_IN + EPS:
        return False, req_stand_x
    if sup_area < min_support * (dx * dy) - 1e-4:
        return False, req_stand_x

    # 0.45g braking & pothole shake topple guard: prevent unbraced slender Jenga columns.
    if enforce_shake:
        req_brace_z = z1 + 0.35 * dz
        braced_neg_x = x1 <= 1.5
        braced_pos_x = x2 >= L - 1.5
        braced_neg_y = y1 <= 1.5
        braced_pos_y = y2 >= W - 1.5
        for bx1, by1, _, bx2, by2, bz2 in placed_boxes:
            if bz2 < req_brace_z:
                continue
            if min(y2, by2) - max(y1, by1) > EPS:
                if abs(bx2 - x1) <= 2.5:
                    braced_neg_x = True
                if abs(bx1 - x2) <= 2.5:
                    braced_pos_x = True
            if min(x2, bx2) - max(x1, bx1) > EPS:
                if abs(by2 - y1) <= 2.5:
                    braced_neg_y = True
                if abs(by1 - y2) <= 2.5:
                    braced_pos_y = True

        if (not braced_neg_y and not braced_pos_y) and (z2 / max(1.0, col_dy) > 2.15):
            return False, req_stand_x
        if (not braced_neg_x and not braced_pos_x) and (z2 / max(1.0, col_dx) > 2.15):
            return False, req_stand_x
        if (not braced_pos_x and (not braced_neg_y or not braced_pos_y)) and (
            z2 / max(1.0, min(col_dx, col_dy)) > 3.55
        ):
            return False, req_stand_x

    return True, req_stand_x


def _candidate_anchors(
    dx: float,
    dy: float,
    W: float,
    placed: list[dict],
    placed_boxes: list[tuple[float, float, float, float, float, float]],
) -> list[tuple[float, float, float]]:
    pts: list[tuple[float, float, float]] = [
        (0.0, 0.0, 0.0),
        (0.0, max(0.0, W - dy), 0.0),
    ]
    if len(placed) <= 2:
        pts.append((0.0, max(0.0, 0.5 * (W - dy)), 0.0))

    for i, b in enumerate(placed):
        bx1, by1, bz1, bx2, by2, bz2 = placed_boxes[i]
        # Advance along truck length (+x) on floor and at b's level, or tuck right behind an elevated column
        pts.append((bx2, by1, bz1))
        if bz1 > EPS and bx1 - dx >= -EPS:
            pts.append((max(0.0, bx1 - dx), by1, bz1))
        pts.append((bx2, 0.0, 0.0))
        pts.append((bx2, max(0.0, W - dy), 0.0))
        # Adjacent across width (+y from left, -y from right)
        pts.append((bx1, by2, bz1))
        if by1 - dy >= -EPS:
            pts.append((bx1, max(0.0, by1 - dy), bz1))
        # Stack on top of b if allowed (both back-aligned for box columns and door-flush for deeper bases)
        if b["stackable"] != "no":
            pts.append((bx1, by1, bz2))
            if by2 - dy >= -EPS:
                pts.append((bx1, max(0.0, by2 - dy), bz2))
            if bx2 - dx >= bx1 - EPS:
                fx = max(0.0, bx2 - dx)
                pts.append((fx, by1, bz2))
                if by2 - dy >= -EPS:
                    pts.append((fx, max(0.0, by2 - dy), bz2))

    seen: set[tuple[int, int, int]] = set()
    uniq: list[tuple[float, float, float]] = []
    for x, y, z in pts:
        k = (round(x * 20), round(y * 20), round(z * 20))
        if k not in seen:
            seen.add(k)
            uniq.append((x, y, z))
    return uniq


def _recenter_sparse_y(placed: list[dict], W: float, balance_band: tuple[float, float]) -> None:
    """Rigidly shift all items in `y` only when a sparse truck's CoG falls outside the safe band."""
    if not placed or W <= 0:
        return
    tot_wt = sum(it["weight_lb"] for it in placed)
    if tot_wt <= 0:
        return
    cog_y = sum(it["weight_lb"] * (it["pos_in"][1] + 0.5 * it["size_in"][1]) for it in placed) / tot_wt
    ratio = cog_y / W
    if balance_band[0] + 0.005 <= ratio <= balance_band[1] - 0.005:
        return
    min_y = min(it["pos_in"][1] for it in placed)
    max_y = max(it["pos_in"][1] + it["size_in"][1] for it in placed)
    desired_shift = 0.5 * W - cog_y
    shift = max(-min_y, min(W - max_y, desired_shift))
    if abs(shift) > EPS:
        for it in placed:
            it["pos_in"][1] = round(it["pos_in"][1] + shift, 2)


def _assign_walk_in_load_seq(placed: list[dict]) -> None:
    """Order `placed` wall/tier-by-tier from cab wall (`x=0`) toward rear door (`x=L`).

    Uses Kahn's min-heap topological sort over vertical support dependencies so:
      1. Every supporting item loads strictly before anything resting on top of it (`load_seq_support`).
      2. Each vertical column/tier is built bottom-to-top while the truck floor from `stand_x`
         to the rear door is still completely empty (`walk_in_access` — no stepping on boxes).
    """
    n = len(placed)
    if n == 0:
        return
    boxes = [
        (
            float(it["pos_in"][0]),
            float(it["pos_in"][1]),
            float(it["pos_in"][2]),
            float(it["pos_in"][0] + it["size_in"][0]),
            float(it["pos_in"][1] + it["size_in"][1]),
            float(it["pos_in"][2] + it["size_in"][2]),
        )
        for it in placed
    ]
    stand_x = verify.compute_stand_x(boxes)

    deps: list[set[int]] = [set() for _ in range(n)]
    rdeps: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        ax1, ay1, az1, ax2, ay2, _ = boxes[i]
        if az1 <= verify.SUPPORT_Z_TOL:
            continue
        for j in range(n):
            if i == j:
                continue
            bx1, by1, _, bx2, by2, bz2 = boxes[j]
            if bz2 <= az1 + verify.SUPPORT_Z_TOL:
                if min(ax2, bx2) - max(ax1, bx1) > EPS and min(ay2, by2) - max(ay1, by1) > EPS:
                    deps[i].add(j)
                    rdeps[j].append(i)

    def _prio(k: int) -> tuple[float, float, float, float, float, int]:
        x1, y1, z1, x2, _, _ = boxes[k]
        return (round(stand_x[k], 2), round(x2, 2), round(x1, 2), round(z1, 2), round(y1, 2), k)

    in_deg = [len(deps[k]) for k in range(n)]
    heap = [_prio(k) for k in range(n) if in_deg[k] == 0]
    heapq.heapify(heap)
    ordered_indices: list[int] = []
    while heap:
        *_, k = heapq.heappop(heap)
        ordered_indices.append(k)
        for m in rdeps[k]:
            in_deg[m] -= 1
            if in_deg[m] == 0:
                heapq.heappush(heap, _prio(m))

    if len(ordered_indices) < n:
        seen = set(ordered_indices)
        rest = sorted((k for k in range(n) if k not in seen), key=_prio)
        ordered_indices.extend(rest)

    reordered = [placed[k] for k in ordered_indices]
    placed[:] = reordered
    for seq, it in enumerate(placed, start=1):
        it["load_seq"] = seq


def _pack_single_bin_constrained(
    pieces: list[dict],
    bin_dims: list[float],
    max_weight_lb: float,
    *,
    prefix: str,
    strategy: dict,
    balance_width: bool = True,
) -> tuple[list[dict], list[dict]]:
    """Pack as many `pieces` as fit into one 3D bin; return `(placed_items, leftover_pieces)`."""
    L, W, H = [float(v) for v in bin_dims]
    # Instantiate py3dbp Bin to keep metadata/decimals aligned with py3dbp representation
    _py3_bin = Py3Bin(prefix, L, W, H, max_weight_lb)

    min_support = max(0.75, float(strategy.get("min_support", 0.76)))
    light_max_lb = float(strategy.get("light_max_lb", verify.DEFAULT_LIGHT_MAX_LB))
    allow_all_rot = bool(strategy.get("allow_all_rotations", False))
    balance_wt = float(strategy.get("balance_weight", 180.0)) if balance_width else 0.0

    placed: list[dict] = []
    placed_boxes: list[tuple[float, float, float, float, float, float]] = []
    placed_stand_x: list[float] = []
    leftovers: list[dict] = []
    cur_wt = 0.0
    weighted_y = 0.0

    # When total horizontal footprint fits within <=50% of floor area, keep cargo on the floor (`z=0`)
    # to minimize gravitational potential energy (`U = m*g*z_cm`) and eliminate shake/braking topple risk.
    floor_area = max(1.0, L * W)
    est_footprint = sum(float(p["dims_in"][0]) * float(p["dims_in"][1]) for p in pieces)
    sparse_floor = est_footprint <= 0.50 * floor_area

    for piece in pieces:
        wt = float(piece["weight_lb"])
        if cur_wt + wt > max_weight_lb + EPS:
            leftovers.append(piece)
            continue

        orients = valid_orientations(piece, allow_all_rotations=allow_all_rot)
        best_choice: tuple[float, float, float, float, float, float, float, float] | None = None

        for dx, dy, dz in orients:
            if dx > L + EPS or dy > W + EPS or dz > H + EPS:
                continue
            anchors = _candidate_anchors(dx, dy, W, placed, placed_boxes)
            for x, y, z in anchors:
                if x < -EPS or y < -EPS or z < -EPS:
                    continue
                if x + dx > L + EPS or y + dy > W + EPS or z + dz > H + EPS:
                    continue
                if sparse_floor and balance_width and z > EPS and (dz >= 6.0 or z + dz > 18.0):
                    continue
                if _overlaps_3d(x, y, z, x + dx, y + dy, z + dz, placed_boxes):
                    continue
                ok_sup, req_stand_x = _check_support_and_stacking(
                    x, y, z, dx, dy, dz, wt,
                    str(piece.get("stackable", "no")),
                    bool(piece.get("fragile", False)),
                    placed, placed_boxes, placed_stand_x,
                    L=L, W=W, enforce_shake=balance_width,
                    min_support=min_support, light_max_lb=light_max_lb,
                )
                if not ok_sup:
                    continue

                new_wt = cur_wt + wt
                new_cog_y = (weighted_y + wt * (y + 0.5 * dy)) / (new_wt * W) if (new_wt > 0 and W > 0) else 0.5
                bal_cost = abs(new_cog_y - 0.5) * balance_wt

                # Gravitational potential energy penalty (`z_cm = z + 0.5*dz`): floor slots (`z=0`) across
                # truck width ALWAYS beat stacking upward (`z>0`), preventing skinny single-column towers.
                z_cm = z + 0.5 * dz
                floor_z_cost = (0.5 * dz) * (0.42 + wt / 90.0)
                if sparse_floor and z > EPS:
                    pe_cost = 4000.0 + z_cm * 8.0
                else:
                    pe_cost = z_cm * (0.42 + wt / 90.0)

                # Small tie-breaker for flush column alignment ONLY among `z > 0` candidates (never beats `z = 0`).
                align_adj = 0.0
                if z > EPS and not sparse_floor and piece.get("stackable") == "yes":
                    for si, sup in enumerate(placed):
                        bx1, by1, bz1, bx2, by2, bz2 = placed_boxes[si]
                        if (
                            abs(bz2 - z) <= 0.05
                            and abs(bx1 - x) <= 0.5
                            and abs(by1 - y) <= 0.5
                            and sup.get("catalog_id") == piece.get("catalog_id")
                        ):
                            align_adj = -3.5
                            break

                effective_z_cost = max(floor_z_cost + (2.5 if z > EPS else 0.0), pe_cost + align_adj)
                cost = x * 1.15 + effective_z_cost + bal_cost + y * 0.01
                if best_choice is None or cost < best_choice[0]:
                    best_choice = (cost, x, y, z, dx, dy, dz, req_stand_x)

        if best_choice is None:
            leftovers.append(piece)
            continue

        _, x, y, z, dx, dy, dz, chosen_stand_x = best_choice
        placed_item = _build_placed_record(piece, prefix, len(placed) + 1, [x, y, z], [dx, dy, dz])
        placed.append(placed_item)
        placed_boxes.append((x, y, z, x + dx, y + dy, z + dz))
        placed_stand_x.append(chosen_stand_x)
        cur_wt += wt
        weighted_y += wt * (y + 0.5 * dy)

    if balance_width:
        _recenter_sparse_y(placed, W, verify.DEFAULT_BALANCE_BAND)

    _assign_walk_in_load_seq(placed)
    return placed, leftovers


def _pack_single_bin_raw_py3dbp(
    pieces: list[dict],
    bin_dims: list[float],
    max_weight_lb: float,
    *,
    prefix: str,
) -> tuple[list[dict], list[dict]]:
    """Run stock `py3dbp.Packer` on one bin (useful as an unguided baseline for B6/B7/eval)."""
    L, W, H = [float(v) for v in bin_dims]
    packer = Py3Packer()
    pbin = Py3Bin(prefix, L, W, H, max_weight_lb)
    packer.add_bin(pbin)

    by_name: dict[str, dict] = {}
    for p in pieces:
        l, w, h = p["dims_in"]
        by_name[p["id"]] = p
        packer.add_item(Py3Item(p["id"], l, w, h, p["weight_lb"]))

    packer.pack(bigger_first=True, distribute_items=False)

    placed: list[dict] = []
    fitted_ids: set[str] = set()
    for seq, ib in enumerate(pbin.items, start=1):
        src = by_name[ib.name]
        fitted_ids.add(ib.name)
        pos = [round(float(v), 2) for v in ib.position]
        sz = [round(float(v), 2) for v in ib.get_dimension()]
        rec = _build_placed_record(src, prefix, seq, pos, sz)
        rec["load_seq"] = seq
        placed.append(rec)

    leftovers = [p for p in pieces if p["id"] not in fitted_ids]
    return placed, leftovers


def _build_placed_record(
    piece: dict,
    prefix: str,
    idx: int,
    pos: list[float],
    size: list[float],
) -> dict[str, Any]:
    return {
        "id": f"{prefix}_{piece['id']}",
        "piece_id": piece["id"],
        "source_id": piece["source_id"],
        "label": piece["label"],
        "catalog_id": piece["catalog_id"],
        "category": piece.get("category"),
        "room_id": piece["room_id"],
        "room_name": piece["room_name"],
        "is_box": piece["is_box"],
        "box_short_name": piece.get("box_short_name"),
        "contents": piece.get("contents"),
        "pos_in": [round(float(v), 2) for v in pos],
        "size_in": [round(float(v), 2) for v in size],
        "orig_dims_in": [round(float(v), 2) for v in piece["dims_in"]],
        "weight_lb": round(float(piece["weight_lb"]), 1),
        "load_seq": idx,
        "fragile": bool(piece.get("fragile")),
        "must_stay_upright": bool(piece.get("must_stay_upright")),
        "load_on_edge": bool(piece.get("load_on_edge")),
        "disassemble": bool(piece.get("disassemble")),
        "two_person": bool(piece.get("two_person")),
        "stackable": piece.get("stackable", "no"),
        "stack_count": int(piece.get("stack_count", 1)),
        "dest_zone": piece.get("dest_zone"),
        "dest_zone_name": piece.get("dest_zone_name"),
        "dock_stop": piece.get("dock_stop"),
    }


def _pack_penn_zones(
    pieces: list[dict],
    strategy: dict,
) -> list[dict]:
    """Pack assigned items into each Penn Station store/zone in 3D, spilling overflow if allowed."""
    zones = catalog.list_penn_zones()
    if not zones:
        return []
    spill = bool(strategy.get("spill_zone_overflow", True))

    by_zone: dict[str, list[dict]] = {z["zone_id"]: [] for z in zones}
    for p in pieces:
        zid = p.get("dest_zone")
        if zid not in by_zone:
            zid = zones[-1]["zone_id"]
            p["dest_zone"] = zid
            p["dest_zone_name"] = zones[-1]["name"]
            p["dock_stop"] = zones[-1]["dock_stop"]
        by_zone[zid].append(p)

    zone_results: list[dict] = []
    overflow_pool: list[dict] = []

    for i, z in enumerate(zones):
        zid = z["zone_id"]
        incoming = by_zone[zid] + [p for p in overflow_pool if can_pass_door(p, z)]
        remaining_overflow = [p for p in overflow_pool if not can_pass_door(p, z)]
        # Update metadata on spilled items that entered this zone
        for p in incoming:
            if p["dest_zone"] != zid:
                p["dest_zone"] = zid
                p["dest_zone_name"] = z["name"]
                p["dock_stop"] = z["dock_stop"]

        ordered = sorted(incoming, key=lambda p: (_support_tier(p), -p["weight_lb"], -p["volume_cuft"]))
        placed, left = _pack_single_bin_constrained(
            ordered,
            z["dims_in"],
            z["max_weight_lb"],
            prefix=zid,
            strategy=strategy,
            balance_width=False,
        )

        unplaced_here: list[dict] = []
        if left:
            if spill and i < len(zones) - 1:
                overflow_pool = remaining_overflow + left
            else:
                overflow_pool = remaining_overflow
                unplaced_here = [{"id": p["id"], "label": p["label"]} for p in left]
        else:
            overflow_pool = remaining_overflow

        z_vol = max(1.0, z["length_in"] * z["width_in"] * z["height_in"])
        placed_vol = sum(it["size_in"][0] * it["size_in"][1] * it["size_in"][2] for it in placed)
        floor_used = sum(it["size_in"][0] * it["size_in"][1] for it in placed if it["pos_in"][2] <= EPS)
        floor_area = max(1.0, z["length_in"] * z["width_in"])

        zone_results.append({
            "zone_id": zid,
            "name": z["name"],
            "zone_type": z["zone_type"],
            "dock_stop": z["dock_stop"],
            "dims_in": list(z["dims_in"]),
            "door_in": list(z["door_in"]),
            "max_weight_lb": z["max_weight_lb"],
            "weight_lb": round(sum(it["weight_lb"] for it in placed), 1),
            "fill_pct": round((placed_vol / z_vol) * 100.0, 1),
            "floor_pct": round((floor_used / floor_area) * 100.0, 1),
            "item_count": len(placed),
            "items": placed,
            **({"unplaced": unplaced_here} if unplaced_here else {}),
        })

    return zone_results


def solve_pieces(pieces: list[dict], strategy: dict | None = None) -> dict[str, Any]:
    """Pack expanded `pieces` into a right-sized fleet of vans/trucks and Penn Station stores."""
    strategy = dict(strategy or {})
    raw_tid = str(strategy.get("truck_id") or "auto").strip()
    auto_rightsize = raw_tid in ("", "auto")
    default_truck_id = "uhaul_26" if auto_rightsize else raw_tid
    truck_seq: list[str] = list(strategy.get("truck_sequence") or [])
    engine = str(strategy.get("packer_engine") or "constrained")
    downsize_last = bool(strategy.get("downsize_last_truck", auto_rightsize))

    # First pack Penn Station destination stores so any capacity spill updates `dock_stop` before truck LIFO sort.
    zone_placements = _pack_penn_zones(pieces, strategy)

    remaining = sort_pieces(pieces, strategy)
    trucks_out: list[dict] = []
    unplaced_out: list[dict] = []

    # When `truck_id="auto"` (default), first check if a single smaller van/truck (`uhaul_van` -> `uhaul_26`)
    # fits the entire move cleanly with 0 physics/shake violations before opening multi-truck `uhaul_26` fleets.
    if auto_rightsize and not truck_seq and remaining and engine != "raw_py3dbp":
        for cand_spec in catalog.list_trucks():
            cand_placed, cand_left = _pack_single_bin_constrained(
                remaining, cand_spec["dims_in"], cand_spec["max_weight_lb"], prefix="t1", strategy=strategy
            )
            if not cand_left and cand_placed:
                tv, _ = verify.verify_truck({
                    "truck_id": cand_spec["truck_id"],
                    "index": 0,
                    "dims_in": cand_spec["dims_in"],
                    "max_weight_lb": cand_spec["max_weight_lb"],
                    "items": cand_placed,
                })
                if not tv:
                    default_truck_id = cand_spec["truck_id"]
                    break

    t_idx = 0
    while remaining:
        tid = truck_seq[t_idx] if t_idx < len(truck_seq) else default_truck_id
        t_spec = catalog.get_truck(tid)
        if t_spec is None:
            raise ValueError(f"unknown truck_id: {tid!r}")

        prefix = f"t{t_idx + 1}"
        if engine == "raw_py3dbp":
            placed, leftovers = _pack_single_bin_raw_py3dbp(
                remaining, t_spec["dims_in"], t_spec["max_weight_lb"], prefix=prefix
            )
        else:
            placed, leftovers = _pack_single_bin_constrained(
                remaining, t_spec["dims_in"], t_spec["max_weight_lb"], prefix=prefix, strategy=strategy
            )

        if not placed:
            # Remaining items cannot fit even in an empty truck of `tid` (e.g. item taller than ceiling).
            for p in leftovers:
                unplaced_out.append({
                    "id": p["id"],
                    "label": p["label"],
                    "dims_in": p["dims_in"],
                    "weight_lb": p["weight_lb"],
                    "reason": (
                        f"dims {p['dims_in']} (upright={p.get('must_stay_upright')}, edge={p.get('load_on_edge')}) "
                        f"cannot fit in empty {tid} {t_spec['dims_in']}"
                    ),
                })
            break

        # Right-size the final truck to the smallest van/truck (`uhaul_van`..`uhaul_20`) that passes physics checks.
        if not leftovers and downsize_last and engine != "raw_py3dbp":
            for smaller in catalog.list_trucks():
                if smaller["volume_cuft"] >= t_spec["volume_cuft"]:
                    break
                cand_placed, cand_left = _pack_single_bin_constrained(
                    remaining, smaller["dims_in"], smaller["max_weight_lb"], prefix=prefix, strategy=strategy
                )
                if not cand_left and cand_placed:
                    tv, _ = verify.verify_truck({
                        "truck_id": smaller["truck_id"],
                        "index": t_idx,
                        "dims_in": smaller["dims_in"],
                        "max_weight_lb": smaller["max_weight_lb"],
                        "items": cand_placed,
                    })
                    if not tv:
                        t_spec = smaller
                        tid = smaller["truck_id"]
                        placed = cand_placed
                        break

        t_vol = max(1.0, t_spec["length_in"] * t_spec["width_in"] * t_spec["height_in"])
        p_vol = sum(it["size_in"][0] * it["size_in"][1] * it["size_in"][2] for it in placed)
        t_wt = round(sum(it["weight_lb"] for it in placed), 1)

        # Attach truck index & unload_seq (reverse of load_seq) for B8/B10 convenience
        total_in_truck = len(placed)
        for it in placed:
            it["truck_index"] = t_idx
            it["truck_id"] = tid
            it["unload_seq"] = total_in_truck - it["load_seq"] + 1

        trucks_out.append({
            "truck_id": tid,
            "name": t_spec["name"],
            "index": t_idx,
            "dims_in": list(t_spec["dims_in"]),
            "max_weight_lb": t_spec["max_weight_lb"],
            "weight_lb": t_wt,
            "fill_pct": round((p_vol / t_vol) * 100.0, 1),
            "items": placed,
        })

        remaining = leftovers
        t_idx += 1

    # Sync truck assignment back onto zone items so labels/UI know which truck brings each store's goods
    piece_truck_map = {
        it["piece_id"]: (it["truck_index"], it["truck_id"], it["load_seq"], it["unload_seq"])
        for t in trucks_out
        for it in t["items"]
    }
    for z in zone_placements:
        for zit in z.get("items", []):
            info = piece_truck_map.get(zit["piece_id"])
            if info:
                zit["truck_index"], zit["truck_id"], zit["load_seq"], zit["unload_seq"] = info

    counts_by_tid: dict[str, int] = {}
    for t in trucks_out:
        counts_by_tid[t["truck_id"]] = counts_by_tid.get(t["truck_id"], 0) + 1
    fleet_label = " + ".join(f"{n} × {tid}" for tid, n in counts_by_tid.items()) or "0 trucks"

    placed_all = [it for t in trucks_out for it in t["items"]]
    placement: dict[str, Any] = {
        "trucks": trucks_out,
        "zones": zone_placements,
        "unplaced": unplaced_out,
        "summary": {
            "truck_count": len(trucks_out),
            "fleet_label": fleet_label,
            "total_items": len(placed_all),
            "furniture_count": sum(1 for it in placed_all if not it["is_box"]),
            "box_count": sum(1 for it in placed_all if it["is_box"]),
            "unplaced_count": len(unplaced_out),
            "zones_stocked": sum(1 for z in zone_placements if z["item_count"] > 0),
            "total_weight_lb": round(sum(it["weight_lb"] for it in placed_all), 1),
            "total_volume_cuft": round(
                sum(it["size_in"][0] * it["size_in"][1] * it["size_in"][2] for it in placed_all) / 1728.0, 1
            ),
        },
        "strategy": strategy,
    }
    placement["score"] = verify.verify(placement)
    return placement


def solve(inventory: dict, strategy: dict | None = None) -> dict[str, Any]:
    """End-to-end Track B solve from an `inventory_v2` JSON object."""
    strategy = dict(strategy or {})
    pieces = expand_inventory(inventory, strategy=strategy)
    return solve_pieces(pieces, strategy=strategy)


def main() -> None:
    ap = argparse.ArgumentParser(description="Pack an inventory_v2 JSON into U-Haul trucks and Penn Station stores.")
    ap.add_argument("inventory", type=Path, help="Path to inventory_v2 JSON (e.g. data/sample_venue.json)")
    ap.add_argument("--truck", default="uhaul_26", help="Default truck_id (uhaul_10, uhaul_15, uhaul_20, uhaul_26)")
    ap.add_argument("--engine", default="constrained", choices=["constrained", "raw_py3dbp"])
    ap.add_argument("--order", default="lifo_heavy_first")
    ap.add_argument("--out", type=Path, default=None, help="Optional path to write placement JSON")
    args = ap.parse_args()

    inv = json.loads(args.inventory.read_text(encoding="utf-8"))
    plan = solve(inv, strategy={"truck_id": args.truck, "packer_engine": args.engine, "order_mode": args.order})
    s = plan["summary"]
    sc = plan["score"]
    print(
        f"Fleet: {s['fleet_label']} | placed={s['total_items']} ({s['furniture_count']} furniture + {s['box_count']} boxes) "
        f"| zones={s['zones_stocked']}/6 | score={sc['total']} valid={sc['valid']} "
        f"fill={sc['fill_pct']}% balance={sc['balance_pct']}% lifo={sc['lifo_score']}/10 violations={sc['violation_count']}"
    )
    for t in plan["trucks"]:
        print(f"  Truck {t['index']} ({t['truck_id']}): {len(t['items'])} items, {t['weight_lb']} lb, fill={t['fill_pct']}%")
    for z in plan["zones"]:
        print(f"  Stop {z['dock_stop']} {z['zone_id']} ({z['name']}): {z['item_count']} items, floor={z['floor_pct']}%, fill={z['fill_pct']}%")
    if sc["violations"]:
        print("  Violations by rule:", sc["violation_counts_by_rule"])
        for v in sc["violations"][:8]:
            print(f"    - [{v['rule']}] {v['detail']}")
    if args.out:
        args.out.write_text(json.dumps(plan, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
