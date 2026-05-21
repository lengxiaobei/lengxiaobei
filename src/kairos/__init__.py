"""
KAIROS — LLM 驱动长会话心跳与状态管理系统
============================================

包结构:
- config.py: KairosConfig, KairosState, SessionState
- daily_log.py: DailyLogManager (append-only 日志)
- scheduler.py: CronTask, CronScheduler
- monitor.py: 系统监控与代码分析
- decision.py: 自主决策引擎
- engine.py: Kairos 核心引擎 + create_kairos 工厂
"""

from .config import KairosConfig, KairosState, SessionState
from .daily_log import DailyLogManager
from .scheduler import CronTask, CronScheduler
from .engine import Kairos, create_kairos

__all__ = [
    "KairosConfig", "KairosState", "SessionState",
    "DailyLogManager", "CronTask", "CronScheduler",
    "Kairos", "create_kairos",
]