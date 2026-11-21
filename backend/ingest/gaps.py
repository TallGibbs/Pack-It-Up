"""Stage 5: questions, plus the answer/edit store.

Answers and review-screen edits are stored in runs/<run_id>/answers.json and
re-applied to merged.json after every merge, so they survive re-runs. Only stage 4
(resolve) runs again after an answer.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend import catalog
from backend.llm import LLMError, Media, for_job
from backend.llm import media as mu

from .common import read_json, run_dir, write_json
from .merge import canon_key

EDITABLE = {"quantity", "disposition", "catalog_id", "label"}
DISPOSITIONS = {"keep", "sell", "donate", "trash", "stays", "undecided"}


def _find_item(merged: dict, item_id: str) -> tuple[dict, dict] | tuple[None, None]:
    for room in merged["rooms"]:
        for it in room["items"]:
            if it["id"] == item_id:
                return room, it
    return None, None


def _apply(merged: dict, ans: dict) -> str | None:
    """Apply one stored answer to merged.json in memory. Returns an error string or None."""
    kind = ans["kind"]
    if kind == "add_item":
        room = next((r for r in merged["rooms"] if r["id"] == ans["room_id"]), None)
        if room is None:
            return f"no room {ans['room_id']}"
        room["items"].append(_added_item(ans))
        return None
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


# ---------------------------------------------------------------- items the user adds

ADDED_MAX_IN = 240   # longest side accepted for a typed size (20 ft)
ADDED_MAX_QTY = 500


def add_item(run_id: str, body: dict) -> dict:
    """Review screen "Add an item": something the camera didn't see ("add a piano").

    body: {room, catalog_id, quantity, label?} for a catalog item, or {room, label, dims_in: [L, W, H],
    quantity} for one that isn't in the catalog. Stored as an answer, so it survives every rebuild();
    resolve gives it its size, weight and handling flags like any other item. Later quantity and
    disposition edits use the normal PATCH route with the item id returned here.
    Call with the run lock held: the item id counts the answers already stored."""
    rd = run_dir(run_id)
    merged = read_json(rd / "merged.json")
    room_id = body.get("room")
    if merged is None or not any(r["id"] == room_id for r in merged["rooms"]):
        raise KeyError(room_id)
    cid = str(body.get("catalog_id") or "unknown").strip()
    row = catalog.get(cid) if cid != "unknown" else None
    if cid != "unknown" and row is None:
        raise ValueError(f"no catalog item {cid!r}; GET /catalog lists them")
    qty = body.get("quantity", 1)
    if isinstance(qty, bool) or not isinstance(qty, int) or not 1 <= qty <= ADDED_MAX_QTY:
        raise ValueError(f"quantity must be a whole number from 1 to {ADDED_MAX_QTY}")
    label = " ".join(str(body.get("label") or (row or {}).get("name") or "").split())[:80]
    dims = None  # a catalog item takes the catalog's size
    if row is None:
        dims = body.get("dims_in")
        if not label:
            raise ValueError("an item that isn't in the catalog needs a label")
        if not (isinstance(dims, list) and len(dims) == 3
                and all(isinstance(d, (int, float)) and not isinstance(d, bool) and 0 < d <= ADDED_MAX_IN for d in dims)):
            raise ValueError(f"an item that isn't in the catalog needs dims_in: [length, width, height] in inches, "
                             f"each above 0 and at most {ADDED_MAX_IN}")
    answers = read_json(rd / "answers.json", {"answers": []})["answers"]
    n = sum(1 for a in answers if a.get("kind") == "add_item" and a.get("room_id") == room_id) + 1
    return store_answer(run_id, {"kind": "add_item", "room_id": room_id, "item_id": f"{room_id}_added_{n:02d}",
                                 "item": {"catalog_id": cid, "label": label, "quantity": qty, "dims_in": dims}})


def _added_item(ans: dict) -> dict:
    """The merged.json line for a user-added item, in the shape merge.py gives a seen one."""
    it = ans["item"]
    return {"id": ans["item_id"], "group_key": "added:" + canon_key(it["label"]), "label": it["label"],
            "catalog_id": it["catalog_id"], "quantity": it["quantity"], "stack_count": 1, "confidence": 1.0,
            "move_class": "movable", "material": "mixed", "est_dims_in": it.get("dims_in") or [], "est_weight_lb": 0,
            "fragile": False, "must_stay_upright": False, "disassemble": False, "two_person": False,
            "stackable": False, "partially_visible": False,
            "evidence": {"source": None, "sha256": None, "kind": "user", "timestamp_s": None, "box_2d": None},
            "also_seen_in": [], "per_file_counts": {}, "variants": [it["label"]], "members": [],
            "disposition": "keep", "notes": "added on the review screen", "user_added": True}


# ---------------------------------------------------------------- questions

AUTO_APPLY = 0.7       # Decisions API answers at or above this confidence are applied automatically
MAX_SHOWN = 5          # open questions shown to the user at once
MODEL_ONLY = {"same_item", "fixture_check"}  # never open cards for the user (Chris, 11:38)
CONTAINER_CUFT = {"small": 6, "medium": 15, "large": 30}
FULLNESS = ["empty", "quarter", "half", "three_quarters", "full"]


def _qid(*parts) -> str:
    return "q_" + hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:10]


def _crop_media(rd: Path, files_by_name: dict, source: str, box, t, tag: str) -> Media | None:
    """Write a JPEG crop for a question and return it as Media."""
    entry = files_by_name.get(source)
    if entry is None:
        return None
    jpg = mu.crop_jpeg(rd / entry["path"], entry["kind"], box, t, max_side=768)
    sha = hashlib.sha256(jpg).hexdigest()
    p = rd / "crops" / f"{sha[:16]}.jpg"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(jpg)
    return Media(p, "image", "image/jpeg", sha, caption=tag)


def _whole_media(rd: Path, files_by_name: dict, source: str, tag: str) -> Media | None:
    entry = files_by_name.get(source)
    if entry is None:
        return None
    return Media(rd / entry["path"], entry["kind"], entry["mime"], entry["sha256"], caption=tag)


def _dims(d) -> str:
    return " x ".join(f"{v:g}" for v in d) + " in"


def _candidates(rd: Path, inv: dict, merged: dict, files_by_name: dict) -> list[dict]:
    """Every question the current state raises, with the media and options to ask it."""
    qs: list[dict] = []
    for inv_room, m_room in zip(inv["rooms"], merged["rooms"]):
        items = {i["id"]: i for i in inv_room["items"]}
        fixture_nouns = {canon_key(f["label"]) for f in m_room["fixtures"]}

        for it in inv_room["items"]:
            if it["disposition"] in ("stays", "trash", "sell", "donate") or it.get("heard_only"):
                continue  # not going on the truck, or only heard (unfilmed_area covers it)
            if it.get("source") == "user_added":
                continue  # the user typed it in: nothing to check against footage
            s, ev = it["size"], it["evidence"]
            crop = lambda tag, it=it, ev=ev: _crop_media(rd, files_by_name, ev["source"], ev.get("box_2d"),
                                                          ev.get("timestamp_s"), tag)
            # size_check: model and catalog disagree
            if "size_check" in it:
                sc = it["size_check"]
                vol_c = sc["catalog_dims_in"][0] * sc["catalog_dims_in"][1] * sc["catalog_dims_in"][2] / 1728
                vol_v = s["vision_dims_in"][0] * s["vision_dims_in"][1] * s["vision_dims_in"][2] / 1728
                qs.append({"id": _qid("size_check", it["id"]), "kind": "size_check", "refers_to": it["id"],
                           "text": f"Which size is closer for the {it['label']}: A) {_dims(sc['catalog_dims_in'])} "
                                   f"(catalog) or B) {_dims(sc['vision_dims_in'])} (measured from the footage)?",
                           "options": {"catalog": f"A: {_dims(sc['catalog_dims_in'])}",
                                       "vision": f"B: {_dims(sc['vision_dims_in'])}"},
                           "ask": "decisions_api", "volume_at_stake": abs(vol_v - vol_c) * it["quantity"],
                           "confidence": it["confidence"], "media": [crop(f"Photo of the {it['label']}")]})
            # identify_item: unknown and low confidence
            if it["catalog_id"] == "unknown" and it["confidence"] < 0.6:
                qs.append({"id": _qid("identify_item", it["id"]), "kind": "identify_item", "refers_to": it["id"],
                           "text": f"What is this? We saw \"{it['label']}\" but aren't sure.",
                           "options": None, "free_text": True, "ask": "user",
                           "volume_at_stake": s["volume_cuft_total"], "confidence": it["confidence"], "media": [crop("")]})
            # count_check: partly visible or many of them
            if it["partially_visible"] or it["quantity"] > 4:
                q = it["quantity"]
                # Not capped at what the files showed: hidden or occupied pieces push the true count up
                # (Malin: 16 work chairs, footage showed at most 10). Add 1.5x and 2x, plus "more" and typed numbers.
                counts = sorted({max(1, q - 1), q, q + 1, q + 2, round(q * 1.5), q * 2,
                                 *it.get("per_file_counts", {}).values()})
                options = {str(c): f"{c}" for c in counts}
                options["more"] = f"more than {counts[-1]}"
                srcs = sorted(it.get("per_file_counts", {}), key=lambda f: -it["per_file_counts"][f])[:2]
                media = [_whole_media(rd, files_by_name, f, f"[{f}]") for f in srcs]
                qs.append({"id": _qid("count_check", it["id"]), "kind": "count_check", "refers_to": it["id"],
                           "text": f"How many {it['label']} are there in this room in total? Count each physical one "
                                   f"once even if it appears in several photos or twice in the video; ignore reflections. "
                                   f"Some may be hidden behind people, bags or other furniture, or cut off at the edge.",
                           "options": options, "free_text": "number", "ask": "decisions_api",
                           "volume_at_stake": s["volume_cuft_each"] * max(1, q * 0.25),
                           "confidence": it["confidence"], "media": media})
            # fixture_check (added to the spec's list): a "movable" item that another file called a fixture
            noun = canon_key(it["label"])
            if noun in fixture_nouns or (it["catalog_id"].startswith("bookshelf") and "shelving_unit" in fixture_nouns):
                qs.append({"id": _qid("fixture_check", it["id"]), "kind": "fixture_check", "refers_to": it["id"],
                           "text": f"Is the {it['label']} built into the wall or floor, or is it a free-standing "
                                   f"piece of furniture that movers would carry out?",
                           "options": {"built_in": "attached to the building; it stays",
                                       "free_standing": "free-standing furniture; it moves"},
                           "ask": "decisions_api", "volume_at_stake": s["volume_cuft_total"],
                           "confidence": it["confidence"], "media": [crop(f"Photo of the {it['label']}")]})

        # unfilmed_area: only heard, never seen -> the user confirms, with the quote
        for it in inv_room["items"]:
            if not it.get("heard_only"):
                continue
            quote = next((r["quote"] for r in it.get("set_by_speech", []) if r["field"] == "heard_only"),
                         next((r["quote"] for r in it.get("set_by_speech", [])), ""))
            qs.append({"id": _qid("unfilmed_area", it["id"]), "kind": "unfilmed_area", "refers_to": it["id"],
                       "text": f"You said \"{quote}\" but it isn't in the footage. Should the {it['label']} go on "
                               f"the truck? (A photo or clip of it would give us its real size.)",
                       "quote": quote, "options": {"yes": "yes, it's moving", "no": "no, leave it out"}, "ask": "user",
                       "volume_at_stake": it["size"]["volume_cuft_total"], "confidence": 0.5, "media": []})

        # same_item: merge flagged differing labels across files
        for f in m_room.get("merge_flags", []):
            base, b = f["base"], f["b"]
            it = items.get(f["item_id"])
            if it is None:
                continue
            media = [_crop_media(rd, files_by_name, a["file"], a["evidence"].get("box_2d"),
                                 a["evidence"].get("timestamp_s"), f"Already counted, piece {i + 1}: {a['label']} (from {a['file']})")
                     for i, a in enumerate(base[:8])]
            media.append(_crop_media(rd, files_by_name, b["file"], b["evidence"].get("box_2d"),
                                     b["evidence"].get("timestamp_s"), f"New sighting: {b['label']} (from {b['file']})"))
            counted = "; ".join(f"{i + 1}) {a['label']}" for i, a in enumerate(base[:8]))
            qs.append({"id": _qid("same_item", f["item_id"], b["file"], b["label"]),
                       "kind": "same_item", "refers_to": f["item_id"],
                       "text": f"The last image is a new sighting ({b['label']}, from {b['file']}). The images before it "
                               f"are the pieces already counted in this room: {counted}. Is the new sighting one of the "
                               f"pieces already counted (the same physical piece seen again from another angle or in other "
                               f"light), or a different piece?",
                       "options": {"same": "one of the pieces already counted",
                                   "different": "a different piece, not yet counted"},
                       "ask": "decisions_api", "member": b,
                       "volume_at_stake": it["size"]["volume_cuft_each"] * b["quantity"],
                       "confidence": b["confidence"], "media": media})

        # hidden_contents: closed cabinets. Footage can't see inside, so the Decisions API isn't asked
        # (Chris, Nov 21): resolve assumes empty, and the user is always asked.
        for c in m_room["containers"]:
            if c["fullness"] != "not_visible":
                continue
            src = c["seen_in"][0]
            ev = c.get("evidence") or {}
            qs.append({"id": _qid("hidden_contents", inv_room["room"]["id"], c["label"]), "kind": "hidden_contents",
                       "refers_to": c["label"], "always_show": True,
                       "text": f"We couldn't see inside the {c['label']}, so we've assumed it's empty. About how full is it?",
                       "options": {f: f.replace("_", " ") for f in FULLNESS}, "ask": "user",
                       "volume_at_stake": CONTAINER_CUFT.get(c["size"], 15), "confidence": 0.3,
                       "media": [_crop_media(rd, files_by_name, src, ev.get("box_2d"), ev.get("timestamp_s"), "")]})

        # include_class: personal belongings, once per room
        pb = inv_room["left_out"]
        if pb["personal_belongings"]:
            kinds = ", ".join(f"{k}s" for k in pb["personal_belonging_kinds"])
            qs.append({"id": _qid("include_class", inv_room["room"]["id"]), "kind": "include_class",
                       "refers_to": inv_room["room"]["id"],
                       "text": f"We left out {pb['personal_belongings']} personal belongings ({kinds}). Leave them out?",
                       "options": {"yes": "leave them out", "no": "they are part of the move"}, "ask": "user",
                       "volume_at_stake": 1.0, "confidence": 0.5, "media": []})
    # Speech first: a question the narrator already answered is shown as answered, with the quote.
    said = {}
    for room in inv["rooms"]:
        for it in room["items"]:
            said[it["id"]] = it.get("set_by_speech", [])
        for c in room["containers"]:
            said[c["label"]] = c.get("set_by_speech", [])
    for q in qs:
        q["media"] = [m for m in q["media"] if m is not None]
        q["rank_score"] = round(q["volume_at_stake"] * (1 - q["confidence"]), 2)
        fields = SPEECH_ANSWERS.get(q["kind"])
        if fields:
            rec = next((r for r in said.get(q["refers_to"], []) if r["field"].split(".")[0] in fields), None)
            if rec:
                q["speech"] = rec
    return qs


# Which spoken fields settle which question kinds.
SPEECH_ANSWERS = {"count_check": {"quantity"}, "size_check": {"size"}, "identify_item": {"label", "catalog_id"},
                  "fixture_check": {"disposition"}, "hidden_contents": {"contents", "fullness"}}


def _patch_for(q: dict, answer: str) -> dict:
    kind = q["kind"]
    if kind == "size_check":
        return {"op": "set_item", "item_id": q["refers_to"], "changes": {"size_choice": answer}}
    if kind == "count_check":
        return {"op": "set_item", "item_id": q["refers_to"], "changes": {"quantity": int(answer)}}
    if kind == "same_item":
        return {"op": "split_member", "item_id": q["refers_to"], "member": q["member"]} if answer == "different" else {"op": "none"}
    if kind == "unfilmed_area":
        return {"op": "set_item", "item_id": q["refers_to"],
                "changes": {"disposition": "removed"} if answer == "no" else {"confidence": 1.0}}
    if kind == "fixture_check":
        return {"op": "move_to_fixtures", "item_id": q["refers_to"]} if answer == "built_in" else {"op": "none"}
    if kind == "hidden_contents":
        return {"op": "set_container", "label": q["refers_to"], "changes": {"fullness": answer}}
    if kind == "identify_item":
        if catalog.get(answer.strip()):
            return {"op": "set_item", "item_id": q["refers_to"], "changes": {"catalog_id": answer.strip()}}
        return {"op": "set_item", "item_id": q["refers_to"], "changes": {"label": answer.strip()[:80], "confidence": 0.9}}
    return {"op": "none"}


def _public(q: dict) -> dict:
    """What questions.json / the API shows: no Media objects or member blobs."""
    out = {k: v for k, v in q.items() if k not in ("media", "member")}
    out["crops"] = [str(m.path.name) for m in q.get("media", []) if m.kind == "image" and m.path.parent.name == "crops"]
    return out


def build_questions(run_id: str) -> list[dict]:
    """Raise questions, let the Decisions API answer what it can, rank the rest for the user."""
    rd = run_dir(run_id)
    inv, merged = read_json(rd / "inventory.json"), read_json(rd / "merged.json")
    manifest = read_json(rd / "manifest.json")
    files_by_name = {f["name"]: f for f in manifest["files"]}
    answered = {a.get("question_id"): a for a in read_json(rd / "answers.json", {"answers": []})["answers"]}
    old = {q["id"]: q for q in read_json(rd / "questions.json", {"questions": []})["questions"]}
    qs = _candidates(rd, inv, merged, files_by_name)

    to_ask = [q for q in qs if q["id"] not in answered and "speech" not in q
              and q["ask"].startswith("decisions_api") and q["media"]]
    job = for_job("decide", run_dir=rd)

    def ask(q):
        try:
            return q["id"], job.decide(q["text"], media=q["media"], options=list(q["options"]),
                                       criteria=q["options"], label=f"{q['kind']}:{q['refers_to']}")
        except LLMError as e:
            return q["id"], {"error": str(e)[:200]}

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = dict(pool.map(ask, to_ask))

    for q in qs:
        if q["id"] in answered:
            a = answered[q["id"]]
            q.update(status="answered", answer=a["answer"], answered_by=a["source"], confidence=a.get("confidence", 1.0))
            # Every upload rebuilds every question. Keep what the Decisions API said the first time, or a
            # second room wipes the first room's model answers and confidences (FAILURES.md 13:10).
            for k in ("model_answer", "low_confidence", "suggested"):
                if k in old.get(q["id"], {}):
                    q[k] = old[q["id"]][k]
            continue
        if "speech" in q:  # already applied in merge; nothing to store
            s = q.pop("speech")
            q.update(status="answered", answer=str(s["value"]), answered_by="speech", quote=s["quote"],
                     quote_source=s["source"], quote_timestamp_s=s.get("timestamp_s"))
            continue
        r = results.get(q["id"])
        if r and "answer" in r:
            q["model_answer"] = {k: r[k] for k in ("answer", "confidence", "rationale", "via")}
            # Model-only questions (Chris, 11:38): their text is written for the model and refers to images the
            # user can't see, so the best guess is always applied and shown as answered with a Change link.
            model_only = q["kind"] in MODEL_ONLY
            if (r["confidence"] >= AUTO_APPLY or model_only) and r["answer"] != "more":  # "more" needs a number
                store_answer(run_id, {"kind": q["kind"], "question_id": q["id"], "answer": r["answer"],
                                      "source": r["via"], "confidence": r["confidence"],
                                      "patch": _patch_for(q, r["answer"])})
                q.update(status="answered", answer=r["answer"], answered_by=r["via"],
                         low_confidence=r["confidence"] < AUTO_APPLY)
                continue
            q["suggested"] = r["answer"]
        elif r and "error" in r:
            q["model_error"] = r["error"]
        q["status"] = "open"

    # Questions marked always_show (closed containers) are shown on top of the MAX_SHOWN ranked ones.
    open_qs = sorted((q for q in qs if q["status"] == "open" and not q.get("always_show")), key=lambda q: -q["rank_score"])
    for i, q in enumerate(open_qs):
        q["shown"] = i < MAX_SHOWN
    for q in qs:
        if q["status"] == "open" and q.get("always_show"):
            q["shown"] = True
    for q in qs:  # keep any earlier question that no longer triggers but was answered
        old.pop(q["id"], None)
    kept = [q for q in old.values() if q.get("status") == "answered"]
    pub = [_public(q) for q in qs] + kept
    pub.sort(key=lambda q: (q["status"] != "open", not q.get("shown", False), -q.get("rank_score", 0)))
    write_json(rd / "questions.json", {"run_id": run_id, "questions": pub,
                                       "decisions_calls": len(to_ask),
                                       "auto_applied": sum(1 for q in qs if q.get("answered_by") in ("decisions_api", "generate_json_fallback"))})
    return pub


def answer_question(run_id: str, question_id: str, answer, source: str = "user") -> dict:
    rd = run_dir(run_id)
    data = read_json(rd / "questions.json", {"questions": []})
    q = next((x for x in data["questions"] if x["id"] == question_id), None)
    if q is None:
        raise KeyError(question_id)
    answer = str(answer).strip()
    if q.get("free_text") == "number" and answer not in (q.get("options") or {}):
        if not answer.isdigit() or not 0 < int(answer) <= 500:
            raise ValueError(f"answer must be one of {list(q['options'])} or a whole number from 1 to 500")
    elif q.get("options") and answer not in q["options"]:
        raise ValueError(f"answer must be one of {list(q['options'])}")
    if answer == "more":
        raise ValueError("type the number instead of 'more'")
    if not answer:
        raise ValueError("empty answer")
    full = q
    if q["kind"] == "same_item":  # the member blob isn't in questions.json; rebuild it
        merged = read_json(rd / "merged.json")
        manifest = read_json(rd / "manifest.json")
        inv = read_json(rd / "inventory.json")
        full = next((c for c in _candidates(rd, inv, merged, {f["name"]: f for f in manifest["files"]})
                     if c["id"] == question_id), q)
    ans = store_answer(run_id, {"kind": q["kind"], "question_id": question_id, "answer": answer, "source": source,
                                "confidence": 1.0, "patch": _patch_for(full, answer)})
    q.update(status="answered", answer=answer, answered_by=source)
    q.pop("shown", None)
    write_json(rd / "questions.json", data)
    return ans
