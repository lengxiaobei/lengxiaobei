"""Compatibility probes for reference-agent-shaped local directories.

LengXiaobei's target is native capability, not dependency on downstream agents.
This module is retained as a compatibility/discovery boundary only.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentProfile:
    """Public profile of a compatibility lane."""
    id: str
    name: str
    description: str = ""
    capabilities: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
        }


class BaseIntegration:
    """Base class for external agent integrations."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = home or Path.home()
        # Note: type annotation for `home` attribute is `Path`. The `| None` in parameter is for convenience.

    def profile(self) -> AgentProfile:
        raise NotImplementedError

    async def status(self) -> dict[str, Any]:
        raise NotImplementedError

    async def assign_task(self, task: str, context: str = "", timeout: int = 120) -> dict[str, Any]:
        raise NotImplementedError


class OpenClawIntegration(BaseIntegration):
    """Integration with a local OpenClaw gateway."""

    def __init__(self, home: Path | None = None, base_url: str = "http://localhost:18789", token: str = "") -> None:
        super().__init__(home)
        self.base_url = base_url.rstrip("/")
        self.token = token

    def profile(self) -> AgentProfile:
        return AgentProfile(
            id="openclaw",
            name="OpenClaw",
            description="多渠道网关调度中枢，支持 webchat/telegram/whatsapp 等多渠道接入",
            capabilities=["gateway", "multi-agent", "tools", "memory", "skills"],
        )

    async def status(self) -> dict[str, Any]:
        if not (self.home / ".openclaw").exists():
            return {
                "ok": False,
                "installed": False,
                "gateway_online": False,
                "gateway_compatible": False,
                "profile": self.profile().as_dict(),
            }
        try:
            import httpx
            logger.info(f"Checking status of OpenClaw service at {self.base_url}")
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/health", headers=headers)
                return {
                    "ok": resp.status_code == 200,
                    "installed": True,
                    "gateway_online": resp.status_code == 200,
                    "profile": self.profile().as_dict(),
                }
        except ImportError:
            logger.error("httpx library not installed. Cannot check OpenClaw status.")
            return {"status": "unavailable", "error": "httpx library not installed"}
        except Exception as exc:
            return {"ok": False, "installed": False, "error": str(exc), "profile": self.profile().as_dict()}

    async def assign_task(self, task: str, context: str = "", timeout: int = 120) -> dict[str, Any]:
        try:
            import httpx
            headers = {"Content-Type": "application/json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            body = {
                "model": "tokenplan/mimo-v2.5-pro",
                "messages": [{"role": "user", "content": f"{context}\n\n{task}" if context else task}],
                "max_tokens": 4096,
            }
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=body, headers=headers,
                )
                data = resp.json()
                content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                return {"ok": True, "result": content}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


class HermesIntegration(BaseIntegration):
    """Integration with a local Hermes agent."""

    def __init__(self, home: Path | None = None) -> None:
        super().__init__(home)

    def profile(self) -> AgentProfile:
        return AgentProfile(
            id="hermes",
            name="Hermes",
            description="自主学习 Agent，闭环反思与技能进化",
            capabilities=["reflection", "skill-evolution", "autonomous-learning"],
        )

    async def status(self) -> dict[str, Any]:
        import subprocess
        try:
            result = subprocess.run(
                ["pgrep", "-f", "hermes_cli.main gateway"],
                capture_output=True, timeout=5,
            )
            running = result.returncode == 0
            return {
                "ok": running,
                "installed": True,
                "profile": self.profile().as_dict(),
            }
        except Exception as exc:
            return {"ok": False, "installed": False, "error": str(exc), "profile": self.profile().as_dict()}

    async def assign_task(self, task: str, context: str = "", timeout: int = 120) -> dict[str, Any]:
        return {"ok": False, "error": "Hermes task assignment not yet implemented"}


class OpenHumanIntegration(BaseIntegration):
    """Integration with OpenHuman memory system."""

    def __init__(self, home: Path | None = None) -> None:
        super().__init__(home)

    def profile(self) -> AgentProfile:
        return AgentProfile(
            id="openhuman",
            name="OpenHuman",
            description="长期记忆系统，结构化知识库与语义检索",
            capabilities=["memory-tree", "vector-search", "graph-store", "sync"],
        )

    async def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "installed": True,
            "profile": self.profile().as_dict(),
        }

    async def assign_task(self, task: str, context: str = "", timeout: int = 120) -> dict[str, Any]:
        return {"ok": True, "result": "OpenHuman memory operations are handled locally"}


def build_reference_integrations(home: Path | None = None) -> dict[str, BaseIntegration]:
    """Build the three reference integrations: OpenClaw, Hermes, OpenHuman."""
    return {
        "openclaw": OpenClawIntegration(home=home),
        "hermes": HermesIntegration(home=home),
        "openhuman": OpenHumanIntegration(home=home),
    }
