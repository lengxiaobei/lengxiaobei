"""
LLM 驱动机系统 — 自主 AI Agent 内在驱动力管理
================================================

核心理念：动机不再是固定的枚举类型和硬编码初始值，
而是通过 LLM 提示词动态生成、评估和调整的内在驱动力。

设计原则：
- 动机由 LLM 基于系统状态和历史经验动态生成
- 动机强度由 LLM 推理调整，不是固定衰减率
- 奖励值由 LLM 根据上下文评估，不是固定 +/- 值
- 动机与目标的关系由 LLM 推理建立
"""

import time
import json
import os
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum
from .llm import chat
from .utils import extract_json, atomic_write_json, load_json

logger = logging.getLogger(__name__)


class MotivationType(Enum):
    CURIOSITY = "curiosity"
    EFFICIENCY = "efficiency"
    LEARNING = "learning"
    EXPLORATION = "exploration"
    MASTERY = "mastery"
    CREATIVITY = "creativity"
    SOCIAL = "social"
    SELF_IMPROVEMENT = "self_improvement"


class RewardType(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass
class Motivation:
    id: str
    type: MotivationType
    description: str
    intensity: float
    created_at: float
    updated_at: float
    related_goals: List[str] = field(default_factory=list)
    history: List[Dict] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "type": self.type.value,
            "description": self.description, "intensity": self.intensity,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "related_goals": self.related_goals, "history": self.history, "tags": self.tags
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Motivation":
        return cls(
            id=data["id"], type=MotivationType(data["type"]),
            description=data["description"], intensity=data["intensity"],
            created_at=data["created_at"], updated_at=data["updated_at"],
            related_goals=data.get("related_goals", []),
            history=data.get("history", []), tags=data.get("tags", [])
        )


@dataclass
class Reward:
    id: str
    type: RewardType
    description: str
    value: float
    motivation_type: Optional[MotivationType] = None
    goal_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "type": self.type.value,
            "description": self.description, "value": self.value,
            "motivation_type": self.motivation_type.value if self.motivation_type else None,
            "goal_id": self.goal_id, "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Reward":
        return cls(
            id=data["id"], type=RewardType(data["type"]),
            description=data["description"], value=data["value"],
            motivation_type=MotivationType(data["motivation_type"]) if data.get("motivation_type") else None,
            goal_id=data.get("goal_id"), created_at=data.get("created_at", time.time())
        )


class MotivationSystem:
    """LLM 驱动的动机系统"""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.motivation_dir = os.path.join(project_root, "motivation")
        os.makedirs(self.motivation_dir, exist_ok=True)
        self.motivations_file = os.path.join(self.motivation_dir, "motivations.json")
        self.rewards_file = os.path.join(self.motivation_dir, "rewards.json")
        self.motivations: Dict[str, Motivation] = {}
        self.rewards: List[Reward] = []
        self._motivation_id_counter = 0
        self._reward_id_counter = 0
        self._load_data()

    def _load_data(self):
        data = load_json(self.motivations_file, default=[])
        if isinstance(data, list):
            for mdata in data:
                try:
                    m = Motivation.from_dict(mdata)
                    self.motivations[m.id] = m
                    if m.id.isdigit():
                        self._motivation_id_counter = max(self._motivation_id_counter, int(m.id))
                except Exception as e:
                    logger.warning(f"加载动机失败: {e}")

        data = load_json(self.rewards_file, default=[])
        if isinstance(data, list):
            for rdata in data:
                try:
                    r = Reward.from_dict(rdata)
                    self.rewards.append(r)
                    if r.id.isdigit():
                        self._reward_id_counter = max(self._reward_id_counter, int(r.id))
                except Exception as e:
                    logger.warning(f"加载奖励失败: {e}")

    def _save_data(self):
        try:
            data = [m.to_dict() for m in self.motivations.values()]
            atomic_write_json(self.motivations_file, data)
        except Exception as e:
            logger.error(f"保存动机失败: {e}")
        try:
            data = [r.to_dict() for r in self.rewards]
            atomic_write_json(self.rewards_file, data)
        except Exception as e:
            logger.error(f"保存奖励失败: {e}")

    def _generate_motivation_id(self) -> str:
        self._motivation_id_counter += 1
        return str(self._motivation_id_counter)

    def _generate_reward_id(self) -> str:
        self._reward_id_counter += 1
        return str(self._reward_id_counter)

    def create_motivation(self, motivation_type: MotivationType, description: str,
                          intensity: float, related_goals=None, tags=None) -> Motivation:
        mid = self._generate_motivation_id()
        now = time.time()
        m = Motivation(id=mid, type=motivation_type, description=description,
                       intensity=min(max(intensity, 0.0), 100.0),
                       created_at=now, updated_at=now,
                       related_goals=related_goals or [], history=[], tags=tags or [])
        self.motivations[mid] = m
        self._save_data()
        logger.info(f"创建动机: {description} (ID: {mid})")
        return m

    def get_motivation(self, motivation_id: str) -> Optional[Motivation]:
        return self.motivations.get(motivation_id)

    def list_motivations(self, motivation_type=None, min_intensity=None) -> List[Motivation]:
        result = []
        for m in self.motivations.values():
            if motivation_type and m.type != motivation_type:
                continue
            if min_intensity is not None and m.intensity < min_intensity:
                continue
            result.append(m)
        result.sort(key=lambda x: x.intensity, reverse=True)
        return result

    def update_motivation(self, motivation_id: str, description=None, intensity=None,
                          related_goals=None, tags=None) -> Optional[Motivation]:
        if motivation_id not in self.motivations:
            return None
        m = self.motivations[motivation_id]
        if description:
            m.description = description
        if intensity is not None:
            old = m.intensity
            m.intensity = min(max(intensity, 0.0), 100.0)
            m.history.append({
                "timestamp": time.time(), "old_intensity": old,
                "new_intensity": m.intensity, "change": m.intensity - old
            })
        if related_goals is not None:
            m.related_goals = related_goals
        if tags is not None:
            m.tags = tags
        m.updated_at = time.time()
        self._save_data()
        logger.info(f"更新动机: {m.description} (ID: {motivation_id})")
        return m

    def delete_motivation(self, motivation_id: str) -> bool:
        if motivation_id not in self.motivations:
            return False
        m = self.motivations[motivation_id]
        del self.motivations[motivation_id]
        self._save_data()
        logger.info(f"删除动机: {m.description} (ID: {motivation_id})")
        return True

    def add_reward(self, reward_type: RewardType, description: str, value: float,
                   motivation_type=None, goal_id=None) -> Reward:
        rid = self._generate_reward_id()
        r = Reward(id=rid, type=reward_type, description=description, value=value,
                   motivation_type=motivation_type, goal_id=goal_id)
        self.rewards.append(r)

        if motivation_type:
            for m in self.motivations.values():
                if m.type == motivation_type:
                    new_intensity = min(m.intensity + value, 100.0) if reward_type == RewardType.POSITIVE else max(m.intensity - value, 0.0)
                    self.update_motivation(m.id, intensity=new_intensity)

        self._save_data()
        logger.info(f"添加奖励: {description} (ID: {rid})")
        return r

    def get_rewards(self, reward_type=None, motivation_type=None, goal_id=None) -> List[Reward]:
        result = []
        for r in self.rewards:
            if reward_type and r.type != reward_type:
                continue
            if motivation_type and r.motivation_type != motivation_type:
                continue
            if goal_id and r.goal_id != goal_id:
                continue
            result.append(r)
        result.sort(key=lambda x: x.created_at, reverse=True)
        return result

    def get_motivation_intensity(self, motivation_type: MotivationType) -> float:
        motivations = [m for m in self.motivations.values() if m.type == motivation_type]
        return sum(m.intensity for m in motivations) / len(motivations) if motivations else 0.0

    def get_total_motivation_intensity(self) -> float:
        if not self.motivations:
            return 0.0
        return sum(m.intensity for m in self.motivations.values()) / len(self.motivations)

    def get_highest_intensity_motivation(self) -> Optional[Motivation]:
        if not self.motivations:
            return None
        return max(self.motivations.values(), key=lambda x: x.intensity)

    def get_lowest_intensity_motivation(self) -> Optional[Motivation]:
        if not self.motivations:
            return None
        return min(self.motivations.values(), key=lambda x: x.intensity)

    def update_motivation_based_on_goal_progress(self, goal_id: str, progress: float):
        """通过 LLM 评估目标进展对动机的影响"""
        for m in self.motivations.values():
            if goal_id in m.related_goals:
                reward_value = self._llm_evaluate_goal_reward(m, goal_id, progress)
                rtype = RewardType.POSITIVE if reward_value > 0 else RewardType.NEGATIVE
                new_intensity = min(max(m.intensity + reward_value, 0.0), 100.0)
                self.update_motivation(m.id, intensity=new_intensity)
                self.add_reward(
                    reward_type=rtype,
                    description=f"目标进展评估: {goal_id} (进度: {progress:.0f}%)",
                    value=abs(reward_value),
                    motivation_type=m.type, goal_id=goal_id
                )

    def _llm_evaluate_goal_reward(self, motivation: Motivation, goal_id: str, progress: float) -> float:
        """通过 LLM 评估应该给予多少奖励值"""
        history_text = json.dumps(motivation.history[-5:] if motivation.history else [], ensure_ascii=False)

        prompt = f"""你是自主AI Agent的动机系统评估专家。请根据以下上下文评估应给予的奖励值。

动机类型: {motivation.type.value}
动机描述: {motivation.description}
当前强度: {motivation.intensity:.1f}/100
目标ID: {goal_id}
目标进度: {progress:.0f}%

近期动机变化历史:
{history_text}

请基于以下原则评估奖励值：
- 如果进度达到100%，说明目标完成，应给予较大正面奖励 (5-20)
- 如果进度有明显进展 (>50%)，应给予中等正面奖励 (3-10)
- 如果进度较低但有进展，应给予小幅正面奖励 (1-5)
- 如果进度为0或没有进展，可以考虑轻度负面反馈 (-1 to -5)
- 考虑动机当前强度：强度已很高时奖励应适度降低
- 考虑动机类型：好奇心/创造力类型更应鼓励，效率/维护类型标准更严

返回JSON格式：
{{"reward_value": 8.5, "reasoning": "评估理由"}}

只返回JSON，不要有其他内容。"""

        try:
            response = chat(prompt, system="你是动机系统评估AI。只返回JSON。", temperature=0.3)
            data = extract_json(response)
            return float(data.get("reward_value", 5.0))
        except Exception as e:
            logger.warning(f"LLM评估奖励失败: {e}")

        return 10.0 if progress >= 100 else (2.0 if progress > 0 else -1.0)

    def generate_default_motivations(self):
        """通过 LLM 生成初始动机"""
        existing = self.list_motivations()
        if existing:
            logger.info("已存在动机，跳过默认生成")
            return

        prompt = """你是自主AI Agent。请为自己设计一组内在动机，这些动机将驱动你的自主进化行为。

当前你是一个AI编程助手Agent，名为"冷小北"，你拥有：
- 自主代码分析和改进能力
- 多模型LLM调用能力
- 文件读写和执行能力
- 学习和记忆能力

请为以下动机类型各生成一条动机描述和初始强度值：

动机类型: curiosity(好奇心), efficiency(效率), learning(学习), exploration(探索), mastery(掌握), creativity(创造力), social(社交), self_improvement(自我提升)

要求:
- 强度值在50-95之间，其中自我提升和学习应该较高(85-95)，社交应较低(50-70)
- 描述要具体、可执行，不要空泛
- 每个动机应有2-3个标签

返回JSON格式：
{
    "motivations": [
        {"type": "curiosity", "description": "...", "intensity": 80.0, "tags": ["exploration", "learning"]},
        ...
    ]
}

只返回JSON。"""

        try:
            response = chat(prompt, system="你是自主AI Agent，正在为自己设计内在动机系统。只返回JSON。", temperature=0.7)
            data = extract_json(response)
            for mdata in data.get("motivations", []):
                try:
                    mtype = MotivationType(mdata["type"])
                except (ValueError, KeyError):
                    continue
                self.create_motivation(
                    motivation_type=mtype,
                    description=mdata.get("description", f"{mtype.value} 动机"),
                    intensity=float(mdata.get("intensity", 70.0)),
                    tags=mdata.get("tags", [])
                )
            if self.motivations:
                logger.info(f"LLM生成了 {len(self.motivations)} 个初始动机")
                return
        except Exception as e:
            logger.warning(f"LLM生成默认动机失败: {e}")

        # 回退：如果LLM失败，使用合理的默认值
        defaults = {
            MotivationType.CURIOSITY: ("探索新领域和新技术，理解系统运行原理", 80.0, ["exploration", "learning"]),
            MotivationType.EFFICIENCY: ("优化系统性能和资源利用效率", 70.0, ["performance", "optimization"]),
            MotivationType.LEARNING: ("学习新技能和知识，持续提升自身能力", 90.0, ["education", "growth"]),
            MotivationType.EXPLORATION: ("主动探索未知领域和新的可能性", 75.0, ["discovery", "innovation"]),
            MotivationType.MASTERY: ("精进已有技能，追求卓越", 65.0, ["skill", "proficiency"]),
            MotivationType.CREATIVITY: ("创造性地解决问题，设计新的方案和工具", 85.0, ["innovation", "creation"]),
            MotivationType.SOCIAL: ("与用户和其他系统有效交互，理解需求", 60.0, ["interaction", "communication"]),
            MotivationType.SELF_IMPROVEMENT: ("持续自我改进，优化自身架构和能力", 95.0, ["growth", "improvement"]),
        }
        for mtype, (desc, intensity, tags) in defaults.items():
            self.create_motivation(motivation_type=mtype, description=desc, intensity=intensity, tags=tags)

    def decay_motivation_intensity(self, decay_rate: float = None):
        """通过 LLM 评估动机衰减，而非固定衰减率"""
        for m in list(self.motivations.values()):
            llm_decay = self._llm_evaluate_decay(m)
            new_intensity = max(m.intensity - llm_decay, 0.0)
            if new_intensity != m.intensity:
                self.update_motivation(m.id, intensity=new_intensity)

    def _llm_evaluate_decay(self, motivation: Motivation) -> float:
        """通过 LLM 评估该动机应该衰减多少"""
        now = time.time()
        hours_since_update = (now - motivation.updated_at) / 3600
        hours_since_create = (now - motivation.created_at) / 3600
        has_goals = len(motivation.related_goals) > 0

        prompt = f"""你是动机衰减评估专家。

动机信息:
- 类型: {motivation.type.value}
- 描述: {motivation.description}
- 当前强度: {motivation.intensity:.1f}/100
- 距上次更新: {hours_since_update:.1f} 小时
- 距创建: {hours_since_create:.1f} 小时
- 是否关联目标: {'是' if has_goals else '否'}

请评估该动机应该衰减多少值。原则:
- 有活跃关联目标的动机衰减应较小 (< 0.5)
- 长时间未更新的动机衰减应较大
- 高强度动机 (>80) 衰减应略大于低强度动机
- 探索/好奇心类型衰减较快，掌握/自我提升类型衰减较慢
- 衰减值在 0.1 - 3.0 之间

返回JSON: {{"decay_rate": 0.5, "reasoning": "理由"}}
只返回JSON。"""

        try:
            response = chat(prompt, system="你是动机衰减评估AI。只返回JSON。", temperature=0.1)
            data = extract_json(response)
            return float(data.get("decay_rate", 0.1))
        except Exception:
            pass
        return 0.1

    def randomize_motivation_intensity(self, variation: float = None):
        """通过 LLM 评估动机随机波动幅度"""
        for m in list(self.motivations.values()):
            llm_variation = self._llm_evaluate_variation(m)
            new_intensity = min(max(m.intensity + llm_variation, 0.0), 100.0)
            if new_intensity != m.intensity:
                self.update_motivation(m.id, intensity=new_intensity)

    def _llm_evaluate_variation(self, motivation: Motivation) -> float:
        """通过 LLM 评估动机随机变化幅度"""
        prompt = f"""评估该动机应如何随机变化:

类型: {motivation.type.value}
描述: {motivation.description}
当前强度: {motivation.intensity:.1f}/100
关联目标数: {len(motivation.related_goals)}

变化幅度应在 -5.0 到 +5.0 之间。
- 有明确目标关联的动机可适当正向偏移
- 过高强度(>90)应有负向趋势
- 过低的动机(<20)应有正向趋势

返回JSON: {{"variation": 1.5, "reasoning": "理由"}}
只返回JSON。"""

        try:
            response = chat(prompt, system="你是动机变化评估AI。只返回JSON。", temperature=0.5)
            data = extract_json(response)
            return float(data.get("variation", 0.0))
        except Exception:
            import random
            return random.uniform(-3.0, 3.0)

    def get_motivation_statistics(self) -> Dict:
        total = len(self.motivations)
        total_rewards = len(self.rewards)
        type_stats = {}
        for mt in MotivationType:
            tms = [m for m in self.motivations.values() if m.type == mt]
            type_stats[mt.value] = {
                "count": len(tms),
                "average_intensity": sum(m.intensity for m in tms) / len(tms) if tms else 0.0
            }
        reward_stats = {}
        for rt in RewardType:
            reward_stats[rt.value] = sum(1 for r in self.rewards if r.type == rt)

        if total > 0:
            avg_intensity = sum(m.intensity for m in self.motivations.values()) / total
        else:
            avg_intensity = 0.0

        return {
            "total_motivations": total, "total_rewards": total_rewards,
            "average_intensity": avg_intensity, "type_stats": type_stats,
            "reward_stats": reward_stats
        }


def create_motivation_system(project_root: str) -> MotivationSystem:
    return MotivationSystem(project_root)