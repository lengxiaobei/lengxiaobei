"""Network learning for autonomous improvement."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import requests


DEFAULT_SOURCES = {
    "OpenClaw": [
        "https://api.github.com/search/repositories?q=OpenClaw+agent",
        "https://api.github.com/search/repositories?q=multi+channel+agent+gateway+tools",
    ],
    "OpenHuman": [
        "https://api.github.com/search/repositories?q=OpenHuman+memory+agent",
        "https://api.github.com/search/repositories?q=memory+tree+agent+vector+graph",
    ],
    "Hermes": [
        "https://api.github.com/search/repositories?q=Hermes+agent+skill+reflection",
        "https://api.github.com/search/repositories?q=agent+skill+generation+reflection+evaluator",
    ],
}


@dataclass
class LearningResult:
    reference: str
    url: str
    title: str
    summary: str
    ok: bool
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "url": self.url,
            "title": self.title,
            "summary": self.summary,
            "ok": self.ok,
            "error": self.error,
        }


class NetworkLearner:
    """Fetch reference material and compress it into memory-ready notes."""

    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    def learn(self, reference: str, limit: int = 2) -> list[dict[str, Any]]:
        urls = DEFAULT_SOURCES.get(reference, [])[:limit]
        return [self.fetch(reference, url).as_dict() for url in urls]

    def fetch(self, reference: str, url: str) -> LearningResult:
        try:
            response = requests.get(
                url,
                timeout=self.timeout,
                headers={"Accept": "application/json,text/plain,*/*", "User-Agent": "lengxiaobei-autonomy/1.0"},
            )
            response.raise_for_status()
            text = response.text
            return LearningResult(
                reference=reference,
                url=url,
                title=self._title(text) or url,
                summary=self._summary(text),
                ok=True,
            )
        except Exception as exc:
            return LearningResult(reference=reference, url=url, title=url, summary="", ok=False, error=str(exc))

    def _title(self, text: str) -> str:
        match = re.search(r'"full_name"\s*:\s*"([^"]+)"', text)
        if match:
            return match.group(1)
        html = re.search(r"<title>(.*?)</title>", text, flags=re.I | re.S)
        return re.sub(r"\s+", " ", html.group(1)).strip() if html else ""

    def _summary(self, text: str, limit: int = 900) -> str:
        cleaned = re.sub(r"\s+", " ", text)
        if '"items"' in cleaned:
            names = re.findall(r'"full_name"\s*:\s*"([^"]+)"', cleaned)[:5]
            desc = re.findall(r'"description"\s*:\s*("[^"]*"|null)', cleaned)[:5]
            parts = [f"repositories={', '.join(names)}"] if names else []
            if desc:
                parts.append("descriptions=" + ", ".join(item.strip('"') for item in desc if item != "null"))
            return "; ".join(parts)[:limit]
        return cleaned[:limit]

