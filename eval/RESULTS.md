# Results

Built by `python eval/results_table.py` on Nov 21 2026 at 14:50 from the 24 moves in `runs/` that have an inventory. Do not edit by hand; run the script again.

**The test set.** Every move on the demo laptop: photos and clips uploaded today, Nov 21 2026, while we built and tested. Most are rooms at the hackathon venue; we did not record where each was filmed. The 24 moves come from 14 different sets of files: moves with the same letter under "Set" are repeat runs of the same footage (prompt changes during the build, or a file sent twice), so they are not independent. Where a line says "one per set", it counts only the latest move of each set.

## 1. Packing: a stock packer against ours, scored by the same checker

The baseline is `py3dbp`, an open-source 3D bin packer, used as it comes (`packer_engine="raw_py3dbp"`). Ours is the solver in `backend/solver.py`. Both plans go through `backend/verify.py`, which checks fit and payload, overlap, support under each piece, upright and on-edge rules, stacking and fragile rules, left/right balance and the doorways at the destination.

| | Stock packer | Ours |
|---|---|---|
| Plans with no rule broken | 4 of 24 | 22 of 24 |
| The same, one per set | 3 of 14 | 13 of 14 |
| Rules broken, all moves | 298 | 2 |
| Rules broken per move, mean | 12.4 | 0.1 |

Rules the stock packer broke: support 142, no_stack 116, upright 15, light_only_on_top 12, weight_balance 11, zone_distribution 2.
Rules ours broke: zone_distribution 2.

| Move | Set | Rooms | Pieces | Load (cu ft) | Stock: trucks | Stock: rules broken | Ours: trucks | Ours: rules broken | Ours: score |
|---|---|---|---|---|---|---|---|---|---|
| 110218 | A | 1 | 58 | 824 | 1 | 32 | 2 | 0 | 89.2 |
| 110422 | A | 1 | 58 | 824 | 1 | 32 | 2 | 0 | 89.2 |
| 110438 | A | 1 | 60 | 902 | 1 | 23 | 2 | 0 | 88.5 |
| 110750 | A | 1 | 58 | 824 | 1 | 32 | 2 | 0 | 89.2 |
| 110908 | B | 1 | 44 | 650 | 1 | 20 | 2 | 0 | 84.0 |
| 110958 | A | 1 | 59 | 851 | 1 | 34 | 2 | 0 | 89.5 |
| 111353 | C | 1 | 46 | 424 | 1 | 0 | 1 | 0 | 83.5 |
| 111600 | A | 1 | 61 | 841 | 1 | 31 | 2 | 0 | 88.8 |
| 111600 | C | 1 | 43 | 421 | 1 | 0 | 1 | 0 | 83.1 |
| 113646 | A | 1 | 59 | 811 | 1 | 7 | 1 | 0 | 92.9 |
| 114124 | A | 1 | 59 | 811 | 1 | 7 | 1 | 0 | 92.9 |
| 115436 | D | 1 | 17 | 142 | 1 | 2 | 1 | 1 | 62.4 |
| 120009 | E | 2 | 66 | 252 | 1 | 1 | 1 | 0 | 82.3 |
| 120427 | F | 1 | 7 | 46 | 1 | 1 | 1 | 0 | 83.0 |
| 124056 | G | 1 | 14 | 58 | 1 | 2 | 1 | 1 | 67.7 |
| 130657 | H | 1 | 12 | 45 | 1 | 1 | 1 | 0 | 84.3 |
| 130913 | I | 1 | 16 | 251 | 1 | 1 | 1 | 0 | 77.0 |
| 132950 | J | 1 | 39 | 551 | 1 | 0 | 1 | 0 | 87.2 |
| 133201 | K | 2 | 68 | 864 | 1 | 50 | 2 | 0 | 91.5 |
| 134559 | L | 1 | 5 | 15 | 1 | 1 | 1 | 0 | 77.5 |
| 134605 | M | 3 | 51 | 708 | 1 | 19 | 1 | 0 | 90.0 |
| 140739 | N | 1 | 11 | 93 | 1 | 1 | 1 | 0 | 76.7 |
| 144333 | I | 1 | 32 | 444 | 1 | 0 | 1 | 0 | 83.9 |
| 144416 | D | 1 | 6 | 85 | 1 | 1 | 1 | 0 | 74.6 |

The stock packer always reports one truck because it stacks without the rules; the load does not travel that way. Trucks are U-Haul 26 ft.

## 2. The Neon planner loop

`gemini-4-neon` reads the checker's score and broken rules and changes the solver's settings, for up to three solver runs; the best round with no rule broken is kept. Run on the latest move of each set of footage (14 moves): the score went up on 9 and the start was already best on 5; the truck count went down on 1. The score is the checker's own (fill, unload order, balance), so a higher score with smaller trucks means a tighter load, not a cheaper one.

| Move | Start | Start score | Kept round | Kept | Kept score | Settings changed from the round before |
|---|---|---|---|---|---|---|
| 114124 | 1 × 26 ft | 92.9 | 2 of 3 | 2 × 20 ft | 94.7 | truck_id: 26 ft → 20 ft; allow_all_rotations: False → True; downsize_last_truck: False → True |
| 110908 | 2 × 26 ft | 84.0 | 3 of 3 | 1 × 26 ft + 1 × 10 ft | 87.9 | order_mode: lifo_heavy_first → zone_strict_lifo |
| 111600 | 1 × 26 ft | 83.1 | 2 of 3 | 1 × 15 ft + 1 × 10 ft | 91.1 | truck_id: 26 ft → 15 ft; allow_all_rotations: False → True; downsize_last_truck: False → True |
| 144416 | 1 × 26 ft | 74.6 | 1 of 3 | 1 × 26 ft | 74.6 | nothing (the start was best) |
| 120009 | 1 × 26 ft | 82.3 | 3 of 3 | 1 × 15 ft | 89.4 | truck_id: 10 ft → 15 ft |
| 120427 | 1 × 26 ft | 83.0 | 1 of 3 | 1 × 26 ft | 83.0 | nothing (the start was best) |
| 124056 | 1 × 26 ft | 67.7 | 1 of 3 | 1 × 26 ft | 67.7 | nothing (the start was best) |
| 130657 | 1 × 26 ft | 84.3 | 1 of 3 | 1 × 26 ft | 84.3 | nothing (the start was best) |
| 144333 | 1 × 26 ft | 83.9 | 2 of 3 | 1 × 15 ft + 1 × 10 ft | 91.2 | truck_id: 26 ft → 15 ft; allow_all_rotations: False → True; downsize_last_truck: False → True |
| 132950 | 1 × 26 ft | 87.2 | 2 of 3 | 1 × 15 ft + 1 × 10 ft | 95.7 | truck_id: 26 ft → 15 ft; allow_all_rotations: False → True; downsize_last_truck: False → True |
| 133201 | 2 × 26 ft | 91.5 | 2 of 3 | 1 × 26 ft | 95.2 | allow_all_rotations: False → True; downsize_last_truck: False → True |
| 134559 | 1 × 26 ft | 77.5 | 1 of 3 | 1 × 26 ft | 77.5 | nothing (the start was best) |
| 134605 | 1 × 26 ft | 90.0 | 3 of 3 | 1 × 26 ft | 90.3 | truck_id: 20 ft → 26 ft; order_mode: lifo_heavy_first → zone_strict_lifo |
| 140739 | 1 × 26 ft | 76.7 | 2 of 3 | 1 × 10 ft | 84.0 | truck_id: 26 ft → 10 ft; order_mode: lifo_heavy_first → zone_strict_lifo; downsize_last_truck: False → True |

## 3. Truck size: the rental site's bedroom rule against the smallest truck that fits

How people pick a truck today: U-Haul's site names a truck by home size (10 ft: studio to 1 bedroom apartment, 402 cu ft; 15 ft: 1 bedroom home to 2 bedroom apartment, 764 cu ft; 20 ft: 2 bedroom home to 3 bedroom apartment, 1,016 cu ft; 26 ft: 3 to 4 bedroom home, 1,682 cu ft; [uhaul.com/Truck-Rentals](https://www.uhaul.com/Truck-Rentals/), read Nov 21 2026). We count each filmed room as a bedroom, which is our assumption and is generous to the rule. "Trucks of that size needed" is our solver packing the move into that truck size, checked. "Smallest that fits" is the smallest single U-Haul our solver fills with nothing left over.

| Move | Set | Rooms | Rule picks | Load (cu ft) | Trucks of that size needed | Smallest that fits | Rule was |
|---|---|---|---|---|---|---|---|
| 110218 | A | 1 | 1 × 10 ft | 824 | 6 | 2 × 26 ft | too small |
| 110422 | A | 1 | 1 × 10 ft | 824 | 6 | 2 × 26 ft | too small |
| 110438 | A | 1 | 1 × 10 ft | 902 | 7 | 2 × 26 ft | too small |
| 110750 | A | 1 | 1 × 10 ft | 824 | 6 | 2 × 26 ft | too small |
| 110908 | B | 1 | 1 × 10 ft | 650 | 5 | 2 × 26 ft | too small |
| 110958 | A | 1 | 1 × 10 ft | 851 | 6 | 2 × 26 ft | too small |
| 111353 | C | 1 | 1 × 10 ft | 424 | 3 | 1 × 20 ft | too small |
| 111600 | A | 1 | 1 × 10 ft | 841 | 4 | 2 × 26 ft | too small |
| 111600 | C | 1 | 1 × 10 ft | 421 | 3 | 1 × 26 ft | too small |
| 113646 | A | 1 | 1 × 10 ft | 811 | 4 | 1 × 26 ft | too small |
| 114124 | A | 1 | 1 × 10 ft | 811 | 4 | 1 × 26 ft | too small |
| 115436 | D | 1 | 1 × 10 ft | 142 | 2 | 1 × 15 ft | too small |
| 120009 | E | 2 | 1 × 15 ft | 252 | 1 | 1 × 15 ft | right |
| 120427 | F | 1 | 1 × 10 ft | 46 | 1 | 1 × 10 ft | right |
| 124056 | G | 1 | 1 × 10 ft | 58 | 1 | 1 × 10 ft | right |
| 130657 | H | 1 | 1 × 10 ft | 45 | 1 | 1 × 10 ft | right |
| 130913 | I | 1 | 1 × 10 ft | 251 | 2 | 1 × 15 ft | too small |
| 132950 | J | 1 | 1 × 10 ft | 551 | 3 | 1 × 26 ft | too small |
| 133201 | K | 2 | 1 × 15 ft | 864 | 3 | 2 × 26 ft | too small |
| 134559 | L | 1 | 1 × 10 ft | 15 | 1 | 1 × 10 ft | right |
| 134605 | M | 3 | 1 × 20 ft | 708 | 2 | 1 × 26 ft | too small |
| 140739 | N | 1 | 1 × 10 ft | 93 | 1 | 1 × 10 ft | right |
| 144333 | I | 1 | 1 × 10 ft | 444 | 4 | 1 × 26 ft | too small |
| 144416 | D | 1 | 1 × 10 ft | 85 | 1 | 1 × 10 ft | right |

Over the 24 moves the rule's truck was too small on 17, right on 7; one per set (14), too small on 7, right on 7. Most of these are venue rooms (a lounge, a workspace, a conference room), not bedrooms, so this shows that a room count says little about a load; it is not a test of the rule on homes.

## 4. Inventory against a count made in person

The venue lounge was counted in person by Chris (5 files of footage, 51 movable things; `eval/hand_counts/malin.json`). The count includes things that are in the room but hidden or out of frame, so 100% is not reachable from this footage. Each row is one run of the same footage; the prompt changed between runs. Scored by `eval/score_inventory.py`.

| Move | Found | Missed | Counted twice | Recall | Precision |
|---|---|---|---|---|---|
| 110218 | 38 of 51 | 13 | 4 | 74.5% | 90.5% |
| 110422 | 38 of 51 | 13 | 4 | 74.5% | 90.5% |
| 110438 | 38 of 51 | 13 | 7 | 74.5% | 84.4% |
| 110750 | 38 of 51 | 13 | 4 | 74.5% | 90.5% |
| 110958 | 38 of 51 | 13 | 5 | 74.5% | 88.4% |
| 111600 | 34 of 51 | 17 | 6 | 66.7% | 85.0% |
| 113646 | 36 of 51 | 15 | 4 | 70.6% | 90.0% |
| 114124 | 36 of 51 | 15 | 4 | 70.6% | 90.0% |

Recall 66.7% to 74.5%, precision 84.4% to 90.5% over 8 runs. One room only: this is a first reading, not a measured accuracy.

## 5. Decisions API answers, graded in person

The questions the pipeline raised about the venue lounge, answered by `gemini-decision-1` and graded by Chris against the room ([grading/malin_decisions_1109.md](grading/malin_decisions_1109.md)):

- Applied automatically (confidence >= 0.7): 4 of 4 correct
- Suggested only (confidence < 0.7): 2 of 5 correct as graded by Chris; 2 of 6 including one derived row

So the confidence separated the answers that could be applied from the ones a person should see. Nine graded answers, one room.

## What these tables do not show

- Homes. Most moves are venue rooms.
- Independent samples. Repeat runs of the same footage are separate rows in tables 1 and 3; the "one per set" lines count each set once.
- A neutral checker. The rules are ours and the stock packer was not built for them; the table shows what a packer without the rules does, not that it is a bad packer.
- A single-model-call baseline (one model asked for the whole plan with coordinates). Not built.
- Whether the sizes are right. Item sizes are model estimates or catalog values; nobody measured the furniture.
