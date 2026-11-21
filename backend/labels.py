"""Stage B10 + Stretch A6: Offline Self-Contained QR Box Labels & Photo Box Matcher (`backend/labels.py`).

Implements:
  1. Pure-Python ISO/IEC 18004 QR Code encoder (Byte mode, Versions 1..12, EC Level L,
     Reed-Solomon GF(256) ECC, 8-mask penalty evaluation, SVG + Pillow PNG output) so
     zero extra pip packages are required on any teammate's laptop.
  2. `build_labels(placement, ...)`: one printable label per packed box (plus optional
     furniture tags) whose QR code **holds the box's manifest text itself** (not a URL):
     box short name, ID, source room, Penn Station destination store & dock stop, truck
     and load/unload step, handling flags, weight, and contents — readable by any phone
     camera completely offline with no server or wifi.
  3. `identify_box_from_photo(...)` (Stretch A6): identifies a marker-labelled box from
     a phone photo without scanning a QR code — `for_job("perceive")` (Gemini 4 Hydrogen)
     reads handwritten marker text, box size, visible contents, and damage, then
     `for_job("decide")` (Gemini Decision 1) selects the matching box from the run's
     stored manifest (with an explicit `"other"` catch-all).

No model SDK is imported here; all model calls go through `backend.llm.for_job()`.

CLI:
    python -m backend.labels data/sample_venue.json --out-dir /tmp/labels_preview
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from backend import solver
from backend.ingest.common import read_json, run_dir, write_json
from backend.llm import LLMError, for_job, media_from_path

MAX_QR_BYTES = 240

# ---------------------------------------------------------------------------
# Pure-Python ISO/IEC 18004 QR Code Encoder (Byte Mode, EC Level L, V1..V12)
# ---------------------------------------------------------------------------

# (ec_codewords_per_block, group1_blocks, group1_data_cw, group2_blocks, group2_data_cw)
_QR_L_SPECS: dict[int, tuple[int, int, int, int, int]] = {
    1: (7, 1, 19, 0, 0),
    2: (10, 1, 34, 0, 0),
    3: (15, 1, 55, 0, 0),
    4: (20, 1, 80, 0, 0),
    5: (26, 1, 108, 0, 0),
    6: (18, 2, 68, 0, 0),
    7: (20, 2, 78, 0, 0),
    8: (24, 2, 97, 0, 0),
    9: (30, 2, 116, 0, 0),
    10: (18, 2, 68, 2, 69),
    11: (20, 4, 81, 0, 0),
    12: (24, 2, 92, 2, 93),
}

_ALIGN_CENTERS: dict[int, list[int]] = {
    1: [],
    2: [6, 18],
    3: [6, 22],
    4: [6, 26],
    5: [6, 30],
    6: [6, 34],
    7: [6, 22, 38],
    8: [6, 24, 42],
    9: [6, 26, 46],
    10: [6, 28, 50],
    11: [6, 30, 54],
    12: [6, 32, 58],
}

# GF(256) log/exp tables with primitive polynomial 0x11D (x^8 + x^4 + x^3 + x^2 + 1)
_GF_EXP = [0] * 512
_GF_LOG = [0] * 256
_x = 1
for _i in range(255):
    _GF_EXP[_i] = _x
    _GF_LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _GF_EXP[_i] = _GF_EXP[_i - 255]


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def _rs_generator_poly(degree: int) -> list[int]:
    """Compute monic Reed-Solomon generator polynomial coefficients (highest degree first)."""
    poly = [1]
    for i in range(degree):
        nxt = [0] * (len(poly) + 1)
        root = _GF_EXP[i]
        for j, coef in enumerate(poly):
            nxt[j] ^= coef
            nxt[j + 1] ^= _gf_mul(coef, root)
        poly = nxt
    return poly


def _rs_remainder(data: list[int], ec_len: int) -> list[int]:
    gen = _rs_generator_poly(ec_len)
    reg = [0] * ec_len
    for byte in data:
        factor = byte ^ reg[0]
        reg = reg[1:] + [0]
        if factor != 0:
            for j in range(ec_len):
                reg[j] ^= _gf_mul(gen[j + 1], factor)
    return reg


def _pick_version(payload_len: int) -> int:
    for ver, (_, g1b, g1d, g2b, g2d) in _QR_L_SPECS.items():
        total_data_cw = g1b * g1d + g2b * g2d
        count_bits = 8 if ver <= 9 else 16
        # 4 mode bits + count_bits <= 20 bits (at most 2.5 bytes)
        usable_bytes = (total_data_cw * 8 - 4 - count_bits) // 8
        if payload_len <= usable_bytes:
            return ver
    raise ValueError(f"QR payload ({payload_len} bytes) exceeds Version 12 capacity")


def _encode_data_codewords(data: bytes, ver: int) -> list[int]:
    _, g1b, g1d, g2b, g2d = _QR_L_SPECS[ver]
    total_data_cw = g1b * g1d + g2b * g2d
    capacity_bits = total_data_cw * 8

    bits: list[int] = [0, 1, 0, 0]  # Byte mode indicator (0100)
    count_bits = 8 if ver <= 9 else 16
    n = len(data)
    for shift in range(count_bits - 1, -1, -1):
        bits.append((n >> shift) & 1)
    for b in data:
        for shift in range(7, -1, -1):
            bits.append((b >> shift) & 1)

    # Terminator: up to 4 zero bits
    term = min(4, capacity_bits - len(bits))
    bits.extend([0] * term)
    # Pad to byte boundary
    while len(bits) % 8 != 0:
        bits.append(0)

    codewords = []
    for i in range(0, len(bits), 8):
        val = 0
        for bit in bits[i : i + 8]:
            val = (val << 1) | bit
        codewords.append(val)

    pad_bytes = (0xEC, 0x11)
    p_idx = 0
    while len(codewords) < total_data_cw:
        codewords.append(pad_bytes[p_idx % 2])
        p_idx += 1
    return codewords


def _interleave_blocks(data_cw: list[int], ver: int) -> list[int]:
    ec_len, g1b, g1d, g2b, g2d = _QR_L_SPECS[ver]
    data_blocks: list[list[int]] = []
    ec_blocks: list[list[int]] = []
    pos = 0
    for _ in range(g1b):
        blk = data_cw[pos : pos + g1d]
        pos += g1d
        data_blocks.append(blk)
        ec_blocks.append(_rs_remainder(blk, ec_len))
    for _ in range(g2b):
        blk = data_cw[pos : pos + g2d]
        pos += g2d
        data_blocks.append(blk)
        ec_blocks.append(_rs_remainder(blk, ec_len))

    out: list[int] = []
    max_d = max(len(b) for b in data_blocks)
    for i in range(max_d):
        for b in data_blocks:
            if i < len(b):
                out.append(b[i])
    for i in range(ec_len):
        for eb in ec_blocks:
            out.append(eb[i])
    return out


def _format_bits(mask: int) -> int:
    # EC Level L = 01
    data = (0b01 << 3) | mask
    rem = data << 10
    for shift in range(14, 9, -1):
        if (rem >> shift) & 1:
            rem ^= 0x537 << (shift - 10)
    return ((data << 10) | rem) ^ 0x5412


def _version_bits(ver: int) -> int:
    rem = ver << 12
    for shift in range(17, 11, -1):
        if (rem >> shift) & 1:
            rem ^= 0x1F25 << (shift - 12)
    return (ver << 12) | rem


def _place_finder(grid: list[list[int]], is_func: list[list[bool]], r0: int, c0: int) -> None:
    size = len(grid)
    for dr in range(-1, 8):
        for dc in range(-1, 8):
            r, c = r0 + dr, c0 + dc
            if 0 <= r < size and 0 <= c < size:
                in_outer = 0 <= dr <= 6 and 0 <= dc <= 6
                on_ring = dr in (0, 6) or dc in (0, 6)
                in_core = 2 <= dr <= 4 and 2 <= dc <= 4
                grid[r][c] = 1 if (in_outer and (on_ring or in_core)) else 0
                is_func[r][c] = True


def _place_alignment(grid: list[list[int]], is_func: list[list[bool]], rc: int, cc: int) -> None:
    for dr in range(-2, 3):
        for dc in range(-2, 3):
            dist = max(abs(dr), abs(dc))
            grid[rc + dr][cc + dc] = 1 if dist in (0, 2) else 0
            is_func[rc + dr][cc + dc] = True


def _write_format_bits(grid: list[list[int]], is_func: list[list[bool]], mask: int) -> None:
    size = len(grid)
    fb = _format_bits(mask)
    # Copy 1 around top-left finder
    tl_coords = [
        (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5),
        (8, 7), (8, 8), (7, 8),
        (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8),
    ]
    for idx, (r, c) in enumerate(tl_coords):
        bit = (fb >> (14 - idx)) & 1
        grid[r][c] = bit
        is_func[r][c] = True

    # Copy 2 split across bottom-left and top-right
    for idx in range(7):
        bit = (fb >> (14 - idx)) & 1
        r, c = size - 1 - idx, 8
        grid[r][c] = bit
        is_func[r][c] = True
    for idx in range(7, 15):
        bit = (fb >> (14 - idx)) & 1
        r, c = 8, size - 15 + idx
        grid[r][c] = bit
        is_func[r][c] = True

    # Always-dark module
    grid[size - 8][8] = 1
    is_func[size - 8][8] = True


def _mask_bit(mask: int, r: int, c: int) -> bool:
    if mask == 0:
        return (r + c) % 2 == 0
    if mask == 1:
        return r % 2 == 0
    if mask == 2:
        return c % 3 == 0
    if mask == 3:
        return (r + c) % 3 == 0
    if mask == 4:
        return (r // 2 + c // 3) % 2 == 0
    if mask == 5:
        return (r * c) % 2 + (r * c) % 3 == 0
    if mask == 6:
        return ((r * c) % 2 + (r * c) % 3) % 2 == 0
    return ((r + c) % 2 + (r * c) % 3) % 2 == 0


def _penalty_score(grid: list[list[int]]) -> int:
    size = len(grid)
    score = 0
    # Rule 1: runs of >=5 same-colored modules in rows and columns
    for r in range(size):
        run_len = 1
        for c in range(1, size):
            if grid[r][c] == grid[r][c - 1]:
                run_len += 1
            else:
                if run_len >= 5:
                    score += 3 + (run_len - 5)
                run_len = 1
        if run_len >= 5:
            score += 3 + (run_len - 5)

    for c in range(size):
        run_len = 1
        for r in range(1, size):
            if grid[r][c] == grid[r - 1][c]:
                run_len += 1
            else:
                if run_len >= 5:
                    score += 3 + (run_len - 5)
                run_len = 1
        if run_len >= 5:
            score += 3 + (run_len - 5)

    # Rule 2: 2x2 blocks of identical color
    for r in range(size - 1):
        for c in range(size - 1):
            v = grid[r][c]
            if grid[r][c + 1] == v and grid[r + 1][c] == v and grid[r + 1][c + 1] == v:
                score += 3

    # Rule 3: finder-like 1:1:3:1:1 patterns next to 4 light modules
    pat_a = [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]
    pat_b = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
    for r in range(size):
        padded = [0, 0, 0, 0] + grid[r] + [0, 0, 0, 0]
        for i in range(len(padded) - 10):
            seg = padded[i : i + 11]
            if seg == pat_a or seg == pat_b:
                score += 40
    for c in range(size):
        col = [0, 0, 0, 0] + [grid[r][c] for r in range(size)] + [0, 0, 0, 0]
        for i in range(len(col) - 10):
            seg = col[i : i + 11]
            if seg == pat_a or seg == pat_b:
                score += 40

    # Rule 4: dark module balance
    dark = sum(sum(row) for row in grid)
    total = size * size
    steps = abs(dark * 20 - total * 10) // total
    score += steps * 10
    return score


def encode_qr_matrix(text: str) -> list[list[int]]:
    """Encode UTF-8 `text` into a 2D QR Code bit matrix (`1` = dark, `0` = light)."""
    raw = text.encode("utf-8")
    ver = _pick_version(len(raw))
    size = 21 + 4 * (ver - 1)

    base = [[0] * size for _ in range(size)]
    is_func = [[False] * size for _ in range(size)]

    _place_finder(base, is_func, 0, 0)
    _place_finder(base, is_func, 0, size - 7)
    _place_finder(base, is_func, size - 7, 0)

    centers = _ALIGN_CENTERS[ver]
    for r in centers:
        for c in centers:
            if (r == 6 and c == 6) or (r == 6 and c == centers[-1]) or (r == centers[-1] and c == 6):
                continue
            _place_alignment(base, is_func, r, c)

    for i in range(8, size - 8):
        if not is_func[6][i]:
            base[6][i] = 1 if i % 2 == 0 else 0
            is_func[6][i] = True
        if not is_func[i][6]:
            base[i][6] = 1 if i % 2 == 0 else 0
            is_func[i][6] = True

    # Reserve format info slots before placing data bits
    _write_format_bits(base, is_func, 0)

    if ver >= 7:
        vb = _version_bits(ver)
        for i in range(18):
            bit = (vb >> i) & 1
            r1, c1 = size - 11 + (i % 3), i // 3
            r2, c2 = i // 3, size - 11 + (i % 3)
            base[r1][c1] = bit
            is_func[r1][c1] = True
            base[r2][c2] = bit
            is_func[r2][c2] = True

    codewords = _interleave_blocks(_encode_data_codewords(raw, ver), ver)
    bitstream: list[int] = []
    for cw in codewords:
        for shift in range(7, -1, -1):
            bitstream.append((cw >> shift) & 1)

    bit_idx = 0
    upward = True
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for r in rows:
            for dc in (0, 1):
                c = col - dc
                if not is_func[r][c]:
                    base[r][c] = bitstream[bit_idx] if bit_idx < len(bitstream) else 0
                    bit_idx += 1
        upward = not upward
        col -= 2

    best_grid: list[list[int]] | None = None
    best_score = 10**9
    for mask in range(8):
        cand = [row[:] for row in base]
        for r in range(size):
            for c in range(size):
                if not is_func[r][c] and _mask_bit(mask, r, c):
                    cand[r][c] ^= 1
        _write_format_bits(cand, [[False] * size for _ in range(size)], mask)
        sc = _penalty_score(cand)
        if sc < best_score:
            best_score = sc
            best_grid = cand

    assert best_grid is not None
    return best_grid


def qr_svg(text: str, *, border: int = 4) -> str:
    """Render `text` as a compact, crisp inline SVG QR code with a quiet zone."""
    mat = encode_qr_matrix(text)
    n = len(mat)
    dim = n + 2 * border
    rects: list[str] = []
    for r, row in enumerate(mat):
        c = 0
        while c < n:
            if row[c]:
                start = c
                while c < n and row[c]:
                    c += 1
                w = c - start
                rects.append(f"M{start + border},{r + border}h{w}v1h-{w}z")
            else:
                c += 1
    path_d = "".join(rects)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dim} {dim}" '
        f'shape-rendering="crispEdges" role="img" aria-label="QR code">'
        f'<rect width="{dim}" height="{dim}" fill="#ffffff"/>'
        f'<path d="{path_d}" fill="#000000"/></svg>'
    )


def qr_png_bytes(text: str, *, scale: int = 8, border: int = 4) -> bytes:
    """Render `text` as high-contrast PNG bytes via Pillow."""
    mat = encode_qr_matrix(text)
    n = len(mat)
    dim = (n + 2 * border) * scale
    img = Image.new("RGB", (dim, dim), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for r, row in enumerate(mat):
        for c, val in enumerate(row):
            if val:
                x0 = (c + border) * scale
                y0 = (r + border) * scale
                draw.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Stage B10: Self-Contained Box Label Builder
# ---------------------------------------------------------------------------

ZONE_COLORS: dict[str, tuple[str, str]] = {
    "penn_merch_kiosk": ("Amber", "#d97706"),
    "penn_cafe": ("Coral", "#e11d48"),
    "penn_bookshop": ("Emerald", "#059669"),
    "penn_tech_hub": ("Blue", "#2563eb"),
    "penn_lounge": ("Violet", "#7c3aed"),
    "penn_concourse": ("Slate", "#334155"),
}


def format_qr_manifest(box: dict[str, Any], max_bytes: int = MAX_QR_BYTES) -> str:
    """Format the self-contained plain-text manifest stored directly inside the QR code.

    Any phone camera scanning this QR code reads the box's name, contents, handling
    flags, truck/step, and Penn Station destination with zero server or wifi.
    """
    short = str(box.get("short_name") or box.get("id") or "Box 1")
    flags: list[str] = []
    if box.get("fragile"):
        flags.append("FRAGILE")
    if box.get("must_stay_upright"):
        flags.append("UPRIGHT")
    if box.get("two_person"):
        flags.append("2-PERSON")
    flag_tag = f" [{'/'.join(flags)}]" if flags else ""

    stop = box.get("dock_stop")
    dest_name = str(box.get("dest_zone_name") or box.get("dest_zone") or "Destination")
    stop_prefix = f"Stop {stop}: " if stop is not None else ""
    room = str(box.get("room_name") or "Room")
    t_num = int(box.get("truck_index", 0)) + 1
    load_s = box.get("load_seq", "?")
    unload_s = box.get("unload_seq", "?")
    wt = box.get("weight_lb", 0)
    contents = str(box.get("contents") or box.get("label") or "packed items").strip()

    header_lines = [
        f"PACK IT UP · {short}{flag_tag}",
        f"{room} -> {stop_prefix}{dest_name}",
        f"Truck {t_num} · Load #{load_s} · Unload #{unload_s} ({wt:g} lb)",
    ]
    prefix = "\n".join(header_lines) + "\nContents: "
    budget = max(24, max_bytes - len(prefix.encode("utf-8")))

    encoded_contents = contents.encode("utf-8")
    if len(encoded_contents) > budget:
        trimmed = encoded_contents[: max(8, budget - 4)].decode("utf-8", errors="ignore").rstrip(",; ")
        contents = trimmed + "..."
    return prefix + contents


def build_labels(
    placement: dict[str, Any],
    *,
    run_id: str | None = None,
    include_furniture_tags: bool = False,
) -> dict[str, Any]:
    """Generate printable offline QR labels for every box (and optional furniture) in `placement`."""
    labels_out: list[dict[str, Any]] = []
    fallback_counter: dict[str, int] = {}

    for t in placement.get("trucks") or []:
        t_idx = int(t.get("index", 0))
        t_id = str(t.get("truck_id") or "uhaul_26")
        t_name = str(t.get("name") or t_id)
        for it in t.get("items") or []:
            is_box = bool(it.get("is_box"))
            if not is_box and not include_furniture_tags:
                continue

            room_name = str(it.get("room_name") or it.get("room_id") or "Room")
            short = it.get("box_short_name")
            if not short:
                prefix = re.sub(r"[^A-Za-z0-9]+", "", room_name.split()[0] if room_name.split() else "Tag")[:8] or "Tag"
                fallback_counter[prefix] = fallback_counter.get(prefix, 0) + 1
                short = f"{prefix} F{fallback_counter[prefix]}"

            zid = str(it.get("dest_zone") or "penn_concourse")
            color_name, color_hex = ZONE_COLORS.get(zid, ("Slate", "#334155"))
            piece_id = str(it.get("piece_id") or it.get("id") or short)

            rec: dict[str, Any] = {
                "box_id": piece_id,
                "placed_id": str(it.get("id") or piece_id),
                "short_name": short,
                "marker_code": f"{color_name} · {short}",
                "color_name": color_name,
                "color_hex": color_hex,
                "is_box": is_box,
                "label": str(it.get("label") or short),
                "catalog_id": str(it.get("catalog_id") or "box_medium"),
                "room_id": str(it.get("room_id") or "room_1"),
                "room_name": room_name,
                "contents": str(it.get("contents") or it.get("label") or ""),
                "dims_in": list(it.get("size_in") or [18, 18, 16]),
                "weight_lb": round(float(it.get("weight_lb") or 0.0), 1),
                "fragile": bool(it.get("fragile")),
                "must_stay_upright": bool(it.get("must_stay_upright")),
                "two_person": bool(it.get("two_person")),
                "truck_index": t_idx,
                "truck_id": t_id,
                "truck_name": t_name,
                "load_seq": int(it.get("load_seq") or 1),
                "unload_seq": int(it.get("unload_seq") or 1),
                "dest_zone": zid,
                "dest_zone_name": str(it.get("dest_zone_name") or zid),
                "dock_stop": it.get("dock_stop"),
            }
            qr_text = format_qr_manifest(rec)
            rec["qr_text"] = qr_text
            rec["qr_bytes_len"] = len(qr_text.encode("utf-8"))
            rec["qr_svg"] = qr_svg(qr_text)
            labels_out.append(rec)

    # Sort by dock_stop (unloaded first at Penn Station), then truck_index, then unload_seq
    labels_out.sort(key=lambda b: (int(b.get("dock_stop") or 99), b["truck_index"], b["unload_seq"]))

    return {
        "run_id": run_id or placement.get("run_id") or "sample_venue",
        "count": len(labels_out),
        "box_count": sum(1 for b in labels_out if b["is_box"]),
        "furniture_tag_count": sum(1 for b in labels_out if not b["is_box"]),
        "fleet_label": (placement.get("summary") or {}).get("fleet_label", ""),
        "labels": labels_out,
    }


def labels_for_run(run_id: str, *, include_furniture_tags: bool = False) -> dict[str, Any]:
    """Load or solve `placement` for `run_id` (`sample_venue`, `mock-demo`, or real run) and build labels."""
    repo_root = Path(__file__).resolve().parents[1]
    rid = (run_id or "sample_venue").strip()
    if rid in ("", "sample_venue", "sample"):
        inv = json.loads((repo_root / "data" / "sample_venue.json").read_text(encoding="utf-8"))
        plan = solver.solve(inv, strategy={"downsize_last_truck": True})
        return build_labels(plan, run_id="sample_venue", include_furniture_tags=include_furniture_tags)

    if rid == "mock-demo":
        inv = json.loads((repo_root / "frontend" / "mock" / "inventory.json").read_text(encoding="utf-8"))
        plan = solver.solve(inv, strategy={"downsize_last_truck": True})
        return build_labels(plan, run_id="mock-demo", include_furniture_tags=include_furniture_tags)

    rd = run_dir(rid)
    if not rd.exists():
        raise FileNotFoundError(f"run not found: {rid}")
    plan = read_json(rd / "placement.json")
    if plan is None:
        inv = read_json(rd / "inventory.json")
        if inv is None:
            raise ValueError(f"run {rid!r} has no inventory.json yet")
        plan = solver.solve(inv, strategy={"downsize_last_truck": True})
        write_json(rd / "placement.json", plan)

    bundle = build_labels(plan, run_id=rid, include_furniture_tags=include_furniture_tags)
    write_json(
        rd / "labels.json",
        {
            **bundle,
            "labels": [{k: v for k, v in b.items() if k != "qr_svg"} for b in bundle["labels"]],
        },
    )
    return bundle


# ---------------------------------------------------------------------------
# Stretch A6: Photo-to-Box Recognizer Without QR (`Hydrogen` + `Decision 1`)
# ---------------------------------------------------------------------------

BOX_OBSERVATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["written_text", "tape_or_color", "size_guess", "visible_contents", "damaged", "damage_note"],
    "properties": {
        "written_text": {
            "type": "string",
            "description": "Handwritten marker or printed label text read from the box (e.g. 'Lounge 1', 'Kitchen 3'), or empty string.",
        },
        "tape_or_color": {"type": "string"},
        "size_guess": {"type": "string", "enum": ["small", "medium", "large", "wardrobe", "unknown"]},
        "visible_contents": {"type": "string"},
        "damaged": {"type": "boolean"},
        "damage_note": {"type": "string"},
    },
}


def identify_box_from_photo(
    photo_bytes: bytes,
    mime: str,
    labels_list: list[dict[str, Any]],
    *,
    run_dir_path: Path | None = None,
    hint_text: str = "",
) -> dict[str, Any]:
    """Identify a marked moving box from a photo without scanning its QR code (Stretch A6).

    1. `for_job("perceive")` reads marker handwriting, tape/color, box size, and any damage.
    2. `for_job("decide")` (`gemini-decision-1`) matches the photo + observation against the
       stored box manifest (with an explicit `"other"` catch-all when no box matches).
    """
    if not labels_list:
        raise ValueError("no packed boxes in this move to match against")

    ext = ".png" if "png" in mime.lower() else ".jpg"
    sha = hashlib.sha256(photo_bytes).hexdigest()
    tmp_dir = Path(run_dir_path / "box_scans") if run_dir_path else Path(tempfile.gettempdir()) / "pack_it_up_scans"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    img_path = tmp_dir / f"{sha[:16]}{ext}"
    if not img_path.exists():
        img_path.write_bytes(photo_bytes)

    media = [media_from_path(img_path, sha256=sha)]
    media[0].caption = "Photo of moving box to identify"

    obs: dict[str, Any] = {
        "written_text": hint_text.strip(),
        "tape_or_color": "",
        "size_guess": "unknown",
        "visible_contents": "",
        "damaged": False,
        "damage_note": "",
    }
    via = "decisions_api"

    try:
        obs_prompt = (
            "Read any handwritten marker text or printed short name on this moving box "
            "(for example 'Lounge 1', 'Main 2', 'Amber · Lounge 1'), note tape/label color, "
            "estimate box size class, describe any visible contents if open, and flag whether "
            "the cardboard box is crushed, torn, or water-damaged."
        )
        obs = for_job("perceive", run_dir=run_dir_path).generate_json(
            obs_prompt,
            media=media,
            schema=BOX_OBSERVATION_SCHEMA,
            prompt_version="identify_box_v1",
            label=f"box_scan:{sha[:10]}",
        )
    except LLMError:
        via = "heuristic_text_fallback"

    # Candidate shortlist (up to 40 boxes so Decision 1 stays crisp and fast)
    candidates = labels_list[:40]
    criteria: dict[str, str] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for b in candidates:
        bid = b["box_id"]
        by_id[bid] = b
        criteria[bid] = (
            f"Short name '{b['short_name']}' ({b['marker_code']}), room '{b['room_name']}', "
            f"size {b['catalog_id']}, contents: {b['contents'][:80]}, dest: {b['dest_zone_name']}"
        )
    criteria["other"] = "None of the listed boxes match this photo."

    if via != "heuristic_text_fallback":
        q_text = (
            f"Perceived box handwriting/notes: {json.dumps(obs)}. "
            "Which stored moving box in this move matches the photographed box? "
            "Choose 'other' if none of the stored boxes plausibly match."
        )
        try:
            dec = for_job("decide", run_dir=run_dir_path).decide(
                q_text,
                media=media,
                options=list(criteria.keys()),
                criteria=criteria,
                label=f"identify_box:{sha[:10]}",
            )
            picked = dec["answer"]
            matched = by_id.get(picked)
            return {
                "matched": matched is not None,
                "box_id": picked if matched else None,
                "confidence": round(float(dec["confidence"]), 3),
                "via": dec.get("via", "decisions_api"),
                "observation": obs,
                "box": {k: v for k, v in matched.items() if k != "qr_svg"} if matched else None,
            }
        except LLMError:
            via = "heuristic_text_fallback"

    # Deterministic fallback matcher on written_text / hint_text
    needle = (obs.get("written_text") or hint_text or "").strip().lower()
    matched = None
    conf = 0.0
    if needle:
        for b in candidates:
            if b["short_name"].lower() in needle or needle in b["short_name"].lower() or b["box_id"].lower() == needle:
                matched = b
                conf = 0.85
                break
    return {
        "matched": matched is not None,
        "box_id": matched["box_id"] if matched else None,
        "confidence": conf,
        "via": via,
        "observation": obs,
        "box": {k: v for k, v in matched.items() if k != "qr_svg"} if matched else None,
    }


def render_qr_png(text: str, scale: int = 8, border: int = 4) -> bytes:
    """Alias for `qr_png_bytes` matching top-flap helper signature."""
    return qr_png_bytes(text, scale=scale, border=border)


def render_qr_svg(text: str, border: int = 4) -> str:
    """Alias for `qr_svg` matching top-flap helper signature."""
    return qr_svg(text, border=border)


def build_qr_payload(box_item: dict[str, Any]) -> str:
    """Self-contained multi-line text payload encoded directly into the box's top-flap QR label."""
    short_name = str(box_item.get("box_short_name") or box_item.get("id") or "BOX")
    room = str(box_item.get("room_name") or "")
    stop = box_item.get("dock_stop") or "-"
    dest = str(box_item.get("dest_zone_name") or "Penn Station")
    corner = str(box_item.get("dest_corner") or "").strip()
    dest_full = f"Stop {stop} {dest}" + (f" ({corner})" if corner else "")
    truck_num = int(box_item.get("truck_index") or 0) + 1
    load_seq = box_item.get("load_seq") or "-"
    unload_seq = box_item.get("unload_seq") or "-"
    handling = "FRAGILE-UPRIGHT" if box_item.get("fragile") else "STD"
    contents = str(box_item.get("contents") or box_item.get("label") or "")[:90]
    return "\n".join([
        f"PACK-IT-UP | BOX:{short_name}",
        f"DEST:{dest_full}",
        f"TRUCK:T{truck_num} Load#{load_seq} Unload#{unload_seq}",
        f"ROOM:{room} | HANDLING:{handling} | MOUNT:TOP-FLAPS",
        f"IN:{contents}",
    ])


def extract_box_labels(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all box label descriptors (with scannable SVG QR + payload) across the solved fleet."""
    out: list[dict[str, Any]] = []
    for t in plan.get("trucks") or []:
        for it in t.get("items") or []:
            if not it.get("is_box"):
                continue
            payload = build_qr_payload(it)
            out.append({
                "id": it.get("id"),
                "box_short_name": it.get("box_short_name") or it.get("id"),
                "placement_surface": "top",
                "room_name": it.get("room_name"),
                "dock_stop": it.get("dock_stop"),
                "dest_zone_name": it.get("dest_zone_name"),
                "dest_corner": it.get("dest_corner") or "Stock",
                "truck_index": it.get("truck_index", 0),
                "load_seq": it.get("load_seq"),
                "unload_seq": it.get("unload_seq"),
                "fragile": bool(it.get("fragile")),
                "weight_lb": it.get("weight_lb"),
                "qr_payload": payload,
                "qr_svg": render_qr_svg(payload),
            })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage B10: generate offline scannable QR box labels.")
    ap.add_argument("inventory", nargs="?", type=Path, default=None, help="Optional inventory_v2 JSON")
    ap.add_argument("--run", dest="run_id", default="sample_venue", help="run_id or sample_venue / mock-demo")
    ap.add_argument("--out-dir", type=Path, default=None, help="Optional directory to write PNG QR labels")
    args = ap.parse_args()

    if args.inventory:
        inv = json.loads(args.inventory.read_text(encoding="utf-8"))
        plan = solver.solve(inv, strategy={"downsize_last_truck": True})
        bundle = build_labels(plan, run_id=args.inventory.stem)
    else:
        bundle = labels_for_run(args.run_id)

    print(
        f"[QR Labels] run={bundle['run_id']} boxes={bundle['box_count']} "
        f"fleet={bundle['fleet_label']}"
    )
    for b in bundle["labels"][:6]:
        print(
            f"  - {b['short_name']:10s} ({b['color_name']}) -> Stop {b['dock_stop']} {b['dest_zone_name']} "
            f"| Truck {b['truck_index']+1} Unload #{b['unload_seq']} | QR={b['qr_bytes_len']}B"
        )
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        for b in bundle["labels"]:
            png = qr_png_bytes(b["qr_text"])
            slug_name = re.sub(r"[^A-Za-z0-9_\-]+", "_", b["short_name"])
            (args.out_dir / f"{slug_name}.png").write_bytes(png)
        print(f"Wrote {len(bundle['labels'])} QR PNGs to {args.out_dir}")


if __name__ == "__main__":
    main()
