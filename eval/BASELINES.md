# Evaluation & Baseline Comparison (`eval/RESULTS.md`)

Evaluated with the exact same pure-function physics and Penn Station destination verifier (`backend/verify.py`), enforcing 8 real-world moving constraints:
1. **3D Fit & Payload** (`fit`, `unplaced_item`, `truck_overweight`)
2. **Zero 3D AABB Overlap** (`overlap`)
3. **>= 75% Base Area Support & Load-Before-Support** (`support`, `load_seq_support`)
4. **Walk-In Tier Loading Access (no stepping over cargo)** (`walk_in_access`)
5. **Upright & Load-On-Edge Orientation** (`upright`, `load_on_edge`)
6. **Stacking Tier & Fragile Crush Protection** (`no_stack`, `light_only_on_top`, `fragile_crushed`)
7. **40%-60% Left-Right Axle Center-of-Gravity Balance** (`weight_balance`)
8. **Penn Station Store Doorway Clearances & LIFO Dock-Stop Unload** (`zone_door_clearance`, `zone_fit`, `zone_overlap`)

## Packing Plan Benchmark (`sample_venue.json` — 152 Expanded Pieces, 3 Rooms -> 6 Penn Station Zones)

| Method | Verifier Score | Valid Plan? | Rule Violations | Fleet Chosen | Primary Failure Modes Caught by Verifier |
|---|---:|---|---:|---|---|
| **Pack It Up (Agents + Constrained Solver + Verifier)** | **90.7 / 100** | **Yes (100%)** | **0** | `3 × uhaul_26` | **0 violations** · >=75% base support, walk-in tier order, 50% L/R axle balance, Penn LIFO dock order |
| **Baseline A1: Single-Call LLM 3D Coordinates** (`eval/baseline_single_call.py`) | `0.0 / 100` | No (0%) | **283** | `5 × uhaul_26` | Mid-air floating items (`support`), 3D AABB collisions (`overlap`), tipped upright monitors/whiteboards |
| **Baseline A2: Stock `py3dbp` 3D Bin Packer** (`packer_engine="raw_py3dbp"`) | `0.0 / 100` | No (0%) | **233** | `2 × uhaul_26` | `<75%` base support overhangs, heavy furniture stacked on `no_stack` / `light_only`, walk-in access blocked |
| **Baseline B: Rental-Site Room-Count Calculator** (`eval/baseline_bedroom.py`) | `0.0 / 100` | No (0%) | **54** | `1 × uhaul_20` | Quotes a single 20-ft truck for 3 rooms -> **54 pieces stranded on the curb** (`unplaced_item`) |

## Interactive 3D Verification in the Live App

Open `frontend/index.html` and use the top action bar above the 3D viewport:
- **⚡ Raw 1-Call LLM Chaos**: swaps the 3D viewport to `POST /eval/chaos-plan` so judges visually inspect mid-air floats, intersecting meshes, and crimson violation wireframes.
- **💥 NYC Pothole / 0.8g Brake Test**: applies a forward 0.8g brake + BQE pothole impulse in Three.js — unverified items physically slide and topple, while the **Pack It Up Verified** load holds with `0` items shifted.

## Reproduce

```bash
.venv/bin/python -m backend.solver data/sample_venue.json
.venv/bin/python eval/baseline_single_call.py
.venv/bin/python eval/baseline_bedroom.py
```
