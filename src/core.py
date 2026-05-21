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
        return self.think(message)

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