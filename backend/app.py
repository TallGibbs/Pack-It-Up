"""Pack It Up API. Run: uvicorn backend.app:app --reload

Track A routes live in backend/ingest/api.py; Track B adds its own router here
(e.g. POST /solve, POST /render).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.ingest.api import router as ingest_router

app = FastAPI(title="Pack It Up")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(ingest_router)


@app.get("/health")
def health():
    return {"ok": True}
