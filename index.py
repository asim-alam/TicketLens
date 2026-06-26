"""
Vercel entrypoint (also a valid local target: `uvicorn index:app`).

Vercel's FastAPI backend framework auto-detects a top-level `app` in a root entry
file (index.py / main.py / app.py / server.py) plus requirements.txt, and serves the
ASGI app at the deployment BASE URL — so `/health` and `/analyze-ticket` resolve at the
root (no `/api` prefix). The real app lives in the `app/` package.
"""
from app.main import app  # noqa: F401
