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

from .common import read_json, run_dir, update_status, write_json

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

    for p in perceptions:
        for q in p.get("uncertain", []):
            uncertain.append({"file": p["file"], "text": q})
        for it in p["items"]:
            mc = it["move_class"]
            if mc == "movable":
                groups[group_key(it)].append((p, it))
            elif mc == "fixture":
                k = canon_key(it["label"]) + ":" + it["label"].lower()
                f = fixtures.setdefault(k, {"label": it["label"], "quantity": 0, "seen_in": []})
                f["quantity"] = max(f["quantity"], it["quantity"])
                f["seen_in"].append(p["file"])
            elif mc == "personal_belonging":
                personal_per_file[p["file"]][canon_key(it["label"])] += it["quantity"]
            else:  # small_loose
                k = it["label"].lower()
                s = small.setdefault(k, {"label": it["label"], "quantity": 0, "seen_in": [],
                                         "est_dims_in": it["est_dims_in"], "material": it["material"],
                                         "fragile": it["fragile"]})
                s["quantity"] = max(s["quantity"], it["quantity"])
                s["seen_in"].append(p["file"])
        for c in p.get("containers", []):
            k = (c["kind"], c["contents"], canon_key(c["label"]) if c["kind"] != "open_surfaces" else "")
            cur = containers.get(k)
            if cur is None:
                containers[k] = {**c, "seen_in": [p["file"]]}
            else:
                cur["seen_in"].append(p["file"])
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
        }
        items.append(item)
        # Rule 4: entries in other files whose colours match nothing in the best file.
        for f, ms in by_file.items():
            if f == best_file:
                continue
            for m in ms:
                if not any(compatible(m["label"], b["label"]) for b in base):
                    # Ask whether m is any of the pieces already counted (all of `base`), not just one of them.
                    flags.append({"kind": "same_item", "item_id": item_id, "base": base, "b": m})

    return {
        "id": rid, "name": room["name"],
        "files": [p["file"] for p in perceptions],
        "room_guesses": sorted({p.get("room_guess", "") for p in perceptions}),
        "scale_refs": sorted({s for p in perceptions for s in p.get("scale_refs", [])}),
        "items": items,
        "fixtures": sorted(fixtures.values(), key=lambda f: f["label"].lower()),
        "personal_belongings": {"count": sum(personal.values()), "kinds": dict(personal)},
        "small_loose": sorted(small.values(), key=lambda s: s["label"].lower()),
        "containers": list(containers.values()),
        "uncertain": uncertain,
        "merge_flags": flags,
    }


def _group_label(gk: str, base: list[dict]) -> str:
    labels = [m["label"] for m in base]
    if len(set(l.lower() for l in labels)) == 1:
        return labels[0]
    noun = gk.split(":", 1)[-1].replace("_", " ")
    return f"{noun}s ({', '.join(sorted(set(labels), key=str.lower))})"


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
