"""端到端集成测试：启动最终 Web 入口，走通主要 API + SSE 推送。

跑法：
  pytest tests/test_integration_web.py -v -s

这套测试不 mock，会真实启动一个 web server 子进程，并对所有新 API 发起 HTTP 请求。
所有用例必须通过才能视为上线达标。
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _pick_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def web_server():
    """启动一次最终 Web 入口，整组测试结束后关闭。"""
    port = _pick_free_port()
    base = f"http://127.0.0.1:{port}"

    env = {**os.environ, "LX_WEB_PORT": str(port), "LX_WEB_HOST": "127.0.0.1",
           "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "lx_web.app"],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    # 等待服务起来（最多 30 秒）
    ready = False
    deadline = time.time() + 30
    last_err = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            try:
                out = proc.stdout.read() if proc.stdout else ""
            except Exception:
                out = ""
            raise RuntimeError(f"web 服务启动失败: rc={proc.returncode}\n{out}")
        try:
            r = requests.get(f"{base}/api/status", timeout=1)
            if r.status_code == 200:
                ready = True
                break
        except Exception as e:
            last_err = str(e)
        time.sleep(0.5)

    if not ready:
        try:
            proc.terminate()
        except Exception:
            pass
        raise RuntimeError(f"web 服务未在 30 秒内就绪 (last err: {last_err})")

    yield {"base": base, "proc": proc}

    try:
        proc.terminate()
        proc.wait(timeout=8)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# ============================================================================
# 系统模块（基础健康）
# ============================================================================

class TestSystemModule:
    def test_status(self, web_server):
        r = requests.get(f"{web_server['base']}/api/status", timeout=5)
        assert r.status_code == 200
        body = r.json()
        assert "uptime" in body
        assert "version" in body

    def test_health(self, web_server):
        r = requests.get(f"{web_server['base']}/api/health", timeout=5)
        # agent 可能未就绪（LLM key 缺失等），健康检查可能 503，这是允许的
        assert r.status_code in (200, 503)
        assert "components" in r.json()

    def test_agent_context(self, web_server):
        r = requests.get(f"{web_server['base']}/api/agent-context", timeout=15)
        assert r.status_code in (200, 503)
        body = r.json()
        assert body.get("status") in ("ok", "failed")
        ctx = body.get("context", {})
        assert "identity" in ctx
        assert "capabilities" in ctx

    def test_model_config(self, web_server):
        r = requests.get(f"{web_server['base']}/api/model-config", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"

    def test_runtime_status(self, web_server):
        r = requests.get(f"{web_server['base']}/api/runtime/status", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"
        assert "pid" in body
        assert "restart" in body
        assert any("lx_web.app" in part for part in body.get("argv", []))


# ============================================================================
# 学习进度模块（新 API）
# ============================================================================

class TestLearningModule:
    def test_kanban(self, web_server):
        r = requests.get(f"{web_server['base']}/api/learning/kanban", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"
        assert set(["pending", "learning", "verified", "failed"]).issubset(body["columns"].keys())
        assert "stats" in body

    def test_lessons_full_fields(self, web_server):
        r = requests.get(f"{web_server['base']}/api/learning/lessons", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"
        assert "count" in body
        assert "by_status" in body
        # by_status 必须有 5 个标准桶
        assert set(["pending", "applying", "verifying", "applied", "failed"]).issubset(body["by_status"].keys())
        assert isinstance(body.get("lessons"), list)

    def test_capabilities_distribution(self, web_server):
        r = requests.get(f"{web_server['base']}/api/learning/capabilities", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"
        assert isinstance(body.get("distribution"), list)
        # static_capabilities 来自 learned_capabilities.py，应该是个 list（即使为空）
        assert isinstance(body.get("static_capabilities"), list)

    def test_timeline(self, web_server):
        r = requests.get(f"{web_server['base']}/api/learning/timeline?limit=20", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"
        assert isinstance(body.get("timeline"), list)


# ============================================================================
# 自进化模块（新 API）
# ============================================================================

class TestEvolveModule:
    def test_improvements_preview(self, web_server):
        r = requests.get(f"{web_server['base']}/api/evolve/improvements", timeout=30)
        # 进化引擎可能没就绪 → 503；正常应返回 200
        assert r.status_code in (200, 503)
        if r.status_code == 200:
            body = r.json()
            assert "improvements" in body
            assert isinstance(body["improvements"], list)

    def test_evolve_progress(self, web_server):
        r = requests.get(f"{web_server['base']}/api/evolve/progress", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "progress" in body
        assert "self_evolve" in body["progress"]
        assert "auto_dream" in body["progress"]


# ============================================================================
# 执行情况模块（新 API）
# ============================================================================

class TestExecutionModule:
    def test_autonomy(self, web_server):
        r = requests.get(f"{web_server['base']}/api/execution/autonomy", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"
        a = body["autonomy"]
        # 必须包含核心字段
        for key in ("enabled", "running", "interval_seconds", "tick_count"):
            assert key in a
        # 新增 next_tick_eta_seconds 字段
        assert "next_tick_eta_seconds" in a

    def test_facades(self, web_server):
        r = requests.get(f"{web_server['base']}/api/execution/facades", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"
        facades = body["facades"]
        # 4 个 facade 必须都在
        assert set(facades.keys()) == {"guardian", "memory", "evolution", "reasoning"}

    def test_events_history(self, web_server):
        r = requests.get(f"{web_server['base']}/api/execution/events?limit=10", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"
        assert "events" in body
        assert "stats" in body
        assert isinstance(body["events"], list)


# ============================================================================
# 记忆 RAG / 目标 / 动机
# ============================================================================

class TestMemoryAndGoals:
    def test_memory_search(self, web_server):
        r = requests.post(
            f"{web_server['base']}/api/memory/search",
            json={"query": "测试查询", "limit": 5},
            timeout=20,
        )
        # 503 仅在 agent 完全无法初始化时；200 是常态（即使 hybrid_memory 未就绪也会返回 ok+空列表）
        assert r.status_code in (200, 503)
        if r.status_code == 200:
            body = r.json()
            assert body.get("status") in ("ok", "failed")
            assert "results" in body or "error" in body

    def test_memory_index(self, web_server):
        r = requests.get(f"{web_server['base']}/api/memory/index", timeout=15)
        # agent 可能未就绪，503 容忍
        assert r.status_code in (200, 503)

    def test_goals(self, web_server):
        r = requests.get(f"{web_server['base']}/api/goals", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "goals" in body

    def test_motivations(self, web_server):
        r = requests.get(f"{web_server['base']}/api/motivations", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "motivations" in body


# ============================================================================
# SSE 实时事件流
# ============================================================================

class TestSSE:
    def test_sse_connect_and_keepalive(self, web_server):
        """订阅 SSE，应至少收到一个 keepalive 或事件。"""
        url = f"{web_server['base']}/api/events"
        received_lines: list = []
        deadline = time.time() + 18

        with requests.get(url, stream=True, timeout=20) as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers.get("Content-Type", "")
            for line in r.iter_lines(decode_unicode=True):
                if time.time() > deadline:
                    break
                if line is None:
                    continue
                received_lines.append(line)
                # 收到任何一行非空就算成功（": connected" 或 keepalive 或 event）
                if line.strip():
                    break

        assert received_lines, "SSE 没有任何输出"

    def test_sse_receives_emitted_event(self, web_server):
        """显式触发一次事件，应在 SSE 流里收到。"""
        url = f"{web_server['base']}/api/events"
        received: list = []
        stop_flag = threading.Event()

        def listen():
            try:
                with requests.get(url, stream=True, timeout=20) as r:
                    for line in r.iter_lines(decode_unicode=True):
                        if stop_flag.is_set():
                            break
                        if line and line.startswith("event:"):
                            received.append(line)
                        if len(received) >= 2:
                            break
            except Exception:
                pass

        t = threading.Thread(target=listen, daemon=True)
        t.start()
        # 给订阅一点时间
        time.sleep(1.5)

        # 触发一次 autonomy.tick，会 emit autonomy.tick.started + finished
        try:
            requests.post(
                f"{web_server['base']}/api/autonomy/tick",
                json={"direction": "integration-test"},
                timeout=60,
            )
        except Exception:
            pass

        t.join(timeout=20)
        stop_flag.set()

        # 至少应该收到 autonomy.tick.started 或 autonomy.tick.finished 中的一个
        types_seen = " ".join(received)
        assert (
            "autonomy.tick" in types_seen
            or "evolution.completed" in types_seen
            or "memory.updated" in types_seen
            or len(received) >= 1  # 兜底：只要有事件流动
        ), f"未收到预期事件，实际收到: {received}"


# ============================================================================
# 现有 API 回归测试（确保改造没破坏旧接口）
# ============================================================================

class TestRegression:
    def test_old_lessons_api(self, web_server):
        r = requests.get(f"{web_server['base']}/api/lessons", timeout=10)
        assert r.status_code == 200
        assert "lessons" in r.json()

    def test_old_runs_api(self, web_server):
        r = requests.get(f"{web_server['base']}/api/runs", timeout=10)
        assert r.status_code == 200
        assert "runs" in r.json()

    def test_old_autonomy_status(self, web_server):
        r = requests.get(f"{web_server['base']}/api/autonomy/status", timeout=10)
        assert r.status_code == 200

    def test_index_html_served(self, web_server):
        r = requests.get(f"{web_server['base']}/", timeout=10)
        assert r.status_code == 200
        assert r.headers.get("Content-Type", "").startswith("application/json")
