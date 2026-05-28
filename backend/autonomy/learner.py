"""Network learning for autonomous improvement."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx


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
    "LengXiaobei": [
        "https://api.github.com/search/repositories?q=autonomous+agent+self-improvement+python",
        "https://api.github.com/search/repositories?q=agent+framework+memory+reflection+skill+python",
    ],
}

# Keywords extracted from reference strings that aren't exact matches
_FALLBACK_KEYWORDS = {
    "native authority": "agent+tool+execution+authority+self-modification",
    "native channels": "agent+channel+runtime+telegram+slack+reconnect",
    "native memory": "memory+graph+entity+extraction+knowledge+agent",
    "native sync": "agent+sync+connector+authenticated+incremental",
    "native skills": "agent+skill+verification+replay+evaluation",
    "native reflection": "agent+reflection+evaluator+hypothesis+improvement",
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

    async def learn(self, reference: str, limit: int = 2) -> list[dict[str, Any]]:
        urls = self._resolve_urls(reference, limit)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            results = []
            for url in urls:
                result = await self._fetch_with_client(client, reference, url)
                # If we got GitHub search results, try to fetch README from top repos
                if result.ok and '"items"' in result.summary:
                    readme_notes = await self._fetch_top_readmes(client, reference, result.summary)
                    if readme_notes:
                        result.summary += "\n\n## README Highlights\n" + readme_notes
                results.append(result.as_dict())
        return results

    def _resolve_urls(self, reference: str, limit: int) -> list[str]:
        """Resolve reference to search URLs, with fallback for partial matches."""
        # Exact match first
        if reference in DEFAULT_SOURCES:
            return DEFAULT_SOURCES[reference][:limit]
        # Partial keyword match from fallback
        for keyword, query in _FALLBACK_KEYWORDS.items():
            if keyword in reference.lower():
                return [f"https://api.github.com/search/repositories?q={query}"][:limit]
        # Generic fallback: search for the reference string itself
        safe_ref = reference.replace(" ", "+")[:60]
        return [f"https://api.github.com/search/repositories?q={safe_ref}+agent"][:limit]

    async def _fetch_top_readmes(self, client: httpx.AsyncClient, reference: str, search_summary: str) -> str:
        """Extract README snippets from top repos found in search results."""
        # Parse repo full_names from the search summary
        names = re.findall(r"repositories=([^;]+)", search_summary)
        if not names:
            return ""
        repo_list = [n.strip() for n in names[0].split(",")[:3]]
        snippets = []
        for repo in repo_list:
            try:
                resp = await client.get(
                    f"https://api.github.com/repos/{repo}/readme",
                    headers={"Accept": "application/vnd.github.v3.raw"},
                )
                if resp.status_code == 200:
                    text = resp.text[:800]
                    # Extract first meaningful paragraph (skip badges/links)
                    lines = [l.strip() for l in text.split("\n") if l.strip() and not l.startswith(("!", "[", "<", "#"))]
                    snippet = " ".join(lines[:3])[:300]
                    if snippet:
                        snippets.append(f"**{repo}**: {snippet}")
            except Exception:
                continue
        return "\n".join(snippets)

    async def fetch(self, reference: str, url: str) -> LearningResult:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await self._fetch_with_client(client, reference, url)

    async def _fetch_with_client(
        self, client: httpx.AsyncClient, reference: str, url: str
    ) -> LearningResult:
        try:
            response = await client.get(
                url,
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
        except httpx.TimeoutException:
            return LearningResult(
                reference=reference, url=url, title=url, summary="", ok=False, error="request timed out"
            )
        except httpx.HTTPError as exc:
            return LearningResult(
                reference=reference, url=url, title=url, summary="", ok=False, error=str(exc)
            )

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

