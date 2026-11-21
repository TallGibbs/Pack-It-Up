"""Print which model did which job. Usage:

    python -m backend.analysis              # totals across every run
    python -m backend.analysis <run_id>     # one run
"""
from __future__ import annotations

import sys

from . import store


def _jobs_table(jobs: list[dict]) -> str:
    head = "| Job | Role | Model | Calls | Live | Cached | Avg s (live) | Tokens in | Tokens out |\n|---|---|---|---|---|---|---|---|---|"
    rows = [f"| {j['job']} | {j['role']} | {j['model']} | {j['calls']} | {j['live_calls']} | {j['cached']} | "
            f"{j['avg_latency_s'] if j['avg_latency_s'] is not None else '–'} | {j['tokens_in']} | {j['tokens_out']} |"
            for j in jobs]
    return "\n".join([head, *rows])


def _decisions(d: dict) -> str:
    agree = f"{d['agreement']:.0%}" if d["agreement"] is not None else "no user checks yet"
    return (f"Questions: {d['questions']} ({d['by_decisions_api']} by the Decisions API, {d['by_fallback']} by the fallback); "
            f"{d['applied_automatically']} applied automatically, {d['answered_by_user']} answered by the user, "
            f"{d['open']} open. Mean confidence {d['mean_confidence']}. "
            f"User agreed with the model's answer: {agree} ({d['user_checked']} checked, {d['user_changed']} changed).")


def main(argv: list[str]) -> int:
    if argv:
        s = store.run_summary(argv[0])
        if s is None:
            print(f"no run {argv[0]}")
            return 1
        r = s["run"]
        print(f"Run {r['run_id']} ({r['rooms']}): {r['n_files']} files, {r['items']} items, stage {r['stage']}\n")
        print(_jobs_table(s["jobs"]))
        print("\n" + _decisions(s["decision_stats"]))
        print(f"\nCalls span {s['timeline']['span_s']} s from first to last.")
    else:
        s = store.overall()
        print(f"{s['runs']} runs\n")
        print(_jobs_table(s["jobs"]))
        print("\n" + _decisions(s["decision_stats"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
