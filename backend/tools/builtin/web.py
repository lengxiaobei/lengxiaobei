"""Web fetch tool.

参考来源：OpenClaw web toolkit。这里只提供最小 HTTP fetch；生产环境应加 allowlist、缓存和清洗。
"""

from __future__ import annotations

import requests


def fetch(url: str, timeout: int = 20) -> str:
    return requests.get(url, timeout=timeout).text
