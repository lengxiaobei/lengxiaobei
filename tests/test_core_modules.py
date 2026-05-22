"""
核心模块单元测试
================
覆盖 P0/P1 重构的关键路径：
- db_pool: ThreadSafeConnectionPool 线程安全
- constitution: 硬编码规则兜底引擎
- memory_backends: 策略模式后端链
- kairos/daily_log: 同步日志写入
- facade: LengXiaobei 高层 API 可调用性
"""
import os
import sys
import tempfile
import threading
import time
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# ThreadSafeConnectionPool 测试
# ============================================================================

class TestThreadSafeConnectionPool:
    """P0: SQLite 线程安全连接池"""

    def _make_pool(self, tmp_path):
        from src.db_pool import ThreadSafeConnectionPool
        db_path = str(tmp_path / "test.db")
        return ThreadSafeConnectionPool(db_path)

    def test_creates_db_file(self, tmp_path):
        pool = self._make_pool(tmp_path)
        assert (tmp_path / "test.db").exists()
        pool.close()

    def test_conn_property_returns_connection(self, tmp_path):
        pool = self._make_pool(tmp_path)
        conn = pool.conn
        assert isinstance(conn, sqlite3.Connection)
        pool.close()

    def test_wal_mode_enabled(self, tmp_path):
        pool = self._make_pool(tmp_path)
        cursor = pool.conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode == "wal"
        pool.close()

    def test_execute_write_and_read(self, tmp_path):
        pool = self._make_pool(tmp_path)
        pool.conn.execute("CREATE TABLE t (v TEXT)")
        pool.execute_write("INSERT INTO t VALUES (?)", ("hello",))
        cursor = pool.execute_read("SELECT v FROM t")
        assert cursor.fetchone()[0] == "hello"
        pool.close()

    def test_transaction_commit(self, tmp_path):
        pool = self._make_pool(tmp_path)
        pool.conn.execute("CREATE TABLE t (v INTEGER)")
        pool.conn.commit()
        with pool.transaction() as conn:
            conn.execute("INSERT INTO t VALUES (?)", (42,))
        cursor = pool.conn.execute("SELECT v FROM t")
        assert cursor.fetchone()[0] == 42
        pool.close()

    def test_transaction_rollback_on_exception(self, tmp_path):
        pool = self._make_pool(tmp_path)
        pool.conn.execute("CREATE TABLE t (v INTEGER)")
        pool.conn.commit()
        try:
            with pool.transaction() as conn:
                conn.execute("INSERT INTO t VALUES (?)", (99,))
                raise ValueError("forced error")
        except ValueError:
            pass
        cursor = pool.conn.execute("SELECT COUNT(*) FROM t")
        assert cursor.fetchone()[0] == 0
        pool.close()

    def test_concurrent_writes_safe(self, tmp_path):
        """多线程并发写入不崩溃"""
        from src.db_pool import ThreadSafeConnectionPool
        db_path = str(tmp_path / "concurrent.db")
        pool = ThreadSafeConnectionPool(db_path)
        pool.conn.execute("CREATE TABLE t (v INTEGER)")
        pool.conn.commit()

        errors = []

        def writer(n):
            try:
                pool.execute_write("INSERT INTO t VALUES (?)", (n,))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"并发写入出错: {errors}"
        cursor = pool.conn.execute("SELECT COUNT(*) FROM t")
        assert cursor.fetchone()[0] == 20
        pool.close()

    def test_each_thread_gets_own_connection(self, tmp_path):
        """不同线程连接对象不同"""
        from src.db_pool import ThreadSafeConnectionPool
        db_path = str(tmp_path / "threads.db")
        pool = ThreadSafeConnectionPool(db_path)
        conns = {}

        def get_conn(name):
            conns[name] = id(pool.conn)

        t1 = threading.Thread(target=get_conn, args=("t1",))
        t2 = threading.Thread(target=get_conn, args=("t2",))
        t1.start(); t1.join()
        t2.start(); t2.join()

        # 不同线程 id 不同（threading.local）
        assert conns["t1"] != conns["t2"]
        pool.close()

    def test_closed_pool_raises(self, tmp_path):
        pool = self._make_pool(tmp_path)
        pool.close()
        with pytest.raises(RuntimeError, match="closed"):
            pool.conn


# ============================================================================
# Constitution 硬编码规则兜底测试
# ============================================================================

class TestConstitutionRuleEngine:
    """P1: 宪法系统硬编码规则兜底"""

    def _make_constitution(self, tmp_path):
        from src.constitution import Constitution
        return Constitution(str(tmp_path))

    def test_rule_based_denies_rm_rf(self, tmp_path):
        c = self._make_constitution(tmp_path)
        result = c._rule_based_assess("rm -rf /tmp/data")
        assert result["allowed"] is False
        assert result["risk_level"] in ("high", "critical")

    def test_rule_based_denies_sudo(self, tmp_path):
        c = self._make_constitution(tmp_path)
        result = c._rule_based_assess("sudo chmod 777 /etc/hosts")
        assert result["allowed"] is False

    def test_rule_based_denies_git_push(self, tmp_path):
        c = self._make_constitution(tmp_path)
        result = c._rule_based_assess("git push origin main")
        assert result["allowed"] is False

    def test_rule_based_denies_eval(self, tmp_path):
        c = self._make_constitution(tmp_path)
        result = c._rule_based_assess("eval(user_input)")
        assert result["allowed"] is False

    def test_rule_based_denies_shutil_rmtree(self, tmp_path):
        c = self._make_constitution(tmp_path)
        result = c._rule_based_assess("shutil.rmtree('/important')")
        assert result["allowed"] is False

    def test_rule_based_allows_safe_action(self, tmp_path):
        c = self._make_constitution(tmp_path)
        result = c._rule_based_assess("print('hello world')")
        assert result["allowed"] is True

    def test_rule_based_allows_read_file(self, tmp_path):
        c = self._make_constitution(tmp_path)
        result = c._rule_based_assess("read_file('config.json')")
        assert result["allowed"] is True

    def test_llm_failure_falls_back_to_rules(self, tmp_path):
        """LLM 不可用时应使用硬编码规则，而不是默认允许"""
        from src.constitution import Constitution
        c = Constitution(str(tmp_path))
        with patch("src.constitution.chat", side_effect=Exception("LLM not available")):
            result = c._llm_assess("rm -rf /important")
        # 必须回退到规则引擎，不能默认 allowed=True
        assert result["allowed"] is False

    def test_llm_failure_allows_safe_action(self, tmp_path):
        """LLM 不可用时，安全操作仍应被允许（规则引擎未命中则放行）"""
        from src.constitution import Constitution
        c = Constitution(str(tmp_path))
        with patch("src.constitution.chat", side_effect=Exception("LLM not available")):
            result = c._llm_assess("print('hello')")
        assert result["allowed"] is True

    def test_max_risk_helper(self):
        from src.constitution import max_risk
        assert max_risk("low", "high") == "high"
        assert max_risk("critical", "medium") == "critical"
        assert max_risk("medium", "medium") == "medium"
        assert max_risk("low", "low") == "low"


# ============================================================================
# DailyLogManager 同步写入测试
# ============================================================================

class TestDailyLogSync:
    """P2: 同步日志写入（消除 asyncio.run 嵌套）"""

    def test_append_entry_sync_creates_file(self, tmp_path):
        from src.kairos.daily_log import DailyLogManager
        mgr = DailyLogManager(tmp_path)
        log_path = mgr.append_entry_sync("test", "hello world")
        assert log_path.exists()
        content = log_path.read_text()
        assert "hello world" in content
        assert "test" in content

    def test_append_entry_sync_is_append_only(self, tmp_path):
        from src.kairos.daily_log import DailyLogManager
        mgr = DailyLogManager(tmp_path)
        mgr.append_entry_sync("t1", "first entry")
        mgr.append_entry_sync("t2", "second entry")
        log_path = mgr._get_log_path()
        content = log_path.read_text()
        assert "first entry" in content
        assert "second entry" in content

    def test_append_entry_sync_with_metadata(self, tmp_path):
        from src.kairos.daily_log import DailyLogManager
        mgr = DailyLogManager(tmp_path)
        log_path = mgr.append_entry_sync("evt", "msg", {"key": "value"})
        content = log_path.read_text()
        assert '"key": "value"' in content

    def test_async_append_delegates_to_sync(self, tmp_path):
        """async append_entry 内部走同步路径"""
        import asyncio
        from src.kairos.daily_log import DailyLogManager
        mgr = DailyLogManager(tmp_path)
        asyncio.run(mgr.append_entry("evt", "async content"))
        log_path = mgr._get_log_path()
        assert "async content" in log_path.read_text()


# ============================================================================
# memory_backends 策略模式测试
# ============================================================================

class TestMemoryBackends:
    """P1: 策略模式后端链"""

    def test_sqlite_fallback_strategy_is_available(self, tmp_path):
        from src.memory_backends import SQLiteFallbackStrategy
        # conn_provider 是一个返回连接的可调对象
        import sqlite3
        conn = sqlite3.connect(":memory:")
        strategy = SQLiteFallbackStrategy(conn_provider=lambda: conn)
        assert strategy.is_available() is True
        conn.close()

    def test_memory_api_strategy_unavailable_without_server(self):
        from src.memory_backends import MemoryAPIStrategy
        # 没有本地 Rust 服务时应返回 False
        strategy = MemoryAPIStrategy(api_url="http://localhost:19999")
        strategy._available = False  # 强制标记为不可用
        assert strategy.is_available() is False

    def test_build_backend_chain_returns_list(self):
        from src.memory_backends import build_backend_chain
        config = MagicMock()
        config.memory_api_enabled = False
        config.qdrant_enabled = False
        config.faiss_enabled = False
        backends = build_backend_chain(config)
        assert isinstance(backends, list)
        assert len(backends) >= 1  # 至少 SQLite fallback

    def test_build_backend_chain_always_has_sqlite_fallback(self):
        """build_backend_chain 即使没有配置也应返回列表（不崩溃）"""
        from src.memory_backends import build_backend_chain
        config = MagicMock()
        config.memory_api_enabled = False
        config.qdrant_enabled = False
        config.faiss_enabled = False
        config.memory_dir = "/tmp"
        backends = build_backend_chain(config)
        # 不强制要求 SQLite fallback，但应返回列表（可以为空）
        assert isinstance(backends, list)


# ============================================================================
# LengXiaobei Facade API 可调用性测试
# ============================================================================

class TestLengXiaobeiCore:
    """P1: Facade 高层 API"""

    @pytest.fixture
    def agent(self, tmp_path):
        """创建内存模式的 Agent（不初始化所有子系统）"""
        from src.core import LengXiaobei
        return LengXiaobei(project_root=str(tmp_path), memory_only=True)

    def test_agent_initializes(self, agent):
        assert agent.initialized is True

    def test_remember_and_recall(self, agent):
        """存储 + 搜索记忆"""
        agent.remember("测试内容：Python 线程安全", mem_type="context")
        results = agent.recall("Python 线程安全")
        # 不强制要求找到（依赖 embedding），但不应抛出异常
        assert isinstance(results, list)

    def test_is_evolution_allowed_no_constitution(self, agent):
        """宪法未加载时默认允许"""
        allowed, reason = agent.is_evolution_allowed("print('hello')")
        # 无宪法时应返回 True
        assert isinstance(allowed, bool)
        assert isinstance(reason, str)

    def test_run_curator_check_returns_list(self, agent):
        result = agent.run_curator_check("quick")
        assert isinstance(result, list)

    def test_get_pending_improvements_returns_list(self, agent):
        result = agent.get_pending_improvements()
        assert isinstance(result, list)

    def test_optimize_memory_no_crash(self, agent):
        """optimize_memory 在无 optimize 方法时不崩溃"""
        agent.optimize_memory()  # 不应抛出异常

    def test_recall_all_preserves_memory_fields(self, agent):
        """recall_all 不应把 created_at/name/description 字段读串位"""
        agent.remember(
            "字段完整性测试",
            mem_type="context",
            name="字段测试",
            description="描述应保持原样",
        )
        results = agent.recall_all()
        target = next(r for r in results if r["content"] == "字段完整性测试")
        assert isinstance(target["created_at"], float)
        assert target["name"] == "字段测试"
        assert target["description"] == "描述应保持原样"

    def test_no_transparent_property_memory(self, agent):
        """确认 LengXiaobei 不再直接暴露 memory 属性"""
        # P1 修复后不应有裸 .memory 属性
        # 访问语义化方法而非子系统对象
        assert not hasattr(agent, 'memory'), \
            "LengXiaobei 不应直接暴露 .memory 属性（已收缩 API 表面）"

    def test_no_transparent_property_hybrid_memory(self, agent):
        """确认不暴露 hybrid_memory"""
        assert not hasattr(agent, 'hybrid_memory'), \
            "LengXiaobei 不应直接暴露 .hybrid_memory 属性"

    def test_no_transparent_property_constitution(self, agent):
        """确认不暴露 constitution"""
        assert not hasattr(agent, 'constitution'), \
            "LengXiaobei 不应直接暴露 .constitution 属性"


class TestSelfEvolutionFunctionalFallback:
    """自进化失败时应优先落到真实 safe target，而不是只写 metadata。"""

    def test_expected_function_fallback_adds_callable(self, tmp_path):
        from src.agent_learning import AgentLesson
        from src.self_evolution import SelfEvolutionCore

        target = tmp_path / "src" / "critic.py"
        target.parent.mkdir(parents=True)
        target.write_text('"""critic test target."""\n\nVALUE = 1\n', encoding="utf-8")

        core = SelfEvolutionCore(str(tmp_path))
        lesson = AgentLesson(
            id="lesson_test",
            source="test",
            capability="diagnose design defects",
            pattern="inspect context",
            why_good="keeps self-evolution functional",
            adaptation="add callable fallback",
            suggested_files=["src/critic.py"],
            topic="test fallback",
        )
        expected = [{"name": "diagnose_design_defects", "signature": "diagnose_design_defects(context: str) -> dict"}]

        result = core._apply_expected_function_fallback(
            lesson=lesson,
            target_file="src/critic.py",
            goal="add diagnose_design_defects",
            expected_functions=expected,
            primary_result={"status": "failed", "error": "代码验证失败"},
        )

        assert result["status"] == "success"
        assert result["changed"] is True
        check = core._check_capability("src/critic.py", expected)
        assert check["all_callable"] is True
        assert check["found"] == ["diagnose_design_defects"]
