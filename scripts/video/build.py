"""Builds the 60 s submission video from scripts/video/shots.json (plan: plan/VIDEO_SCRIPT.md).

    .venv\\Scripts\\python.exe -m scripts.video.build --write-script   # Gemini writes the lines and cards (script.json)
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
SCRIPT = HERE / "script.json"
FACTS = ROOT / "scripts" / "slides" / "brief.md"
_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
         "seventeen eighteen nineteen").split()
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def numbers_in(text: str) -> set[str]:
    """Digits and spelled-out numbers (up to ninety-nine) in a piece of text, as digit strings."""
    found = set(re.findall(r"\d+(?:\.\d+)?", text))
    pat = (r"\b(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](one|two|three|four|five|six|seven|eight|nine))?\b"
           r"|\b(" + "|".join(_ONES) + r")\b")
    for m in re.finditer(pat, text.lower()):
        if m.group(1):
            found.add(str(_TENS[m.group(1)] + (_ONES.index(m.group(2)) if m.group(2) else 0)))
        else:
            found.add(str(_ONES.index(m.group(3))))
    return found


def visible_text(doc: str) -> str:
    import html as htmllib
    doc = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", doc)
    return htmllib.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<!--.*?-->", " ", doc)))


def check_script(sc: dict, spec: dict, facts: str) -> list[str]:
    errs = []
    allowed = numbers_in(facts) | {str(n) for n in range(0, 9)}
    budgets = {s["id"]: s["words_max"] for s in spec["shots"]} | {"S6_alt": 16}
    lines = sc.get("lines") or {}
    cards = sc.get("cards") or {}
    for sid, mx in budgets.items():
        line = lines.get(sid, "")
        n = len(line.split())
        if not line:
            errs.append(f"line {sid} is missing")
        elif n > mx:
            errs.append(f"line {sid} has {n} words, the limit is {mx}")
        bad = sorted(numbers_in(line) - allowed)
        if bad:
            errs.append(f"line {sid} has numbers not in the facts: {bad}")
    if "venue" not in lines.get("S7", "").lower():
        errs.append("line S7 must say the footage is mostly venue rooms")
    for kind in ("title", "results", "end"):
        doc = cards.get(kind, "")
        if not re.match(r"(?is)\s*<!doctype html", doc):
            errs.append(f"card {kind} must be a complete HTML page starting with <!doctype html>")
            continue
        for src in re.findall(r'(?i)<img[^>]+src="([^"]+)"', doc):
            if src != "qr.png" or kind != "end":
                errs.append(f"card {kind} uses image {src!r}; only qr.png, on the end card")
        if re.search(r"(?i)<script[^>]+src=", doc):
            errs.append(f"card {kind} loads an external script")
        for url in re.findall(r'(?i)(?:href|src)="(https?://[^"]+)"', doc):
            if not re.match(r"https://fonts\.(googleapis|gstatic)\.com(/|$)", url):
                errs.append(f"card {kind} loads {url!r}")
        bad = sorted(numbers_in(visible_text(doc)) - allowed - {"1920", "1080"})
        if bad:
            errs.append(f"card {kind} has numbers not in the facts: {bad}")
    if 'src="qr.png"' not in cards.get("end", ""):
        errs.append("the end card must show qr.png")
    return errs


_KEYS = ["S1", "S2", "S3", "S4", "S5", "S6", "S6_alt", "S7", "S8"]
SCRIPT_SCHEMA = {
    "type": "object", "required": ["lines", "cards"],
    "properties": {
        "lines": {"type": "object", "required": _KEYS, "properties": {k: {"type": "string"} for k in _KEYS}},
        "cards": {"type": "object", "required": ["title", "results", "end"],
                  "properties": {k: {"type": "string", "description": "complete HTML page, 1920x1080"}
                                 for k in ["title", "results", "end"]}},
    },
}


def write_script(spec: dict, fresh: bool) -> None:
    """Gemini writes the narration lines and the three cards; checked, then saved to script.json."""
    sys.path.insert(0, str(ROOT))
    from backend.llm import for_job
    facts = FACTS.read_text(encoding="utf-8")
    prompt = ("You write the narration and the text cards for a 60-second hackathon demo video. Follow the brief "
              "exactly; use only facts and numbers from the facts file. Return JSON: `lines` (S1..S8 and S6_alt, each "
              "one spoken line) and `cards` (title, results, end: each a complete HTML page).\n\n# Brief\n\n"
              + (HERE / "brief.md").read_text(encoding="utf-8") + "\n\n# Facts\n\n" + facts)
    job = for_job("video_script")
    pv = "video_script_v1" + (time.strftime("_%H%M%S") if fresh else "")
    for attempt in (1, 2):
        log(f"script: {job} (attempt {attempt})")
        sc = job.generate_json(prompt, schema=SCRIPT_SCHEMA, prompt_version=pv, label="video script")
        errs = check_script(sc, spec, facts)
        if not errs:
            out = {"_made_by": f"{job.spec} (job video_script) on {time.strftime('%Y-%m-%d %H:%M')} from "
                               "scripts/video/brief.md and scripts/slides/brief.md. Do not edit by hand: run "
                               "python -m scripts.video.build --write-script.", **sc}
            SCRIPT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            for k, v in sc["lines"].items():
                print(f"  {k} ({len(v.split())} words): {v}")
            log(f"wrote {SCRIPT}")
            return
        log("script check failed: " + " | ".join(errs))
        prompt += ("\n\n# Your previous answer failed these checks; fix them and answer again\n\n"
                   + "\n".join(f"- {e}" for e in errs))
        pv += "_retry"
    sys.exit("the script failed its checks twice")


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
            html.write_text(spec["_script"]["cards"][c["card"]], encoding="utf-8")
            shutil.copy(ROOT / "plan" / "demo_qr.png", cards / "qr.png")
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
    ap.add_argument("--write-script", action="store_true", help="have Gemini write the lines and cards (script.json), then stop")
    ap.add_argument("--fresh", action="store_true", help="with --write-script: ask the model again instead of using the cache")
    a = ap.parse_args()
    spec = json.loads((HERE / "shots.json").read_text(encoding="utf-8"))
    shots = spec["shots"]
    if a.write_script:
        write_script(spec, a.fresh)
        return
    if not SCRIPT.exists():
        sys.exit("no script.json yet: run python -m scripts.video.build --write-script first (Gemini writes it)")
    spec["_script"] = json.loads(SCRIPT.read_text(encoding="utf-8"))
    errs = check_script(spec["_script"], spec, FACTS.read_text(encoding="utf-8"))
    if errs:
        sys.exit("script.json fails its checks: " + " | ".join(errs))
    for s_ in shots:
        s_["line"] = spec["_script"]["lines"][s_["id"]]
        if s_.get("alt"):
            s_["alt_line"] = spec["_script"]["lines"][s_["alt"]]
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
