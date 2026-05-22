"""
共享状态变量 — 供各 Blueprint 和共享模块引用。
"""

import os
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# kairos events 可用性标志
# ---------------------------------------------------------------------------

try:
    from src.kairos import events as kairos_events
    _KAIROS_EVENTS_OK = True
except Exception:
    kairos_events = None
    _KAIROS_EVENTS_OK = False

# ---------------------------------------------------------------------------
# Agent 单例
# ---------------------------------------------------------------------------

_agent = None

_system_info = {
    "platform": sys.platform,
    "python_version": sys.version,
    "start_time": time.time(),
    "version": "Phase 2.1",
}

IDENTITY_DOCS = [
    "docs/SOUL.md",
    "docs/IDENTITY.md",
    "docs/USER.md",
    "docs/AUTONOMY.md",
    "docs/CONSTITUTION.md",
]

MODEL_CONFIG_FILES = [
    "config/default.yaml",
    "config/development.yaml",
    "config/production.yaml",
    "config/config.json",
]

READABLE_FILES = {
    "config/default.yaml",
    "config/development.yaml",
    "config/production.yaml",
    "config/config.json",
    "src/llm.py",
    "src/core.py",
    "src/self_evolution.py",
    "src/learned_capabilities.py",
    "memory/agent_lessons.json",
    "memory/self_evolution_runs.json",
    "memory/autonomy_runs.json",
    "memory/autonomy_learning_plan.json",
    "memory/code_change_logs.json",
}

# ---------------------------------------------------------------------------
# 自主循环状态
# ---------------------------------------------------------------------------

AUTONOMY_RUNS_FILE = PROJECT_ROOT / "memory" / "autonomy_runs.json"
AUTONOMY_LEARNING_PLAN_FILE = PROJECT_ROOT / "memory" / "autonomy_learning_plan.json"
AUTONOMY_DEFAULT_INTERVAL = int(os.environ.get("LX_AUTONOMY_INTERVAL", "300"))

_autonomy_lock = threading.Lock()
_autonomy_state = {
    "enabled": False,
    "running": False,
    "interval_seconds": AUTONOMY_DEFAULT_INTERVAL,
    "thread_alive": False,
    "tick_count": 0,
    "last_tick_at": None,
    "last_result": None,
}
_autonomy_thread = None
_autonomy_tick_lock = threading.Lock()

# ---------------------------------------------------------------------------
# 重启状态
# ---------------------------------------------------------------------------

_restart_lock = threading.Lock()
_restart_state = {
    "pending": False,
    "reason": "",
    "scheduled_at": None,
    "restart_at": None,
}

# ---------------------------------------------------------------------------
# 默认学习主题
# ---------------------------------------------------------------------------

DEFAULT_LEARNING_TOPICS = [
    {
        "topic": "自主学习 OpenHands 的任务拆解、工作区执行和错误恢复能力，并提炼一个可落地改进",
        "url": "https://github.com/All-Hands-AI/OpenHands",
    },
    {
        "topic": "自主学习 Aider 的 git 感知代码修改、最小补丁和提交前验证能力，并提炼一个可落地改进",
        "url": "https://github.com/Aider-AI/aider",
    },
    {
        "topic": "自主学习 Continue 的 IDE 上下文、代码库索引和开发者交互设计能力，并提炼一个可落地改进",
        "url": "https://github.com/continuedev/continue",
    },
    {
        "topic": "自主学习 AutoGen 的多 Agent 协作、角色分工和任务交接机制，并提炼一个可落地改进",
        "url": "https://github.com/microsoft/autogen",
    },
    {
        "topic": "自主学习 Claude Code 的计划执行、工具调用反馈和长任务汇报体验，并提炼一个可落地改进",
        "url": "",
    },
]

# ---------------------------------------------------------------------------
# 目标 / 动机系统
# ---------------------------------------------------------------------------

_goal_system = None
_motivation_system = None
_goal_system_lock = threading.Lock()


# ---------------------------------------------------------------------------
# 延迟初始化 Agent（避免启动时加载所有模块）
# ---------------------------------------------------------------------------

def _get_agent():
    global _agent
    if _agent is None:
        try:
            from src.core import LengXiaobei
            _agent = LengXiaobei()
            _agent.start()
        except Exception as e:
            print(f"[lx_web] Agent 初始化失败: {e}")
            _agent = None
    return _agent
