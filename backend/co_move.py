"""Human + Robot Co-Move Biomechanics, `gemini-robotics-er-2-preview` Spatial Coach,
and Penn Station "Already Full of Stuff" Occupancy & Egress Guardrails.

All model calls go exclusively through `backend.llm.for_job("robotics")`
(with automatic fallback to `robotics_fallback` -> `gemini-4-neon`).
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from backend.llm import LLMError, Media, for_job, media_from_path

# NIOSH-inspired ergonomic thresholds for residential & venue crews
SAFE_BOX_MAX_LB = 40.0
ROBOT_BOX_MAX_LB = 50.0
HEAVY_HUMAN_LIFT_LB = 65.0
STD_ORIGIN_DOOR_IN = (32.0, 80.0)  # Standard NYC interior/apartment doorway (W x H)
MOYNIHAN_FREIGHT_ELEVATOR_IN = (68.0, 96.0, 96.0)  # (door_w, door_h, cab_depth) for Stop 5 (+20 ft Mezzanine)
MOYNIHAN_FREIGHT_MAX_LB = 4500.0

# Architectural gross sq ft vs leased pop-up/tenant bays in `data/penn_zones.csv`
# Matches `frontend/ui/penn-venue-3d.js` SOM Moynihan Train Hall & LIRR Concourse specs.
PENN_ARCHITECTURAL_CONTEXT: dict[str, dict[str, Any]] = {
    "penn_merch_kiosk": {
        "gross_wing_sqft": 936.0,  # 36 x 26 ft West Entrance Check-In & Swag bay
        "existing_fixtures": "Amtrak ticket kiosks, West 9th Ave turnstiles, security stanchions & 8-ft commuter entry lane",
        "egress_aisle_in": 44,
        "elevation_ft": 0,
        "requires_freight_elevator": False,
    },
    "penn_cafe": {
        "gross_wing_sqft": 2560.0,  # 64 x 40 ft Moynihan Food Hall colonnade bay
        "existing_fixtures": "Fixed marble espresso bar, plumbing/POS island, Food Hall queue rails & shared dining tables",
        "egress_aisle_in": 44,
        "elevation_ft": 0,
        "requires_freight_elevator": False,
    },
    "penn_bookshop": {
        "gross_wing_sqft": 1980.0,  # 55 x 36 ft LIRR 33rd St Concourse retail bay
        "existing_fixtures": "Built-in perimeter Hudson shelving, cash wrap counter & 57-ft LIRR commuter concourse flow",
        "egress_aisle_in": 44,
        "elevation_ft": 0,
        "requires_freight_elevator": False,
    },
    "penn_tech_hub": {
        "gross_wing_sqft": 2856.0,  # 68 x 42 ft South 31st St Arcade bay
        "existing_fixtures": "Structural 1912 steel columns, glass partition mullions & 31st St Arcade pedestrian corridor",
        "egress_aisle_in": 48,
        "elevation_ft": 0,
        "requires_freight_elevator": False,
    },
    "penn_lounge": {
        "gross_wing_sqft": 3024.0,  # 72 x 42 ft Upper South Mezzanine Balcony (+20 ft)
        "existing_fixtures": "Reception podium, glass balcony balustrade, buffet credenza & +20 ft freight elevator access",
        "egress_aisle_in": 48,
        "elevation_ft": 20,
        "requires_freight_elevator": True,
    },
    "penn_concourse": {
        "gross_wing_sqft": 30452.0,  # 200 x 150 ft Main Skylit Boarding Hall
        "existing_fixtures": "Track 5–16 escalator islands, LED departure totems, FDNY 96-in fire lanes & 400k daily riders",
        "egress_aisle_in": 96,
        "elevation_ft": 0,
        "requires_freight_elevator": False,
    },
}

OCCUPANCY_MODES: dict[str, dict[str, Any]] = {
    "permitted_bays": {
        "id": "permitted_bays",
        "label": "Permitted Pop-Up Bays (Default · 96.0% of Hall Untouched)",
        "existing_bay_clutter_pct": 0.0,
        "aisle_reserve_pct": 0.28,  # 28% inside each permitted bay reserved for 36"-44" walk paths
        "load_window": "MTA Off-Peak Freight Window (11:00 PM – 5:00 AM via W 31st St Service Dock)",
    },
    "crowded_stalls_35": {
        "id": "crowded_stalls_35",
        "label": "Partially Full Stalls (35% Existing Counters & Fixtures Inside Bays)",
        "existing_bay_clutter_pct": 0.35,
        "aisle_reserve_pct": 0.22,
        "load_window": "Staged Night Load-In + Pre-Cleared Tenant Corners",
    },
    "rush_hour_55": {
        "id": "rush_hour_55",
        "label": "Tight / Half-Full Spaces (55% Occupied + Strict FDNY Egress)",
        "existing_bay_clutter_pct": 0.55,
        "aisle_reserve_pct": 0.18,
        "load_window": "Restricted Daytime Window — Hold Overflow on Dock AMR Carts",
    },
}

ROBOTICS_SCAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["scene_summary", "clear_path_ready", "waypoints"],
    "properties": {
        "scene_summary": {"type": "string"},
        "clear_path_ready": {"type": "boolean"},
        "waypoints": {
            "type": "array",
            "minItems": 2,
            "maxItems": 8,
            "items": {
                "type": "object",
                "required": ["step", "kind", "point", "label", "instruction"],
                "properties": {
                    "step": {"type": "integer", "minimum": 1, "maximum": 12},
                    "kind": {
                        "type": "string",
                        "enum": ["clear_first", "robot_pick", "human_grip", "keep_out", "stage_zone"],
                    },
                    "point": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 2,
                        "items": {"type": "integer", "minimum": 0, "maximum": 1000},
                    },
                    "label": {"type": "string"},
                    "instruction": {"type": "string"},
                },
            },
        },
    },
}


def _classify_handler(item: dict[str, Any]) -> dict[str, str]:
    """Assign each item to the safest realistic robot, powered dolly, or human crew role."""
    is_box = bool(item.get("is_box"))
    wt = float(item.get("weight_lb") or 0.0)
    fragile = bool(item.get("fragile"))
    load_on_edge = bool(item.get("load_on_edge"))
    cid = str(item.get("catalog_id") or "").lower()
    lbl = str(item.get("label") or "").lower()
    key = f"{cid} {lbl}"
    dims = [float(x) for x in (item.get("orig_dims_in") or item.get("size_in") or [20, 20, 20])]
    max_dim = max(dims)

    # 1. Dock Box Unloader Robot (Boston Dynamics Stretch / Pickle class): sealed non-fragile boxes <= 50 lb
    if is_box and wt <= ROBOT_BOX_MAX_LB and not fragile:
        return {
            "role": "dock_robot",
            "role_label": "Dock Unloader Robot (Stretch class)",
            "gear": "Vacuum-gripper truck unloader -> AMR concourse shuttle",
            "why": f"Uniform {wt:.0f} lb carton (<=50 lb robot suction spec); saves repetitive human stooping.",
        }

    # 2. Autonomous Concourse Cart (AMR): fragile boxes <= 50 lb, Pelican 1510 lens cases, compact gear <= 42 lb
    if (is_box and wt <= ROBOT_BOX_MAX_LB and fragile) or "pelican_1510" in key or (
        not is_box
        and wt <= 42.0
        and max_dim <= 36.0
        and not any(k in key for k in ("lamp", "plant", "mirror", "art", "frame", "chair", "stool", "pouf"))
    ):
        return {
            "role": "amr_cart",
            "role_label": "Padded Concourse AMR Cart",
            "gear": "Shock-damped autonomous concourse flatbed cart",
            "why": "Human sets item once onto padded AMR deck; robot hauls the 420-ft concourse run.",
        }

    # 3. Tracked Gyroscopic Stair/Ramp Dolly (XSTO / Zonzini class): dense rigid cases/appliances > 50 lb
    is_rigid_case = any(
        k in key
        for k in (
            "pelican_1650",
            "pelican",
            "safe",
            "refrigerator",
            "fridge",
            "washer",
            "dryer",
            "filing",
            "cabinet",
            "appliance",
            "printer",
            "copier",
            "crate",
        )
    ) or (is_box and wt > ROBOT_BOX_MAX_LB)
    if is_rigid_case and not load_on_edge:
        return {
            "role": "stair_dolly",
            "role_label": "Tracked Gyro Stair/Ramp Dolly",
            "gear": "Motorized rubber-track dolly w/ auto-brake (XSTO / Zonzini class)",
            "why": f"Motorized treads bear 100% of {wt:.0f} lb dead weight on ramps/curbs; 1 human steers upright.",
        }

    # 4. Human Biomechanics Crew: sofas, stone/mohair Orior pieces, tables, tall shelving, carts, art
    if any(k in key for k in ("c_stand", "magliner")) or "cart" in key:
        gear = "Roll on locked pneumatic casters + truck ramp (2-person spotter on ramp)"
    elif wt >= HEAVY_HUMAN_LIFT_LB or bool(item.get("two_person")):
        gear = "2-Person Forearm/Shoulder Straps + Furniture Sliders (hip-hinge, zero spinal twist)"
    elif fragile or load_on_edge:
        gear = "Quilted cotton pad + edge-carry handles (keep vertical, never flat)"
    else:
        gear = "1-Person close-to-core carry (elbows tucked, step to turn — don't twist)"

    return {
        "role": "human_ergo",
        "role_label": "Human Biomechanics Crew",
        "gear": gear,
        "why": "Irregular geometry, doorway pivot, or bespoke finish that suction/industrial robots cannot grip.",
    }


def _doorway_maneuver(item: dict[str, Any], dest_door_in: list[float]) -> dict[str, Any]:
    """Compute realistic doorway clearance & tilt-and-pivot / disassembly guidance."""
    dims = [float(x) for x in (item.get("orig_dims_in") or item.get("size_in") or [24, 24, 24])]
    l, w, h = dims
    cid = str(item.get("catalog_id") or "").lower()
    lbl = str(item.get("label") or "").lower()
    key = f"{cid} {lbl}"
    upright = bool(item.get("must_stay_upright"))
    disassemble = bool(item.get("disassemble")) or any(
        k in key for k in ("dining_table", "communal", "conference", "bed_", "desk")
    )

    # Evaluate against the tighter of NYC 32x80 origin door vs Penn Station storefront door
    dw = min(STD_ORIGIN_DOOR_IN[0], float(dest_door_in[0]))
    dh = min(STD_ORIGIN_DOOR_IN[1], float(dest_door_in[1]))
    knuckle_margin = 2.0  # 1" per side so movers don't crush fingers against jambs

    s0, s1, s2 = sorted([l, w, h])
    min_plan = min(l, w)

    # Straight upright walk-through with 2" knuckle clearance
    if h <= dh - 1.0 and min_plan <= dw - knuckle_margin:
        return {
            "status": "straight_walk_in",
            "badge": "Straight Walk-In",
            "door_tested_in": [round(dw, 1), round(dh, 1)],
            "instruction": f"Clears {dw:.0f}\"×{dh:.0f}\" doorway upright ({min_plan:.0f}\" wide, {dw - min_plan:.0f}\" knuckle margin).",
        }

    # Check if unbolting legs / Knock-down makes a wide table/desk effortless
    if disassemble and s0 <= dw - knuckle_margin:
        return {
            "status": "unbolt_legs_first",
            "badge": "Unbolt Legs First",
            "door_tested_in": [round(dw, 1), round(dh, 1)],
            "instruction": (
                f"Unbolt legs/frame before lifting ({l:.0f}\"×{w:.0f}\"×{h:.0f}\") -> Carry slab on edge through "
                f"{dw:.0f}\" door; tape Ziploc bolt bag to underside."
            ),
        }

    # Diagonal tilt-and-pivot math across door frame diagonal
    diag_usable = math.hypot(dw, dh) * 0.90
    if not upright and s0 <= dw + 1.5 and s1 <= diag_usable:
        tilt_deg = round(math.degrees(math.atan2(dw, dh)), 0)
        return {
            "status": "diagonal_tilt_pivot",
            "badge": f"Tilt {int(tilt_deg)}° & Pivot",
            "door_tested_in": [round(dw, 1), round(dh, 1)],
            "instruction": (
                f"Too wide flat ({min_plan:.0f}\" vs {dw:.0f}\" door); angle ~{int(tilt_deg)}° into frame diagonal "
                f"({diag_usable:.0f}\" diag). Person B leads bottom corner, step feet—never twist spine."
            ),
        }

    if s0 <= dw and s1 <= dh:
        return {
            "status": "tight_clearance",
            "badge": "Tight (<2\" Margin)",
            "door_tested_in": [round(dw, 1), round(dh, 1)],
            "instruction": (
                f"Tight {max(0.0, dw - s0):.1f}\" doorway margin on {dw:.0f}\" frame — wrap corners in cotton pads "
                f"and pop interior hinge pins (+1.75\") if needed."
            ),
        }

    return {
        "status": "hinge_pin_or_reroute",
        "badge": "Service Door / Crate Split",
        "door_tested_in": [round(dw, 1), round(dh, 1)],
        "instruction": (
            f"{s0:.0f}\"×{s1:.0f}\" profile exceeds {dw:.0f}\"×{dh:.0f}\" interior door — route via double freight "
            f"doors or disassemble before move day."
        ),
    }


def audit_penn_occupancy(plan: dict[str, Any], occupancy_mode: str = "permitted_bays") -> dict[str, Any]:
    """Audit Penn Station destination zones accounting for existing commuters, counters & egress."""
    mode = OCCUPANCY_MODES.get(occupancy_mode) or OCCUPANCY_MODES["permitted_bays"]
    clutter_pct = float(mode["existing_bay_clutter_pct"])
    aisle_pct = float(mode["aisle_reserve_pct"])

    zones_out: list[dict[str, Any]] = []
    total_gross_sqft = sum(v["gross_wing_sqft"] for v in PENN_ARCHITECTURAL_CONTEXT.values())
    total_permitted_sqft = 0.0
    total_net_clear_sqft = 0.0
    total_furniture_floor_sqft = 0.0
    overflow_zones = 0
    elevator_flags: list[str] = []

    for z in plan.get("zones") or []:
        zid = str(z.get("zone_id") or "penn_concourse")
        ctx = PENN_ARCHITECTURAL_CONTEXT.get(zid, PENN_ARCHITECTURAL_CONTEXT["penn_concourse"])
        dims = z.get("dims_in") or [240, 180, 108]
        permitted_sqft = round((float(dims[0]) * float(dims[1])) / 144.0, 1)
        usable_ratio = max(0.20, 1.0 - clutter_pct - aisle_pct)
        net_clear_sqft = round(permitted_sqft * usable_ratio, 1)

        # Ground-contact footprint (z <= 1.0") so stacked boxes only occupy floor once
        floor_sqin = 0.0
        z_items = z.get("items") or []
        overflow_candidates: list[str] = []
        for it in z_items:
            pos = it.get("pos_in") or [0, 0, 0]
            sz = it.get("size_in") or [18, 18, 16]
            if float(pos[2]) <= 1.0:
                floor_sqin += float(sz[0]) * float(sz[1])

            # Check Stop 5 (+20 ft Mezzanine) freight elevator cab limits
            if ctx["requires_freight_elevator"]:
                s_dims = sorted([float(x) for x in (it.get("orig_dims_in") or sz)])
                ew, eh, ed = MOYNIHAN_FREIGHT_ELEVATOR_IN
                if s_dims[0] > ew or s_dims[1] > eh or s_dims[2] > ed:
                    elevator_flags.append(
                        f"{it.get('label', it.get('id'))} ({sz[0]:.0f}×{sz[1]:.0f}×{sz[2]:.0f}\") exceeds Mezzanine freight cab"
                    )

        placed_floor_sqft = round(floor_sqin / 144.0, 1)
        total_permitted_sqft += permitted_sqft
        total_net_clear_sqft += net_clear_sqft
        total_furniture_floor_sqft += placed_floor_sqft

        fill_of_clear_pct = round((placed_floor_sqft / max(1.0, net_clear_sqft)) * 100.0, 1)
        fits_clear = placed_floor_sqft <= net_clear_sqft + 0.5
        if not fits_clear:
            overflow_zones += 1
            # Suggest holding lowest-priority boxes/duplicates on AMR staging cart
            sorted_by_area = sorted(
                [i for i in z_items if float((i.get("pos_in") or [0, 0, 0])[2]) <= 1.0],
                key=lambda x: (not bool(x.get("is_box")), -(float(x["size_in"][0]) * float(x["size_in"][1]))),
            )
            excess_sqft = placed_floor_sqft - net_clear_sqft
            acc = 0.0
            for cand in sorted_by_area:
                if acc >= excess_sqft:
                    break
                overflow_candidates.append(str(cand.get("label") or cand.get("id")))
                acc += (float(cand["size_in"][0]) * float(cand["size_in"][1])) / 144.0

        zones_out.append({
            "zone_id": zid,
            "name": z.get("name") or zid,
            "dock_stop": int(z.get("dock_stop") or 6),
            "gross_wing_sqft": ctx["gross_wing_sqft"],
            "permitted_bay_sqft": permitted_sqft,
            "net_clear_sqft": net_clear_sqft,
            "placed_floor_sqft": placed_floor_sqft,
            "fill_of_clear_pct": fill_of_clear_pct,
            "fits_occupied_space": fits_clear,
            "existing_fixtures": ctx["existing_fixtures"],
            "egress_aisle_in": ctx["egress_aisle_in"],
            "requires_freight_elevator": ctx["requires_freight_elevator"],
            "overflow_reroute_items": overflow_candidates[:4],
        })

    untouched_station_sqft = round(max(0.0, total_gross_sqft - total_permitted_sqft), 1)
    untouched_station_pct = round((untouched_station_sqft / max(1.0, total_gross_sqft)) * 100.0, 1)
    zone_total_wt = sum(
        float(z.get("total_weight_lb") or 0.0)
        for z in (plan.get("zones") or [])
        if z.get("zone_id") == "penn_lounge"
    )
    mezz_trips = max(1, math.ceil(zone_total_wt / (MOYNIHAN_FREIGHT_MAX_LB * 0.75))) if zone_total_wt > 0 else 0

    return {
        "occupancy_mode": mode["id"],
        "occupancy_label": mode["label"],
        "load_window": mode["load_window"],
        "gross_station_sqft": round(total_gross_sqft, 0),
        "untouched_station_sqft": untouched_station_sqft,
        "untouched_station_pct": untouched_station_pct,
        "permitted_bays_sqft": round(total_permitted_sqft, 1),
        "net_clear_floor_sqft": round(total_net_clear_sqft, 1),
        "placed_floor_sqft": round(total_furniture_floor_sqft, 1),
        "all_bays_clear": overflow_zones == 0 and len(elevator_flags) == 0,
        "overflow_zone_count": overflow_zones,
        "mezzanine_elevator_trips": mezz_trips,
        "mezzanine_elevator_ok": len(elevator_flags) == 0,
        "mezzanine_elevator_flags": elevator_flags,
        "plothole_answer": (
            f"Moynihan & LIRR span {total_gross_sqft:,.0f} sq ft, and {untouched_station_pct:.1f}% "
            f"({untouched_station_sqft:,.0f} sq ft) stays 100% untouched for commuters, escalators, existing counters, "
            f"and FDNY 44\"–96\" egress lanes. Our solver only places {total_furniture_floor_sqft:.0f} sq ft of ground "
            f"footprint inside {total_permitted_sqft:,.0f} sq ft of permitted pop-up/tenant bays during the off-peak "
            f"W 31st St freight dock window."
        ),
        "zones": sorted(zones_out, key=lambda r: r["dock_stop"]),
    }


def analyze_co_move(plan: dict[str, Any], occupancy_mode: str = "permitted_bays") -> dict[str, Any]:
    """Compute Human + Robot Co-Move assignments, NIOSH biomechanics checks, and Penn occupancy."""
    zone_doors: dict[str, list[float]] = {
        str(z.get("zone_id")): list(z.get("door_in") or [36.0, 80.0])
        for z in (plan.get("zones") or [])
    }

    role_stats: dict[str, dict[str, Any]] = {
        "dock_robot": {"role": "dock_robot", "label": "Dock Unloader Robot", "count": 0, "weight_lb": 0.0, "examples": []},
        "amr_cart": {"role": "amr_cart", "label": "Concourse AMR Cart", "count": 0, "weight_lb": 0.0, "examples": []},
        "stair_dolly": {"role": "stair_dolly", "label": "Tracked Gyro Dolly", "count": 0, "weight_lb": 0.0, "examples": []},
        "human_ergo": {"role": "human_ergo", "label": "Human Biomechanics Crew", "count": 0, "weight_lb": 0.0, "examples": []},
    }

    total_items = 0
    total_weight = 0.0
    overweight_boxes: list[dict[str, Any]] = []
    fatigue_streaks: list[dict[str, Any]] = []
    doorway_playbook: list[dict[str, Any]] = []
    seen_door_labels: set[str] = set()

    for t in plan.get("trucks") or []:
        t_idx = int(t.get("index") or 0) + 1
        ordered = sorted(t.get("items") or [], key=lambda x: int(x.get("load_seq") or 0))
        consec_heavy = 0
        streak_labels: list[str] = []

        for it in ordered:
            total_items += 1
            wt = float(it.get("weight_lb") or 0.0)
            total_weight += wt
            h_info = _classify_handler(it)
            role = h_info["role"]
            bucket = role_stats[role]
            bucket["count"] += 1
            bucket["weight_lb"] = round(bucket["weight_lb"] + wt, 1)
            lbl = str(it.get("label") or it.get("id") or "item")
            if len(bucket["examples"]) < 3 and lbl not in bucket["examples"]:
                bucket["examples"].append(lbl)

            if bool(it.get("is_box")) and wt > SAFE_BOX_MAX_LB:
                overweight_boxes.append({
                    "id": it.get("id"),
                    "label": lbl,
                    "weight_lb": round(wt, 1),
                    "fix": f"Split into 2 small boxes (~{wt / 2:.0f} lb each) under 40 lb safe spine target.",
                })

            if role == "human_ergo" and wt >= HEAVY_HUMAN_LIFT_LB:
                consec_heavy += 1
                streak_labels.append(f"{lbl} ({wt:.0f} lb)")
                if consec_heavy == 3:
                    fatigue_streaks.append({
                        "truck": t_idx,
                        "items": list(streak_labels),
                        "advice": "Insert a dock-robot box batch or 90-sec micro-break after 2 heavy team carries.",
                    })
            else:
                consec_heavy = 0
                streak_labels = []

            dims = [float(x) for x in (it.get("orig_dims_in") or it.get("size_in") or [20, 20, 20])]
            if not bool(it.get("is_box")) and (max(dims) >= 34.0 or wt >= 55.0 or bool(it.get("two_person"))):
                sig = f"{lbl}:{it.get('dest_zone')}"
                if sig not in seen_door_labels:
                    seen_door_labels.add(sig)
                    d_door = zone_doors.get(str(it.get("dest_zone") or ""), [36.0, 80.0])
                    dm = _doorway_maneuver(it, d_door)
                    doorway_playbook.append({
                        "id": it.get("id"),
                        "label": lbl,
                        "weight_lb": round(wt, 1),
                        "dims_in": [round(d, 1) for d in dims],
                        "dest_zone_name": it.get("dest_zone_name") or it.get("dest_zone") or "Penn Station",
                        "handler_role": role,
                        "handler_label": h_info["role_label"],
                        "gear": h_info["gear"],
                        **dm,
                    })

    offloaded_lb = round(
        role_stats["dock_robot"]["weight_lb"]
        + role_stats["amr_cart"]["weight_lb"]
        + role_stats["stair_dolly"]["weight_lb"],
        1,
    )
    offloaded_cnt = (
        role_stats["dock_robot"]["count"]
        + role_stats["amr_cart"]["count"]
        + role_stats["stair_dolly"]["count"]
    )
    offloaded_pct = round((offloaded_lb / max(1.0, total_weight)) * 100.0, 1)

    # Ergonomic score (100 = ideal offload + <=40 lb boxes + spaced lifts)
    penalty = len(overweight_boxes) * 4 + len(fatigue_streaks) * 7
    ergo_score = max(62, min(100, 100 - penalty))

    # Prioritize interesting maneuvers first (unbolt / diagonal / tight before straight walk-in)
    priority_rank = {
        "hinge_pin_or_reroute": 0,
        "unbolt_legs_first": 1,
        "diagonal_tilt_pivot": 2,
        "tight_clearance": 3,
        "straight_walk_in": 4,
    }
    doorway_playbook.sort(key=lambda r: (priority_rank.get(r["status"], 9), -r["weight_lb"]))

    penn_occ = audit_penn_occupancy(plan, occupancy_mode=occupancy_mode)

    return {
        "total_items": total_items,
        "total_weight_lb": round(total_weight, 1),
        "offloaded_items": offloaded_cnt,
        "offloaded_weight_lb": offloaded_lb,
        "offloaded_pct": offloaded_pct,
        "human_ergo_items": role_stats["human_ergo"]["count"],
        "human_ergo_weight_lb": role_stats["human_ergo"]["weight_lb"],
        "ergo_score": ergo_score,
        "safe_box_cap_lb": SAFE_BOX_MAX_LB,
        "overweight_boxes": overweight_boxes[:6],
        "fatigue_streaks": fatigue_streaks[:5],
        "roles": list(role_stats.values()),
        "doorway_playbook": doorway_playbook[:10],
        "penn_occupancy": penn_occ,
    }


def scan_space_with_robotics(
    image_path: Path,
    target: str = "origin",
    context_hint: str = "",
) -> dict[str, Any]:
    """Run Google's `gemini-robotics-er-2-preview` (`v1beta`) to generate `[y, x]` spatial callouts."""
    media = [media_from_path(image_path)]
    if target == "destination":
        prompt = (
            "You are an embodied robotics & commercial move-in spatial planner inspecting a destination space "
            "(such as NY Penn Station / Moynihan Train Hall or a furnished room that already has existing fixtures "
            "and people). Identify 4 to 6 key normalized `[y, x]` points (`0` to `1000`, where `[0, 0]` is top-left "
            "and `[1000, 1000]` is bottom-right):\n"
            "- Use `keep_out` for existing counters, columns, seating, displays, or active pedestrian/commuter lanes "
            "that movers and AMR carts MUST NOT block.\n"
            "- Use `clear_first` for any movable clutter in the entry path.\n"
            "- Use `stage_zone` for open, unobstructed floor areas where an autonomous AMR cart or 2-person crew can "
            "safely stage incoming furniture while preserving a 44-inch ADA/FDNY walkway.\n"
            f"{('Context: ' + context_hint) if context_hint else ''}\n"
            "Return strict JSON matching the schema."
        )
    else:
        prompt = (
            "You are an embodied robotics & human-biomechanics move coach inspecting an origin room before move-out. "
            "Identify 4 to 6 key normalized `[y, x]` points (`0` to `1000`, where `[0, 0]` is top-left and "
            "`[1000, 1000]` is bottom-right) in exact execution sequence:\n"
            "- Step 1..2 `clear_first`: floor obstacles (stools, poufs, cables, rugs, bags) to clear out of the exit lane first.\n"
            "- `robot_pick`: uniform boxes or rigid cases<=50 lb that a dock robot / AMR cart / tracked dolly can haul.\n"
            "- `human_grip`: exact safe 2-person grip zone on bulky/bespoke furniture (note hip-hinge posture, forearm straps, "
            "leg unbolting, or Orior white-glove protection for stone/upholstery).\n"
            f"{('Context: ' + context_hint) if context_hint else ''}\n"
            "Return strict JSON matching the schema."
        )

    used_model = "gemini-robotics-er-2-preview"
    via = "robotics_er_2"
    try:
        job = for_job("robotics")
        used_model = job.provider.model
        res = job.generate_json(
            prompt,
            media=media,
            schema=ROBOTICS_SCAN_SCHEMA,
            prompt_version=f"co_move_{target}_v1",
            label=image_path.name,
        )
    except LLMError:
        fb = for_job("robotics_fallback")
        used_model = fb.provider.model
        via = "gemini_4_fallback"
        res = fb.generate_json(
            prompt,
            media=media,
            schema=ROBOTICS_SCAN_SCHEMA,
            prompt_version=f"co_move_{target}_fb_v1",
            label=image_path.name,
        )

    waypoints = sorted(res.get("waypoints") or [], key=lambda w: int(w.get("step") or 1))
    return {
        "target": target,
        "model": used_model,
        "via": via,
        "scene_summary": res.get("scene_summary") or "",
        "clear_path_ready": bool(res.get("clear_path_ready")),
        "waypoints": waypoints,
    }
