"""Pack It Up API. Run: uvicorn backend.app:app --reload

Track A routes live in backend/ingest/api.py; Track B adds its own router here
(e.g. POST /solve, POST /render).
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.analysis.api import router as analysis_router
from backend.arena_api import router as arena_router
from backend.co_move_api import router as co_move_router
from backend.commerce_api import router as commerce_router
from backend.eval_api import router as eval_router
from backend.ingest.api import router as ingest_router
from backend.judge_api import router as judge_router
from backend.labels_api import router as labels_router
from backend.pack_api import router as pack_router
from backend.render_api import router as render_router
from backend.route_api import router as route_router

app = FastAPI(title="Pack It Up")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(ingest_router)
app.include_router(analysis_router)  # which model did which job: frontend/models.html
app.include_router(pack_router)
app.include_router(arena_router)
app.include_router(co_move_router)
app.include_router(commerce_router)
app.include_router(route_router)
app.include_router(judge_router)
app.include_router(labels_router)
app.include_router(render_router)
app.include_router(eval_router)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", include_in_schema=False)
def root():
    # A phone typing just the laptop's address lands on the capture page instead of a 404.
    return RedirectResponse("/app/capture.html")


class LiveStatic(StaticFiles):
    """frontend/ served so that a saved edit is what every phone gets next.

    With no Cache-Control header, Cloudflare keeps .js and .css at its edge for hours (it never
    caches .html), and phones keep them too. A new page then loads old scripts and breaks
    (FAILURES.md 12:40). "no-cache" means: keep a copy if you like, but check it with the server
    every time; unchanged files cost one small 304 reply.
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Phone pages (frontend/capture.html, review.html, index.html) on the same port as the API,
# so one tunnel address serves both: open /app/capture.html. Mounted last so the API routes win.
app.mount("/app", LiveStatic(directory=Path(__file__).resolve().parent.parent / "frontend", html=True), name="app")
