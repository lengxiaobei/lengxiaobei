"""统一 LLM 调用层 — 标准化 JSON 提取、回退、重试"""

import json
import logging
from typing import Dict, Any, Optional

from .. import llm
from ..config import config_manager
from .config import Config, _call_claude_code

logger = logging.getLogger(__name__)


def extract_json(text: str) -> Dict[str, Any]:
    """从 LLM 响应中提取 JSON，支持嵌套对象和 markdown fence"""
    clean = text.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    elif clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    start = clean.find("{")
    if start == -1:
        raise json.JSONDecodeError("No JSON object found", clean, 0)

    depth = 0
    for i in range(start, len(clean)):
        if clean[i] == "{":
            depth += 1
        elif clean[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(clean[start : i + 1])

    raise json.JSONDecodeError("Unclosed JSON object", clean, start)


def chat(
    prompt: str,
    system: str = "",
    temperature: float = 0.3,
    model: Optional[str] = None,
) -> str:
    """统一 LLM 调用 — 自动路由、超时、重试"""
    return llm.chat(prompt, model=model, system=system, temperature=temperature)


def chat_json(
    prompt: str,
    system: str = "你是AI助手。只返回JSON。",
    temperature: float = 0.1,
    model: Optional[str] = None,
    fallback: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """调用 LLM 并解析为 JSON — 优先 Claude Code，回退到多条模型"""
    claude_result = _call_claude_code(prompt)
    if claude_result:
        try:
            return extract_json(claude_result)
        except json.JSONDecodeError:
            pass

    models = Config.get_llm_models()
    if model:
        models = [model] + [m for m in models if m != model]

    for m in models:
        try:
            response = llm.chat(prompt, model=m, system=system, temperature=temperature)
            return extract_json(response)
        except (json.JSONDecodeError, Exception) as e:
            logger.debug(f"模型 {m} 返回非法 JSON: {e}")
            continue

    if fallback is not None:
        logger.warning("所有模型均返回非法 JSON，使用回退值")
        return fallback

    raise RuntimeError("所有 LLM 模型均无法返回合法 JSON")


def generate_code(
    prompt: str,
    model: Optional[str] = None,
) -> str:
    """生成代码 — 优先 Claude Code，回退到代码模型"""
    claude_result = _call_claude_code(prompt)
    if claude_result and _looks_like_code(claude_result):
        return claude_result

    models = Config.get_llm_models()
    code_model = next((m for m in models if "coder" in m.lower()), None)
    if code_model:
        return llm.chat(prompt, model=code_model)
    if model:
        return llm.chat(prompt, model=model)
    return llm.chat(prompt, model=models[0] if models else None)


def _looks_like_code(text: str) -> bool:
    return any(kw in text for kw in ["def ", "class ", "import ", "from ", "async def"])


def chat_bool(
    prompt: str,
    system: str = "你是决策AI。只返回JSON。",
    temperature: float = 0.1,
    fallback: bool = False,
) -> bool:
    """调用 LLM 返回布尔判断"""
    try:
        result = chat_json(prompt, system=system, temperature=temperature)
        return result.get("result", result.get("should_evolve", fallback))
    except Exception:
        return fallback