"""Vercel serverless entrypoint — exposes the FastAPI ASGI app.

Vercel's @vercel/python runtime serves the module-level `app` object. We add the
project root to sys.path so `webapp` and its sibling modules import cleanly.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webapp import app  # noqa: E402,F401
