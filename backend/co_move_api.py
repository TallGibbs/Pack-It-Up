"""HTTP routes for Human + Robot Co-Move Biomechanics, Penn Station Occupancy,
and live `gemini-robotics-er-2-preview` spatial `[y, x]` scanning.
"""
from __future__ import annotations

import base64
import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field

from backend import co_move, solver
from backend.ingest.common import run_dir
from backend.llm import media as mu
from backend.pack_api import _list_nypenn_files, _load_inventory_for_run

router = APIRouter(prefix="/co-move", tags=["co-move"])

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_CACHE_DIR = REPO_ROOT / ".cache" / "co_move_scans"


class CoMoveAnalyzeRequest(BaseModel):
    run_id: str | None = "sample_venue"
    plan: dict[str, Any] | None = None
    strategy: dict[str, Any] | None = None
    occupancy_mode: str = "permitted_bays"


class RoboticsScanRequest(BaseModel):
    run_id: str | None = "sample_venue"
    target: str = Field(default="origin", pattern="^(origin|destination)$")
    image_base64: str | None = None
    mime_type: str | None = "image/jpeg"
    context_hint: str = ""


def _render_diagram_scene(target: str, out_path: Path) -> Path:
    """Create a clean room or Moynihan concourse diagram image when no camera media is on disk."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        return out_path

    img = Image.new("RGB", (960, 540), (242, 240, 234) if target == "origin" else (232, 237, 244))
    d = ImageDraw.Draw(img)

    if target == "destination":
        # Moynihan Train Hall bay: commuter lane at top, existing espresso/kiosk counter left, clear bay right
        d.rectangle([20, 20, 940, 145], fill=(214, 222, 235), outline=(120, 136, 160), width=3)
        d.text((40, 68), "ACTIVE MOYNIHAN COMMUTER CONCOURSE & FDNY 96-IN EGRESS LANE (KEEP CLEAR)", fill=(50, 62, 82))
        # Escalator island
        d.rectangle([660, 40, 910, 128], fill=(186, 198, 218), outline=(92, 108, 134), width=2)
        d.text((682, 75), "TRACK 9-10 ESCALATOR ISLAND", fill=(40, 50, 70))
        # Existing cafe / retail counter inside bay
        d.rectangle([40, 185, 310, 495], fill=(198, 176, 152), outline=(118, 92, 68), width=3)
        d.text((68, 325), "EXISTING ESPRESSO BAR\n& FIXED POS COUNTER", fill=(65, 44, 28))
        # Movable clutter near bay entrance
        d.ellipse([345, 190, 420, 260], fill=(218, 154, 92), outline=(140, 82, 30), width=2)
        d.text((352, 218), "SIGN A-FRAME", fill=(70, 35, 10))
        # Permitted clear staging zone
        d.rectangle([455, 195, 910, 495], fill=(216, 238, 225), outline=(46, 134, 86), width=3)
        d.text((535, 330), "PERMITTED POP-UP STAGING ENVELOPE\n(AMR CART + 2-PERSON PLACEMENT)", fill=(24, 92, 54))
    else:
        # Origin venue lounge: exit door top-right, stools/poufs in path, stacked boxes, bespoke sofa & table
        d.rectangle([25, 25, 935, 515], outline=(110, 104, 96), width=4)
        # Exit doorway
        d.rectangle([805, 20, 915, 42], fill=(46, 144, 88))
        d.text((812, 48), "32-IN EXIT DOOR", fill=(28, 98, 58))
        # Bespoke Orior sofa (left)
        d.rectangle([65, 90, 290, 395], fill=(182, 160, 142), outline=(102, 82, 66), width=3)
        d.text((95, 225), "BESPOKE BOUCLE SOFA\n(90x38x32 in, 185 lb)", fill=(58, 42, 30))
        # Travertine communal table (bottom-center)
        d.rectangle([365, 315, 735, 475], fill=(208, 198, 184), outline=(115, 105, 92), width=3)
        d.text((435, 385), "COMMUNAL TABLE (UNBOLT LEGS)", fill=(62, 56, 48))
        # Floor obstacles blocking doorway path (poufs & stools)
        for idx, (cx, cy) in enumerate([(685, 165), (765, 210)], start=1):
            d.ellipse([cx - 34, cy - 34, cx + 34, cy + 34], fill=(224, 152, 96), outline=(142, 76, 28), width=2)
            d.text((cx - 24, cy - 8), f"POUF {idx}", fill=(68, 32, 10))
        # Uniform moving boxes & Pelican case near center-top
        for bx in (380, 465, 550):
            d.rectangle([bx, 85, bx + 72, 155], fill=(214, 184, 136), outline=(132, 98, 52), width=2)
            d.text((bx + 12, 114), "BOX 32lb", fill=(72, 50, 20))

    img.save(out_path, format="JPEG", quality=88)
    return out_path


def _resolve_scan_image(req: RoboticsScanRequest) -> tuple[Path, str]:
    """Resolve an image path on disk + data URL preview for the frontend overlay."""
    SCAN_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Explicit uploaded/captured base64 image from phone or browser
    if req.image_base64:
        raw_b64 = req.image_base64.split(",", 1)[-1].strip()
        try:
            raw_bytes = base64.b64decode(raw_b64)
            im = Image.open(BytesIO(raw_bytes)).convert("RGB")
            im.thumbnail((1280, 1280))
            digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
            out_p = SCAN_CACHE_DIR / f"upload_{digest}.jpg"
            im.save(out_p, format="JPEG", quality=86)
            buf = BytesIO()
            im.save(buf, format="JPEG", quality=82)
            return out_p, "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            raise HTTPException(400, f"Invalid uploaded image: {e}") from e

    # 2. Destination media in `data/NYPenn/` if present
    if req.target == "destination":
        nypenn = _list_nypenn_files()
        if nypenn:
            src = nypenn[0]
            if src.suffix.lower() in mu.VIDEO_EXT:
                frames = mu.sample_frames(src, SCAN_CACHE_DIR / f"nypenn_{src.stem}", fps=0.5, max_frames=1)
                if frames:
                    src = frames[0][1]
            im = Image.open(src).convert("RGB")
            im.thumbnail((1100, 1100))
            buf = BytesIO()
            im.save(buf, format="JPEG", quality=82)
            return src, "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

    # 3. Origin room media in `runs/<run_id>/uploads/` if present
    rid = (req.run_id or "").strip()
    if req.target == "origin" and rid and rid not in ("sample_venue", "sample", "mock-demo", "inline"):
        try:
            rd = run_dir(rid)
            up_dir = rd / "uploads"
            if up_dir.exists():
                candidates = sorted(
                    p for p in up_dir.rglob("*")
                    if p.is_file() and p.suffix.lower() in (set(mu.IMAGE_EXT) | set(mu.VIDEO_EXT))
                )
                if candidates:
                    src = candidates[0]
                    if src.suffix.lower() in mu.VIDEO_EXT:
                        frames = mu.sample_frames(src, SCAN_CACHE_DIR / f"run_{rid}_{src.stem}", fps=0.5, max_frames=1)
                        if frames:
                            src = frames[0][1]
                    im = Image.open(src).convert("RGB")
                    im.thumbnail((1100, 1100))
                    buf = BytesIO()
                    im.save(buf, format="JPEG", quality=82)
                    return src, "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        except Exception:
            pass

    # 4. Fallback architectural scene diagram so live Robotics ER 2 always has crisp visual input
    diag_path = _render_diagram_scene(req.target, SCAN_CACHE_DIR / f"scene_{req.target}_v1.jpg")
    b64 = base64.b64encode(diag_path.read_bytes()).decode()
    return diag_path, f"data:image/jpeg;base64,{b64}"


@router.post("/analyze")
def post_analyze(req: CoMoveAnalyzeRequest) -> dict[str, Any]:
    plan = req.plan
    if not isinstance(plan, dict) or "trucks" not in plan:
        _, inv = _load_inventory_for_run(req.run_id)
        plan = solver.solve(inv, strategy=req.strategy or {})
    return co_move.analyze_co_move(plan, occupancy_mode=req.occupancy_mode)


@router.get("/analyze/{run_id}")
def get_analyze(
    run_id: str,
    occupancy_mode: str = Query("permitted_bays"),
) -> dict[str, Any]:
    _, inv = _load_inventory_for_run(run_id)
    plan = solver.solve(inv)
    return co_move.analyze_co_move(plan, occupancy_mode=occupancy_mode)


@router.post("/scan")
def post_robotics_scan(req: RoboticsScanRequest) -> dict[str, Any]:
    img_path, preview_url = _resolve_scan_image(req)
    result = co_move.scan_space_with_robotics(
        img_path,
        target=req.target,
        context_hint=req.context_hint,
    )
    return {
        **result,
        "image_source": img_path.name,
        "preview_data_url": preview_url,
    }
