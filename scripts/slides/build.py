"""Makes the judging slide deck with Gemini: frontend/slides/index.html (served at /app/slides/).

    .venv\\Scripts\\python.exe -m scripts.slides.build             # capture screenshots, generate, check, render
    options: --skip-capture (reuse the screenshots), --fresh (ask the model again instead of using the cache),
             --render-only (re-render the committed deck to PNG and PDF),
             --revise (Gemini fixes the current deck using scripts/slides/revise.md, keeping its design)

Gemini 4 Carbon (job `slides` in backend/llm/models.toml) writes all the copy and the design from
scripts/slides/brief.md (facts) and scripts/slides/prompt.md (format), looking at real screenshots of the app.
Nobody hand-edits the HTML: change the brief or the prompt and run this again (AGENTS.md, "Demo and presentation
outputs are made by Gemini"). Screenshots go to frontend/slides/shots/ (git-ignored); review renders go to
.cache/slides/. Needs the demo API on 127.0.0.1:8000, Node 22+ and Chrome.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html as htmllib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DECK_DIR = ROOT / "frontend" / "slides"
SHOTS = DECK_DIR / "shots"
REVIEW = ROOT / ".cache" / "slides"
SHOOT = ROOT / "scripts" / "video" / "shoot.mjs"
BASE = "http://127.0.0.1:8000"
RUN = "20261121-133201-gibbs-ee2a93"
CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe"
N_SLIDES = 8

PHONE = {"width": 390, "height": 844, "dsf": 2, "mobile": True}
DESK = {"width": 1280, "height": 860, "dsf": 1.5, "mobile": False}

# name, description for the model, view, url, steps
IMAGES = [
    ("capture.png", "Phone, capture page: two rooms filmed (a clip and a photo each), each file read in about 20-35 s, "
     "footer '52 items + 16 boxes in 2 rooms' and the 'Plan the truck load' button", PHONE,
     f"/app/capture.html?run_id={RUN}&who=Demo", [{"js": "__v.sleep(300)"}]),
    ("review_answers.png", "Phone, review page with the answered gap questions open: answers from the Decisions API "
     "and answers given by the person", PHONE, f"/app/review.html?run_id={RUN}&who=Demo",
     [{"js": "__v.clickText('answered · see or change')"}, {"js": "__v.sleep(600)"},
      {"js": "__v.scrollToText('Answered by the Decisions API', 330, 1)"}, {"js": "__v.sleep(400)"}]),
    ("review_items.png", "Phone, review page item list: thumbnails, sizes, weights, handling tags, Move / Stays / Sell "
     "/ Toss, an upright piano added by the person", PHONE, f"/app/review.html?run_id={RUN}&who=Demo",
     [{"js": "__v.scrollToText('added by you', 330, 1)"}, {"js": "__v.sleep(400)"}]),
    ("plan_neon.png", "Laptop, 3D plan after 'Plan with Neon': headline with the truck count and 0 rule violations, "
     "the 3D truck, and Neon's rounds with the score of each", DESK, f"/app/index.html?run_id={RUN}&who=Demo",
     [{"js": "__v.sleep(500)"}, {"js": "__v.click('#btn-plan')"},
      {"js": "__v.waitFor(() => !document.querySelector('#planner-rounds').classList.contains('hidden'), 150000)"},
      {"js": "__v.sleep(2500)"}]),
    ("models.png", "Laptop, models page: which Gemini model did each job for this move, with calls, time and tokens",
     DESK, f"/app/models.html?run_id={RUN}&who=Demo", [{"js": "__v.sleep(300)"}]),
]
ALLOWED_IMAGES = {name for name, *_ in IMAGES} | {"qr.png"}


def log(msg: str) -> None:
    print(dt.datetime.now().strftime("%H:%M:%S"), msg, flush=True)


def shoot(jobs: list[dict], tag: str) -> None:
    jf = REVIEW / f"{tag}_jobs.json"
    jf.write_text(json.dumps(jobs, indent=1), encoding="utf-8")
    r = subprocess.run(["node", str(SHOOT), str(jf), str(REVIEW / "chrome-profile")], cwd=ROOT)
    if r.returncode != 0:
        sys.exit("headless Chrome failed")


def capture() -> None:
    log("capture: screenshots of the running app")
    tmp = REVIEW / "capture"
    jobs = [{"id": name, "url": BASE + url, **view, "wait_ms": 7000 if "index" in url else 3500, "steps": steps,
             "mode": "still", "out_dir": str(tmp / name)} for name, _, view, url, steps in IMAGES]
    shoot(jobs, "capture")
    SHOTS.mkdir(parents=True, exist_ok=True)
    for name, *_ in IMAGES:
        meta = json.loads((tmp / name / "meta.json").read_text(encoding="utf-8"))
        if meta["errors"]:
            sys.exit(f"{name}: {meta['errors']}")
        shutil.copy(tmp / name / "still.png", SHOTS / name)
    shutil.copy(ROOT / "plan" / "demo_qr.png", DECK_DIR / "qr.png")


def visible_text(doc: str) -> str:
    doc = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", doc)
    doc = re.sub(r"(?s)<!--.*?-->", " ", doc)
    return htmllib.unescape(re.sub(r"<[^>]+>", " ", doc))


def check(doc: str, brief: str) -> list[str]:
    errs = []
    if not re.match(r"(?is)\s*<!doctype html", doc):
        errs.append("the file must start with <!doctype html>")
    n = len(re.findall(r'<section[^>]*class="[^"]*\bslide\b', doc))
    if n != N_SLIDES:
        errs.append(f"found {n} <section class=\"slide\"> elements, need exactly {N_SLIDES}")
    sections = re.split(r'(?i)<section\b', doc)[1:]
    no_qr = [str(i + 1) for i, sec in enumerate(sections) if 'qr.png' not in sec.split('</section>')[0]]
    if no_qr:
        errs.append(f"slides without the QR code (qr.png): {', '.join(no_qr)}; every slide must show it")
    for src in re.findall(r'(?i)<img[^>]+src="([^"]+)"', doc):
        if src.removeprefix("shots/") not in ALLOWED_IMAGES or (src.startswith("shots/") and src == "shots/qr.png"):
            errs.append(f"image {src!r} is not one of the listed files")
    if re.search(r'(?i)<script[^>]+src=', doc):
        errs.append("external <script src> is not allowed")
    for url in re.findall(r'(?i)(?:href|src)="(https?://[^"]+)"', doc):
        if not re.match(r"https://fonts\.(googleapis|gstatic)\.com(/|$)", url) and url.rstrip("/") not in (
                "https://packitup.temperedanalytics.com", "https://github.com/TallGibbs/Pack-It-Up"):
            errs.append(f"external resource {url!r} is not allowed")
    allowed = set(re.findall(r"\d+(?:\.\d+)?", brief)) | {"1", "2", "3", "4", "5", "6", "7", "8"}
    norm = lambda x: x.lstrip("0") or "0"  # "01" on a step badge is 1
    allowed = {norm(x) for x in allowed}
    bad = sorted({x for x in re.findall(r"\d+(?:\.\d+)?", visible_text(doc)) if norm(x) not in allowed})
    if bad:
        errs.append(f"numbers on the slides that are not in the brief: {', '.join(bad)}")
    return errs


def generate(fresh: bool, revise: bool = False) -> str:
    sys.path.insert(0, str(ROOT))
    from backend.llm import for_job, media_from_path
    brief = (HERE / "brief.md").read_text(encoding="utf-8")
    images = "\n".join(f"{i + 1}. `shots/{name}` ({_size(SHOTS / name)}): {desc}" for i, (name, desc, *_) in enumerate(IMAGES))
    prompt = ((HERE / "prompt.md").read_text(encoding="utf-8") +
              f"\n\n## Images (attached in this order)\n\n{images}\n{len(IMAGES) + 1}. `qr.png` (square): QR code for "
              f"https://packitup.temperedanalytics.com (not attached)\n\n## Brief\n\n{brief}")
    if revise:
        prompt += ("\n\n## Your current deck (revise it; return the whole file)\n\n"
                   + (DECK_DIR / "index.html").read_text(encoding="utf-8")
                   + "\n\n" + (HERE / "revise.md").read_text(encoding="utf-8"))
    media = [media_from_path(SHOTS / name) for name, *_ in IMAGES]
    job = for_job("slides")
    pv = ("slides_revise" if revise else "slides_v1") + (dt.datetime.now().strftime("_%H%M%S") if fresh else "")
    for attempt in (1, 2):
        log(f"generate: {job} (attempt {attempt}, prompt version {pv})")
        out = job.generate_text(prompt, media=media, prompt_version=pv, label="slide deck")
        doc = re.sub(r"^\s*```(?:html)?\s*|\s*```\s*$", "", out.strip())
        errs = check(doc, brief)
        if not errs:
            return doc
        log("check failed: " + " | ".join(errs))
        prompt += "\n\n## Your previous file failed these checks; fix them and return the whole file again\n\n" + \
                  "\n".join(f"- {e}" for e in errs)
        pv += "_retry"
    sys.exit("the deck failed its checks twice; see the messages above")


def _size(p: Path) -> str:
    from PIL import Image
    with Image.open(p) as im:
        return f"{im.width}×{im.height} px"


def render() -> None:
    log("render: one PNG per slide and a PDF, for review")
    jobs = [{"id": f"slide_{n}", "url": f"{BASE}/app/slides/index.html?r={n}#slide={n}", "width": 1920, "height": 1080,
             "dsf": 1, "mobile": False, "wait_ms": 2500, "steps": [], "mode": "still",
             "out_dir": str(REVIEW / "render" / f"slide_{n}")} for n in range(1, N_SLIDES + 1)]
    shoot(jobs, "render")
    for n in range(1, N_SLIDES + 1):
        shutil.copy(REVIEW / "render" / f"slide_{n}" / "still.png", REVIEW / f"slide_{n}.png")
    pdf = REVIEW / "pack-it-up-slides.pdf"
    subprocess.run([CHROME, "--headless=new", "--no-pdf-header-footer", f"--print-to-pdf={pdf}",
                    f"--user-data-dir={REVIEW / 'chrome-pdf'}", f"{BASE}/app/slides/index.html"],
                   capture_output=True, timeout=120)
    log(f"review: {REVIEW} (slide_1.png .. slide_{N_SLIDES}.png, {pdf.name if pdf.exists() else 'no PDF'})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-capture", action="store_true")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--revise", action="store_true", help="Gemini revises the current deck with scripts/slides/revise.md")
    a = ap.parse_args()
    REVIEW.mkdir(parents=True, exist_ok=True)
    DECK_DIR.mkdir(parents=True, exist_ok=True)
    if not a.render_only:
        if not a.skip_capture:
            capture()
        doc = generate(a.fresh, a.revise)
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        header = (f"<!-- Generated by Gemini 4 Carbon (job `slides`, backend/llm/models.toml) on {stamp} from "
                  f"scripts/slides/brief.md and prompt.md. Do not edit by hand: run python -m scripts.slides.build. -->\n")
        doc = re.sub(r"(?is)^(\s*<!doctype html>\s*)", lambda m: m.group(1) + header, doc, count=1)
        (DECK_DIR / "index.html").write_text(doc, encoding="utf-8")
        log(f"wrote {DECK_DIR / 'index.html'} ({len(doc):,} characters)")
    render()


if __name__ == "__main__":
    main()
