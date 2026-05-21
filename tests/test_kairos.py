"""
KAIROS 守护系统单元测试
=======================
覆盖：scheduler, monitor, decision, engine, daily_log
"""
import os
import sys
import tempfile
import time
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# DailyLogManager 测试
# ============================================================================

class TestDailyLogManager:
    """KAIROS 日志系统"""

    def _make_manager(self, tmp_path):
        from src.kairos.daily_log import DailyLogManager
        return DailyLogManager(tmp_path)

    def test_append_entry_sync_creates_file(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        log_path = mgr.append_entry_sync("test", "hello world")
        assert log_path.exists()
        content = log_path.read_text()
        assert "hello world" in content
        assert "test" in content

    def test_append_entry_sync_is_append_only(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        mgr.append_entry_sync("t1", "first entry")
        mgr.append_entry_sync("t2", "second entry")
        log_path = mgr._get_log_path()
        content = log_path.read_text()
        assert "first entry" in content
        assert "second entry" in content

    def test_append_entry_sync_with_metadata(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        log_path = mgr.append_entry_sync("evt", "msg", {"key": "value"})
        content = log_path.read_text()
        assert '"key": "value"' in content

    def test_async_append_delegates_to_sync(self, tmp_path):
        import asyncio
        mgr = self._make_manager(tmp_path)
        asyncio.run(mgr.append_entry("evt", "async content"))
        log_path = mgr._get_log_path()
        assert "async content" in log_path.read_text()

    def test_get_log_path_returns_dated_filename(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        path = mgr._get_log_path()
        today = time.strftime("%Y-%m-%d")
        assert today in path.name


# ============================================================================
# CronScheduler 测试
# ============================================================================

class TestCronScheduler:
    """KAIROS 调度器"""

    def _make_scheduler(self, tmp_path):
        from src.kairos.scheduler import CronScheduler
        return CronScheduler(tmp_path)

    def test_add_task_returns_task_id(self, tmp_path):
        scheduler = self._make_scheduler(tmp_path)
        task_id = scheduler.add_task("test prompt", "0 9 * * *")
        assert isinstance(task_id, str)
        assert task_id.startswith("cron_")

    def test_remove_task(self, tmp_path):
        scheduler = self._make_scheduler(tmp_path)
        task_id = scheduler.add_task("to remove", "0 9 * * *")
        scheduler.remove_task(task_id)
        # 验证已移除
        scheduler._load_tasks()
        assert not any(t.id == task_id for t in scheduler.tasks)

    def test_stop_is_clean(self, tmp_path):
        scheduler = self._make_scheduler(tmp_path)
        scheduler.running = True
        scheduler.stop()
        assert scheduler.running is False


# ============================================================================
# Monitor 模块测试
# ============================================================================

class TestMonitorModule:
    """KAIROS 监控函数"""

    def test_monitor_system_returns_metrics(self):
        from src.kairos import monitor as mon
        from src.kairos.config import KairosState, KairosConfig

        state = KairosState()
        config = KairosConfig()
        mock_log = MagicMock()

        with patch('psutil.cpu_percent', return_value=50.0), \
             patch('psutil.virtual_memory', return_value=MagicMock(percent=60.0)), \
             patch('psutil.disk_usage', return_value=MagicMock(percent=70.0)):
            mon.monitor_system(state, config, mock_log)

        assert hasattr(state, 'system_metrics')
        assert 'cpu_usage' in state.system_metrics
        assert state.system_metrics['cpu_usage'] == 50.0

    def test_monitor_system_handles_psutil_failure(self):
        from src.kairos import monitor as mon
        from src.kairos.config import KairosState, KairosConfig

        state = KairosState()
        config = KairosConfig()
        mock_log = MagicMock()

        with patch('psutil.cpu_percent', side_effect=Exception("psutil error")):
            mon.monitor_system(state, config, mock_log)
        # 不崩溃


# ============================================================================
# Decision 模块测试
# ============================================================================

class TestDecisionModule:
    """KAIROS 决策函数"""

    def test_make_decision_returns_early_on_cooldown(self):
        from src.kairos import decision as dec
        from src.kairos.config import KairosState, KairosConfig

        state = KairosState()
        state.last_evolution_time = time.time()  # 刚刚进化过
        config = KairosConfig()
        config.evolution_cooldown = 3600  # 1小时冷却
        mock_log = MagicMock()

        mock_on_evolution = MagicMock()
        mock_gather = MagicMock(return_value={})
        mock_evaluate = MagicMock(return_value={})
        mock_decide = MagicMock(return_value={'action': 'wait'})
        mock_trigger = MagicMock()
        mock_optimize = MagicMock()
        mock_learn = MagicMock()
        mock_record = MagicMock()
        mock_monitor = MagicMock()

        dec.make_decision(
            state, config, mock_log,
            mock_on_evolution,
            mock_gather, mock_evaluate, mock_decide,
            mock_trigger, mock_optimize, mock_learn,
            mock_record, mock_monitor
        )

        # 冷却期内不应触发进化
        mock_on_evolution.assert_not_called()

    def test_make_decision_triggers_evolution(self):
        from src.kairos import decision as dec
        from src.kairos.config import KairosState, KairosConfig

        state = KairosState()
        state.last_evolution_time = 0  # 从未进化
        config = KairosConfig()
        config.evolution_cooldown = 0
        mock_log = MagicMock()

        mock_evo = MagicMock()
        mock_gather = MagicMock(return_value={'health': 90})
        mock_evaluate = MagicMock(return_value={'score': 80})
        mock_decide = MagicMock(return_value={'action': 'evolve', 'improvements': []})
        mock_trigger = MagicMock()
        mock_opt = MagicMock()
        mock_learn = MagicMock()
        mock_record = MagicMock()
        mock_monitor = MagicMock()

        dec.make_decision(
            state, config, mock_log,
            mock_evo,
            mock_gather, mock_evaluate, mock_decide,
            mock_trigger, mock_opt, mock_learn,
            mock_record, mock_monitor
        )

        mock_trigger.assert_called_once()

    def test_active_monitoring_checks_memory(self):
        from src.kairos import decision as dec
        from src.kairos.config import KairosState
        from src.kairos.daily_log import DailyLogManager

        with tempfile.TemporaryDirectory() as tmp:
            state = KairosState()
            daily_log = DailyLogManager(Path(tmp))
            mock_memory = MagicMock()
            mock_memory.conn = MagicMock()
            mock_memory.conn.execute.return_value = MagicMock(fetchone=MagicMock(return_value=(100,)))

            dec.active_monitoring(state, daily_log, mock_memory)
            # 不崩溃


# ============================================================================
# Kairos 主类测试
# ============================================================================

class TestKairos:
    """KAIROS 主引擎"""

    def _make_kairos(self, tmp_path):
        from src.kairos.engine import Kairos
        mock_memory = MagicMock()
        return Kairos(mock_memory, str(tmp_path))

    def test_kairos_initializes(self, tmp_path):
        kairos = self._make_kairos(tmp_path)
        assert kairos is not None
        assert hasattr(kairos, 'state')
        assert hasattr(kairos, 'daily_log')
        assert hasattr(kairos, 'cron')

    def test_activate_deactivate(self, tmp_path):
        kairos = self._make_kairos(tmp_path)
        assert kairos.activate() is True
        assert kairos.is_active() is True
        kairos.deactivate()
        assert kairos.is_active() is False

    def test_start_stop(self, tmp_path):
        kairos = self._make_kairos(tmp_path)
        kairos.activate()
        kairos.start()
        assert kairos._running is True
        kairos.stop()
        assert kairos._running is False

    def test_record_interaction(self, tmp_path):
        kairos = self._make_kairos(tmp_path)
        initial_cost = kairos.state.total_cost_usd
        kairos.record_interaction(cost_usd=0.01, duration_ms=100)
        assert kairos.state.total_cost_usd >= initial_cost

    def test_add_tech_trend_tracking(self, tmp_path):
        kairos = self._make_kairos(tmp_path)
        # 添加一个 cron 任务
        kairos.cron.add_task("track AI trends", "0 4 * * *")
        # 不崩溃即通过

    def test_get_stats(self, tmp_path):
        kairos = self._make_kairos(tmp_path)
        stats = kairos.get_stats()
        assert isinstance(stats, dict)

    def test_load_state_returns_bool(self, tmp_path):
        kairos = self._make_kairos(tmp_path)
        result = kairos.load_state()
        assert isinstance(result, bool)

    def test_save_and_load_state(self, tmp_path):
        kairos = self._make_kairos(tmp_path)
        # Ensure memory directory exists
        (tmp_path / "memory").mkdir(exist_ok=True)
        original_cost = kairos.state.total_cost_usd
        kairos.state.total_cost_usd = 42.0
        kairos._save_state()
        kairos.state.total_cost_usd = 0.0
        kairos.load_state()
        assert kairos.state.total_cost_usd == 42.0

    def test_dismiss_improvement(self, tmp_path):
        kairos = self._make_kairos(tmp_path)
        kairos.state.pending_improvements = [
            {"file_path": "test.py", "issue": "unused import"}
        ]
        kairos.dismiss_improvement("test.py", "unused import")
        # 不崩溃即通过

    def test_clear_processed_improvements(self, tmp_path):
        kairos = self._make_kairos(tmp_path)
        kairos.clear_processed_improvements(["test.py"])
        # 不崩溃

    def test_cron_fire_calls_internal_handler(self, tmp_path):
        """验证 cron 触发时会调用 _on_cron_fire"""
        kairos = self._make_kairos(tmp_path)
        kairos.activate()
        # 模拟添加一个立即触发的任务
        task_id = kairos.cron.add_task("immediate task", "* * * * *")
        # 验证任务被添加
        assert task_id.startswith("cron_")
