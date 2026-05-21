"""
KAIROS 引擎 — 长会话心跳与状态管理核心类
"""

import os
import sys
import time
import json
import asyncio
import threading
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable

from .config import KairosConfig, KairosState, SessionState
from .daily_log import DailyLogManager
from .scheduler import CronScheduler
from . import monitor as mon
from . import decision as dec
from ..llm import chat
from ..language_selector import select_language


class Kairos:
    """KAIROS — 长会话心跳与状态管理"""

    def __init__(self, memory, project_root: str):
        self.memory = memory
        self.project_root = Path(project_root)
        self.memory_dir = self.project_root / "memory"
        self.config = KairosConfig()

        self.state = KairosState()
        self.state.project_root = project_root
        self.state.original_cwd = os.getcwd()

        self.daily_log = DailyLogManager(self.memory_dir)
        self.cron = CronScheduler(self.project_root)

        self._running = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._cron_task: Optional[asyncio.Task] = None
        self._monitor_thread: Optional[threading.Thread] = None

        self.on_heartbeat: Optional[Callable] = None
        self.on_session_timeout: Optional[Callable] = None
        self.on_evolution_trigger: Optional[Callable] = None

        self._last_monitor: float = 0
        self._last_decision: float = 0
        self._last_code_analysis: float = 0

    # ---- 生命周期 ----

    def activate(self, session_id: str = "") -> bool:
        if self.state.kairos_active:
            return True
        self.state.kairos_active = True
        self.state.session_id = session_id or f"kairos_{int(time.time())}"
        self.state.start_time = time.time()
        self._save_state()
        print(f"[KAIROS] Activated — session: {self.state.session_id}")
        return True

    def deactivate(self):
        self.state.kairos_active = False
        self.stop()
        self._save_state()
        print("[KAIROS] Deactivated")

    def start(self):
        if not self.state.kairos_active:
            print("[KAIROS] Not activated, call activate() first")
            return
        if self._running:
            return

        self._running = True

        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        def run_cron():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.cron.start(self._on_cron_fire))

        cron_thread = threading.Thread(target=run_cron, daemon=True)
        cron_thread.start()

        print("[KAIROS] Services started")

    def stop(self):
        self._running = False
        self.cron.stop()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)
        print("[KAIROS] Services stopped")

    # ---- 心跳循环 ----

    def _heartbeat_loop(self):
        while self._running:
            try:
                self._do_heartbeat()
                time.sleep(self.config.heartbeat_interval)
            except Exception as e:
                print(f"[KAIROS] Heartbeat error: {e}")
                time.sleep(10)

    def _do_heartbeat(self):
        now = time.time()
        self.state.last_heartbeat = now

        idle_time = now - self.state.last_interaction_time
        if idle_time > self.config.max_session_idle:
            self.state.session_state = SessionState.IDLE.value
        else:
            self.state.session_state = SessionState.ACTIVE.value

        if now - getattr(self, '_last_auto_save', 0) > self.config.auto_save_interval:
            self._auto_save()
            self._last_auto_save = now

        if now - self._last_monitor > self.config.monitor_interval:
            mon.monitor_system(self.state, self.config, self.daily_log)
            self._last_monitor = now

        if now - self._last_code_analysis > self.config.code_analysis_interval:
            mon.analyze_code(
                self.state, self.config, self.daily_log, self.project_root,
                self.memory,
                lambda fp: mon.generate_specific_suggestion(fp),
                lambda fp: mon.get_file_modification_count(self.memory, fp),
                lambda fp, days=1: mon.is_recently_processed(self.memory, fp, days)
            )
            self._last_code_analysis = now

        if now - self._last_decision > self.config.decision_interval:
            dec.make_decision(
                self.state, self.config, self.daily_log, self.on_evolution_trigger,
                lambda: dec.gather_observations(
                    self.state,
                    lambda: dec.get_historical_decisions(self.memory),
                    lambda: dec.get_memory_insights(self.memory)
                ),
                lambda obs: dec.evaluate_observations(
                    obs,
                    lambda fp: mon.generate_specific_suggestion(fp),
                    lambda hd: dec.calculate_decision_success_rate(hd)
                ),
                lambda ev: dec.make_informed_decision(ev),
                lambda: self._trigger_evolution(),
                lambda targets: self._trigger_optimization(targets),
                lambda topics: self._trigger_learning(topics),
                lambda d, e: self._record_decision(d, e),
                lambda: dec.active_monitoring(self.state, self.daily_log, self.memory)
            )
            self._last_decision = now

        if self.on_heartbeat:
            self.on_heartbeat(self.state)

    # ---- 状态管理 ----

    def _auto_save(self):
        self._save_state()
        if hasattr(self.memory, 'save'):
            self.memory.save()

    def _save_state(self):
        from dataclasses import asdict
        state_file = self.memory_dir / ".kairos_state.json"
        try:
            with open(state_file, 'w') as f:
                json.dump(asdict(self.state), f, indent=2)
        except Exception as e:
            print(f"[KAIROS] Failed to save state: {e}")

    def load_state(self) -> bool:
        state_file = self.memory_dir / ".kairos_state.json"
        if not state_file.exists():
            return False
        try:
            with open(state_file, 'r') as f:
                data = json.load(f)
                self.state = KairosState(**data)
                return True
        except Exception as e:
            print(f"[KAIROS] Failed to load state: {e}")
            return False

    # ---- Cron 回调 ----

    def _on_cron_fire(self, prompt: str):
        print(f"[KAIROS] Executing scheduled task: {prompt[:50]}...")
        if prompt.startswith("tech_trend:"):
            topic = prompt.replace("tech_trend:", "").strip()
            self._track_tech_trend(topic)
        elif prompt == "auto_dream":
            self._trigger_auto_dream()
        elif prompt == "auto_evolution":
            self._trigger_auto_evolution()

    def _track_tech_trend(self, topic: str):
        try:
            print(f"[KAIROS] Tracking tech trend: {topic}")
            from ..tool_registry import ToolRegistry
            registry = ToolRegistry(str(self.project_root))
            search_tool = registry.get('web_search')
            if search_tool:
                result = search_tool(f"{topic} latest 2025", count=3)
                self.memory.store(
                    f"技术趋势跟踪: {topic}\n\n{result[:1000]}",
                    role="system",
                    mem_type="tech_trend",
                    tags=["kairos", "auto_tracking", topic.replace(" ", "_")]
                )
                print(f"[KAIROS] Tech trend tracked: {topic}")
        except Exception as e:
            print(f"[KAIROS] Failed to track tech trend: {e}")

    def _trigger_auto_dream(self):
        try:
            print("[KAIROS] Triggering AutoDream...")
        except Exception as e:
            print(f"[KAIROS] Failed to trigger AutoDream: {e}")

    def _trigger_auto_evolution(self):
        try:
            print("[KAIROS] Triggering auto evolution...")
            if self.on_evolution_trigger:
                improvements = self._generate_real_improvements()
                self.on_evolution_trigger(improvements)
        except Exception as e:
            print(f"[KAIROS] Failed to trigger auto evolution: {e}")

    # ---- 改进点生成 ----

    def _generate_real_improvements(self):
        improvements = []
        if self.state.system_metrics:
            llm_improvements = mon.llm_analyze_system_metrics(self.state.system_metrics)
            improvements.extend(llm_improvements)

        code_issues = mon.analyze_code_quality(
            self.project_root,
            lambda node: mon.calculate_complexity(node)
        )
        if code_issues:
            improvements.append({
                'type': 'code_quality',
                'issues': code_issues,
                'priority': 'medium'
            })

        if not improvements:
            improvements.append({
                'type': 'maintenance',
                'issues': ['定期系统维护'],
                'priority': 'medium'
            })
        return improvements

    # ---- 记录 ----

    def _record_decision(self, decision, evaluation):
        try:
            self.daily_log.append_entry_sync(
                "decision",
                f"决策: {decision['action']}, 评估: {str(evaluation)[:100]}"
            )
            if hasattr(self, 'memory') and hasattr(self.memory, 'store'):
                self.memory.store(
                    f"KAIROS决策: {decision['action']}\n评估: {str(evaluation)[:200]}",
                    role="system",
                    mem_type="decision",
                    tags=["kairos", "autonomous", decision['action']]
                )
        except Exception as e:
            print(f"[KAIROS] Failed to record decision: {e}")

    # ---- 触发 ----

    def _trigger_evolution(self):
        try:
            now = time.time()
            self.state.last_evolution_time = now
            print("[KAIROS] Triggering evolution based on autonomous decision")

            evolution_reasons = []
            for imp in self.state.pending_improvements:
                if 'suggestion' in imp and imp['suggestion']:
                    evolution_reasons.append(imp['suggestion'])
                else:
                    evolution_reasons.append(imp.get('type', 'unknown'))

            self.daily_log.append_entry_sync(
                "evolution",
                f"自动触发进化，原因: {'; '.join(evolution_reasons)}"
            )

            if self.on_evolution_trigger:
                for imp in self.state.pending_improvements:
                    if 'file_path' in imp:
                        file_name = imp['file_path'].split('/')[-1]
                        if 'memory' in file_name:
                            task_type, requirements = "性能关键", ["极致性能", "内存安全", "并发"]
                        elif 'llm' in file_name:
                            task_type, requirements = "AI/ML", ["生态系统", "快速开发", "AI/ML"]
                        elif 'coordinator' in file_name:
                            task_type, requirements = "并发任务", ["并发", "网络编程", "部署简单"]
                        else:
                            task_type, requirements = "通用编程", ["可读性", "生态系统", "开发速度"]
                        imp['suggested_language'] = select_language(task_type, requirements)

                self.on_evolution_trigger(self.state.pending_improvements)

            self.state.pending_improvements = []
        except Exception as e:
            print(f"[KAIROS] Failed to trigger evolution: {e}")

    def _trigger_optimization(self, targets):
        try:
            print(f"[KAIROS] Triggering optimization for: {targets[:2]}")
            self.daily_log.append_entry_sync(
                "optimization",
                f"自动触发优化，目标: {'; '.join(targets[:3])}"
            )
        except Exception as e:
            print(f"[KAIROS] Failed to trigger optimization: {e}")

    def _trigger_learning(self, topics):
        try:
            print(f"[KAIROS] Triggering learning for: {topics}")
            self.daily_log.append_entry_sync(
                "learning",
                f"自动触发学习，主题: {'; '.join(topics)}"
            )
        except Exception as e:
            print(f"[KAIROS] Failed to trigger learning: {e}")

    # ---- 公共 API ----

    def add_tech_trend_tracking(self, topic: str, cron: str = "0 4 * * *"):
        task_id = self.cron.add_task(f"tech_trend:{topic}", cron)
        print(f"[KAIROS] Added tech trend tracking: {topic} (task: {task_id})")
        return task_id

    def record_interaction(self, cost_usd: float = 0, duration_ms: float = 0):
        now = time.time()
        self.state.last_interaction_time = now
        self.state.total_cost_usd += cost_usd
        self.state.total_api_duration += duration_ms
        self.state.session_state = SessionState.ACTIVE.value

    def get_daily_log_prompt(self) -> str:
        return self.daily_log.get_daily_log_prompt()

    def is_active(self) -> bool:
        return self.state.kairos_active

    def dismiss_improvement(self, file_path: str, issue: str):
        """进化成功后消除对应 KAIROS 待处理项，防止周期性空转"""
        self.state.code_issues = [
            c for c in self.state.code_issues
            if file_path not in c or (issue[:30] not in c and c.split(":")[0].strip() != "代码复杂度高")
        ]
        self.state.pending_improvements = [
            i for i in self.state.pending_improvements
            if not (i.get("file_path") == file_path or i.get("file") == file_path)
        ]
        print(f"[KAIROS] 已 dismiss: {file_path}")

    def clear_processed_improvements(self, processed_files: List[str]):
        """批量清除已处理的改进项"""
        for f in processed_files:
            self.dismiss_improvement(f, "")

    def get_stats(self) -> Dict:
        now = time.time()
        return {
            'kairos_active': self.state.kairos_active,
            'session_id': self.state.session_id,
            'uptime_hours': (now - self.state.start_time) / 3600,
            'idle_minutes': (now - self.state.last_interaction_time) / 60,
            'total_cost_usd': self.state.total_cost_usd,
            'session_state': self.state.session_state,
            'cron_tasks': len(self.cron.tasks),
            'system_metrics': self.state.system_metrics,
            'performance_issues': self.state.performance_issues,
            'memory_issues': self.state.memory_issues,
            'code_issues': self.state.code_issues,
            'last_decision_time': self.state.last_decision_time,
            'last_evolution_time': self.state.last_evolution_time,
            'pending_improvements': self.state.pending_improvements,
            'last_code_analysis': self.state.last_code_analysis,
            'code_complexity': self.state.code_complexity
        }


def create_kairos(memory, project_root: str) -> Kairos:
    kairos = Kairos(memory, project_root)
    kairos.load_state()
    return kairos