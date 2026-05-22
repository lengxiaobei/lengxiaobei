"""
chat Blueprint — 对话 API，包含 agentic chat 和工具调度
"""

import sys
import os
import json
import time
import threading
from pathlib import Path

from flask import Blueprint, jsonify, request

from lx_web.shared.state import (
    _get_agent,
    _system_info,
    PROJECT_ROOT,
    AUTONOMY_DEFAULT_INTERVAL,
)
from lx_web.shared.utils import (
    _schedule_restart_if_source_changed,
    _run_core_tests,
    _run_reflection_async,
)
from lx_web.shared.sse import _emit_event

chat_bp = Blueprint('chat', __name__)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _format_tool_observations(observations: list) -> str:
    lines = ["已按指令自主调用后端工具："]
    for obs in observations:
        lines.append(f"- {obs.get('tool')}: {'成功' if obs.get('ok') else '失败'}，耗时 {obs.get('elapsed_seconds')}s")
        if "error" in obs:
            lines.append(f"  错误: {obs['error']}")
    return "\n".join(lines)


def _format_model_config_reply(model_config: dict) -> str:
    lines = [
        "我可以直接读取本地模型配置，不需要你贴文件。",
        "",
        f"- 配置文件: config/default.yaml",
        f"- 默认模型: {model_config.get('configured_default') or '未配置'}",
        f"- 启用模型: {', '.join(model_config.get('enabled') or [])}",
        f"- temperature: {model_config.get('temperature')}",
        f"- max_tokens: {model_config.get('max_tokens')}",
        f"- timeout: {model_config.get('timeout')} 秒",
        f"- max_retries: {model_config.get('max_retries')}",
        "",
        "Provider 状态:",
    ]
    providers = model_config.get("providers") or {}
    for name, info in providers.items():
        key_state = "有 key" if info.get("has_key") else "无 key"
        model_ids = [item.get("id", "") for item in info.get("models", [])]
        lines.append(f"- {name}: {key_state}; {', '.join(model_ids)}")

    status_text = model_config.get("status_text")
    if status_text:
        lines.extend(["", "模型状态:", status_text])
    return "\n".join(lines)


def _reload_modules(agent, modules: list) -> dict:
    """热加载已修改的 Python 模块，重新挂载到 agent。

    高风险操作：失败可能导致 agent 进入半坏状态。
    总是先用 compileall 验证语法，再 reload。
    """
    import importlib
    import subprocess

    if not isinstance(modules, list) or not modules:
        return {"status": "failed", "error": "modules 为空或格式错误"}

    # 1. 先 compileall 验证语法
    compile_proc = subprocess.run(
        ["python3", "-m", "compileall", "-q", "src"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if compile_proc.returncode != 0:
        return {
            "status": "failed",
            "error": "语法检查失败，拒绝热加载",
            "stderr": compile_proc.stderr[-500:],
        }

    reloaded: list = []
    errors: list = []
    for mod_name in modules:
        try:
            mod = importlib.import_module(mod_name)
            importlib.reload(mod)
            reloaded.append(mod_name)
        except Exception as exc:
            errors.append({"module": mod_name, "error": str(exc)})

    # 2. 重新挂载关键对象到 agent（仅 self_evolution）
    rebind_info = {}
    if "src.self_evolution" in reloaded and agent is not None:
        try:
            from src.self_evolution import SelfEvolutionCore
            agent.self_evolution = SelfEvolutionCore(str(PROJECT_ROOT))
            rebind_info["self_evolution"] = "rebound to agent"
        except Exception as exc:
            errors.append({"module": "rebind self_evolution", "error": str(exc)})

    _emit_event("modules.reloaded", {"reloaded": reloaded, "errors": errors}, source="web")

    return {
        "status": "success" if not errors else "partial",
        "reloaded": reloaded,
        "errors": errors,
        "rebind": rebind_info,
        "message": (
            f"已热加载 {len(reloaded)} 个模块" +
            (f"，{len(errors)} 个失败" if errors else "")
        ),
    }


def _execute_agent_tool(agent, name: str, args: dict, original_message: str) -> dict:
    # 延迟导入避免循环依赖
    from lx_web.blueprints.system import (
        _safe_public_model_config, _ping_enabled_models, _read_allowed_file,
    )
    from lx_web.blueprints.autonomy import (
        _autonomy_start, _autonomy_stop, _autonomy_tick, _autonomy_snapshot,
    )

    started = time.time()
    _emit_event("chat.tool.started", {"tool": name, "args": args}, source="chat")
    try:
        if name == "model_config":
            result = _safe_public_model_config()
        elif name == "ping_models":
            max_models = int(args.get("max_models") or 5)
            timeout = int(args.get("timeout") or 20)
            result = _ping_enabled_models(max_models=max(1, min(max_models, 5)), timeout=max(5, min(timeout, 30)))
        elif name == "read_file":
            result = _read_allowed_file(str(args.get("path", "")).strip())
        elif name == "health":
            result = {
                "status": "healthy" if agent is not None else "unhealthy",
                "components": {"web": "healthy", "core": "healthy" if agent is not None else "unhealthy"},
                "uptime": int(time.time() - _system_info["start_time"]),
            }
        elif name == "apply_pending":
            result = agent.evolve_from_lessons()
            restart = _schedule_restart_if_source_changed(result, "chat_apply_pending_source_changed")
            if restart:
                result = {**result, "restart": restart}
        elif name == "self_evolve":
            topic = str(args.get("topic") or original_message).strip()
            url = str(args.get("url") or "").strip()
            result = agent.self_evolve(topic, url=url)
            restart = _schedule_restart_if_source_changed(result, "chat_self_evolve_source_changed")
            if restart:
                result = {**result, "restart": restart}
        elif name == "run_tests":
            result = _run_core_tests()
        elif name == "autonomy_run":
            direction = str(args.get("direction") or original_message).strip()
            result = {"report": agent.run_autonomously(direction)}
        elif name == "autonomy_start":
            interval = int(args.get("interval_seconds") or AUTONOMY_DEFAULT_INTERVAL)
            result = _autonomy_start(interval)
        elif name == "autonomy_stop":
            result = _autonomy_stop()
        elif name == "autonomy_status":
            result = _autonomy_snapshot()
        elif name == "autonomy_tick":
            direction = str(args.get("direction") or original_message).strip()
            result = _autonomy_tick(reason="manual", direction=direction)
        elif name == "reload_modules":
            # 热加载已修改的源码模块，不需要重启 lx_web
            modules = args.get("modules") or ["src.self_evolution", "src.self_reflection",
                                              "src.agent_learning", "src.code_change_log"]
            result = _reload_modules(agent, modules)
        else:
            result = {"status": "failed", "error": f"未知工具: {name}"}
        ok = not (isinstance(result, dict) and result.get("status") == "failed")
        elapsed = round(time.time() - started, 3)
        _emit_event(
            "chat.tool.finished" if ok else "tool.failed",
            {"tool": name, "ok": ok, "elapsed_seconds": elapsed},
            source="chat",
        )
        return {
            "tool": name,
            "ok": ok,
            "elapsed_seconds": elapsed,
            "result": result,
        }
    except Exception as exc:
        _emit_event("tool.failed",
                    {"tool": name, "ok": False, "error": str(exc),
                     "elapsed_seconds": round(time.time() - started, 3)},
                    source="chat")
        return {
            "tool": name,
            "ok": False,
            "elapsed_seconds": round(time.time() - started, 3),
            "error": str(exc),
        }


def _agentic_chat(agent, message: str) -> dict:
    """Let the model decide whether to use local tools, then execute allowed tools."""
    try:
        from src import llm
        from src.utils import extract_json

        decision_prompt = f"""你是冷小北的本地指令调度层。宿主刚发来一条指令。

你拥有以下后端工具权限，应该自主判断是否调用工具，而不是让宿主手动贴文件或自己执行命令。

可用工具：
1. model_config: 读取脱敏后的真实模型配置和 provider key 状态。args={{}}
2. ping_models: 对启用模型发起真实 ping 测试。args={{"max_models": 1-5, "timeout": 秒数}}
3. read_file: 读取白名单文件。args={{"path": "config/default.yaml|src/llm.py|src/core.py|src/self_evolution.py|src/learned_capabilities.py|memory/agent_lessons.json|memory/self_evolution_runs.json"}}
4. health: 读取实时健康状态。args={{}}
5. apply_pending: 应用下一条 pending lesson，真实修改源码并验证。args={{}}
6. self_evolve: 学习方向并自进化。args={{"topic": "学习方向", "url": "可选URL"}}
7. run_tests: 运行本地编译和核心测试。args={{}}
8. autonomy_run: 按宿主方向自主扫描、计划、执行、验证。args={{"direction": "方向"}}
9. autonomy_start: 启动后台自主优化循环。args={{"interval_seconds": 300}}
10. autonomy_stop: 停止后台自主优化循环。args={{}}
11. autonomy_status: 查看后台自主优化状态。args={{}}
12. autonomy_tick: 立刻执行一次后台自主优化循环。args={{"direction": "方向"}}
13. reload_modules: 热加载指定 Python 模块（不需要重启 lx_web）。args={{"modules": ["src.self_evolution", "src.self_reflection"]}}。先 compileall 验证语法，再 importlib.reload。失败不影响主流程。

硬边界：
- 不修改 docs/SOUL.md / docs/CONSTITUTION.md / docs/AUTONOMY.md。
- 不做支付、采购、发布、推送、外部账号操作。
- 不删除核心记忆。
- 需要这些高风险动作时，返回 final 说明需要宿主确认。

判断规则：
- 如果宿主是在下命令、要求检查、测试、读取、应用、优化、修复，就优先调用工具。
- 如果宿主说"系统不会自主优化/开始自己优化/后台运行/不用我催"，优先调用 autonomy_start 或 autonomy_tick。
- 如果只是闲聊或概念讨论，可以不调用工具。
- 不要说"我没有文件读取工具/你贴给我"，因为你有上述后端工具。

只返回 JSON，不要 Markdown：
{{
  "mode": "tool" 或 "chat",
  "tool_calls": [{{"name": "工具名", "args": {{...}}}}],
  "final": "如果不需要工具，直接回复；如果需要工具，这里留空"
}}

宿主指令：{message}
"""
        raw = llm.chat(
            decision_prompt,
            system="你是冷小北的工具调度器。只返回JSON。",
            temperature=0.1,
            use_cache=False,
        )
        decision = extract_json(raw)
    except Exception as exc:
        return {"reply": agent.chat(message), "source": "fallback_chat", "planner_error": str(exc)}

    calls = decision.get("tool_calls") or []
    if decision.get("mode") != "tool" or not calls:
        final = decision.get("final") or agent.chat(message)
        return {"reply": final, "source": "plain_chat"}

    observations = []
    for call in calls[:3]:
        if not isinstance(call, dict):
            continue
        observations.append(_execute_agent_tool(agent, call.get("name", ""), call.get("args") or {}, message))

    try:
        from src import llm

        final_prompt = f"""宿主指令：{message}

你刚刚自主调用了以下后端工具，得到真实结果：
{json.dumps(observations, ensure_ascii=False, indent=2)[:12000]}

请用中文简洁汇报：
- 实际执行了什么
- 真实结果是什么
- 如果失败，下一步该怎么处理
不要声称没有工具。不要把默认统计值说成真实测试。"""
        reply = llm.chat(
            final_prompt,
            system="你是冷小北，基于真实工具结果向宿主汇报。",
            temperature=0.2,
            use_cache=False,
        )
    except Exception:
        reply = _format_tool_observations(observations)

    # 反思：扫这次对话+工具调用，找冷小北自己的能力缺口
    try:
        chat_summary = json.dumps({
            "user_message": message,
            "agent_reply": reply[:600] if isinstance(reply, str) else str(reply)[:600],
            "tools_called": [obs.get("tool") for obs in observations],
            "tool_failures": [obs for obs in observations if not obs.get("ok")],
        }, ensure_ascii=False)
        _run_reflection_async(trigger="chat", context_text=chat_summary)
    except Exception:
        pass

    return {
        "reply": reply,
        "source": "agentic_tools",
        "tool_calls": calls[:3],
        "tool_results": observations,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@chat_bp.route("/api/chat", methods=["POST"])
def api_chat():
    agent = _get_agent()
    if agent is None:
        return jsonify({"error": "Agent 未就绪"}), 503

    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "message 为空"}), 400

    try:
        result = _agentic_chat(agent, message)
        return jsonify({"status": "ok", **result})
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500
