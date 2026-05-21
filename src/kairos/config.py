"""
KAIROS 配置与状态模型
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Any
from enum import Enum


@dataclass
class KairosConfig:
    """KAIROS 配置（默认值，实际判断由 LLM 完成）"""
    heartbeat_interval: int = 60
    session_timeout: int = 3600 * 24 * 30
    daily_log_dir: str = "logs"
    max_session_idle: int = 3600 * 2
    auto_save_interval: int = 300
    cron_check_interval: int = 1

    monitor_interval: int = 60
    performance_threshold: float = 80.0
    memory_threshold: float = 80.0

    decision_interval: int = 300
    evolution_cooldown: int = 600

    code_analysis_interval: int = 3600
    complexity_threshold: int = 50


class SessionState(Enum):
    ACTIVE = "active"
    IDLE = "idle"
    SUSPENDED = "suspended"
    RECOVERING = "recovering"


@dataclass
class KairosState:
    kairos_active: bool = False
    session_id: str = ""
    original_cwd: str = ""
    project_root: str = ""

    start_time: float = 0
    last_interaction_time: float = 0
    last_heartbeat: float = 0

    total_cost_usd: float = 0
    total_api_duration: float = 0
    total_tool_duration: float = 0
    total_lines_added: int = 0
    total_lines_removed: int = 0

    model_usage: Dict[str, Dict] = field(default_factory=dict)

    session_state: str = SessionState.ACTIVE.value
    is_interactive: bool = True

    system_metrics: Dict[str, Any] = field(default_factory=dict)
    performance_issues: List[str] = field(default_factory=list)
    memory_issues: List[str] = field(default_factory=list)
    code_issues: List[str] = field(default_factory=list)

    last_decision_time: float = 0
    last_evolution_time: float = 0
    pending_improvements: List[Dict[str, Any]] = field(default_factory=list)

    last_code_analysis: float = 0
    code_complexity: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        if self.start_time == 0:
            self.start_time = time.time()
        if self.last_interaction_time == 0:
            self.last_interaction_time = time.time()
        if not self.system_metrics:
            self.system_metrics = {
                'cpu_usage': 0.0,
                'memory_usage': 0.0,
                'disk_usage': 0.0,
                'response_time': 0.0
            }