"""Evolution Subpackage — 模块化架构 + 治理内嵌

Discover → Propose → Execute → Verify
每个步骤嵌入: Constitution 合规 + 权限审批 + 熔断器

Modules:
- models:       Data models (ImprovementRecord 统一 schema)
- config:       Configuration and LLM helpers
- llm_client:   Unified LLM calling layer
- curator:      Curator — periodic review + dedup
- proposer:     Proposal generation (with diff/patch mode)
- executor:     Safe execution (permission pre-check + backup/write/rollback)
- verifier:     Pytest-based test verification (cleanup locked behind success)
- skills_store: Knowledge persistence from successful evolutions
- engine:       Thin orchestrator (< 350 lines)
"""

from .models import (
    EvolutionPhase,
    EvolutionStatus,
    RiskLevel,
    Goal,
    EvolutionContext,
    AIDecision,
    ImprovementRecord,
)

from .config import Config, _get_project_llm_models, _call_claude_code

from .llm_client import chat, chat_json, generate_code, extract_json, chat_bool

from .curator import Curator, Improvement

from .proposer import Proposer, Proposal

from .executor import SafeExecutor, ExecutionResult

from .verifier import PytestVerifier, TestResult

from .skills_store import SkillsStore

from .engine import AutonomousEvolutionEngine, create_autonomous_evolution_engine

__all__ = [
    "EvolutionPhase",
    "EvolutionStatus",
    "RiskLevel",
    "Goal",
    "EvolutionContext",
    "AIDecision",
    "ImprovementRecord",
    "Config",
    "Curator",
    "Improvement",
    "Proposer",
    "Proposal",
    "SafeExecutor",
    "ExecutionResult",
    "PytestVerifier",
    "TestResult",
    "SkillsStore",
    "AutonomousEvolutionEngine",
    "create_autonomous_evolution_engine",
    "chat",
    "chat_json",
    "generate_code",
    "extract_json",
    "chat_bool",
]