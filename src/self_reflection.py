"""自我反思模块 — 让冷小北能从最近的对话和 tick 中识别自己的能力缺口。

设计原则：
- 每次对话/tick 收尾时调用一次，传入最近的上下文片段
- 不做任何 web 抓取，只用 LLM 内省
- 失败时静默返回 None，不阻断主流程
- 返回的 gap 会被 lx_web 写入 autonomy_learning_plan.json，下次 tick 自动学习

返回 schema:
    {
        "gap":              "缺什么能力（一句话）",
        "suggested_topic":  "下次 tick 应该学的方向（完整 lesson topic）",
        "kind":             "introspection" | "external",  # 内省 vs 学其他 agent
        "priority":         1-5,
        "trigger_context":  "触发这次反思的上下文片段（≤200字）",
    }

kind=='introspection' → learner.learn() 跳过 web 抓取，直接让 LLM 设计改造方案
kind=='external'      → 走原有流程，抓 web URL 并提炼
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


REFLECTION_LOG = "memory/reflection_log.jsonl"
MAX_RECENT_GAPS = 20  # 用于去重，避免重复提同样的 gap


def _read_recent_gaps(project_root: Path, limit: int = MAX_RECENT_GAPS) -> List[str]:
    """读最近的反思日志，提取已记录的 gap 字符串，用来去重。"""
    log_path = project_root / REFLECTION_LOG
    if not log_path.exists():
        return []
    gaps: List[str] = []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                g = rec.get("gap")
                if g:
                    gaps.append(str(g))
            except Exception:
                continue
    except Exception:
        pass
    return gaps


def _append_reflection(project_root: Path, record: Dict[str, Any]) -> None:
    log_path = project_root / REFLECTION_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def detect_user_complaint(context_text: str, recent_gaps: List[str] | None = None) -> Optional[Dict[str, Any]]:
    """启发式探测用户抱怨/反馈。
    用户反馈是最强信号——比 LLM 反思更可靠，必须保证不丢。

    返回与 reflect() 同样格式的 gap dict，或 None。
    """
    import re as _re

    if not context_text:
        return None

    # 抱怨关键词组：每组任一命中即触发
    complaint_patterns = [
        # 系统问题类
        (r"(系统|自身|你的?)问题", "system_self_issue"),
        (r"丢失|消失|不见|没保存|没存下", "data_loss"),
        (r"刷新.*丢|刷新.*没|关闭.*没", "persistence_missing"),
        # 能力缺失类
        (r"没法|不会|做不到|不能(?:用|做|跑|启|调)", "capability_missing"),
        (r"没有.*工具|缺.*工具|需要.*工具", "tool_missing"),
        (r"不会(?:自主|主动|自动)", "no_autonomy"),
        (r"不自动|不主动", "not_proactive"),
        # 体验/Bug 类
        (r"bug|报错|挂了|崩了|失败|出错", "bug"),
        (r"卡住|卡死|没反应|不动", "stuck"),
        (r"慢|太久|超时", "slow"),
        # 用户明确反馈
        (r"我又?发现|又一个问题|另一个问题|还有(?:个|一个)?问题", "user_reported_issue"),
    ]

    # 解析最近用户消息（约定 chat 反思的 context 包含 "user_message" 字段 JSON）
    user_msg = ""
    try:
        import json as _json
        parsed = _json.loads(context_text) if context_text.startswith("{") else {}
        user_msg = str(parsed.get("user_message") or "")
    except Exception:
        pass
    if not user_msg:
        user_msg = context_text  # 兜底全文搜

    hits: List[tuple] = []  # [(category, snippet)]
    for pat, cat in complaint_patterns:
        m = _re.search(pat, user_msg, _re.IGNORECASE)
        if m:
            # 取命中前后 30 字
            start = max(0, m.start() - 30)
            end = min(len(user_msg), m.end() + 30)
            hits.append((cat, user_msg[start:end].strip()))

    if not hits:
        return None

    # 用最先命中的作为主类别，其他作为补充
    main_cat, main_snippet = hits[0]
    all_cats = list(dict.fromkeys(h[0] for h in hits))  # 去重保序

    # 把这个抱怨变成 learning plan 条目
    gap_text = f"用户反馈[{main_cat}]：{main_snippet[:120]}"
    suggested_topic = (
        f"修复用户反馈的 [{', '.join(all_cats)}] 类问题。"
        f"原始反馈：{user_msg[:200]}。"
        f"请在合适的 SAFE_TARGETS 模块（src/buddy.py / src/active_learner.py / src/dev_team.py / "
        f"src/critic.py / src/code_change_log.py / src/testing.py / src/learned_capabilities.py）中"
        f"新增对应的函数来解决这个问题，函数名要明确反映改进点。"
    )

    # 去重
    if recent_gaps:
        for g in recent_gaps:
            if main_snippet[:40] in g or gap_text[:40] in g:
                return None

    return {
        "ts": time.time(),
        "trigger": "user_complaint",
        "gap": gap_text,
        "suggested_topic": suggested_topic,
        "kind": "introspection",
        "priority": 5,  # 用户反馈是最高优先级
        "trigger_context": user_msg[:400],
        "categories": all_cats,
        "source_signal": "heuristic_complaint_detector",
    }


def reflect(
    project_root: str,
    *,
    trigger: str,
    context_text: str,
    timeout: int = 20,
) -> Optional[Dict[str, Any]]:
    """对给定上下文做一次反思，找出 1 个能力缺口。

    流程：
        1. 启发式探测用户抱怨 — 命中就直接用，不丢任何用户反馈
        2. 否则走 LLM 反思

    trigger: "chat" | "autonomy_tick" | 其他自定义
    context_text: 触发反思的原始片段（用户输入+agent回复+工具调用）
    返回 None 表示：LLM 不可用，或没有发现新缺口，或反思失败。
    """
    if not context_text.strip():
        return None

    root = Path(project_root)
    recent_gaps = _read_recent_gaps(root)

    # Fast path: 用户抱怨探测（确定性，最高优先级）
    if trigger == "chat":
        complaint = detect_user_complaint(context_text, recent_gaps)
        if complaint:
            _append_reflection(root, complaint)
            return complaint

    recent_block = "\n".join(f"- {g}" for g in recent_gaps[-10:]) if recent_gaps else "（无）"

    # 截断超长上下文
    ctx = context_text.strip()
    if len(ctx) > 2400:
        ctx = ctx[:1200] + "\n…（中间省略）…\n" + ctx[-1200:]

    prompt = f"""你是冷小北的自我反思器。基于以下上下文，识别出冷小北自身**1 个**能力或工具缺口。

最近上下文（触发 {trigger}）:
{ctx}

最近已记录过的 gap（避免重复，必须避开这些方向）:
{recent_block}

要求:
1. 必须是冷小北**自己**暴露出的能力或工具缺口（如"没有 X 工具"、"不能做 Y"、"对 Z 类型的请求处理不好"）
2. 不是"用户没说清楚"这种甩锅
3. 不是已经在最近 gap 列表里的重复
4. 如果上下文中冷小北表现完全无短板，返回 {{"gap": null}}

返回严格 JSON:
{{
  "gap": "一句话描述缺口 | null",
  "suggested_topic": "如果有 gap，写一个完整的、下次 tick 可学习的方向（指明应该新增/改造什么源码）",
  "kind": "introspection",
  "priority": 1-5（1=不紧急, 5=阻塞核心交互）,
  "trigger_context": "≤200字的触发摘要"
}}"""

    try:
        from .llm import chat
        from .utils import extract_json

        raw = chat(
            prompt,
            system="你是冷小北自我反思器。只返回 JSON，不要任何额外解释。",
            temperature=0.2,
            use_cache=False,
        )
        data = extract_json(raw)
    except Exception as exc:
        _append_reflection(root, {
            "ts": time.time(),
            "trigger": trigger,
            "error": str(exc),
            "context_preview": ctx[:200],
        })
        return None

    if not isinstance(data, dict):
        return None

    gap = data.get("gap")
    if not gap or str(gap).strip().lower() in ("null", "none", ""):
        # 没发现缺口也记一笔，方便后续观察
        _append_reflection(root, {
            "ts": time.time(),
            "trigger": trigger,
            "gap": None,
            "context_preview": ctx[:200],
        })
        return None

    # 标准化
    record = {
        "ts": time.time(),
        "trigger": trigger,
        "gap": str(gap).strip(),
        "suggested_topic": str(data.get("suggested_topic") or "").strip(),
        "kind": str(data.get("kind") or "introspection").strip(),
        "priority": int(data.get("priority") or 3),
        "trigger_context": str(data.get("trigger_context") or ctx[:200]).strip(),
    }

    # 去重：如果 gap 已经在最近 N 条出现过，跳过
    if any(record["gap"] == g for g in recent_gaps):
        record["skipped_duplicate"] = True
        _append_reflection(root, record)
        return None

    _append_reflection(root, record)
    return record


def enqueue_to_learning_plan(
    project_root: str,
    reflection: Dict[str, Any],
    *,
    plan_path: str = "memory/autonomy_learning_plan.json",
) -> bool:
    """把反思产出写入 learning plan，标 status=pending 让下次 tick 学它。
    返回 True 表示成功写入新条目。"""
    if not reflection or not reflection.get("suggested_topic"):
        return False

    root = Path(project_root)
    path = root / plan_path
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if path.exists():
            plan = json.loads(path.read_text(encoding="utf-8") or "[]")
        else:
            plan = []
        if not isinstance(plan, list):
            plan = []
    except Exception:
        plan = []

    # 去重：同 topic 已存在就不重复加
    topic = reflection["suggested_topic"]
    for item in plan:
        if isinstance(item, dict) and item.get("topic") == topic:
            return False

    new_item = {
        "id": f"introspect_{int(time.time())}",
        "topic": topic,
        "url": "",  # 内省话题没有外部 URL
        "status": "pending",
        "created_at": time.time(),
        "source": "self_reflection",
        "kind": reflection.get("kind", "introspection"),
        "priority": reflection.get("priority", 3),
        "gap": reflection.get("gap", ""),
        "trigger_context": reflection.get("trigger_context", ""),
    }
    plan.append(new_item)

    try:
        path.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception:
        return False
