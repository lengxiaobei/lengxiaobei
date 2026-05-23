"""Route helpers for the canonical FastAPI API package."""

from __future__ import annotations

from fastapi import Request


def runtime(request: Request):
    return request.app.state.runtime
