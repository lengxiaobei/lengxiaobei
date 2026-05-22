"""
冷小北 · Phase 2 — KAIROS 守护进程
====================================
后台常驻代理，每隔几秒评估"anything worth doing right now?"

守护模式 vs 手动模式：
- 手动模式（Phase 1）：python3 -m src.core → 启动对话
- 守护模式（Phase 2）：python3 daemon.py → 后台常驻

KAIROS 心跳：
- 每 HEARTBEAT_INTERVAL 秒评估一次当前状态
- append-only 日志（不删除自己的历史）
- 夜间 autoDream 整理当天学到的东西
"""

import sys
import os
import time
import signal
import json
import atexit
import asyncio
from datetime import datetime, time as dtime
from pathlib import Path

from src.core import LengXiaobei
from src.auto_dream import AutoDreamV2
from src.language_selector import select_language, evaluate_language_choice, get_language_metacognition
from src.logging_config import get_logger

# ============================================================================
# 配置
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.resolve()
STATE_FILE = PROJECT_ROOT / "memory" / "daemon_state.json"
LOG_FILE = PROJECT_ROOT / "memory" / "kairos.log"

HEARTBEAT_INTERVAL = 60
DREAM_HOUR = 3
DREAM_MINUTE = 30


# ============================================================================
# 状态持久化
# ============================================================================

class DaemonState:
    """守护进程状态管理"""

    def __init__(self):
        self.state_file = STATE_FILE
        self._ensure_dir()
        self.data = self._load()

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

    def _load(self) -> dict:
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return self._default_state()

    def _default_state(self) -> dict:
        return {
            "last_heartbeat": None,
            "last_dream": None,
            "consecutive_quiet": 0,
            "last_activity": None,
            "total_heartbeats": 0,
            "version": "Phase 2.1",
        }

    def save(self):
        self.data["last_heartbeat"] = datetime.now().isoformat()
        with open(self.state_file, "w") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)


# ============================================================================
# KAIROS 主类
# ============================================================================

class KAIROS:
    """KAIROS 后台守护进程 — 使用 Facade 架构"""

    def __init__(self):
        self.running = True
        self.state = DaemonState()
        self.agent = None
        self.logger = get_logger('kairos', level=10)

        signal.signal(signal.SIGTERM, self._on_sigterm)
        signal.signal(signal.SIGINT, self._on_sigterm)
        atexit.register(self._shutdown)

        self._log("KAIROS 守护进程启动")
        self.state.save()

    def _on_sigterm(self, signum, frame):
        self._log(f"收到信号 ({signum})，准备退出...")
        self.running = False

    def _shutdown(self):
        self._log("KAIROS 守护进程关闭")
        self.state.save()

    def _log(self, msg: str):
        self.logger.info(msg)
        print(f"🦞 KAIROS: {msg}")

    def _dismiss_in_kairos(self, file_path: str, issue: str):
        """通过核心 API 通知 KAIROS"""
        try:
            if self.agent:
                self.agent.dismiss_kairos_improvement(file_path, issue)
        except Exception:
            pass

    # ------------------------------------------------------------------------
    # 初始化 Agent
    # ------------------------------------------------------------------------

    def _ensure_agent(self):
        if self.agent is None:
            self._log("初始化冷小北核心...")
            self.agent = LengXiaobei()
            self._log("冷小北核心已就绪")
            # 报告 KAIROS 状态
            pending = self.agent.get_pending_improvements()
            if pending:
                self._log(f"KAIROS 状态: pending_improvements={len(pending)}")

    # ------------------------------------------------------------------------
    # 心跳评估
    # ------------------------------------------------------------------------

    def _should_act(self) -> bool:
        self.state.data["total_heartbeats"] += 1
        self._ensure_agent()

        # 通过核心 API 运行策展人检查
        improvements = None
        for level in ["quick", "incremental", "full"]:
            try:
                improvements = self.agent.run_curator_check(level)
                if improvements:
                    break
            except Exception as e:
                self._log(f"策展人检查({level})出错: {e}")

        if improvements:
            self._log(f"发现 {len(improvements)} 个改进点")
            self.state.data["last_activity"] = datetime.now().isoformat()
            self.state.data["pending_improvements"] = [
                {"file": i.file, "issue": i.issue, "priority": i.priority,
                 "type": i.type, "suggestion": i.suggestion,
                 "confidence": i.confidence, "source": "curator"}
                for i in improvements if i.file
            ]
            return True

        return False

    def _heartbeat(self):
        self._log(f"心跳 #{self.state.data['total_heartbeats']}")
        if self._should_act():
            self._log("评估：值得做点什么")
            self._do_evolution_task()
        else:
            self.state.data["consecutive_quiet"] += 1
            self._log("评估：静默")
        self.state.save()

    def _do_evolution_task(self):
        """执行进化 - 通过核心 API"""
        self._ensure_agent()

        improvements = self.state.data.get("pending_improvements", [])

        if not improvements:
            self._log("执行自主进化...")
            try:
                result = self.agent.evolve_autonomously()
                status = result.get("status", "unknown") if isinstance(result, dict) else str(result)
                self._log(f"自主进化完成: {status}")
            except Exception as e:
                self._log(f"自主进化出错: {e}")
            return

        self._log(f"执行定向进化，改进点: {len(improvements)}")

        # 通过核心 API 执行进化
        result = self.agent.execute_evolution_tasks(improvements)
        status = result.get("status", "unknown") if isinstance(result, dict) else str(result)
        self._log(f"进化完成: {status}")

        # 清理已处理的改进点
        for imp_data in improvements[:3]:
            from src.evolution.models import ImprovementRecord
            rec = ImprovementRecord.from_kairos(imp_data)
            if rec:
                self.agent.mark_curator_seen(rec.signature)
                if result.get("status") == "success":
                    self._dismiss_in_kairos(rec.file, rec.issue)

        self.state.data["pending_improvements"] = []
        self._log("已清空待改进项")

        # 记忆整理
        try:
            self._log("执行记忆整理...")
            self.agent.optimize_memory()
        except Exception as e:
            self._log(f"记忆整理出错: {e}")

    def _evaluate_language_choices(self):
        try:
            self._log("评估多语言集成机会...")

            try:
                import psutil
                cpu_usage = psutil.cpu_percent()
                memory_usage = psutil.virtual_memory().percent
            except ImportError:
                self._log("psutil 未安装，跳过多语言集成评估")
                return

            task_requirements = []
            task_type = "general"

            if cpu_usage > 80:
                task_requirements.append("性能")
                task_requirements.append("并发")
                task_type = "performance_critical"
            if memory_usage > 80:
                task_requirements.append("内存效率")
                task_type = "resource_optimization"

            if task_requirements:
                selected_language = select_language(task_type, task_requirements)
                self._log(f"CPU {cpu_usage}% 内存 {memory_usage}% → 推荐: {selected_language}")

                evaluate_language_choice(task_type, selected_language, True)

                metacognition = get_language_metacognition()
                suggestion = metacognition.suggest_improvement()
                if suggestion:
                    self._log(f"建议: {suggestion['current_language']} → {suggestion['suggested_languages']}")
        except Exception as e:
            self._log(f"多语言评估出错: {e}")

    # ------------------------------------------------------------------------
    # autoDream
    # ------------------------------------------------------------------------

    def _is_dream_time(self) -> bool:
        now = datetime.now()
        last_dream = self.state.data.get("last_dream")

        if last_dream:
            try:
                last_dt = datetime.fromisoformat(last_dream)
                if last_dt.date() >= now.date():
                    return False
            except (ValueError, TypeError):
                pass

        target = dtime(hour=DREAM_HOUR, minute=DREAM_MINUTE)
        current = now.time()
        diff = abs(
            (current.hour * 60 + current.minute) -
            (target.hour * 60 + target.minute)
        )
        return diff <= 5

    def auto_dream(self):
        self._log("=" * 40)
        self._log("🌙 开始 autoDream V2")
        self._ensure_agent()

        try:
            dream = AutoDreamV2(self.agent.memory, str(PROJECT_ROOT))
            self._log("  [1/4] 检查门控条件...")

            result = asyncio.run(dream.execute())

            if result:
                if result.success:
                    self._log(f"  完成！整理了 {len(result.files_touched)} 个文件")
                    self._log(f"  摘要: {result.summary[:100]}...")
                else:
                    self._log(f"  跳过: {result.summary}")
            else:
                self._log("  门控条件不满足，跳过 autoDream")

            self.state.data["last_dream"] = datetime.now().isoformat()
            self._log("✅ autoDream V2 完成")
        except Exception as e:
            self._log(f"⚠️ autoDream V2 出错: {e}")
        self._log("=" * 40)

    # ------------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------------

    def run(self):
        self._log(f"主循环开始，心跳间隔 {HEARTBEAT_INTERVAL}s")

        while self.running:
            try:
                if self._is_dream_time():
                    self.auto_dream()
                    time.sleep(HEARTBEAT_INTERVAL)
                    continue

                self._heartbeat()

                for _ in range(HEARTBEAT_INTERVAL):
                    if not self.running:
                        break
                    time.sleep(1)

            except KeyboardInterrupt:
                self._log("KeyboardInterrupt，退出")
                self.running = False
                break
            except Exception as e:
                self._log(f"主循环异常: {e}")
                time.sleep(HEARTBEAT_INTERVAL)

        self._log("KAIROS 主循环结束")


# ============================================================================
# 入口
# ============================================================================

def main():
    print(f"\n{'='*50}")
    print(f"🦞 冷小北 · Phase 2.1 — KAIROS 守护进程")
    print(f"{'='*50}")
    print(f"项目: {PROJECT_ROOT}")
    print(f"心跳: 每 {HEARTBEAT_INTERVAL}s")
    print(f"日志: {LOG_FILE}")
    print(f"状态: {STATE_FILE}")
    print(f"\n按 Ctrl+C 或发送 SIGTERM 优雅退出\n")

    daemon = KAIROS()
    daemon.run()


if __name__ == "__main__":
    main()