"""Runs the stages in order. Shared by the CLI and the HTTP API.

After each file is perceived, merge and resolve run again (they make no model call),
so inventory.json fills in progressively and a slow clip never blanks the screen.
"""
from __future__ import annotations

import threading
from collections import defaultdict

from .common import read_json, run_dir, update_status
from .merge import merge
from .perceive import perceive_all
from .resolve import resolve

# Re-entrant, so a route can hold it across "store the edit" and rebuild().
_run_locks: dict[str, threading.RLock] = defaultdict(threading.RLock)

# Every upload starts its own pipeline thread, so one run can have several at once (room 2
# uploaded while room 1 is still being perceived). The run is "done" only when the last one ends.
_active: dict[str, int] = defaultdict(int)
_active_guard = threading.Lock()


def run_lock(run_id: str) -> threading.RLock:
    return _run_locks[run_id]


def begin_pipeline(run_id: str) -> None:
    """Count a pipeline as running. Call before intake, so a pipeline that finishes while the
    new files are still being hashed can't mark the run done."""
    with _active_guard:
        _active[run_id] += 1


def end_pipeline(run_id: str) -> bool:
    """Count a pipeline as finished. True when it was the last one on the run."""
    with _active_guard:
        _active[run_id] = max(0, _active[run_id] - 1)
        return _active[run_id] == 0


def rebuild(run_id: str, questions: bool = False) -> dict:
    """Merge -> re-apply answers -> (questions) -> resolve. No perceive calls."""
    from . import gaps  # late import: gaps imports resolve

    with run_lock(run_id):
        rd = run_dir(run_id)
        was_done = (read_json(rd / "status.json", {}) or {}).get("stage") == "done"
        merge(run_id)
        gaps.reapply_answers(run_id)
        inv = resolve(run_id)
        if questions:
            gaps.build_questions(run_id)  # may store auto-applied Decisions API answers
            merge(run_id)                 # so rebuild from scratch and apply them once
            gaps.reapply_answers(run_id)
            inv = resolve(run_id)
        # merge and resolve stamp their own stage. A review edit (answer, quantity, added item) on a
        # finished run must leave it "done", or the pages read it as still processing and poll forever.
        if was_done:
            with _active_guard:
                idle = _active[run_id] == 0
            if idle:
                update_status(rd, stage="done")
        return inv


def run_pipeline(run_id: str, room_id: str | None = None, questions: bool = True, counted: bool = False) -> dict:
    """Perceive, merge, ask, resolve. `counted` means the caller already called begin_pipeline()."""
    rd = run_dir(run_id)
    if not counted:
        begin_pipeline(run_id)
    try:
        # counted = started by an upload: read only the files this upload added (see perceive_all)
        perceive_all(run_id, room_id, on_file_done=lambda _r: rebuild(run_id), only_new=counted)
        update_status(rd, stage="questions" if questions else "resolve")
        inv = rebuild(run_id, questions=questions)
    except Exception as e:
        # With another pipeline still working, the run isn't over: record the error and let it finish.
        last = end_pipeline(run_id)
        update_status(rd, stage="failed" if last else "perceive", error=f"pipeline: {type(e).__name__}: {e}")
        raise
    update_status(rd, stage="done" if end_pipeline(run_id) else "perceive")
    return inv
