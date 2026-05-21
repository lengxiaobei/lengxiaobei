"""
LLM 驱动目标系统 — 自主 AI Agent 目标管理
============================================

核心理念：目标不再是硬编码的默认任务，
而是通过 LLM 提示词根据当前动机和系统状态动态生成。

设计原则：
- 目标由 LLM 基于动机和系统状态动态生成
- 目标优先级由 LLM 推理评估，不是固定映射
- 目标分解由 LLM 智能完成
"""

import time
import os
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum
from .llm import chat
from .utils import extract_json, atomic_write_json, load_json

logger = logging.getLogger(__name__)


class GoalType(Enum):
    LEARNING = "learning"
    PERFORMANCE = "performance"
    KNOWLEDGE = "knowledge"
    EXPLORATION = "exploration"
    MAINTENANCE = "maintenance"
    INNOVATION = "innovation"


class GoalPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GoalStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Goal:
    id: str
    title: str
    description: str
    type: GoalType
    priority: GoalPriority
    status: GoalStatus
    created_at: float
    updated_at: float
    deadline: Optional[float] = None
    progress: float = 0.0
    parent_id: Optional[str] = None
    sub_goals: List[str] = field(default_factory=list)
    metrics: Dict = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    resources: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "title": self.title, "description": self.description,
            "type": self.type.value, "priority": self.priority.value,
            "status": self.status.value, "created_at": self.created_at,
            "updated_at": self.updated_at, "deadline": self.deadline,
            "progress": self.progress, "parent_id": self.parent_id,
            "sub_goals": self.sub_goals, "metrics": self.metrics,
            "dependencies": self.dependencies, "resources": self.resources,
            "notes": self.notes, "tags": self.tags
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Goal":
        return cls(
            id=data["id"], title=data["title"], description=data["description"],
            type=GoalType(data["type"]), priority=GoalPriority(data["priority"]),
            status=GoalStatus(data["status"]), created_at=data["created_at"],
            updated_at=data["updated_at"], deadline=data.get("deadline"),
            progress=data.get("progress", 0.0), parent_id=data.get("parent_id"),
            sub_goals=data.get("sub_goals", []), metrics=data.get("metrics", {}),
            dependencies=data.get("dependencies", []), resources=data.get("resources", []),
            notes=data.get("notes", []), tags=data.get("tags", [])
        )


class GoalSystem:
    """LLM 驱动的目标系统"""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.goals_dir = os.path.join(project_root, "goals")
        os.makedirs(self.goals_dir, exist_ok=True)
        self.goals_file = os.path.join(self.goals_dir, "goals.json")
        self.goals: Dict[str, Goal] = {}
        self._backup_goals: Dict[str, Goal] = {}
        self._transaction_active = False
        self._goal_id_counter = 0
        self._load_goals()

    def _load_goals(self):
        data = load_json(self.goals_file, default=[])
        if isinstance(data, list):
            for gdata in data:
                try:
                    g = Goal.from_dict(gdata)
                    self.goals[g.id] = g
                    if g.id.isdigit():
                        self._goal_id_counter = max(self._goal_id_counter, int(g.id))
                except Exception as e:
                    logger.warning(f"加载目标失败: {e}")

    def _save_goals(self):
        try:
            data = [g.to_dict() for g in self.goals.values()]
            atomic_write_json(self.goals_file, data)
        except Exception as e:
            logger.error(f"保存目标失败: {e}")

    def _start_transaction(self):
        self._backup_goals = {k: v for k, v in self.goals.items()}
        self._transaction_active = True

    def _commit_transaction(self):
        self._backup_goals.clear()
        self._transaction_active = False

    def _rollback_transaction(self):
        self.goals = {k: v for k, v in self._backup_goals.items()}
        self._backup_goals.clear()
        self._transaction_active = False

    def _generate_goal_id(self) -> str:
        self._goal_id_counter += 1
        return str(self._goal_id_counter)

    def create_goal(self, title: str, description: str, goal_type: GoalType,
                    priority: GoalPriority, deadline=None, parent_id=None,
                    metrics=None, dependencies=None, resources=None, tags=None) -> Goal:
        self._start_transaction()
        try:
            gid = self._generate_goal_id()
            now = time.time()
            g = Goal(id=gid, title=title, description=description, type=goal_type,
                     priority=priority, status=GoalStatus.PENDING,
                     created_at=now, updated_at=now, deadline=deadline,
                     progress=0.0, parent_id=parent_id, sub_goals=[],
                     metrics=metrics or {}, dependencies=dependencies or [],
                     resources=resources or [], notes=[], tags=tags or [])
            self.goals[gid] = g
            if parent_id and parent_id in self.goals:
                self.goals[parent_id].sub_goals.append(gid)
                self.goals[parent_id].updated_at = now
            self._save_goals()
            logger.info(f"创建目标: {title} (ID: {gid})")
            self._commit_transaction()
            return g
        except Exception as e:
            self._rollback_transaction()
            raise e

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        return self.goals.get(goal_id)

    def list_goals(self, status=None, goal_type=None, priority=None) -> List[Goal]:
        result = []
        for g in self.goals.values():
            if status and g.status != status:
                continue
            if goal_type and g.type != goal_type:
                continue
            if priority and g.priority != priority:
                continue
            result.append(g)
        result.sort(key=lambda x: (x.priority.value, x.deadline or float('inf')))
        return result

    def update_goal(self, goal_id: str, title=None, description=None, status=None,
                    progress=None, deadline=None, metrics=None, notes=None) -> Optional[Goal]:
        if goal_id not in self.goals:
            return None
        self._start_transaction()
        try:
            g = self.goals[goal_id]
            if title:
                g.title = title
            if description:
                g.description = description
            if status:
                g.status = status
            if progress is not None:
                g.progress = min(max(progress, 0.0), 100.0)
                if g.progress >= 100.0 and g.status != GoalStatus.COMPLETED:
                    g.status = GoalStatus.COMPLETED
            if deadline:
                g.deadline = deadline
            if metrics:
                g.metrics.update(metrics)
            if notes:
                g.notes.extend(notes)
            g.updated_at = time.time()
            self._save_goals()
            logger.info(f"更新目标: {g.title} (ID: {goal_id})")
            self._commit_transaction()
            return g
        except Exception as e:
            self._rollback_transaction()
            raise e

    def delete_goal(self, goal_id: str) -> bool:
        if goal_id not in self.goals:
            return False
        # 收集所有需要删除的 ID（广度优先，避免递归事务嵌套）
        to_delete = []
        queue = [goal_id]
        while queue:
            gid = queue.pop(0)
            if gid in self.goals:
                to_delete.append(gid)
                queue.extend(self.goals[gid].sub_goals)
        self._start_transaction()
        try:
            for gid in to_delete:
                g = self.goals.get(gid)
                if not g:
                    continue
                if g.parent_id and g.parent_id in self.goals:
                    parent = self.goals[g.parent_id]
                    if gid in parent.sub_goals:
                        parent.sub_goals.remove(gid)
                        parent.updated_at = time.time()
                for other in self.goals.values():
                    if gid in other.dependencies:
                        other.dependencies.remove(gid)
                        other.updated_at = time.time()
                del self.goals[gid]
                logger.info(f"删除目标: {g.title} (ID: {gid})")
            self._save_goals()
            self._commit_transaction()
            return True
        except Exception as e:
            self._rollback_transaction()
            raise e

    def create_sub_goal(self, parent_id: str, title: str, description: str,
                        goal_type: GoalType, priority: GoalPriority,
                        deadline=None, metrics=None) -> Optional[Goal]:
        if parent_id not in self.goals:
            return None
        return self.create_goal(title=title, description=description, goal_type=goal_type,
                                priority=priority, deadline=deadline, parent_id=parent_id, metrics=metrics)

    def update_progress(self, goal_id: str, progress: float) -> Optional[Goal]:
        return self.update_goal(goal_id, progress=progress)

    def complete_goal(self, goal_id: str, notes=None) -> Optional[Goal]:
        return self.update_goal(goal_id, status=GoalStatus.COMPLETED, progress=100.0, notes=notes)

    def fail_goal(self, goal_id: str, notes=None) -> Optional[Goal]:
        return self.update_goal(goal_id, status=GoalStatus.FAILED, notes=notes)

    def cancel_goal(self, goal_id: str, notes=None) -> Optional[Goal]:
        return self.update_goal(goal_id, status=GoalStatus.CANCELLED, notes=notes)

    def get_goal_hierarchy(self, goal_id: str) -> Dict:
        def _build(g: Goal) -> Dict:
            h = g.to_dict()
            h["sub_goals"] = [_build(self.goals[sid]) for sid in g.sub_goals if sid in self.goals]
            return h
        if goal_id not in self.goals:
            return {}
        return _build(self.goals[goal_id])

    def get_priority_goals(self, limit: int = 5) -> List[Goal]:
        goals = [g for g in self.goals.values() if g.status in [GoalStatus.PENDING, GoalStatus.IN_PROGRESS]]
        goals.sort(key=lambda x: (x.priority.value, x.deadline or float('inf')))
        return goals[:limit]

    def get_goals_by_deadline(self, days: int = 7) -> List[Goal]:
        now = time.time()
        deadline = now + (days * 24 * 3600)
        goals = [g for g in self.goals.values()
                 if g.status in [GoalStatus.PENDING, GoalStatus.IN_PROGRESS]
                 and g.deadline and g.deadline <= deadline]
        goals.sort(key=lambda x: x.deadline)
        return goals

    def generate_default_goals(self):
        """通过 LLM 生成初始目标"""
        existing = self.list_goals()
        if existing:
            logger.info("已存在目标，跳过默认生成")
            return

        prompt = """你是自主AI Agent的目标规划系统。请根据以下系统身份生成一组初始目标。

系统身份：冷小北 - 一个自主进化的AI编程助手Agent
能力：代码分析、代码修改、文件操作、多模型LLM调用、自主学习进化
运行环境：Python项目，包含约60个模块的文件系统

请生成4-6个具体、可执行的目标，考虑以下维度：
- 系统自身的代码优化和重构
- 学习新技术和工具
- 系统维护和健康检查
- 功能增强和创新

每个目标包含:
- title: 简短标题 (< 20字)
- description: 详细描述
- type: learning/performance/knowledge/exploration/maintenance/innovation
- priority: low/medium/high/critical
- deadline_days: 从今天起的天数 (1-14)
- tags: 2-3个标签

返回JSON格式：
{
    "goals": [
        {"title": "...", "description": "...", "type": "learning", "priority": "high", "deadline_days": 7, "tags": ["...", "..."]},
        ...
    ]
}

只返回JSON。"""

        try:
            response = chat(prompt, system="你是自主AI Agent目标规划系统。只返回JSON。", temperature=0.7)
            data = extract_json(response)
            for gdata in data.get("goals", []):
                try:
                    gtype = GoalType(gdata["type"])
                except (ValueError, KeyError):
                    gtype = GoalType.LEARNING
                try:
                    gprio = GoalPriority(gdata["priority"])
                except (ValueError, KeyError):
                    gprio = GoalPriority.MEDIUM
                deadline_days = int(gdata.get("deadline_days", 7))
                self.create_goal(
                    title=gdata.get("title", "未命名目标"),
                    description=gdata.get("description", ""),
                    goal_type=gtype, priority=gprio,
                    deadline=time.time() + (deadline_days * 24 * 3600),
                    tags=gdata.get("tags", [])
                )
            if self.goals:
                logger.info(f"LLM生成了 {len(self.goals)} 个初始目标")
                return
        except Exception as e:
            logger.warning(f"LLM生成默认目标失败: {e}")

        # 回退
        defaults = [
            ("自主分析项目代码质量", "对项目代码进行全面分析，识别改进点", GoalType.MAINTENANCE, GoalPriority.HIGH, 3),
            ("学习最新AI技术趋势", "研究当前AI领域的最新技术和趋势", GoalType.KNOWLEDGE, GoalPriority.MEDIUM, 7),
            ("优化核心模块性能", "分析和优化核心模块的执行效率", GoalType.PERFORMANCE, GoalPriority.MEDIUM, 5),
            ("清理和整理项目结构", "清理冗余代码，优化项目组织结构", GoalType.MAINTENANCE, GoalPriority.LOW, 2),
        ]
        for title, desc, gtype, prio, days in defaults:
            self.create_goal(title=title, description=desc, goal_type=gtype, priority=prio,
                             deadline=time.time() + (days * 24 * 3600))

    def get_goal_statistics(self) -> Dict:
        total = len(self.goals)
        completed = sum(1 for g in self.goals.values() if g.status == GoalStatus.COMPLETED)
        in_progress = sum(1 for g in self.goals.values() if g.status == GoalStatus.IN_PROGRESS)
        pending = sum(1 for g in self.goals.values() if g.status == GoalStatus.PENDING)
        failed = sum(1 for g in self.goals.values() if g.status == GoalStatus.FAILED)
        cancelled = sum(1 for g in self.goals.values() if g.status == GoalStatus.CANCELLED)

        type_stats = {gt.value: sum(1 for g in self.goals.values() if g.type == gt) for gt in GoalType}
        priority_stats = {gp.value: sum(1 for g in self.goals.values() if g.priority == gp) for gp in GoalPriority}

        return {
            "total": total, "completed": completed, "in_progress": in_progress,
            "pending": pending, "failed": failed, "cancelled": cancelled,
            "type_stats": type_stats, "priority_stats": priority_stats
        }


def create_goal_system(project_root: str) -> GoalSystem:
    return GoalSystem(project_root)