"""Runtime configuration, read from environment variables (see backend/.env.example)."""
from __future__ import annotations

import os
import secrets


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./citeright.db")
    # Supabase/Heroku style URLs -> SQLAlchemy + psycopg 3
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _database_url()

# Without SECRET_KEY a random key is used, so sessions end when the server restarts.
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(48)
TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "168"))

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

# Optional keys for metadata providers. They never leave the backend.
GOOGLE_BOOKS_API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY", "")
CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO", "")
COURTLISTENER_TOKEN = os.getenv("COURTLISTENER_TOKEN", "")

HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))

# Folder with the exported web interface (frontend/out). When set, the API serves the
# interface itself, so the whole app runs as one process. Used by the desktop build.
STATIC_DIR = os.getenv("CITERIGHT_STATIC_DIR", "")
