# eval

Results, scoring scripts and the counts they are scored against.

| File | What it is |
|---|---|
| [RESULTS.md](RESULTS.md) | The results tables. Built by `results_table.py`; don't edit by hand |
| `results_table.py` | Packs every move in `runs/` with the stock `py3dbp` packer and with our solver, scores both with `backend/verify.py`, and writes `RESULTS.md`. `--neon` first runs the Neon planner loop on one move per set of footage (model calls) and saves the rounds in `neon_rounds.json` |
| `neon_rounds.json` | The planner's rounds from the last `--neon` run |
| `score_inventory.py` | Scores a run's `inventory.json` against a hand count: found, missed, counted twice |
| `hand_counts/malin.json` | The venue lounge, counted in person |
| `grading/malin_decisions_1109.md` | Decisions API answers for the venue lounge, graded in person |

`runs/` is not in git, so `RESULTS.md` can only be rebuilt on the laptop that holds the moves.
