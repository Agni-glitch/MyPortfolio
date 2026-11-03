"""Vercel serverless entrypoint (ASGI). Vercel detects the `app` variable.

Local dev:  uvicorn api.index:app --reload
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.app import create_app  # noqa: E402

app = create_app()
