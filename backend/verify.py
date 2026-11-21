"""Stage B4: pure-function packing plan verifier and scorer.

Checks both truck-loading physics and Penn Station multi-store destination rules:
  1. `unplaced`: every expanded piece/box was placed on a truck
  2. `fit` & `truck_overweight`: 3D interior bounds `[0..L, 0..W, 0..H]` and max payload
  3. `overlap`: exact 3D AABB intersection check across all pairs in a truck
  4. `support`: at least 75% of every elevated (`z > 0`) item's base area is supported
     by top surfaces directly beneath it (computed via exact 2D rectangle union),
     plus `load_seq_support` (supports must be loaded before the items resting on them)
  5. `upright` & `load_on_edge`: `must_stay_upright` keeps original height vertical (`dz`);
     `load_on_edge` prevents flat slab items (mattresses, banquet rounds, art, mirrors)
     from lying flat on their large face
  6. `no_stack`, `light_only_on_top`, `fragile_crushed`: respects `stackable` (`yes`,
     `no`, `light_only` <= 30 lb) and protects fragile items
  7. `weight_balance`: left-right center of gravity across truck width stays within
     40%-60% of `width_in`
  8. Penn Station destination checks (`zone_door_clearance`, `zone_fit`, `zone_overlap`,
     `zone_overweight`, `zone_distribution`) plus LIFO dock-stop unload quality scoring.

Coordinate convention:
    pos_in  = [x, y, z]  (front-left-floor corner in inches)
    size_in = [dx, dy, dz]  (length along truck, width left-right, height vertical)
"""
from __future__ import annotations

from typing import Any

from backend import catalog

EPS = 1e-3
SUPPORT_Z_TOL = 0.25
DEFAULT_MIN_SUPPORT = 0.75
DEFAULT_LIGHT_MAX_LB = 30.0
DEFAULT_BALANCE_BAND = (0.40, 0.60)
DEFAULT_MAX_REACH_SETBACK_IN = 25.0


def _rect_union_area(rects: list[tuple[float, float, float, float]]) -> float:
    """Exact area of the union of 2D axis-aligned rectangles [(x1, y1, x2, y2), ...]."""
    clean = [(x1, y1, x2, y2) for (x1, y1, x2, y2) in rects if x2 - x1 > EPS and y2 - y1 > EPS]
    if not clean:
        return 0.0
    if len(clean) == 1:
        x1, y1, x2, y2 = clean[0]
        return (x2 - x1) * (y2 - y1)

    xs = sorted({x for r in clean for x in (r[0], r[2])})
    area = 0.0
    for i in range(len(xs) - 1):
        xa, xb = xs[i], xs[i + 1]
        dx = xb - xa
        if dx <= EPS:
            continue
        xm = 0.5 * (xa + xb)
        intervals = sorted((r[1], r[3]) for r in clean if r[0] <= xm <= r[2])
        if not intervals:
            continue
        cur_y1, cur_y2 = intervals[0]
        covered_y = 0.0
        for y1, y2 in intervals[1:]:
            if y1 <= cur_y2 + EPS:
                cur_y2 = max(cur_y2, y2)
            else:
                covered_y += cur_y2 - cur_y1
                cur_y1, cur_y2 = y1, y2
        covered_y += cur_y2 - cur_y1
        area += dx * covered_y
    return area


def _aabb(item: dict) -> tuple[float, float, float, float, float, float]:
    x, y, z = item["pos_in"]
    dx, dy, dz = item["size_in"]
    return float(x), float(y), float(z), float(x + dx), float(y + dy), float(z + dz)


def compute_stand_x(boxes: list[tuple[float, float, float, float, float, float]]) -> list[float]:
    """Return each item's required floor-standing plane `stand_x[i]` toward the rear door.

    For a floor item (`z1 == 0`), the mover stands on the empty truck deck right at its
    door-facing face `x2`. For an elevated item (`z1 > 0`), all items beneath it must
    already be in place, so the mover stands at `max(x2_i, max_{j beneath i} stand_x[j])`.
    """
    n = len(boxes)
    stand_x = [b[3] for b in boxes]
    z_order = sorted(range(n), key=lambda k: (boxes[k][2], boxes[k][5]))
    for i in z_order:
        ax1, ay1, az1, ax2, ay2, _ = boxes[i]
        if az1 <= SUPPORT_Z_TOL:
            continue
        for j in range(n):
            if i == j:
                continue
            bx1, by1, _, bx2, by2, bz2 = boxes[j]
            if bz2 <= az1 + SUPPORT_Z_TOL:
                if min(ax2, bx2) - max(ax1, bx1) > EPS and min(ay2, by2) - max(ay1, by1) > EPS:
                    if stand_x[j] > stand_x[i]:
                        stand_x[i] = stand_x[j]
    return stand_x


def _orig_dims(item: dict) -> list[float] | None:
    orig = item.get("orig_dims_in")
    if isinstance(orig, list) and len(orig) == 3:
        return [float(v) for v in orig]
    cid = item.get("catalog_id")
    if cid and cid != "unknown":
        info = catalog.lookup(cid)
        if info:
            return list(info["dims_in"])
    return None


def _can_pass_zone_door(item: dict, door_in: list[float]) -> bool:
    dw, dh = float(door_in[0]), float(door_in[1])
    dims = _orig_dims(item) or [float(v) for v in item["size_in"]]
    l, w, h = dims
    if item.get("must_stay_upright") and not item.get("disassemble"):
        return h <= dh + EPS and min(l, w) <= dw + EPS
    s0, s1 = sorted([l, w, h])[:2]
    d0, d1 = sorted([dw, dh])
    return s0 <= d0 + EPS and s1 <= d1 + EPS


def _violation(
    rule: str,
    detail: str,
    *,
    truck_index: int | None = None,
    zone_id: str | None = None,
    item_ids: list[str] | None = None,
    severity: str = "error",
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "rule": rule,
        "severity": severity,
        "item_ids": item_ids or [],
        "detail": detail,
    }
    if truck_index is not None:
        out["truck_index"] = truck_index
    if zone_id is not None:
        out["zone_id"] = zone_id
    return out


def verify_truck(
    truck: dict,
    *,
    min_support: float = DEFAULT_MIN_SUPPORT,
    light_max_lb: float = DEFAULT_LIGHT_MAX_LB,
    balance_band: tuple[float, float] = DEFAULT_BALANCE_BAND,
) -> tuple[list[dict], dict[str, float]]:
    """Run all physical and mover-rule checks on a single truck."""
    violations: list[dict] = []
    t_idx = int(truck.get("index", 0))
    dims = truck.get("dims_in") or [0.0, 0.0, 0.0]
    L, W, H = float(dims[0]), float(dims[1]), float(dims[2])
    truck_vol = max(1.0, L * W * H)

    t_meta = catalog.get_truck(truck.get("truck_id", "")) or {}
    max_wt = float(truck.get("max_weight_lb") or t_meta.get("max_weight_lb") or 0.0)

    items = truck.get("items") or []
    boxes = [_aabb(it) for it in items]

    total_wt = 0.0
    placed_vol = 0.0
    weighted_y = 0.0
    weighted_z = 0.0
    floor_min_pe_lb_in = 0.0

    # 1. Fit, dimensions, orientation rules
    for i, it in enumerate(items):
        iid = str(it.get("id", f"item_{i}"))
        x1, y1, z1, x2, y2, z2 = boxes[i]
        dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
        wt = float(it.get("weight_lb") if it.get("weight_lb") is not None else 20.0)
        total_wt += wt
        placed_vol += max(0.0, dx * dy * dz)
        weighted_y += wt * (y1 + 0.5 * dy)
        weighted_z += wt * (z1 + 0.5 * dz)
        floor_min_pe_lb_in += wt * (0.5 * max(0.0, dz))

        if dx <= 0 or dy <= 0 or dz <= 0:
            violations.append(_violation("fit", f"{iid} has non-positive size {it.get('size_in')}", truck_index=t_idx, item_ids=[iid]))
            continue

        if x1 < -EPS or y1 < -EPS or z1 < -EPS or x2 > L + EPS or y2 > W + EPS or z2 > H + EPS:
            violations.append(_violation(
                "fit",
                f"{iid} at [{x1:.1f},{y1:.1f},{z1:.1f}]..[{x2:.1f},{y2:.1f},{z2:.1f}] exceeds truck [{L:.0f},{W:.0f},{H:.0f}]",
                truck_index=t_idx,
                item_ids=[iid],
            ))

        orig = _orig_dims(it)
        if orig:
            if it.get("must_stay_upright") and abs(dz - orig[2]) > 0.25:
                violations.append(_violation(
                    "upright",
                    f"{iid} ({it.get('label')}) must stay upright (orig H={orig[2]:.1f} in, placed dz={dz:.1f} in)",
                    truck_index=t_idx,
                    item_ids=[iid],
                ))
            min_d, max_d = min(orig), max(orig)
            if it.get("load_on_edge") and max_d > min_d * 1.5 and abs(dz - min_d) <= 0.25:
                violations.append(_violation(
                    "load_on_edge",
                    f"{iid} ({it.get('label')}) must be loaded on edge, not flat (dz={dz:.1f} in == thickness {min_d:.1f} in)",
                    truck_index=t_idx,
                    item_ids=[iid],
                ))

    if max_wt > 0 and total_wt > max_wt + EPS:
        violations.append(_violation(
            "truck_overweight",
            f"truck {t_idx} weight {total_wt:.1f} lb exceeds payload limit {max_wt:.1f} lb",
            truck_index=t_idx,
        ))

    # 2. Pairwise 3D overlap
    n = len(items)
    for i in range(n):
        ax1, ay1, az1, ax2, ay2, az2 = boxes[i]
        aid = str(items[i].get("id", f"item_{i}"))
        for j in range(i + 1, n):
            bx1, by1, bz1, bx2, by2, bz2 = boxes[j]
            ox = min(ax2, bx2) - max(ax1, bx1)
            if ox <= EPS:
                continue
            oy = min(ay2, by2) - max(ay1, by1)
            if oy <= EPS:
                continue
            oz = min(az2, bz2) - max(az1, bz1)
            if oz > EPS:
                bid = str(items[j].get("id", f"item_{j}"))
                violations.append(_violation(
                    "overlap",
                    f"{aid} and {bid} overlap by {ox:.1f}x{oy:.1f}x{oz:.1f} in",
                    truck_index=t_idx,
                    item_ids=[aid, bid],
                ))

    # 3. Base support (>= 75%), stacking rules, load_seq support order, walk-in tier reachability,
    #    and gravitational potential energy / road-shake topple physics.
    stand_x = compute_stand_x(boxes)
    floor_area = max(1.0, L * W)
    total_footprint_area = sum(max(0.0, b[3] - b[0]) * max(0.0, b[4] - b[1]) for b in boxes)
    floor_used_area = _rect_union_area([(b[0], b[1], b[3], b[4]) for b in boxes if b[2] <= SUPPORT_Z_TOL])
    sparse_floor = (L > 0 and W > 0 and total_footprint_area <= 0.50 * floor_area)
    pe_ratio = (weighted_z / floor_min_pe_lb_in) if floor_min_pe_lb_in > EPS else 1.0

    for i, it in enumerate(items):
        ax1, ay1, az1, ax2, ay2, az2 = boxes[i]
        dx, dy = ax2 - ax1, ay2 - ay1
        if dx <= 0 or dy <= 0 or az1 <= SUPPORT_Z_TOL:
            continue

        aid = str(it.get("id", f"item_{i}"))
        awt = float(it.get("weight_lb") if it.get("weight_lb") is not None else 20.0)
        aseq = it.get("load_seq")
        base_area = dx * dy
        support_rects: list[tuple[float, float, float, float]] = []

        for j, sup in enumerate(items):
            if i == j:
                continue
            bx1, by1, bz1, bx2, by2, bz2 = boxes[j]
            if abs(bz2 - az1) > SUPPORT_Z_TOL:
                continue
            ix1, iy1 = max(ax1, bx1), max(ay1, by1)
            ix2, iy2 = min(ax2, bx2), min(ay2, by2)
            if ix2 - ix1 <= EPS or iy2 - iy1 <= EPS:
                continue

            support_rects.append((ix1, iy1, ix2, iy2))
            bid = str(sup.get("id", f"item_{j}"))
            bstack = str(sup.get("stackable", "yes")).strip().lower()

            if bstack == "no":
                violations.append(_violation(
                    "no_stack",
                    f"{aid} rests on non-stackable item {bid} ({sup.get('label')})",
                    truck_index=t_idx,
                    item_ids=[aid, bid],
                ))
            elif bstack == "light_only" and awt > light_max_lb + EPS:
                violations.append(_violation(
                    "light_only_on_top",
                    f"{aid} ({awt:.1f} lb > {light_max_lb:.0f} lb) rests on light_only item {bid} ({sup.get('label')})",
                    truck_index=t_idx,
                    item_ids=[aid, bid],
                ))

            if sup.get("fragile") and bstack != "no" and awt > light_max_lb + EPS:
                violations.append(_violation(
                    "fragile_crushed",
                    f"heavy item {aid} ({awt:.1f} lb) rests on fragile item {bid}",
                    truck_index=t_idx,
                    item_ids=[aid, bid],
                ))

            bseq = sup.get("load_seq")
            if aseq is not None and bseq is not None and int(bseq) > int(aseq):
                violations.append(_violation(
                    "load_seq_support",
                    f"{aid} (load_seq={aseq}) is loaded before its support {bid} (load_seq={bseq})",
                    truck_index=t_idx,
                    item_ids=[aid, bid],
                ))

        sup_area = _rect_union_area(support_rects)
        sup_ratio = sup_area / base_area
        if sup_ratio + 1e-5 < min_support:
            violations.append(_violation(
                "support",
                f"{aid} at z={az1:.1f} in has {sup_ratio * 100:.1f}% base support (needs >= {min_support * 100:.0f}%)",
                truck_index=t_idx,
                item_ids=[aid],
            ))

        # Walk-in tier check: movers must never have to step onto lower-level boxes/cargo to place an upper item.
        setback = stand_x[i] - ax2
        if setback > DEFAULT_MAX_REACH_SETBACK_IN + EPS:
            violations.append(_violation(
                "walk_in_access",
                f"{aid} at x={ax1:.0f}..{ax2:.0f} in (z={az1:.0f} in) sits {setback:.0f} in behind its support front "
                f"x={stand_x[i]:.0f} in — unreachable from truck floor without climbing onto lower cargo",
                truck_index=t_idx,
                item_ids=[aid],
            ))
        elif aseq is not None:
            premature_front: tuple[float, int, str, float, float] | None = None
            for j, other in enumerate(items):
                if i == j:
                    continue
                bseq = other.get("load_seq")
                if bseq is None or int(bseq) >= int(aseq):
                    continue
                bx1, _, _, bx2, _, _ = boxes[j]
                if bx1 >= stand_x[i] - 0.05 and bx2 > stand_x[i] + 0.5:
                    cand = (bx2, int(bseq), str(other.get("id", f"item_{j}")), bx1, bx2)
                    if premature_front is None or cand[0] > premature_front[0]:
                        premature_front = cand
            if premature_front is not None:
                _, bseq_bad, bid_bad, bx1_bad, bx2_bad = premature_front
                violations.append(_violation(
                    "walk_in_access",
                    f"{aid} (load_seq={aseq}, x={ax1:.0f}..{ax2:.0f} in, z={az1:.0f} in) is loaded after door-side "
                    f"cargo {bid_bad} (load_seq={bseq_bad}, x={bx1_bad:.0f}..{bx2_bad:.0f} in), forcing movers to step on lower boxes",
                    truck_index=t_idx,
                    item_ids=[aid, bid_bad],
                ))

        # Potential energy & 0.45g braking / pothole shake topple check
        dz_i = az2 - az1
        if sparse_floor and (dz_i >= 6.0 or az2 > 18.0):
            open_floor_pct = max(0.0, 100.0 - (floor_used_area / floor_area) * 100.0)
            violations.append(_violation(
                "shake_stability",
                f"{aid} stacked at z={az1:.0f}..{az2:.0f} in raises gravitational potential energy ({pe_ratio:.1f}x floor baseline) "
                f"while {open_floor_pct:.0f}% of truck floor is open — place cargo on the floor",
                truck_index=t_idx,
                item_ids=[aid],
            ))
        else:
            col_dx, col_dy = dx, dy
            for j in range(n):
                if i == j:
                    continue
                bx1, by1, _, bx2, by2, bz2 = boxes[j]
                if abs(bz2 - az1) <= SUPPORT_Z_TOL:
                    if min(ax2, bx2) - max(ax1, bx1) > EPS and min(ay2, by2) - max(ay1, by1) > EPS:
                        col_dx = max(col_dx, bx2 - bx1)
                        col_dy = max(col_dy, by2 - by1)

            req_brace_z = az1 + 0.35 * dz_i
            braced_neg_x = ax1 <= 1.5
            braced_pos_x = ax2 >= L - 1.5
            braced_neg_y = ay1 <= 1.5
            braced_pos_y = ay2 >= W - 1.5
            for j in range(n):
                if i == j:
                    continue
                bx1, by1, _, bx2, by2, bz2 = boxes[j]
                if bz2 < req_brace_z:
                    continue
                if min(ay2, by2) - max(ay1, by1) > EPS:
                    if abs(bx2 - ax1) <= 2.5:
                        braced_neg_x = True
                    if abs(bx1 - ax2) <= 2.5:
                        braced_pos_x = True
                if min(ax2, bx2) - max(ax1, bx1) > EPS:
                    if abs(by2 - ay1) <= 2.5:
                        braced_neg_y = True
                    if abs(by1 - ay2) <= 2.5:
                        braced_pos_y = True

            if (not braced_neg_y and not braced_pos_y) and (az2 / max(1.0, col_dy) > 2.2):
                violations.append(_violation(
                    "shake_stability",
                    f"{aid} forms an unbraced {az2:.0f}-in tower on a {col_dy:.0f}-in lateral base "
                    f"(slenderness {az2 / max(1.0, col_dy):.1f}x > 2.2x) — topples under 0.45g cornering/pothole shake",
                    truck_index=t_idx,
                    item_ids=[aid],
                ))
            elif (not braced_neg_x and not braced_pos_x) and (az2 / max(1.0, col_dx) > 2.2):
                violations.append(_violation(
                    "shake_stability",
                    f"{aid} forms an unbraced {az2:.0f}-in column on a {col_dx:.0f}-in length base "
                    f"(slenderness {az2 / max(1.0, col_dx):.1f}x > 2.2x) — topples under 0.45g hard braking",
                    truck_index=t_idx,
                    item_ids=[aid],
                ))
            elif (not braced_pos_x and (not braced_neg_y or not braced_pos_y)) and (
                az2 / max(1.0, min(col_dx, col_dy)) > 3.6
            ):
                violations.append(_violation(
                    "shake_stability",
                    f"{aid} stacked {az2:.0f} in high on a narrow {min(col_dx, col_dy):.0f}-in column without side/front bracing "
                    "— topple hazard under road vibration",
                    truck_index=t_idx,
                    item_ids=[aid],
                ))

    # 4. Left-right weight balance across truck width (y axis)
    cog_y_ratio = (weighted_y / (total_wt * W)) if (total_wt > 0 and W > 0) else 0.5
    cog_z_ratio = (weighted_z / (total_wt * H)) if (total_wt > 0 and H > 0) else 0.25
    if items and total_wt > 0 and W > 0:
        lo, hi = balance_band
        if not (lo - 1e-4 <= cog_y_ratio <= hi + 1e-4):
            violations.append(_violation(
                "weight_balance",
                f"truck {t_idx} left-right CoG is at {cog_y_ratio * 100:.1f}% of width (safe band {lo * 100:.0f}%-{hi * 100:.0f}%)",
                truck_index=t_idx,
            ))

    # 5. LIFO dock-stop unload quality along truck length (x=0 cab -> x=L rear door)
    lifo_pairs = 0
    lifo_aligned = 0
    stop_x = [
        (int(it["dock_stop"]), boxes[idx][0] + 0.5 * (boxes[idx][3] - boxes[idx][0]))
        for idx, it in enumerate(items)
        if it.get("dock_stop") is not None
    ]
    for i in range(len(stop_x)):
        s_i, x_i = stop_x[i]
        for j in range(i + 1, len(stop_x)):
            s_j, x_j = stop_x[j]
            if s_i == s_j:
                continue
            lifo_pairs += 1
            # Earlier dock stop (smaller number, unloaded first) should sit closer to rear door (larger x),
            # with a 24-in slack band for items standing side by side in the same bay.
            if (s_i < s_j and x_i + 24.0 >= x_j) or (s_j < s_i and x_j + 24.0 >= x_i):
                lifo_aligned += 1

    lifo_ratio = (lifo_aligned / lifo_pairs) if lifo_pairs > 0 else 1.0

    stats = {
        "fill_pct": (placed_vol / truck_vol) * 100.0,
        "placed_vol_cuin": placed_vol,
        "truck_vol_cuin": truck_vol,
        "total_footprint_area": total_footprint_area,
        "weight_lb": total_wt,
        "cog_y_ratio": cog_y_ratio,
        "cog_z_ratio": cog_z_ratio,
        "cog_z_in": (weighted_z / total_wt) if total_wt > 0 else 0.0,
        "potential_energy_j": weighted_z * 0.112985,
        "pe_ratio": pe_ratio,
        "lifo_ratio": lifo_ratio,
    }
    return violations, stats


def verify_zones(placement: dict) -> tuple[list[dict], dict[str, float]]:
    """Check Penn Station destination store doorway clearances, 3D store layouts, and multi-store distribution."""
    violations: list[dict] = []
    all_truck_items = [it for t in placement.get("trucks", []) for it in t.get("items", [])]
    zones_block = placement.get("zones") or []
    known_zones = catalog.load_penn_zones()

    # Check doorway clearance for every item carrying dest_zone
    zone_counts: dict[str, int] = {}
    for it in all_truck_items:
        zid = it.get("dest_zone")
        if not zid:
            continue
        zone_counts[zid] = zone_counts.get(zid, 0) + 1
        zmeta = known_zones.get(zid)
        if zmeta and not _can_pass_zone_door(it, zmeta["door_in"]):
            iid = str(it.get("id", "item"))
            violations.append(_violation(
                "zone_door_clearance",
                f"{iid} ({it.get('label')}) cannot fit through {zmeta['name']} doorway {zmeta['door_in'][0]:.0f}x{zmeta['door_in'][1]:.0f} in",
                zone_id=zid,
                item_ids=[iid],
            ))

    # Multi-store distribution check: moving into a single giant hall is disallowed when >= 10 items exist
    if len(all_truck_items) >= 10 and zone_counts:
        top_zone, top_cnt = max(zone_counts.items(), key=lambda kv: kv[1])
        distinct_zones = sum(1 for c in zone_counts.values() if c > 0)
        if distinct_zones < 3 or (top_cnt / len(all_truck_items)) > 0.75:
            violations.append(_violation(
                "zone_distribution",
                f"{top_cnt}/{len(all_truck_items)} items ({top_cnt * 100 / len(all_truck_items):.0f}%) routed to {top_zone} "
                f"across only {distinct_zones} zone(s); Penn Station storefronts are under-stocked",
                zone_id=top_zone,
            ))

    # Check 3D layout inside each Penn Station store when `zones` placements are provided
    for z in zones_block:
        zid = str(z.get("zone_id", "zone"))
        L, W, H = [float(v) for v in (z.get("dims_in") or [0, 0, 0])]
        zmeta = known_zones.get(zid) or {}
        max_wt = float(z.get("max_weight_lb") or zmeta.get("max_weight_lb") or 0.0)
        z_items = z.get("items") or []
        z_boxes = [_aabb(it) for it in z_items]
        z_wt = 0.0

        for u in z.get("unplaced") or []:
            uid = str(u.get("id", "item"))
            violations.append(_violation(
                "zone_fit",
                f"{uid} ({u.get('label')}) overflowed Penn Station store {zid}",
                zone_id=zid,
                item_ids=[uid],
            ))

        for i, it in enumerate(z_items):
            iid = str(it.get("id", f"zitem_{i}"))
            x1, y1, z1, x2, y2, z2 = z_boxes[i]
            z_wt += float(it.get("weight_lb") or 0.0)
            if x1 < -EPS or y1 < -EPS or z1 < -EPS or x2 > L + EPS or y2 > W + EPS or z2 > H + EPS:
                violations.append(_violation(
                    "zone_fit",
                    f"{iid} exceeds store {zid} bounds [{L:.0f},{W:.0f},{H:.0f}]",
                    zone_id=zid,
                    item_ids=[iid],
                ))
            for j in range(i + 1, len(z_items)):
                bx1, by1, bz1, bx2, by2, bz2 = z_boxes[j]
                ox = min(x2, bx2) - max(x1, bx1)
                oy = min(y2, by2) - max(y1, by1)
                oz = min(z2, bz2) - max(z1, bz1)
                if ox > EPS and oy > EPS and oz > EPS:
                    bid = str(z_items[j].get("id", f"zitem_{j}"))
                    violations.append(_violation(
                        "zone_overlap",
                        f"{iid} and {bid} overlap inside Penn Station store {zid}",
                        zone_id=zid,
                        item_ids=[iid, bid],
                    ))

        if max_wt > 0 and z_wt > max_wt + EPS:
            violations.append(_violation(
                "zone_overweight",
                f"store {zid} weight {z_wt:.1f} lb exceeds floor limit {max_wt:.1f} lb",
                zone_id=zid,
            ))

    total_zones = max(1, len(known_zones))
    stocked_zones = sum(1 for zid in known_zones if zone_counts.get(zid, 0) > 0)
    zone_cov_pct = (stocked_zones / total_zones) * 100.0 if zone_counts else 0.0
    return violations, {"zone_coverage_pct": zone_cov_pct, "stocked_zones": float(stocked_zones)}


RULE_WEIGHTS: dict[str, float] = {
    "unplaced_item": 15.0,
    "fit": 14.0,
    "overlap": 14.0,
    "truck_overweight": 14.0,
    "support": 9.0,
    "upright": 8.0,
    "load_on_edge": 8.0,
    "no_stack": 8.0,
    "light_only_on_top": 7.0,
    "fragile_crushed": 9.0,
    "load_seq_support": 6.0,
    "walk_in_access": 8.0,
    "shake_stability": 10.0,
    "oversized_truck": 12.0,
    "weight_balance": 10.0,
    "zone_door_clearance": 10.0,
    "zone_fit": 10.0,
    "zone_overlap": 10.0,
    "zone_overweight": 10.0,
    "zone_distribution": 12.0,
}


def verify(
    placement: dict,
    *,
    min_support: float = DEFAULT_MIN_SUPPORT,
    light_max_lb: float = DEFAULT_LIGHT_MAX_LB,
    balance_band: tuple[float, float] = DEFAULT_BALANCE_BAND,
    check_zones: bool = True,
) -> dict[str, Any]:
    """Verify a placement plan and return its structured score and violations."""
    violations: list[dict] = []

    for u in placement.get("unplaced") or []:
        uid = str(u.get("id", "item"))
        reason = u.get("reason") or "could not be placed in any truck"
        violations.append(_violation("unplaced_item", f"{uid} ({u.get('label')}): {reason}", item_ids=[uid]))

    trucks = placement.get("trucks") or []
    if not trucks and not placement.get("unplaced"):
        violations.append(_violation("fit", "placement contains zero trucks"))

    truck_stats: list[dict[str, float]] = []
    for t in trucks:
        tv, st = verify_truck(
            t,
            min_support=min_support,
            light_max_lb=light_max_lb,
            balance_band=balance_band,
        )
        violations.extend(tv)
        truck_stats.append(st)

    # Fleet right-sizing check: catch putting a tiny sparse load into a giant box truck when a smaller van/truck fits.
    if len(trucks) == 1 and not placement.get("unplaced") and truck_stats:
        t0 = trucks[0]
        st0 = truck_stats[0]
        t0_items = t0.get("items") or []
        cur_spec = catalog.get_truck(str(t0.get("truck_id") or ""))
        if cur_spec and t0_items and st0["fill_pct"] < 10.0:
            for sm in catalog.list_trucks():
                if sm["volume_cuft"] >= cur_spec["volume_cuft"] * 0.65:
                    break
                sm_vol_cuin = sm["length_in"] * sm["width_in"] * sm["height_in"]
                sm_floor = sm["length_in"] * sm["width_in"]
                if st0["weight_lb"] > sm["max_weight_lb"] * 0.9:
                    continue
                if st0["placed_vol_cuin"] > sm_vol_cuin * 0.55:
                    continue
                if st0["total_footprint_area"] > sm_floor * 0.80:
                    continue
                all_dims_fit = True
                for it in t0_items:
                    dx, dy, dz = [float(v) for v in it["size_in"]]
                    if dz > sm["height_in"] - 0.5 or max(dx, dy) > sm["length_in"] - 0.5 or min(dx, dy) > sm["width_in"] - 0.5:
                        all_dims_fit = False
                        break
                if all_dims_fit:
                    violations.append(_violation(
                        "oversized_truck",
                        f"Truck 1 ({cur_spec['name']}) is only {st0['fill_pct']:.1f}% full ({st0['weight_lb']:.0f} lb) — "
                        f"cargo fits in {sm['name']} ({sm['truck_id']}); use the smallest van/truck to prevent load shift",
                        truck_index=0,
                    ))
                    break

    zone_stats = {"zone_coverage_pct": 0.0, "stocked_zones": 0.0}
    if check_zones:
        zv, zone_stats = verify_zones(placement)
        violations.extend(zv)

    total_placed_vol = sum(s["placed_vol_cuin"] for s in truck_stats)
    total_truck_vol = sum(s["truck_vol_cuin"] for s in truck_stats)
    overall_fill_pct = (total_placed_vol / total_truck_vol * 100.0) if total_truck_vol > 0 else 0.0

    # Efficiency rewards high fill on full lead trucks, right-sized smallest van selection, and no extra trucks.
    if len(truck_stats) > 1:
        lead_fill = sum(s["fill_pct"] for s in truck_stats[:-1]) / (len(truck_stats) - 1)
        efficiency_pts = min(20.0, 12.0 * (lead_fill / 55.0) + 8.0 * (overall_fill_pct / 50.0))
    elif len(trucks) == 1:
        smallest_tid = catalog.list_trucks()[0]["truck_id"]
        min_floor = 0.65 if trucks[0].get("truck_id") == smallest_tid else 0.35
        efficiency_pts = min(20.0, 20.0 * min(1.0, max(min_floor, overall_fill_pct / 45.0)))
    else:
        efficiency_pts = 0.0

    if truck_stats:
        avg_balance_err = sum(abs(s["cog_y_ratio"] - 0.5) for s in truck_stats) / len(truck_stats)
        avg_cog_z = sum(s["cog_z_ratio"] for s in truck_stats) / len(truck_stats)
        balance_pts = max(0.0, 7.0 * (1.0 - min(1.0, avg_balance_err / 0.15))) + max(0.0, 3.0 * (1.0 - min(1.0, avg_cog_z)))
        avg_lifo = sum(s["lifo_ratio"] for s in truck_stats) / len(truck_stats)
        avg_balance_pct = (sum(s["cog_y_ratio"] for s in truck_stats) / len(truck_stats)) * 100.0
    else:
        balance_pts = 0.0
        avg_lifo = 0.0
        avg_balance_pct = 50.0

    lifo_pts = 10.0 * avg_lifo
    has_zones = any(it.get("dest_zone") for t in trucks for it in t.get("items", []))
    zone_pts = 10.0 * (zone_stats["zone_coverage_pct"] / 100.0) if (check_zones and has_zones) else 10.0

    compliance_pts = 50.0
    penalty = sum(RULE_WEIGHTS.get(v["rule"], 8.0) for v in violations)
    raw_total = compliance_pts + efficiency_pts + balance_pts + lifo_pts + zone_pts - penalty
    total_score = round(max(0.0, min(100.0, raw_total)), 1)

    by_rule: dict[str, int] = {}
    for v in violations:
        by_rule[v["rule"]] = by_rule.get(v["rule"], 0) + 1

    total_pe_j = sum(s["potential_energy_j"] for s in truck_stats)
    avg_pe_ratio = (sum(s["pe_ratio"] for s in truck_stats) / len(truck_stats)) if truck_stats else 1.0
    avg_cog_z_in = (sum(s["cog_z_in"] for s in truck_stats) / len(truck_stats)) if truck_stats else 0.0

    return {
        "total": total_score,
        "valid": len(violations) == 0,
        "fill_pct": round(overall_fill_pct, 1),
        "zone_coverage_pct": round(zone_stats["zone_coverage_pct"], 1),
        "lifo_score": round(lifo_pts, 1),
        "balance_pct": round(avg_balance_pct, 1),
        "potential_energy_j": round(total_pe_j, 1),
        "pe_ratio": round(avg_pe_ratio, 2),
        "cog_height_in": round(avg_cog_z_in, 1),
        "violation_count": len(violations),
        "violation_counts_by_rule": by_rule,
        "violations": violations,
    }
