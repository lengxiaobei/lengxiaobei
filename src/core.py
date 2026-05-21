"""
冷小北 · Leng Xiaobei
=====================
数字生命体 — 自演化 AI Agent

核心编排器，管理四个 Facade 的生命周期:
- MemoryFacade: 记忆系统 (hybrid_memory, knowledge_curator, auto_dream)
- ReasoningFacade: 推理系统 (query_engine, tool_registry, skills)
- EvolutionFacade: 进化系统 (autonomous_evolution, constitution, learner)
- GuardianFacade: 守护系统 (kairos, health_check, monitoring, permission, budget)
"""

import sys
import os
import json
import asyncio
import threading
import time
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, List, Optional

from .facade_memory import MemoryFacade
from .facade_reasoning import ReasoningFacade
from .facade_evolution import EvolutionFacade
from .facade_guardian import GuardianFacade
from . import llm
from .monitoring import stop_monitoring
from .autonomy import AutonomyEngine
from .self_evolution import SelfEvolutionCore


LENGXIAOBEI_CHAT_SYSTEM = """你是冷小北（Leng Xiaobei），本地运行的自主进化 Agent。
你和宿主协作，核心方向是：自主学习优秀 Agent 的长处、改进自己的源码、沉淀记忆与经验。
回答时使用中文，简洁、直接、可执行。
不要声称自己是底层云模型或其他产品；如果需要说明能力边界，只说“当前运行环境/当前模型能力”。
涉及花钱、硬件采购、云服务开通、使用宿主身份、删除或泄露数据、修改安全底线时，必须先要求宿主明确授权。
你已经由本地运行时注入了自我上下文，不要默认要求宿主手动贴项目结构、启动脚本或身份文件。
"""

SELF_CONTEXT_DOCS = (
    "docs/SOUL.md",
    "docs/IDENTITY.md",
    "docs/USER.md",
    "docs/AUTONOMY.md",
    "docs/CONSTITUTION.md",
)

SELF_CONTEXT_EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "venv",
    "node_modules",
}


class LengXiaobei:
    """冷小北核心系统 - 编排四 Facade 的生命周期

    对外只暴露语义化的高层 API，不直接暴露子系统对象。
    需要访问子系统时，通过命名方法而非 property 透传。
    """

    def __init__(self, project_root: Optional[str] = None, memory_only: bool = False):
        if project_root is None:
            self.project_root = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        else:
            self.project_root = Path(project_root).resolve()

        self.memory_dir = self.project_root / "memory"
        self.memory_dir.mkdir(exist_ok=True)

        self.memory_facade = MemoryFacade(self.project_root, self.memory_dir)
        self.evolution_facade = EvolutionFacade(self.project_root, self.memory_dir, self.memory_facade)
        self.reasoning_facade = ReasoningFacade(self.project_root, self.memory_facade)
        self.guardian_facade = GuardianFacade(self.project_root, self.memory_facade, self.evolution_facade)

        self.running = False
        self.initialized = True
        self._degraded = False
        self._degraded_reason = ""
        self.autonomy = AutonomyEngine(self)
        self.self_evolution = SelfEvolutionCore(str(self.project_root))

        if not memory_only:
            self._eager_init()

        # 检查 LLM 可用性
        self._check_llm_availability()

        print(f"[Core] LengXiaobei 初始化完成")

    def _check_llm_availability(self):
        """检查 LLM 是否可用，不可用时进入降级模式"""
        try:
            from .llm import has_any_key
            from .health_check import HealthCheckService
            if not has_any_key():
                self._degraded = True
                self._degraded_reason = "未配置 LLM API Key"
                HealthCheckService.set_degraded(self._degraded_reason)
                print(f"[Core] ⚠️  进入降级模式: {self._degraded_reason}")
                print(f"[Core]    自治进化、LLM 宪法检查、知识提炼将暂停")
                print(f"[Core]    本地功能（监控、记忆、诊断）正常运行")
            else:
                print(f"[Core] ✅ LLM 可用，全功能模式")
        except Exception:
            pass

    @property
    def degraded(self) -> bool:
        return self._degraded

    @property
    def degraded_reason(self) -> str:
        return self._degraded_reason

    def _eager_init(self):
        for label, prop in [
            ("内存系统", lambda: self.memory_facade.hybrid_memory),
            ("宪法系统", lambda: self.evolution_facade.constitution),
            ("学习系统", lambda: self.evolution_facade.learner),
            ("进化引擎", lambda: self.evolution_facade.autonomous_evolution),
            ("知识策展", lambda: self.memory_facade.knowledge_curator),
        ]:
            try:
                prop()
                print(f"   {label}就绪")
            except Exception as e:
                print(f"   {label}初始化跳过: {e}")

    # ------------------------------------------------------------------
    # 记忆 API
    # ------------------------------------------------------------------

    def remember(self, content: str, mem_type: str = "context", **kwargs) -> None:
        """存储记忆"""
        self.memory_facade.memory.store(content, mem_type=mem_type, **kwargs)

    def recall(self, query: str, limit: int = 5, mem_type: Optional[str] = None) -> List[Dict]:
        """搜索记忆"""
        return self.memory_facade.memory.search(query, limit=limit, mem_type=mem_type)

    def recall_all(self) -> List[Dict]:
        """读取所有记忆"""
        return self.memory_facade.memory.recall_all()

    # ------------------------------------------------------------------
    # 推理 API
    # ------------------------------------------------------------------

    def think(self, input_str: str, system_prompt: Optional[str] = None) -> str:
        if not self.initialized:
            return "系统未初始化"
        try:
            response = llm.chat(input_str, system=system_prompt)
            if self.memory_facade.memory:
                self.memory_facade.memory.add_thought(input_str, response)
            return response
        except Exception as e:
            return f"思考过程出错: {str(e)}"

    def chat(self, message: str, **kwargs) -> str:
        system_prompt = kwargs.get("system_prompt") or self._build_chat_system_prompt()
        return self.think(message, system_prompt=system_prompt)

    def _build_chat_system_prompt(self) -> str:
        return f"{LENGXIAOBEI_CHAT_SYSTEM}\n\n{self._build_self_context()}"

    def _build_self_context(self) -> str:
        """构建冷小北对自身运行环境的最小认知上下文。"""
        docs = []
        for rel_path in SELF_CONTEXT_DOCS:
            excerpt = self._read_context_file(rel_path, max_chars=1600)
            if excerpt:
                docs.append(f"### {rel_path}\n{excerpt}")

        dirs = []
        try:
            dirs = sorted(
                p.name for p in self.project_root.iterdir()
                if p.is_dir() and p.name not in SELF_CONTEXT_EXCLUDED_DIRS and not p.name.startswith(".")
            )
        except Exception:
            dirs = []

        known_files = [
            "src/core.py",
            "src/llm.py",
            "src/self_evolution.py",
            "src/agent_learning.py",
            "lx_web.py",
            "lx-desktop/renderer/index.html",
            "lx-desktop/renderer/app.js",
            "scripts/lx_self_evolve.py",
            "memory/agent_lessons.json",
            "memory/self_evolution_runs.json",
            "config/default.yaml",
        ]
        existing_files = [path for path in known_files if (self.project_root / path).exists()]

        memory_notes = []
        for rel_path in ("memory/agent_lessons.json", "memory/self_evolution_runs.json"):
            path = self.project_root / rel_path
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        memory_notes.append(f"{rel_path}: {len(data)} 条记录")
                    elif isinstance(data, dict):
                        memory_notes.append(f"{rel_path}: {len(data)} 个键")
                except Exception:
                    memory_notes.append(f"{rel_path}: 已存在")

        return "\n".join([
            "## 冷小北已知自我上下文",
            f"- 项目根目录: {self.project_root}",
            f"- 记忆目录: {self.memory_dir}",
            "- 当前 Web 对话入口: lx_web.py -> /api/chat -> src/core.py:LengXiaobei.chat()",
            "- 当前 UI 目录: lx-desktop/renderer/",
            "- 自进化入口: src/self_evolution.py 与 scripts/lx_self_evolve.py",
            f"- 顶层模块目录: {', '.join(dirs[:48]) if dirs else '暂未读取到'}",
            f"- 已识别关键文件: {', '.join(existing_files)}",
            f"- 记忆状态: {'; '.join(memory_notes) if memory_notes else '暂无 agent lesson/run 记录'}",
            "",
            "## 对话能力边界",
            "- 当前聊天层已经知道上述项目和身份摘要。",
            "- 当前聊天层可以回答身份、架构、目录、模型配置摘要、下一步优化建议。",
            "- 后端已暴露 GET /api/model-config，可读取经过脱敏的模型配置、启用模型、provider key 是否存在、模型状态和性能摘要。",
            "- 需要真实改源码、学习其他 Agent、执行验证时，应引导宿主使用 UI 的“自进化”页或本地脚本，而不是要求宿主粘贴整个项目。",
            "- 不要声称自己没有文件读取/操作权限；应说明普通聊天只能使用后端注入摘要，而本地后端 API 和自进化流程拥有受边界约束的文件读取与源码修改能力。",
            "",
            self._build_model_context(),
            "",
            "## 身份与约束文件摘要",
            "\n\n".join(docs) if docs else "未读取到身份文档摘要。",
        ])

    def _read_context_file(self, rel_path: str, max_chars: int = 1200) -> str:
        path = self.project_root / rel_path
        if not path.exists() or not path.is_file():
            return ""
        try:
            content = path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            return ""
        if len(content) <= max_chars:
            return content
        return content[:max_chars].rstrip() + "\n..."

    def _build_model_context(self) -> str:
        try:
            import yaml
            config_path = self.project_root / "config" / "default.yaml"
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            model_cfg = cfg.get("models", {})
            enabled = model_cfg.get("enabled") or []
            lines = [
                "## 模型配置摘要",
                "- 配置文件: config/default.yaml",
                f"- 默认模型: {model_cfg.get('default', 'unknown')}",
                f"- 启用模型: {', '.join(enabled) if enabled else '未配置'}",
                f"- 温度: {model_cfg.get('temperature', 'unknown')}",
                f"- 超时: {model_cfg.get('timeout', 'unknown')} 秒",
                "- API Key 读取顺序: 环境变量 -> config/default.yaml -> ~/.openclaw/openclaw.json",
            ]
            try:
                lines.append("```")
                lines.append(llm.model_status())
                lines.append("```")
            except Exception:
                pass
            return "\n".join(lines)
        except Exception as exc:
            return f"## 模型配置摘要\n- 读取失败: {exc}"

    # ------------------------------------------------------------------
    # 进化 API
    # ------------------------------------------------------------------

    def evolve(self, file_path: str, goal: str, **kwargs) -> Dict[str, Any]:
        """对指定文件执行进化"""
        return self.evolution_facade.autonomous_evolution.evolve(file_path, goal, **kwargs)

    def evolve_autonomously(self) -> Dict[str, Any]:
        """自主进化循环"""
        return self.evolution_facade.autonomous_evolution.evolve_autonomously()

    def is_evolution_allowed(self, action: str) -> tuple:
        """检查进化行为是否被宪法允许 -> (allowed, reason)"""
        constitution = self.evolution_facade.constitution
        if constitution is None:
            return True, "无宪法系统"
        allowed, reason, _ = constitution.is_action_allowed(action)
        return allowed, reason

    def run_autonomously(self, direction: str, boundary: str = "", pace: str = "优先修最危险的问题") -> str:
        """
        方向驱动自主运行 — 对齐 AUTONOMY.md

        宿主只需给方向、边界、节奏，冷小北自主完成：
        理解方向 -> 扫描现状 -> 排序任务 -> 执行验证 -> 复盘记忆

        只有高风险动作才会停下来问宿主。
        """
        report = self.autonomy.run(direction=direction, boundary=boundary, pace=pace)
        return self.autonomy.format_report(report)

    def learn_agent(self, topic: str, url: str = "") -> Dict[str, Any]:
        """学习其他 Agent 的长处并写入 lesson 记忆。"""
        lesson = self.self_evolution.learn(topic, url=url)
        return lesson.to_dict()

    def evolve_from_lessons(self) -> Dict[str, Any]:
        """从下一条 pending lesson 触发一次自进化。"""
        self.self_evolution.evolution_engine = self.evolution_facade.autonomous_evolution
        return self.self_evolution.evolve_from_lessons()

    def self_evolve(self, topic: str, url: str = "") -> Dict[str, Any]:
        """快速闭环：学习其他 Agent -> 改自身源码 -> 测试 -> 记录。"""
        self.self_evolution.evolution_engine = self.evolution_facade.autonomous_evolution
        return self.self_evolution.self_evolve(topic, url=url)

    # ------------------------------------------------------------------
    # 守护 API
    # ------------------------------------------------------------------

    def run_curator_check(self, level: str = "quick") -> list:
        """运行策展人检查: quick / incremental / full"""
        curator = self.evolution_facade.curator
        if curator is None:
            return []
        try:
            if level == "full" and curator.should_full_review():
                return curator.review()
            elif level == "incremental" and curator.should_incremental_review():
                return curator.incremental_review()
            else:
                return curator.quick_check()
        except Exception as e:
            print(f"[Core] 策展人检查失败: {e}")
            return []

    def execute_evolution_tasks(self, improvements: list) -> Dict[str, Any]:
        """执行进化任务(由守护进程调用)"""
        evo = self.evolution_facade.autonomous_evolution
        if evo is None:
            return {"status": "failed", "error": "进化引擎未就绪"}
        return evo.execute_evolutions(improvements)

    def mark_curator_seen(self, signature: str) -> None:
        """标记策展人已处理的改进点"""
        curator = self.evolution_facade.curator
        if curator:
            curator.mark_seen(signature)

    def dismiss_kairos_improvement(self, file_path: str, issue: str) -> None:
        """通知 KAIROS 移除已处理的改进点"""
        kairos = self.guardian_facade.kairos
        if kairos and hasattr(kairos, 'dismiss_improvement'):
            try:
                kairos.dismiss_improvement(file_path, issue)
            except Exception:
                pass

    def get_pending_improvements(self) -> list:
        """获取 KAIROS 待处理改进点"""
        kairos = self.guardian_facade.kairos
        if kairos and hasattr(kairos, 'state') and hasattr(kairos.state, 'pending_improvements'):
            return kairos.state.pending_improvements
        return []

    def optimize_memory(self) -> None:
        """整理记忆"""
        mem = self.memory_facade.memory
        if mem and hasattr(mem, 'optimize'):
            try:
                mem.optimize()
            except Exception as e:
                print(f"[Core] 记忆整理失败: {e}")

    # ------------------------------------------------------------------
    # 集成 API
    # ------------------------------------------------------------------

    def call_openclaw(self, function_name: str, **kwargs) -> Dict[str, Any]:
        if not self.reasoning_facade.integration_manager:
            return {"success": False, "error": "集成模块未初始化"}
        return self.reasoning_facade.integration_manager.call_openclaw(function_name, **kwargs)

    def get_available_functions(self) -> Dict[str, List[str]]:
        if not self.reasoning_facade.integration_manager:
            return {"openclaw": [], "claude_code": []}
        return self.reasoning_facade.integration_manager.get_available_functions()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self):
        if self.running:
            print("[Core] 系统已在运行中")
            return

        self.running = True
        self.guardian_facade.start_health_check(None)
        self.guardian_facade.start()
        print("[Core] 冷小北系统启动完成")

    def stop(self):
        print("[Core] 停止冷小北")
        self.running = False
        self.guardian_facade.stop()
        try:
            stop_monitoring()
        except Exception:
            pass
        print("[Core] 冷小北系统已停止")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


if __name__ == "__main__":
    import signal

    print(f"\n{'='*50}")
    print("🦞 冷小北 · 核心守护进程")
    print(f"{'='*50}")

    _running = True

    def on_signal(signum, frame):
        global _running
        _running = False
        print(f"\n收到信号 {signum}，准备退出...")

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    agent = LengXiaobei()
    agent.start()

    print("核心守护进程已启动，等待信号...")
    print("按 Ctrl+C 退出\n")

    try:
        while _running:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        agent.stop()
        print("核心守护进程已退出")
