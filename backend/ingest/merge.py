"""Stage 3: merge. No model call.

Within one room the same item usually shows up in several photos and the clip.
1. Group movable items by catalog_id (or by a canonical noun from the label when unknown).
2. Across different files a group is presumed to be the same set: quantity = the largest
   count seen in any single file, not the sum.
3. Within one file the model already deduplicated, so quantities add.
4. When an entry in another file has colour/material words that match nothing in the
   best file, flag a `same_item` question; stage 5 asks the Decisions API.
5. Containers merge by kind and contents; a known fullness beats not_visible.

Writes runs/<run_id>/merged.json.
"""
from __future__ import annotations

import re
import statistics
from collections import defaultdict

from backend import catalog

from .common import read_json, run_dir, update_status, write_json
from .perceive import parse_ref
from .schemas import DISPOSITIONS

# Canonical nouns for unknown items, so "leather pouf" and "round ottoman" land in one group.
CANON = [
    ("ottoman", ["ottoman", "pouf", "pouffe", "footstool"]),
    ("sideboard", ["sideboard", "credenza", "buffet", "media console"]),
    ("console_table", ["console"]),
    ("counter_table", ["counter", "bar table", "high table", "pub table"]),
    ("framed_art", ["artwork", "art", "painting", "canvas", "print", "picture", "photograph", "poster"]),
    ("potted_plant", ["plant", "tree", "planter"]),
    ("table_lamp", ["table lamp", "desk lamp"]),
    ("floor_lamp", ["floor lamp"]),
    ("shelving_unit", ["etagere", "étagère", "shelving", "shelf unit", "shelves", "bookcase"]),
    ("trash_bin", ["trash", "bin", "waste", "garbage"]),
    ("rug", ["rug", "carpet"]),
    ("mirror", ["mirror"]),
    ("bench", ["bench"]),
    ("stool", ["stool"]),
    ("armchair", ["armchair", "accent chair", "lounge chair", "club chair", "barrel chair"]),
    ("chair", ["chair"]),
    ("table", ["table", "desk"]),
    ("espresso_machine", ["espresso", "coffee machine", "grinder"]),
    ("tv", ["television", "tv"]),
]

COLOUR_FAMILIES = {
    "white": ["white", "cream", "ivory", "off-white", "beige", "boucle", "bouclé", "natural", "oatmeal", "linen"],
    "black": ["black", "charcoal", "ebony"],
    "grey": ["grey", "gray", "silver", "slate"],
    "brown": ["brown", "walnut", "chocolate", "espresso", "tan", "camel", "leather", "mahogany", "dark wood"],
    "light_wood": ["oak", "light wood", "pine", "birch", "blonde", "ash", "natural wood"],
    "orange": ["orange", "rust", "terracotta", "burnt", "copper", "amber"],
    "red": ["red", "burgundy", "maroon", "wine", "oxblood"],
    "yellow": ["yellow", "mustard", "gold", "ochre"],
    "green": ["green", "olive", "sage", "moss", "emerald", "onyx"],
    "blue": ["blue", "navy", "teal", "indigo"],
    "pink": ["pink", "blush", "rose"],
}


def head_phrase(label: str) -> str:
    """The noun phrase before any parenthesis, dash, comma or trailing 'with ...' clause."""
    low = label.lower()
    low = re.split(r"\(|\s-\s|,|;|\bwith\b|\bon\b|\bnear\b|\bunder\b", low)[0]
    return low.strip() or label.lower()


def canon_key(label: str) -> str:
    """Canonical noun: of all CANON words found, the one ending last (the head noun) wins."""
    low = head_phrase(label)
    best = None  # (end position, length, key)
    for key, words in CANON:
        for w in words:
            for mt in re.finditer(rf"\b{re.escape(w)}", low):
                cand = (mt.end(), len(w), key)
                if best is None or cand > best:
                    best = cand
    if best:
        return best[2]
    words = re.findall(r"[a-z]+", low)
    return words[-1] if words else "item"


def group_key(it: dict) -> str:
    return it["catalog_id"] if it["catalog_id"] != "unknown" else f"unknown:{canon_key(it['label'])}"


def colours(label: str) -> set[str]:
    low = label.lower()
    return {fam for fam, ws in COLOUR_FAMILIES.items() if any(re.search(rf"\b{re.escape(w)}", low) for w in ws)}


def compatible(a: str, b: str) -> bool:
    ca, cb = colours(a), colours(b)
    return not ca or not cb or bool(ca & cb)


def evidence_ref(m: dict) -> str:
    t = m["evidence"].get("timestamp_s")
    return f"{m['file']}@{t:g}" if t is not None else m["file"]


def _member(p: dict, it: dict) -> dict:
    return {"file": p["file"], "sha256": p["sha256"], "kind": p["kind"], "label": it["label"],
            "quantity": it["quantity"], "confidence": it["confidence"], "evidence": it["evidence"],
            "est_dims_in": it["est_dims_in"], "partially_visible": it["partially_visible"]}


def _median_dims(members: list[dict]) -> list[float]:
    dims = [m["est_dims_in"] for m in members if m.get("est_dims_in") and len(m["est_dims_in"]) == 3]
    if not dims:
        return []
    return [round(statistics.median(d[i] for d in dims), 1) for i in range(3)]


def merge_room(perceptions: list[dict], room: dict) -> dict:
    rid = room["id"]
    groups: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    fixtures: dict[str, dict] = {}
    personal: dict[str, int] = defaultdict(int)
    personal_per_file: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    small: dict[str, dict] = {}
    containers: dict[tuple, dict] = {}
    uncertain: list[dict] = []

    loose_facts: list[dict] = []  # facts that point at a non-movable item or at nothing
    for p in perceptions:
        for q in p.get("uncertain", []):
            uncertain.append({"file": p["file"], "text": q})
        # Rule 6: each spoken fact follows the item or container it refers to.
        for f in p.get("spoken_facts", []):
            f = {**f, "source": p["file"]}
            ref = parse_ref(f.get("refers_to"))
            if ref and ref[0] == "item":
                p["items"][ref[1]].setdefault("_facts", []).append(f)
            elif ref and ref[0] == "container":
                p["containers"][ref[1]].setdefault("_facts", []).append(f)
            else:
                loose_facts.append(f)
        for it in p["items"]:
            mc = it["move_class"]
            if it.get("heard_only"):  # rule 7: kept as its own line, never folded into a seen item
                groups["heard:" + canon_key(it["label"])].append((p, it))
            elif mc == "movable":
                groups[group_key(it)].append((p, it))
            elif mc == "fixture":
                k = canon_key(it["label"]) + ":" + it["label"].lower()
                f = fixtures.setdefault(k, {"label": it["label"], "quantity": 0, "seen_in": []})
                f["quantity"] = max(f["quantity"], it["quantity"])
                f["seen_in"].append(p["file"])
                # A fixture can still hold things ("the built-in shelf is full of books").
                loose_facts += [{**x, "_item_label": it["label"]} for x in it.get("_facts", [])]
            elif mc == "personal_belonging":
                loose_facts += [{**x, "_item_label": it["label"]} for x in it.get("_facts", [])]
                personal_per_file[p["file"]][canon_key(it["label"])] += it["quantity"]
            else:  # small_loose
                k = it["label"].lower()
                s = small.setdefault(k, {"label": it["label"], "quantity": 0, "seen_in": [],
                                         "est_dims_in": it["est_dims_in"], "material": it["material"],
                                         "fragile": it["fragile"]})
                s["quantity"] = max(s["quantity"], it["quantity"])
                s["seen_in"].append(p["file"])
                loose_facts += [{**x, "_item_label": it["label"]} for x in it.get("_facts", [])]
        for c in p.get("containers", []):
            k = (c["kind"], c["contents"], canon_key(c["label"]) if c["kind"] != "open_surfaces" else "")
            cur = containers.get(k)
            if cur is None:
                containers[k] = {**c, "seen_in": [p["file"]], "_facts": list(c.get("_facts", []))}
            else:
                cur["seen_in"].append(p["file"])
                cur["_facts"] += c.get("_facts", [])
                if cur["fullness"] == "not_visible" and c["fullness"] != "not_visible":
                    cur["fullness"] = c["fullness"]
                cur["est_item_count"] = max(cur.get("est_item_count", 0), c.get("est_item_count", 0))
                if ["small", "medium", "large"].index(c["size"]) > ["small", "medium", "large"].index(cur["size"]):
                    cur["size"] = c["size"]

    # Personal belongings: same "largest single-file count" rule per kind.
    for f, kinds in personal_per_file.items():
        for k, n in kinds.items():
            personal[k] = max(personal[k], n)

    items, flags = [], []
    for gk, entries in sorted(groups.items(), key=lambda kv: kv[0]):
        by_file: dict[str, list[dict]] = defaultdict(list)
        for p, it in entries:
            by_file[p["file"]].append(_member(p, it))
        counts = {f: sum(m["quantity"] for m in ms) for f, ms in by_file.items()}
        # The best file has the largest count; ties go to the most confident.
        best_file = max(by_file, key=lambda f: (counts[f], max(m["confidence"] for m in by_file[f])))
        base = by_file[best_file]
        members = [m for ms in by_file.values() for m in ms]
        best = max(members, key=lambda m: (not m["partially_visible"], m["confidence"]))
        first = next(it for p, it in entries if p["file"] == best["file"] and it["label"] == best["label"])
        item_id = f"{rid}_item_{len(items) + 1:02d}"
        labels = sorted({m["label"] for m in base}, key=str.lower)
        item = {
            "id": item_id,
            "group_key": gk,
            "label": best["label"] if len(base) == 1 else _group_label(gk, base),
            "catalog_id": first["catalog_id"],
            "quantity": max(counts.values()),
            "stack_count": max(it.get("stack_count", 1) for _, it in entries),
            "confidence": round(max(m["confidence"] for m in members), 2),
            "move_class": "movable",
            "material": first["material"],
            "est_dims_in": _median_dims(members),
            "est_weight_lb": round(statistics.median(it["est_weight_lb"] for _, it in entries), 1),
            "fragile": any(it["fragile"] for _, it in entries),
            "must_stay_upright": any(it["must_stay_upright"] for _, it in entries),
            "disassemble": any(it["disassemble"] for _, it in entries),
            "two_person": any(it["two_person"] for _, it in entries),
            "stackable": all(it["stackable"] for _, it in entries),
            "partially_visible": all(m["partially_visible"] for m in members),
            "evidence": {"source": best["file"], "sha256": best["sha256"], "kind": best["kind"],
                         "timestamp_s": best["evidence"].get("timestamp_s"), "box_2d": best["evidence"].get("box_2d")},
            "also_seen_in": sorted({evidence_ref(m) for m in members} - {evidence_ref(best)}),
            "per_file_counts": counts,
            "variants": labels,
            "members": members,
            "disposition": "undecided",
            "notes": "",
            "heard_only": gk.startswith("heard:"),
            "set_by_speech": [],
        }
        if item["heard_only"]:
            item["partially_visible"] = False
            item["evidence"]["box_2d"] = None  # nothing to crop: it was only heard
        items.append(item)
        for _, it in entries:
            for f in it.get("_facts", []):
                if f["kind"] == "contents":
                    loose_facts.append({**f, "_item_label": item["label"]})
                else:
                    apply_item_fact(item, f)
        # Rule 4: entries in other files whose colours match nothing in the best file.
        for f, ms in by_file.items():
            if f == best_file:
                continue
            for m in ms:
                if not any(compatible(m["label"], b["label"]) for b in base):
                    # Ask whether m is any of the pieces already counted (all of `base`), not just one of them.
                    flags.append({"kind": "same_item", "item_id": item_id, "base": base, "b": m})

    # Contents facts set a container (created for the item if the model listed none); facts that point at
    # nothing but name an unfilmed item become a heard-only line.
    cont_list = list(containers.values())
    for c in cont_list:
        for f in c.pop("_facts", []):
            apply_container_fact(c, f)
        c.setdefault("set_by_speech", [])
    for f in loose_facts:
        if f["kind"] == "contents" and f.get("_item_label"):
            noun = canon_key(f["_item_label"])
            c = next((c for c in cont_list if canon_key(c["label"]) == noun), None)
            if c is None:
                shelfy = noun in ("shelving_unit", "bookshelf") or "shel" in f["_item_label"].lower()
                c = {"label": f["_item_label"], "kind": "bookshelf" if shelfy else "other", "contents": "mixed",
                     "fullness": "not_visible", "size": "medium", "est_item_count": 0, "seen_in": [f["source"]],
                     "evidence": None, "set_by_speech": [], "created_by_speech": True}
                cont_list.append(c)
            apply_container_fact(c, f)
        elif f["kind"] == "unfilmed_item" and not any(i["heard_only"] for i in items):
            label = (f.get("label") or f.get("value") or "item mentioned").strip()
            items.append(_heard_item(rid, len(items) + 1, label, f))
        else:
            uncertain.append({"file": f["source"], "text": f"Narrator said: \"{f['quote']}\" (not applied)",
                              "spoken": True})

    return {
        "id": rid, "name": room["name"],
        "files": [p["file"] for p in perceptions],
        "room_guesses": sorted({p.get("room_guess", "") for p in perceptions}),
        "scale_refs": sorted({s for p in perceptions for s in p.get("scale_refs", [])}),
        "items": items,
        "fixtures": sorted(fixtures.values(), key=lambda f: f["label"].lower()),
        "personal_belongings": {"count": sum(personal.values()), "kinds": dict(personal)},
        "small_loose": sorted(small.values(), key=lambda s: s["label"].lower()),
        "containers": cont_list,
        "transcripts": {p["file"]: p.get("transcript", []) for p in perceptions if p.get("transcript")},
        "uncertain": uncertain,
        "merge_flags": flags,
    }


def _speech_record(field: str, value, f: dict) -> dict:
    return {"field": field, "value": value, "quote": f["quote"], "source": f["source"],
            "timestamp_s": f.get("timestamp_s")}


def apply_item_fact(item: dict, f: dict) -> None:
    """Rule 6: a narrator fact beats the catalog and the model (only a typed answer beats it)."""
    kind, rec = f["kind"], item["set_by_speech"]
    if kind in ("disposition", "not_moving"):
        d = "stays" if kind == "not_moving" else (f.get("disposition") or "")
        if d in DISPOSITIONS and d != "undecided":
            item["disposition"] = d
            rec.append(_speech_record("disposition", d, f))
    elif kind == "count" and f.get("count"):
        item["quantity"] = int(f["count"])
        rec.append(_speech_record("quantity", item["quantity"], f))
    elif kind == "fragile":
        item["fragile"] = True
        rec.append(_speech_record("fragile", True, f))
    elif kind == "size" and f.get("size_in"):
        dim = f.get("size_dim") or "length"
        item.setdefault("speech_size", {})[dim] = float(f["size_in"])
        rec.append(_speech_record(f"size.{dim}", float(f["size_in"]), f))
    elif kind == "identity" and (f.get("label") or f.get("value")):
        item["label"] = (f.get("label") or f["value"]).strip()
        rec.append(_speech_record("label", item["label"], f))
        cid = (f.get("catalog_id") or "").strip()
        if cid and (cid == "unknown" or catalog.get(cid)):
            item["catalog_id"] = cid
            rec.append(_speech_record("catalog_id", cid, f))
    elif kind == "unfilmed_item":
        if f.get("count"):
            item["quantity"] = int(f["count"])
        rec.append(_speech_record("heard_only", True, f))
    else:
        item["notes"] = (item.get("notes", "") + f" Narrator: \"{f['quote']}\"").strip()
        rec.append(_speech_record("notes", f["quote"], f))


def apply_container_fact(c: dict, f: dict) -> None:
    rec = c.setdefault("set_by_speech", [])
    if f["kind"] != "contents":
        rec.append(_speech_record("notes", f["quote"], f))
        return
    if f.get("contents"):
        c["contents"] = f["contents"]
        rec.append(_speech_record("contents", f["contents"], f))
    if f.get("fullness") and f["fullness"] != "not_visible":
        c["fullness"] = f["fullness"]
        rec.append(_speech_record("fullness", f["fullness"], f))


def _heard_item(rid: str, n: int, label: str, f: dict) -> dict:
    """A heard-only line built from a fact alone, when the model named the item but listed none."""
    return {"id": f"{rid}_item_{n:02d}", "group_key": "heard:" + canon_key(label), "label": label,
            "catalog_id": f.get("catalog_id") if catalog.get(f.get("catalog_id") or "") else "unknown",
            "quantity": int(f.get("count") or 1), "stack_count": 1, "confidence": 0.6, "move_class": "movable",
            "material": "mixed", "est_dims_in": [], "est_weight_lb": 0, "fragile": False, "must_stay_upright": False,
            "disassemble": False, "two_person": False, "stackable": False, "partially_visible": False,
            "evidence": {"source": f["source"], "sha256": None, "kind": "video", "timestamp_s": f.get("timestamp_s"),
                         "box_2d": None},
            "also_seen_in": [], "per_file_counts": {}, "variants": [label], "members": [],
            "disposition": "undecided", "notes": "", "heard_only": True,
            "set_by_speech": [_speech_record("heard_only", True, f)]}


def _group_label(gk: str, base: list[dict]) -> str:
    labels = [m["label"] for m in base]
    if len(set(l.lower() for l in labels)) == 1:
        return labels[0]
    uniq = sorted({l for l in labels}, key=str.lower)
    out = ", ".join(uniq)
    return out if len(out) <= 80 else out[:77] + "..."


def merge(run_id: str) -> dict:
    rd = run_dir(run_id)
    manifest = read_json(rd / "manifest.json")
    perc = [read_json(p) for p in sorted((rd / "perception").glob("*.json"))]
    rooms = []
    for room in manifest["rooms"]:
        ps = [p for p in perc if p["room_id"] == room["id"]]
        if ps:
            rooms.append(merge_room(ps, room))
    # Answers and edits are re-applied afterwards by gaps.reapply_answers().
    merged = {"run_id": run_id, "rooms": rooms, "answers_applied": []}
    write_json(rd / "merged.json", merged)
    update_status(rd, stage="merge_done")
    return merged
