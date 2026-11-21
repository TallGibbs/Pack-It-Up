"""Builds the 60 s submission video from scripts/video/shots.json (plan: plan/VIDEO_SCRIPT.md).

    .venv\\Scripts\\python.exe -m scripts.video.build            # the real build: narration, opening, capture, MP4
    .venv\\Scripts\\python.exe -m scripts.video.build --dry      # no model calls: silent narration, no Neon click, no opening
    options: --skip-capture (reuse the last capture), --narration-only, --force (render even if a page check fails)

Model calls go through backend/llm only (jobs `narrate` and `video_open`); this file imports no model SDK.
Everything it writes goes under .cache/video/ (git-ignored). Needs: the demo API on 127.0.0.1:8000, Node 22+,
Chrome, and the ffmpeg that ships with imageio-ffmpeg.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import textwrap
import threading
import time
import wave
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / ".cache" / "video"
BUILD = OUT / "build"
FINAL = OUT / "out"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1920, 1080, 30
CAPTION_TOP = 952            # captions live in the band below this line
PHONE_BOX = (452, 40, 452 + 404, 40 + 874)   # where the phone capture goes (x0, y0, x1, y1), 390x844 scaled
DESK_BOX = (110, 0, 110 + 1700, 956)
LEAD_S = 0.2                 # narration starts this long after its shot starts
MARGIN_S = 0.5               # spoken length must be <= shot length - this
MAX_TEMPO = 1.08

BG = (244, 245, 247)
INK = (24, 28, 35)
MUTED = (96, 104, 116)
BAND = (16, 20, 26, 225)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for name in (["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def ff(*args: str, quiet: bool = True) -> None:
    cmd = [FFMPEG, "-hide_banner", "-y", *args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ffmpeg failed ({r.returncode}):\n{' '.join(cmd)}\n{r.stderr[-2500:]}")


def media_duration(path: Path) -> float:
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# ---------------------------------------------------------------- narration
def narrate(shot: dict, line: str, name: str, dry: bool) -> dict:
    """WAV for one line, silence trimmed at both ends, sped up a little if it runs long. Returns a check row."""
    adir = BUILD / "audio"
    adir.mkdir(parents=True, exist_ok=True)
    raw, trimmed = adir / f"{name}_raw.wav", adir / f"{name}.wav"
    slot = shot["end"] - shot["start"] - MARGIN_S
    words = len(line.split())
    if dry:
        est = words / 2.4
        ff("-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", f"{est:.2f}", "-c:a", "pcm_s16le", str(trimmed))
        return {"shot": name, "words": words, "spoken_s": round(est, 2), "slot_s": slot, "tempo": 1.0, "ok": est <= slot,
                "note": "dry: estimated at 2.4 words/s, silent"}
    sys.path.insert(0, str(ROOT))
    from backend.llm import for_job
    raw.write_bytes(for_job("narrate").speak(line, label=f"video {name}"))
    trim = ("silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.05,areverse,"
            "silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.05,areverse")
    ff("-i", str(raw), "-af", trim, "-c:a", "pcm_s16le", str(trimmed))
    spoken, tempo = wav_seconds(trimmed), 1.0
    if spoken > slot and spoken / slot <= MAX_TEMPO:
        tempo = spoken / slot + 0.005
        sped = adir / f"{name}_tempo.wav"
        ff("-i", str(trimmed), "-af", f"atempo={tempo:.3f}", "-c:a", "pcm_s16le", str(sped))
        shutil.move(sped, trimmed)
        spoken = wav_seconds(trimmed)
    return {"shot": name, "words": words, "spoken_s": round(spoken, 2), "slot_s": slot, "tempo": round(tempo, 3),
            "ok": spoken <= slot + 0.01, "note": "" if spoken <= slot + 0.01 else "TOO LONG: shorten the line"}


# ---------------------------------------------------------------- cards and overlays
def card_html(kind: str, c: dict) -> str:
    base = """<!doctype html><meta charset="utf-8"><style>
      html,body{margin:0;width:1920px;height:1080px;font-family:'Segoe UI',Arial,sans-serif;color:#181c23;
        background:radial-gradient(circle at 30% 20%,#ffffff 0,#eef1f5 55%,#e3e8ef 100%)}
      .wrap{position:absolute;inset:0 0 150px 0;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center}
      h1{font-size:150px;font-weight:700;margin:0;letter-spacing:-2px} h2{font-size:64px;font-weight:600;margin:0 0 40px}
      .sub{font-size:52px;color:#2b5fd9;margin-top:18px} .small{font-size:30px;color:#606874;margin-top:36px;max-width:1500px}
      table{font-size:60px;border-collapse:collapse} td{padding:14px 40px} td.n{font-weight:700;text-align:right}
      tr.us td{color:#1f7a45} .row{display:flex;gap:90px;align-items:center} .lines div{font-size:52px;margin:14px 0;text-align:left}
      img{width:330px;height:330px;image-rendering:pixelated;border:14px solid #fff;border-radius:18px}
    </style>"""
    if kind == "title":
        body = f'<div class="wrap"><h1>{c["title"]}</h1><div class="sub">{c["sub"]}</div><div class="small">{c["small"]}</div></div>'
    elif kind == "results":
        rows = "".join(f'<tr class="{"us" if i == 0 else ""}"><td>{a}</td><td class="n">{b}</td></tr>' for i, (a, b) in enumerate(c["rows"]))
        body = f'<div class="wrap"><h2>{c["title"]}</h2><table>{rows}</table><div class="small">{c["small"]}</div></div>'
    else:
        qr = (ROOT / c["qr"]).as_uri()
        lines = "".join(f"<div>{x}</div>" for x in c["lines"])
        body = (f'<div class="wrap"><h1 style="font-size:110px;margin-bottom:40px">{c["title"]}</h1>'
                f'<div class="row"><img src="{qr}"><div class="lines">{lines}</div></div><div class="small">{c["small"]}</div></div>')
    return base + body


def shot_overlay(shot: dict, caption: str, path: Path) -> None:
    """RGBA layer on top of everything in the shot: caption band, step label (desktop), nothing else."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, CAPTION_TOP, W, H], fill=BAND)
    f = font(40)
    lines = textwrap.wrap(caption, 78)[:2]
    y = CAPTION_TOP + (H - CAPTION_TOP - 50 * len(lines)) // 2
    for ln in lines:
        w = d.textlength(ln, font=f)
        d.text(((W - w) / 2, y), ln, font=f, fill=(255, 255, 255, 255))
        y += 50
    if shot["layout"] == "desktop" and shot.get("label"):
        lf = font(30, bold=True)
        d.rounded_rectangle([24, CAPTION_TOP + 16, 24 + d.textlength(shot["label"], font=lf) + 36, CAPTION_TOP + 66], 12, fill=(43, 95, 217, 255))
        d.text((42, CAPTION_TOP + 20), shot["label"], font=lf, fill=(255, 255, 255, 255))
    img.save(path)


def shot_background(shot: dict, path: Path) -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    if shot["layout"] == "phone":
        x0, y0, x1, y1 = PHONE_BOX
        d.rounded_rectangle([x0 - 16, y0 - 16, x1 + 16, y1 + 16], 44, fill=(28, 30, 36))
        d.text((1010, 330), shot.get("label", ""), font=font(92, bold=True), fill=INK)
        d.text((1014, 460), shot.get("sub", ""), font=font(46), fill=MUTED)
    img.save(path)


def tag_layer(text: str, path: Path) -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font(30, bold=True)
    w = d.textlength(text, font=f)
    d.rounded_rectangle([W - w - 70, 28, W - 28, 82], 12, fill=(16, 20, 26, 200))
    d.text((W - w - 50, 33), text, font=f, fill=(255, 255, 255, 255))
    img.save(path)


# ---------------------------------------------------------------- capture
def run_capture(spec: dict, dry: bool) -> dict:
    cdir = BUILD / "capture"
    if cdir.exists():
        shutil.rmtree(cdir)
    cards = BUILD / "cards"
    cards.mkdir(parents=True, exist_ok=True)
    jobs = []
    for cid, c in spec["captures"].items():
        if "card" in c:
            html = cards / f"{c['card']}.html"
            html.write_text(card_html(c["card"], spec["cards"][c["card"]]), encoding="utf-8")
            url, view = html.as_uri(), spec["views"]["card"]
        else:
            url, view = spec["base"] + c["url"].replace("{run}", spec["run_id"]), spec["views"][c["view"]]
        steps = c.get("steps") or (c.get("dry_steps") if dry else c.get("model_steps")) or []
        jobs.append({"id": cid, "url": url, "width": view["width"], "height": view["height"], "dsf": view["dsf"],
                     "mobile": view["mobile"], "wait_ms": c.get("wait_ms", 3500 if "card" not in c else 800),
                     "steps": steps, "mode": c["mode"], "out_dir": str(cdir / cid), "expect": c.get("expect", []),
                     "read": c.get("read", {})})
    jf = BUILD / "jobs.json"
    jf.write_text(json.dumps(jobs, indent=1), encoding="utf-8")
    profile = BUILD / "chrome-profile"
    log("capture: headless Chrome")
    r = subprocess.run(["node", str(HERE / "shoot.mjs"), str(jf), str(profile)], cwd=ROOT)
    if r.returncode != 0:
        sys.exit("capture failed")
    return {cid: json.loads((cdir / cid / "meta.json").read_text(encoding="utf-8")) for cid in spec["captures"]}


def frame_list(meta: dict, cdir: Path, dur: float, fit: str, head_s: float) -> tuple[Path | None, str]:
    """ffconcat file for a recorded capture, fitted to `dur` seconds. Returns (list path, on-screen tag)."""
    frames = meta.get("frames") or []
    if len(frames) < 10 or not meta.get("start_t"):
        return None, ""
    t0, L = meta["start_t"], meta["end_t"] - meta["start_t"]
    pts = [(max(0.0, f["t"] - t0), f["f"]) for f in frames]
    tag = ""
    if fit == "head_tail" and L > dur:
        cut = L - dur
        keep = [(t, f) for t, f in pts if t <= head_s]
        tail = [(t - cut, f) for t, f in pts if t >= head_s + cut]
        before = [f for t, f in pts if t < head_s + cut]
        if before:
            tail.insert(0, (head_s, before[-1]))
        pts = keep + tail
        tag = f"Wait cut: {cut:.0f} s"
    elif L > dur:
        k = L / dur
        pts = [(t / k, f) for t, f in pts]
        if k > 1.15:
            tag = f"Sped up ×{k:.1f}"
    pts.sort()
    start = [f for t, f in pts if t <= 0.0001]
    pts = ([(0.0, start[-1])] if start else []) + [(t, f) for t, f in pts if 0.0001 < t < dur]
    if pts[0][0] > 0:
        pts.insert(0, (0.0, pts[0][1]))
    lines = ["ffconcat version 1.0"]
    for i, (t, f) in enumerate(pts):
        nxt = pts[i + 1][0] if i + 1 < len(pts) else dur
        lines += [f"file '{(cdir / f).as_posix()}'", f"duration {max(nxt - t, 0.001):.4f}"]
    lines.append(f"file '{(cdir / pts[-1][1]).as_posix()}'")
    lf = cdir / "list.ffconcat"
    lf.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lf, tag


def render_part(i: int, shot: dict, part: dict, spec: dict, metas: dict, opening: Path | None) -> Path:
    pdir = BUILD / "parts"
    pdir.mkdir(parents=True, exist_ok=True)
    out = pdir / f"{i:02d}_{shot['id']}.mp4"
    dur = part["dur"]
    bg, ov = pdir / f"{i:02d}_bg.png", pdir / f"{i:02d}_ov.png"
    cap = spec["captures"].get(part.get("capture", ""), {})
    full = part.get("source") == "generated" or "card" in cap
    layout = "full" if full else shot["layout"]
    shot_background({**shot, "layout": layout}, bg)
    shot_overlay({**shot, "layout": layout}, shot["_caption"], ov)
    box = {"phone": PHONE_BOX, "desktop": DESK_BOX}.get(layout, (0, 0, W, H))
    bw, bh = box[2] - box[0], box[3] - box[1]
    tag = part.get("tag", "")
    content: list[str]
    zoom = False
    if part.get("source") == "generated":
        if opening and opening.exists():
            content = ["-an", "-t", f"{dur}", "-i", str(opening)]
        else:  # dry run or the opening failed: the title card stands in, still labelled
            content = ["-loop", "1", "-t", f"{dur}", "-i", str(BUILD / "capture" / "card_title" / "still.png")]
            tag = tag + " (stand-in)" if opening is None else "Opening clip failed: title card"
    else:
        meta = metas[part["capture"]]
        cdir = BUILD / "capture" / part["capture"]
        lf, ftag = (None, "")
        if cap.get("mode") == "record":
            lf, ftag = frame_list(meta, cdir, dur, cap.get("fit", "speed"), cap.get("head_s", 1.5))
        tag = tag or ftag
        if lf:
            content = ["-f", "concat", "-safe", "0", "-i", str(lf)]
        else:
            content = ["-i", str(cdir / "still.png")]
            zoom = not full
    filt = f"[1:v]scale={bw}:{bh}:force_original_aspect_ratio=decrease,pad={bw}:{bh}:(ow-iw)/2:(oh-ih)/2:color=0xF4F5F7,setsar=1"
    if zoom:
        n = int(round(dur * FPS))
        filt = (f"[1:v]scale={bw * 2}:{bh * 2}:force_original_aspect_ratio=decrease,"
                f"zoompan=z='1+0.04*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s={bw}x{bh}:fps={FPS},setsar=1")
    inputs = ["-loop", "1", "-t", f"{dur}", "-i", str(bg), *content, "-loop", "1", "-t", f"{dur}", "-i", str(ov)]
    filt += f"[c];[0:v][c]overlay={box[0]}:{box[1]}:shortest=0[b];[b][2:v]overlay=0:0"
    if tag:
        tg = pdir / f"{i:02d}_tag.png"
        tag_layer(tag, tg)
        inputs += ["-loop", "1", "-t", f"{dur}", "-i", str(tg)]
        filt += "[d];[d][3:v]overlay=0:0"
    if "card" in cap and part.get("capture") == "card_title" and shot["id"] == "S1":
        filt += ",fade=t=in:st=0:d=0.4"
    filt += f",fps={FPS},scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,trim=duration={dur}[v]"
    ff(*inputs, "-filter_complex", filt, "-map", "[v]", "-t", f"{dur}", "-r", str(FPS),
       "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-color_range", "tv", "-colorspace", "bt709",
       "-color_primaries", "bt709", "-color_trc", "bt709", "-an", str(out))
    got = media_duration(out)
    if abs(got - dur) > 0.06:
        sys.exit(f"{out.name}: {got:.2f} s, expected {dur}")
    return out


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="no model calls: silent narration, no Neon click, no generated opening")
    ap.add_argument("--skip-capture", action="store_true")
    ap.add_argument("--narration-only", action="store_true")
    ap.add_argument("--force", action="store_true", help="render even if a page check fails")
    a = ap.parse_args()
    spec = json.loads((HERE / "shots.json").read_text(encoding="utf-8"))
    shots = spec["shots"]
    assert abs(shots[-1]["end"] - spec["length_s"]) < 1e-6 and all(
        abs(sum(p["dur"] for p in s["parts"]) - (s["end"] - s["start"])) < 1e-6 for s in shots), "shot times don't add up"
    BUILD.mkdir(parents=True, exist_ok=True)
    FINAL.mkdir(parents=True, exist_ok=True)

    # 1. Opening clip in the background (1-3 minutes), so it overlaps narration and capture.
    opening_path = BUILD / "opening.mp4"
    opening_err: list[str] = []
    th = None
    if not a.dry and not a.narration_only and any(p.get("source") == "generated" for s in shots for p in s["parts"]):
        def make_opening() -> None:
            try:
                sys.path.insert(0, str(ROOT))
                from backend.llm import for_job
                opening_path.write_bytes(for_job("video_open").generate_video(spec["open_prompt"], label="video opening"))
            except Exception as e:  # noqa: BLE001 - fall back to the title card, keep building
                opening_err.append(str(e)[:300])
        log("opening: gemini-omni-1.2-flash, in the background")
        th = threading.Thread(target=make_opening, daemon=True)
        th.start()

    # 2. Narration, one clip per shot (does not need the footage).
    rows = []
    for s in shots:
        log(f"narration {s['id']}")
        rows.append(narrate(s, s["line"], s["id"], a.dry))
    check = BUILD / "narration_check.txt"

    def write_check() -> None:
        txt = "shot  words  spoken_s  slot_s  tempo  ok\n" + "\n".join(
            f"{r['shot']:<5} {r['words']:>5} {r['spoken_s']:>9} {r['slot_s']:>7} {r['tempo']:>6}  {'ok' if r['ok'] else 'NO'} {r['note']}" for r in rows)
        check.write_text(txt + "\n", encoding="utf-8")
        print(txt)
    write_check()
    if not all(r["ok"] for r in rows):
        sys.exit("a narration clip is longer than its shot; shorten the line in shots.json")
    if a.narration_only:
        return

    # 3. Capture.
    metas = {cid: json.loads((BUILD / "capture" / cid / "meta.json").read_text(encoding="utf-8")) for cid in spec["captures"]} \
        if a.skip_capture else run_capture(spec, a.dry)
    problems = []
    use_alt = set()
    for cid, m in metas.items():
        for e in m.get("errors", []):
            problems.append(f"{cid}: {e}")
        for c in m.get("checks", []):
            if not c["ok"]:
                if c.get("else") == "alt":
                    use_alt.add(cid)
                else:
                    problems.append(f"{cid}: page does not show {c['text']!r} ({c.get('got', 'body text')})")
    for cid, m in metas.items():
        if m.get("read"):
            log(f"{cid} read: {m['read']}")
    if problems:
        print("\n".join("CHECK: " + p for p in problems))
        if not a.force:
            sys.exit("page checks failed; fix the line or the page, or run with --force")

    # 4. Alternative lines where the page did not show what the main line says.
    for s in shots:
        s["_caption"] = s["line"]
        if any(p.get("capture") in use_alt for p in s["parts"]) and s.get("alt_line"):
            if a.dry:
                log(f"{s['id']}: dry run, the page would need the alternative line")
            else:
                log(f"{s['id']}: the page did not show the main line's claim; using the alternative line")
                rows = [r for r in rows if r["shot"] != s["id"]] + [narrate(s, s["alt_line"], s["id"], False)]
                write_check()
                s["_caption"] = s["alt_line"]

    # 5. Opening.
    if th:
        log("waiting for the opening clip")
        th.join(timeout=600)
        if opening_err or not opening_path.exists():
            log(f"opening failed, the title card stands in: {opening_err}")
    opening = None if a.dry else opening_path

    # 6. Video parts.
    parts = []
    for s in shots:
        for p in s["parts"]:
            log(f"render {s['id']} {p.get('capture', p.get('source'))} ({p['dur']} s)")
            parts.append(render_part(len(parts), s, p, spec, metas, opening))
    lst = BUILD / "parts.ffconcat"
    lst.write_text("ffconcat version 1.0\n" + "".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")

    # 7. Audio: every narration clip at its shot's start + LEAD_S, padded to the full length, loudness -16 LUFS.
    ins, delays = [], []
    for k, s in enumerate(shots):
        ins += ["-i", str(BUILD / "audio" / f"{s['id']}.wav")]
        ms = int(round((s["start"] + LEAD_S) * 1000))
        delays.append(f"[{k}:a]aresample=48000,adelay={ms}|{ms}[a{k}]")
    mix = ";".join(delays) + ";" + "".join(f"[a{k}]" for k in range(len(shots))) + \
        f"amix=inputs={len(shots)}:normalize=0,apad,atrim=0:{spec['length_s']}" + \
        ("" if a.dry else ",loudnorm=I=-16:TP=-1.5:LRA=11") + "[out]"
    audio = BUILD / "narration.wav"
    ff(*ins, "-filter_complex", mix, "-map", "[out]", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(audio))

    # 8. Join.
    name = "pack-it-up-60s-DRY.mp4" if a.dry else "pack-it-up-60s.mp4"
    final = FINAL / name
    ff("-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(audio), "-map", "0:v", "-map", "1:a",
       "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", str(spec["length_s"]), "-movflags", "+faststart", str(final))
    got = media_duration(final)
    log(f"final: {final} ({got:.2f} s)")
    if abs(got - spec["length_s"]) > 0.1:
        sys.exit(f"final length {got:.2f} s, expected {spec['length_s']}")

    # 9. Sheets to look at before upload.
    ff("-i", str(final), "-vf", "fps=0.5,scale=384:-1,tile=6x5:padding=4", "-frames:v", "1", str(FINAL / "contact_sheet.jpg"))
    items = [p for p in parts if "_S4" in p.name]
    if items:
        ff("-i", str(items[0]), "-vf", "fps=2,scale=640:-1,tile=4x3:padding=4", "-frames:v", "1", str(FINAL / "thumbs_sheet.jpg"))
    shutil.copy(check, FINAL / "narration_check.txt")
    log(f"done: {FINAL}")


if __name__ == "__main__":
    main()
