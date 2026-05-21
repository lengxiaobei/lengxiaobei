"""
LLM 驱动开发团队 — 自主 AI Agent 协作开发
===========================================

核心理念：不再使用固定的任务流水线和硬编码角色映射，
而是通过 LLM 提示词动态组织协作流程和角色分工。

设计原则：
- 任务分配由 LLM 根据任务特点动态决定
- 协作流程由 LLM 推理，不是固定4步流水线
- 迭代次数由 LLM 根据结果质量动态评估
"""

import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from .llm import chat


class TeamRole(Enum):
    GENERATOR = "generator"
    CRITIC = "critic"
    TESTER = "tester"
    ARCHITECT = "architect"
    PM = "pm"


@dataclass
class DevTask:
    id: str
    title: str
    description: str
    role: TeamRole
    status: str = "todo"
    result: Any = None


class DevTeam:
    """LLM 驱动的开发团队"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.prompts_dir = self.project_root / "prompts"

    def _load_team_prompt(self) -> str:
        prompt_file = self.prompts_dir / "TEAM.md"
        if prompt_file.exists():
            return prompt_file.read_text(encoding="utf-8")
        return ""

    def _role_system_prompt(self, role: TeamRole, task_context: str = "") -> str:
        """通过 LLM 生成本次任务的特定角色提示词"""
        prompt = f"""你是AI开发团队的角色定义专家。请为该角色生成 system prompt。

角色: {role.value}
任务上下文: {task_context}

返回该角色应扮演的身份描述(一句话，中文)：
JSON: {{"role_prompt": "你是..."}}
只返回JSON。"""

        try:
            response = chat(prompt, system="你是角色定义专家。只返回JSON。", temperature=0.3)
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                return data.get("role_prompt", f"你是{role.value}角色")
        except Exception:
            pass

        defaults = {
            TeamRole.GENERATOR: "你是代码生成专家，只返回代码不包含解释",
            TeamRole.CRITIC: "你是代码审查专家，返回 JSON 格式的审查报告",
            TeamRole.TESTER: "你是测试工程师，返回测试报告",
            TeamRole.ARCHITECT: "你是架构师，从架构角度提供决策建议",
            TeamRole.PM: "你是项目经理，确保团队高效协作",
        }
        return defaults.get(role, "")

    def create_session(self, file_path: str, goal: str) -> List[DevTask]:
        """通过 LLM 动态规划任务分配"""
        prompt = f"""你是AI开发团队的项目经理。请根据以下开发任务规划工作分配。

文件路径: {file_path}
开发目标: {goal}

请规划需要哪些角色参与以及各角色应完成什么任务。
可用角色: generator(代码生成), critic(代码审查), tester(测试), architect(架构师), pm(项目经理)

返回JSON:
{{
    "tasks": [
        {{"role": "architect", "title": "架构评估", "description": "评估改造方向"}},
        {{"role": "generator", "title": "代码生成", "description": "实现功能"}},
        {{"role": "critic", "title": "代码审查", "description": "审查生成的代码"}},
        {{"role": "tester", "title": "测试验证", "description": "验证修改正确性"}}
    ],
    "reasoning": "任务分配理由"
}}

只返回JSON。"""

        try:
            response = chat(prompt, system="你是AI开发团队的项目经理。只返回JSON。", temperature=0.4)
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                tasks = []
                for t in data.get("tasks", []):
                    try:
                        role = TeamRole(t["role"])
                    except (ValueError, KeyError):
                        role = TeamRole.GENERATOR
                    tasks.append(DevTask(
                        id=str(uuid.uuid4())[:8],
                        title=t.get("title", role.value),
                        description=t.get("description", goal),
                        role=role
                    ))
                if tasks:
                    return tasks
        except Exception as e:
            print(f"[DevTeam] LLM规划失败: {e}")

        # 回退
        return [
            DevTask(id=str(uuid.uuid4())[:8], title="架构评估",
                    description=f"评估 {file_path} 的架构改进方向", role=TeamRole.ARCHITECT),
            DevTask(id=str(uuid.uuid4())[:8], title="生成代码",
                    description=f"实现: {goal}", role=TeamRole.GENERATOR),
            DevTask(id=str(uuid.uuid4())[:8], title="审查代码",
                    description="审查生成的代码", role=TeamRole.CRITIC),
            DevTask(id=str(uuid.uuid4())[:8], title="测试代码",
                    description="验证修改的正确性", role=TeamRole.TESTER),
        ]

    def execute(self, task: DevTask, context: Dict[str, Any]) -> Dict[str, Any]:
        system = self._role_system_prompt(task.role, task.description)
        team_context = self._load_team_prompt()

        ctx_text = json.dumps(context, ensure_ascii=False, indent=2)
        prompt = f"{team_context}\n\n当前任务: {task.description}\n\n上下文:\n{ctx_text}"
        response = chat(prompt, system=system)
        task.status = "done"
        task.result = response
        return {"role": task.role.value, "result": response}

    def review_loop(self, file_path: str, goal: str, max_iterations: int = None) -> Dict[str, Any]:
        """通过 LLM 动态评估是否需要更多迭代"""
        tasks = self.create_session(file_path, goal)
        context = {"file_path": file_path, "goal": goal}
        history = []

        iteration = 0
        while True:
            iteration += 1
            for task in tasks:
                result = self.execute(task, context)
                context[task.role.value] = result["result"]
                history.append({"iteration": iteration, "role": task.role.value, "status": "done"})

            # 通过 LLM 评估是否需要继续迭代
            should_continue, reason = self._should_continue(context, history, iteration)
            if not should_continue or iteration >= (max_iterations or 10):
                break
            print(f"[DevTeam] 继续迭代 ({iteration}): {reason}")

        return {"status": "completed", "iterations": iteration, "context": context, "history": history}

    def _should_continue(self, context: Dict, history: List, current_iteration: int) -> tuple:
        """通过 LLM 评估是否需要继续迭代"""
        prompt = f"""评估AI开发团队的当前迭代结果，决定是否需要继续迭代。

当前迭代次数: {current_iteration}
各角色输出摘要:
{json.dumps({k: str(v)[:200] for k, v in context.items() if isinstance(v, str)}, ensure_ascii=False, indent=2)}

返回JSON:
{{
    "should_continue": false,
    "reasoning": "质量已达预期，无需继续",
    "max_recommended_iterations": 3
}}

迭代判断原则:
- 如果审查(critic)结果认为代码质量已达标，不需要继续
- 如果测试(tester)结果全部通过，不需要继续
- 如果生成器(generator)输出完整且合理，不需要继续
- 最多推荐迭代 5 次

只返回JSON。"""

        try:
            response = chat(prompt, system="你是AI开发团队项目管理专家。只返回JSON。", temperature=0.2)
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                return data.get("should_continue", False), data.get("reasoning", "")
        except Exception:
            pass

        # 简单回退
        critic_result = str(context.get("critic", ""))
        tester_result = str(context.get("tester", ""))
        needs_more = "needs_revision" in critic_result or "failed" in tester_result
        return needs_more and current_iteration < 3, "回退判断"


def create_dev_team(project_root: str) -> DevTeam:
    return DevTeam(project_root)