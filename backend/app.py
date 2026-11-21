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
from backend.ingest.api import router as ingest_router

app = FastAPI(title="Pack It Up")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(ingest_router)
app.include_router(analysis_router)  # which model did which job: frontend/models.html


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", include_in_schema=False)
def root():
    # A phone typing just the laptop's address lands on the capture page instead of a 404.
    return RedirectResponse("/app/capture.html")


# Phone pages (frontend/capture.html, review.html, index.html) on the same port as the API,
# so one tunnel address serves both: open /app/capture.html. Mounted last so the API routes win.
app.mount("/app", StaticFiles(directory=Path(__file__).resolve().parent.parent / "frontend", html=True), name="app")
