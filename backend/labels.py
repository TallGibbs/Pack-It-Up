"""Stage B10: Real ISO/IEC 18004 Reed-Solomon QR box labels (`backend/labels.py`).

Generates genuine, phone-scannable QR codes (Versions 1–14, Error Correction M/L,
UTF-8 Byte mode) with zero external pip dependencies beyond Pillow:
  - `encode_qr_matrix(text)` -> exact `N x N` boolean module matrix
  - `render_qr_png(text, scale=8, border=4)` -> crisp PNG bytes with 4-module quiet zone
  - `render_qr_svg(text, border=4)` -> crisp vector SVG string
  - `build_qr_payload(box_item)` -> self-contained offline payload per moving carton
  - `extract_box_labels(plan)` -> structured top-flap label descriptors across trucks

Labels are mounted flat on the TOP flaps of each sealed carton and scan offline
with any iPhone or Android camera (no server or Wi-Fi required).
"""
from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageDraw

# GF(2^8) tables with primitive polynomial x^8 + x^4 + x^3 + x^2 + 1 (0x11D)
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

_ALIGN_POS: dict[int, list[int]] = {
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
    13: [6, 34, 62],
    14: [6, 26, 46, 66],
}

# (ec_cw_per_block, g1_blocks, g1_data_cw, g2_blocks, g2_data_cw)
_BLOCKS_M: dict[int, tuple[int, int, int, int, int]] = {
    1: (10, 1, 16, 0, 0),
    2: (16, 1, 28, 0, 0),
    3: (26, 1, 44, 0, 0),
    4: (18, 2, 32, 0, 0),
    5: (24, 2, 43, 0, 0),
    6: (16, 4, 27, 0, 0),
    7: (18, 4, 31, 0, 0),
    8: (22, 2, 38, 2, 39),
    9: (22, 3, 36, 2, 37),
    10: (26, 4, 43, 1, 44),
    11: (30, 1, 50, 4, 51),
    12: (22, 6, 36, 2, 37),
    13: (22, 8, 37, 1, 38),
    14: (24, 4, 40, 5, 41),
}

_BLOCKS_L: dict[int, tuple[int, int, int, int, int]] = {
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
    13: (26, 4, 107, 0, 0),
    14: (30, 3, 115, 1, 116),
}


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def _rs_generator_poly(degree: int) -> list[int]:
    poly = [1]
    for i in range(degree):
        nxt = [0] * (len(poly) + 1)
        root = _GF_EXP[i]
        for j, coef in enumerate(poly):
            nxt[j] ^= coef
            nxt[j + 1] ^= _gf_mul(coef, root)
        poly = nxt
    return poly  # length = degree + 1, leading coef 1


def _rs_remainder(data: list[int], ec_len: int) -> list[int]:
    gen = _rs_generator_poly(ec_len)[1:]
    rem = [0] * ec_len
    for byte in data:
        factor = byte ^ rem[0]
        rem = rem[1:] + [0]
        if factor != 0:
            for j in range(ec_len):
                rem[j] ^= _gf_mul(gen[j], factor)
    return rem


def _format_bits(ec_bits: int, mask: int) -> int:
    data = (ec_bits << 3) | mask
    rem = data << 10
    for i in range(4, -1, -1):
        if rem & (1 << (i + 10)):
            rem ^= 0x537 << i
    return ((data << 10) | rem) ^ 0x5412


def _version_bits(ver: int) -> int:
    rem = ver << 12
    for i in range(5, -1, -1):
        if rem & (1 << (i + 12)):
            rem ^= 0x1F25 << i
    return (ver << 12) | rem


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
        return ((r // 2) + (c // 3)) % 2 == 0
    if mask == 5:
        return ((r * c) % 2) + ((r * c) % 3) == 0
    if mask == 6:
        return (((r * c) % 2) + ((r * c) % 3)) % 2 == 0
    return (((r + c) % 2) + ((r * c) % 3)) % 2 == 0


def _penalty_score(mat: list[list[int]]) -> int:
    n = len(mat)
    score = 0
    # N1: runs of >=5 same-color modules in rows & cols
    for r in range(n):
        run_len = 1
        for c in range(1, n):
            if mat[r][c] == mat[r][c - 1]:
                run_len += 1
            else:
                if run_len >= 5:
                    score += 3 + (run_len - 5)
                run_len = 1
        if run_len >= 5:
            score += 3 + (run_len - 5)

    for c in range(n):
        run_len = 1
        for r in range(1, n):
            if mat[r][c] == mat[r - 1][c]:
                run_len += 1
            else:
                if run_len >= 5:
                    score += 3 + (run_len - 5)
                run_len = 1
        if run_len >= 5:
            score += 3 + (run_len - 5)

    # N2: 2x2 same-color blocks
    for r in range(n - 1):
        row0, row1 = mat[r], mat[r + 1]
        for c in range(n - 1):
            v = row0[c]
            if v == row0[c + 1] and v == row1[c] and v == row1[c + 1]:
                score += 3

    # N3: finder-like 1:1:3:1:1 patterns with 4 light modules on either side
    pat1 = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
    pat2 = [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]
    for r in range(n):
        row = mat[r]
        for c in range(n - 10):
            seg = row[c : c + 11]
            if seg == pat1 or seg == pat2:
                score += 40
    for c in range(n):
        col = [mat[r][c] for r in range(n)]
        for r in range(n - 10):
            seg = col[r : r + 11]
            if seg == pat1 or seg == pat2:
                score += 40

    # N4: dark module ratio balance
    dark = sum(sum(row) for row in mat)
    total = n * n
    k = int(abs(dark * 20 - total * 10) // total)
    score += k * 10
    return score


def _write_format_and_version(mat: list[list[int]], ver: int, ec_bits: int, mask: int) -> None:
    n = len(mat)
    fmt = _format_bits(ec_bits, mask)
    # Copy 1 around top-left finder
    tl_coords = [
        (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
        (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8),
    ]
    for idx, (r, c) in enumerate(tl_coords):
        mat[r][c] = (fmt >> (14 - idx)) & 1

    # Copy 2 along bottom-left col 8 and top-right row 8
    for idx in range(7):
        mat[n - 1 - idx][8] = (fmt >> (14 - idx)) & 1
    for idx in range(8):
        mat[8][n - 8 + idx] = (fmt >> (7 - idx)) & 1
    mat[n - 8][8] = 1  # dark module

    if ver >= 7:
        vbits = _version_bits(ver)
        for i in range(18):
            b = (vbits >> i) & 1
            a, k = i // 3, i % 3
            mat[n - 11 + k][a] = b
            mat[a][n - 11 + k] = b


def encode_qr_matrix(text: str, *, prefer_level: str = "M") -> list[list[bool]]:
    """Encode UTF-8 `text` into an ISO/IEC 18004 QR Code boolean module matrix (`True` = dark)."""
    payload = text.encode("utf-8")
    if len(payload) > 450:
        payload = payload[:450]

    chosen: tuple[int, int, tuple[int, int, int, int, int]] | None = None
    levels = [("M", 0b00, _BLOCKS_M), ("L", 0b01, _BLOCKS_L)] if prefer_level.upper() == "M" else [("L", 0b01, _BLOCKS_L)]
    for _, ec_bits, table in levels:
        for ver in range(1, 15):
            ec_cw, g1_b, g1_d, g2_b, g2_d = table[ver]
            total_data_cw = g1_b * g1_d + g2_b * g2_d
            cc_bits = 8 if ver <= 9 else 16
            max_bytes = (total_data_cw * 8 - 4 - cc_bits) // 8
            if len(payload) <= max_bytes:
                chosen = (ver, ec_bits, table[ver])
                break
        if chosen is not None:
            break

    if chosen is None:
        raise ValueError(f"QR payload too long ({len(payload)} bytes; max supported is 458 bytes)")

    ver, ec_bits, (ec_cw, g1_b, g1_d, g2_b, g2_d) = chosen
    total_data_cw = g1_b * g1_d + g2_b * g2_d
    cc_bits = 8 if ver <= 9 else 16

    # Build data bit stream: Byte mode (0100) + char count + payload + terminator + byte pad + 0xEC/0x11
    bits: list[int] = [0, 1, 0, 0]
    for shift in range(cc_bits - 1, -1, -1):
        bits.append((len(payload) >> shift) & 1)
    for byte in payload:
        for shift in range(7, -1, -1):
            bits.append((byte >> shift) & 1)

    cap_bits = total_data_cw * 8
    term = min(4, cap_bits - len(bits))
    bits.extend([0] * term)
    while len(bits) % 8 != 0:
        bits.append(0)

    data_cw = [
        sum(bits[i + k] << (7 - k) for k in range(8))
        for i in range(0, len(bits), 8)
    ]
    pad_seq = (0xEC, 0x11)
    p_idx = 0
    while len(data_cw) < total_data_cw:
        data_cw.append(pad_seq[p_idx & 1])
        p_idx += 1

    # Split into blocks, compute Reed-Solomon EC codewords, and interleave
    data_blocks: list[list[int]] = []
    ec_blocks: list[list[int]] = []
    pos = 0
    for count, dlen in ((g1_b, g1_d), (g2_b, g2_d)):
        for _ in range(count):
            blk = data_cw[pos : pos + dlen]
            pos += dlen
            data_blocks.append(blk)
            ec_blocks.append(_rs_remainder(blk, ec_cw))

    interleaved: list[int] = []
    max_dlen = max(g1_d, g2_d)
    for col in range(max_dlen):
        for blk in data_blocks:
            if col < len(blk):
                interleaved.append(blk[col])
    for col in range(ec_cw):
        for eblk in ec_blocks:
            interleaved.append(eblk[col])

    stream_bits: list[int] = []
    for byte in interleaved:
        for shift in range(7, -1, -1):
            stream_bits.append((byte >> shift) & 1)

    # Construct base function matrix
    n = 17 + 4 * ver
    base = [[0] * n for _ in range(n)]
    is_func = [[False] * n for _ in range(n)]

    def _place_finder(r0: int, c0: int) -> None:
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                rr, cc = r0 + dr, c0 + dc
                if 0 <= rr < n and 0 <= cc < n:
                    on = (
                        0 <= dr <= 6
                        and 0 <= dc <= 6
                        and (dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4))
                    )
                    base[rr][cc] = 1 if on else 0
                    is_func[rr][cc] = True

    _place_finder(0, 0)
    _place_finder(0, n - 7)
    _place_finder(n - 7, 0)

    centers = _ALIGN_POS[ver]
    for r in centers:
        for c in centers:
            if (r == 6 and c == 6) or (r == 6 and c == n - 7) or (r == n - 7 and c == 6):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    on = max(abs(dr), abs(dc)) in (0, 2)
                    base[r + dr][c + dc] = 1 if on else 0
                    is_func[r + dr][c + dc] = True

    for i in range(8, n - 8):
        if not is_func[6][i]:
            base[6][i] = 1 if i % 2 == 0 else 0
            is_func[6][i] = True
        if not is_func[i][6]:
            base[i][6] = 1 if i % 2 == 0 else 0
            is_func[i][6] = True

    # Reserve format & version regions
    for i in range(9):
        if i != 6:
            is_func[8][i] = True
            is_func[i][8] = True
    for i in range(8):
        is_func[n - 1 - i][8] = True
        is_func[8][n - 8 + i] = True
    base[n - 8][8] = 1
    is_func[n - 8][8] = True

    if ver >= 7:
        for a in range(6):
            for k in range(3):
                is_func[n - 11 + k][a] = True
                is_func[a][n - 11 + k] = True

    # Zig-zag data placement from right-to-left 2-column strips
    bit_idx = 0
    upward = True
    col = n - 1
    while col >= 1:
        if col == 6:
            col -= 1
        rows = range(n - 1, -1, -1) if upward else range(n)
        for r in rows:
            for dc in (0, 1):
                cc = col - dc
                if not is_func[r][cc]:
                    base[r][cc] = stream_bits[bit_idx] if bit_idx < len(stream_bits) else 0
                    bit_idx += 1
        upward = not upward
        col -= 2

    # Evaluate all 8 masks and choose lowest penalty
    best_mat: list[list[int]] | None = None
    best_pen: int | None = None
    for mask in range(8):
        cand = [row[:] for row in base]
        for r in range(n):
            for c in range(n):
                if not is_func[r][c] and _mask_bit(mask, r, c):
                    cand[r][c] ^= 1
        _write_format_and_version(cand, ver, ec_bits, mask)
        pen = _penalty_score(cand)
        if best_pen is None or pen < best_pen:
            best_pen = pen
            best_mat = cand

    assert best_mat is not None
    return [[bool(cell) for cell in row] for row in best_mat]


def render_qr_png(text: str, *, scale: int = 8, border: int = 4) -> bytes:
    """Render a crisp, scannable QR code PNG (with ISO 4-module white quiet zone)."""
    mat = encode_qr_matrix(text)
    n = len(mat)
    dim = (n + border * 2) * scale
    img = Image.new("RGB", (dim, dim), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for r, row in enumerate(mat):
        y0 = (r + border) * scale
        for c, dark in enumerate(row):
            if dark:
                x0 = (c + border) * scale
                draw.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=(17, 17, 17))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_qr_svg(text: str, *, border: int = 4) -> str:
    """Render a vector SVG string for `text` with an ISO quiet zone."""
    mat = encode_qr_matrix(text)
    n = len(mat)
    dim = n + border * 2
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dim} {dim}" shape-rendering="crispEdges">',
        f'<rect width="{dim}" height="{dim}" fill="#ffffff"/>',
    ]
    rects = [
        f"M{c + border},{r + border}h1v1h-1z"
        for r, row in enumerate(mat)
        for c, dark in enumerate(row)
        if dark
    ]
    parts.append(f'<path d="{"".join(rects)}" fill="#111111"/>')
    parts.append("</svg>")
    return "".join(parts)


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
