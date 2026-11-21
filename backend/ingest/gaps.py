"""Stage 5: questions, plus the answer/edit store.

Answers and review-screen edits are stored in runs/<run_id>/answers.json and
re-applied to merged.json after every merge, so they survive re-runs. Only stage 4
(resolve) runs again after an answer.
"""
from __future__ import annotations

import datetime as dt

from .common import read_json, run_dir, write_json

EDITABLE = {"quantity", "disposition", "catalog_id", "label"}
DISPOSITIONS = {"keep", "sell", "donate", "trash", "undecided"}


def _find_item(merged: dict, item_id: str) -> tuple[dict, dict] | tuple[None, None]:
    for room in merged["rooms"]:
        for it in room["items"]:
            if it["id"] == item_id:
                return room, it
    return None, None


def _apply(merged: dict, ans: dict) -> str | None:
    """Apply one stored answer to merged.json in memory. Returns an error string or None."""
    kind = ans["kind"]
    if kind == "edit":
        room, it = _find_item(merged, ans["item_id"])
        if it is None:
            return f"no item {ans['item_id']}"
        for k, v in ans["changes"].items():
            it[k] = v
        it["edited"] = True
        return None
    patch = ans.get("patch") or {}
    op = patch.get("op")
    if op == "set_item":
        room, it = _find_item(merged, patch["item_id"])
        if it is None:
            return f"no item {patch['item_id']}"
        it.update(patch["changes"])
    elif op == "split_member":  # same_item answered "different": the other file's item is a separate piece
        room, it = _find_item(merged, patch["item_id"])
        if it is None:
            return f"no item {patch['item_id']}"
        m = patch["member"]
        new_id = f"{it['id']}_b{sum(1 for x in room['items'] if x['id'].startswith(it['id'] + '_b')) + 1}"
        room["items"].append({**it, "id": new_id, "label": m["label"], "quantity": m["quantity"],
                              "confidence": m["confidence"], "est_dims_in": m["est_dims_in"] or it["est_dims_in"],
                              "evidence": {"source": m["file"], "sha256": m["sha256"], "kind": m["kind"],
                                           "timestamp_s": m["evidence"].get("timestamp_s"),
                                           "box_2d": m["evidence"].get("box_2d")},
                              "also_seen_in": [], "per_file_counts": {m["file"]: m["quantity"]},
                              "members": [m], "variants": [m["label"]],
                              "notes": "split from " + it["id"] + " by a same_item answer"})
    elif op == "set_container":
        for room in merged["rooms"]:
            for c in room["containers"]:
                if c["label"] == patch["label"]:
                    c.update(patch["changes"])
    elif op == "include_personal":
        pass  # personal belongings stay out either way; recorded for the record
    elif op == "move_to_fixtures":
        room, it = _find_item(merged, patch["item_id"])
        if it is None:
            return f"no item {patch['item_id']}"
        room["items"].remove(it)
        room["fixtures"].append({"label": it["label"], "quantity": it["quantity"], "seen_in": [it["evidence"]["source"]]})
    elif op in (None, "none"):
        pass
    else:
        return f"unknown op {op}"
    return None


def reapply_answers(run_id: str) -> int:
    rd = run_dir(run_id)
    answers = read_json(rd / "answers.json", {"answers": []})["answers"]
    merged = read_json(rd / "merged.json")
    if not answers or merged is None:
        return 0
    applied = []
    for ans in answers:
        err = _apply(merged, ans)
        applied.append({"id": ans["id"], "kind": ans["kind"], "ok": err is None, **({"error": err} if err else {})})
    merged["answers_applied"] = applied
    write_json(rd / "merged.json", merged)
    return len(applied)


def store_answer(run_id: str, ans: dict) -> dict:
    rd = run_dir(run_id)
    data = read_json(rd / "answers.json", {"answers": []})
    ans = {"id": ans.get("id") or f"a{len(data['answers']) + 1:03d}",
           "at": dt.datetime.now().isoformat(timespec="seconds"), **ans}
    data["answers"].append(ans)
    write_json(rd / "answers.json", data)
    return ans


def edit_item(run_id: str, item_id: str, changes: dict) -> dict:
    bad = set(changes) - EDITABLE
    if bad:
        raise ValueError(f"cannot edit {sorted(bad)}; editable: {sorted(EDITABLE)}")
    if "disposition" in changes and changes["disposition"] not in DISPOSITIONS:
        raise ValueError(f"disposition must be one of {sorted(DISPOSITIONS)}")
    if "quantity" in changes and (not isinstance(changes["quantity"], int) or changes["quantity"] < 0):
        raise ValueError("quantity must be a non-negative integer")
    if changes.get("quantity") == 0:
        changes = {**changes, "quantity": 1, "disposition": "trash"}
    merged = read_json(run_dir(run_id) / "merged.json")
    if merged is None or _find_item(merged, item_id)[1] is None:
        raise KeyError(item_id)
    return store_answer(run_id, {"kind": "edit", "item_id": item_id, "changes": changes})


def build_questions(run_id: str) -> list[dict]:
    """Filled in at I6."""
    return []


def answer_question(run_id: str, question_id: str, answer, source: str = "user") -> dict:
    """Filled in at I6."""
    raise KeyError(question_id)
