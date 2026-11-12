"""CiteRight API."""
from __future__ import annotations

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import config
from .db import init_db
from .routers import auth, citations, library


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="CiteRight API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
app.include_router(auth.router)
app.include_router(library.router)
app.include_router(citations.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


def mount_frontend(application: FastAPI, directory: str) -> None:
    """Serve the statically exported web interface for every non-API path."""
    root = Path(directory).resolve()

    @application.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        path = path.strip("/")
        for candidate in (path, f"{path}.html", f"{path}/index.html") if path else ("index.html",):
            file = (root / candidate).resolve()
            if file.is_file() and file.is_relative_to(root):
                return FileResponse(file)
        return FileResponse(root / "404.html", status_code=404)


if config.STATIC_DIR and Path(config.STATIC_DIR, "index.html").is_file():
    mount_frontend(app, config.STATIC_DIR)
