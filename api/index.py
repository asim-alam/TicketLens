"""
Vercel serverless entrypoint.

`vercel.json` rewrites every path to `/api/index`, and this module re-exports the
FastAPI ASGI app, which then does its own routing. Net effect: `/health` and
`/analyze-ticket` resolve at the deployment BASE URL (not under `/api/...`).
"""
from app.main import app  # noqa: F401  (Vercel's Python runtime serves `app`)
