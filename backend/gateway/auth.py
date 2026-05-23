"""Gateway auth boundary."""

from __future__ import annotations


def verify_local_token(token: str | None) -> bool:
    return token in {None, "", "local-dev"}
