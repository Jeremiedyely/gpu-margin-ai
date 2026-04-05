"""
FastAPI application entrypoint — GPU Gross Margin Visibility.

Mounts all API routers. CORS configured for local React dev server.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.state_routes import router as state_router
from app.api.ui_routes import router as ui_router
from app.api.upload_routes import router as upload_router
from app.api.export_routes import router as export_router

app = FastAPI(
    title="GPU Gross Margin Visibility",
    version="0.1.0",
)

# CORS — allow React dev server (Vite default port)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(state_router)
app.include_router(ui_router)
app.include_router(upload_router)
app.include_router(export_router)


@app.get("/health")
def health_check():
    """Basic health probe."""
    return {"status": "ok"}
