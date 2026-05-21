"""Evolution data models."""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


class EvolutionPhase(Enum):
    DISCOVER = "discover"
    PROPOSE = "propose"
    EXECUTE = "execute"
    VERIFY = "verify"


class EvolutionStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ImprovementRecord:
    """统一的改进记录 schema — KAIROS/daemon/Curator/Guardian 共用

    字段规范:
    - file: 相对于 project_root 的文件路径（必填）
    - issue: 问题描述（必填）
    - priority: 优先级 high/medium/low（必填）
    - source: 来源标识 kairos/curator/manual（必填）
    - type: 改进类型（可选）
    - suggestion: 改进建议（可选）
    - confidence: 置信度 0-1（可选）
    - signature: 去重签名 = f"{file}:{issue}" （自动生成）
    """

    file: str
    issue: str
    priority: str = "medium"
    source: str = "curator"
    type: str = "code_quality"
    suggestion: str = ""
    confidence: float = 0.8
    severity: str = "minor"
    category: str = "optimization"
    risk_level: str = "medium"

    @property
    def signature(self) -> str:
        return f"{self.file}:{self.issue[:60]}"

    @classmethod
    def from_curator(cls, improvement: Any, source: str = "curator") -> "ImprovementRecord":
        return cls(
            file=getattr(improvement, "file", ""),
            issue=getattr(improvement, "issue", ""),
            priority=getattr(improvement, "priority", "medium"),
            source=source,
            type=getattr(improvement, "type", "code_quality"),
            suggestion=getattr(improvement, "suggestion", ""),
            confidence=getattr(improvement, "confidence", 0.8),
            severity=getattr(improvement, "severity", "minor"),
            category=getattr(improvement, "category", "optimization"),
        )

    @classmethod
    def from_kairos(cls, data: Dict[str, Any]) -> Optional["ImprovementRecord"]:
        file_path = data.get("file", data.get("file_path", ""))
        issue = data.get("issue", data.get("description", ""))
        if not file_path or not issue:
            return None
        return cls(
            file=file_path,
            issue=issue,
            priority=data.get("priority", "medium"),
            source="kairos",
            type=data.get("type", "code_quality"),
            suggestion=data.get("suggestion", ""),
            confidence=data.get("confidence", 0.8),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "issue": self.issue,
            "priority": self.priority,
            "source": self.source,
            "type": self.type,
            "suggestion": self.suggestion,
            "confidence": self.confidence,
            "signature": self.signature,
        }

    def abspath(self, project_root: str) -> str:
        import os
        if os.path.isabs(self.file):
            return self.file
        return os.path.join(project_root, self.file)


@dataclass
class Goal:
    description: str
    constraints: List[str] = field(default_factory=list)
    success_criteria: str = "AI自己判断"
    priority: str = "high"


@dataclass
class EvolutionContext:
    project_root: str
    file_path: str
    original_code: str
    goal: Goal
    phase: EvolutionPhase = EvolutionPhase.DISCOVER
    status: EvolutionStatus = EvolutionStatus.PENDING
    resources: Dict[str, Any] = field(default_factory=dict)
    decisions: Dict[str, Any] = field(default_factory=dict)
    execution_results: Dict[str, Any] = field(default_factory=dict)
    feedback: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.MEDIUM


@dataclass
class AIDecision:
    problems: List[str]
    strategy: str
    approach: str
    steps: List[str]
    success_criteria: str
    confidence: float
    risk_level: RiskLevel = RiskLevel.MEDIUM
    team_feedback: Dict[str, str] = field(default_factory=dict)