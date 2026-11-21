"""Runs the stages in order. Shared by the CLI and the HTTP API.

After each file is perceived, merge and resolve run again (they make no model call),
so inventory.json fills in progressively and a slow clip never blanks the screen.
"""
from __future__ import annotations

import threading
from collections import defaultdict

from .common import run_dir, update_status
from .merge import merge
from .perceive import perceive_all
from .resolve import resolve

_run_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


def run_lock(run_id: str) -> threading.Lock:
    return _run_locks[run_id]


def rebuild(run_id: str, questions: bool = False) -> dict:
    """Merge -> re-apply answers -> (questions) -> resolve. No perceive calls."""
    from . import gaps  # late import: gaps imports resolve

    with run_lock(run_id):
        merge(run_id)
        gaps.reapply_answers(run_id)
        inv = resolve(run_id)
        if questions:
            gaps.build_questions(run_id)  # may store auto-applied Decisions API answers
            merge(run_id)                 # so rebuild from scratch and apply them once
            gaps.reapply_answers(run_id)
            inv = resolve(run_id)
        return inv


def run_pipeline(run_id: str, room_id: str | None = None, questions: bool = True) -> dict:
    rd = run_dir(run_id)
    try:
        perceive_all(run_id, room_id, on_file_done=lambda _r: rebuild(run_id))
        update_status(rd, stage="questions" if questions else "resolve")
        inv = rebuild(run_id, questions=questions)
        update_status(rd, stage="done")
        return inv
    except Exception as e:
        update_status(rd, stage="failed", error=f"pipeline: {type(e).__name__}: {e}")
        raise
