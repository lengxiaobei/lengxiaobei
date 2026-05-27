"""Local agent integration boundary."""

from backend.agents.integrations import OpenClawIntegration, HermesIntegration, OpenHumanIntegration
from backend.agents.local import LocalAgentHub

__all__ = ["LocalAgentHub", "OpenClawIntegration", "HermesIntegration", "OpenHumanIntegration"]
