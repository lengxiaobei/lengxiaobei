"""统一 LLM 调用层 — 标准化 JSON 提取、回退、重试"""

import json
import logging
from typing import Dict, Any, Optional

from .. import llm
from ..utils import extract_json
from .config import Config, _call_claude_code

logger = logging.getLogger(__name__)


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
    """生成代码 — 优先 Claude Code，回退到代码模型。
    自动剥离 markdown 代码块包装，确保返回值是合法 Python 源码。
    """
    claude_result = _call_claude_code(prompt)
    if claude_result:
        cleaned = _strip_markdown_code_fences(claude_result)
        if _looks_like_code(cleaned):
            return cleaned

    models = Config.get_llm_models()
    code_model = next((m for m in models if "coder" in m.lower()), None)
    if code_model:
        return _strip_markdown_code_fences(llm.chat(prompt, model=code_model))
    if model:
        return _strip_markdown_code_fences(llm.chat(prompt, model=model))
    return _strip_markdown_code_fences(llm.chat(prompt, model=models[0] if models else None))


def _strip_markdown_code_fences(text: str) -> str:
    """剥离 ```python ... ``` 包装，提取纯 Python 源码。

    LLM 经常返回 ```python\\n...\\n``` 形式的代码块，整段写入 .py 会语法错。
    处理几种常见格式：
      ```python\\n<code>\\n```
      ```py\\n<code>\\n```
      ```\\n<code>\\n```
      纯代码（直接返回）
      说明文字 + 代码（提取第一个代码块）
    """
    import re as _re

    if not isinstance(text, str) or not text:
        return text or ""

    # 1) 含完整 fenced code block：提取最大的块
    fence_pattern = _re.compile(
        r"```(?:python|py|python3)?\s*\n?(.*?)\n?```",
        _re.DOTALL | _re.IGNORECASE,
    )
    matches = fence_pattern.findall(text)
    if matches:
        return max(matches, key=len).strip() + "\n"

    # 2) 没 fence 但有 markdown 说明 — 找首个 def/class/import 开头跳过废话
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        stripped = ln.lstrip()
        if stripped.startswith(("def ", "class ", "import ", "from ", "async def ",
                                "#!/", '"""', "'''", "@")):
            return "\n".join(lines[i:]).rstrip() + "\n"

    # 3) 看起来就是纯代码，原样返回
    return text


def _looks_like_code(text: str) -> bool:
    """严格代码识别：必须能被 ast.parse 通过。"""
    if not text or not text.strip():
        return False
    if not any(kw in text for kw in ["def ", "class ", "import ", "from ", "async def"]):
        return False
    try:
        import ast
        ast.parse(text)
        return True
    except SyntaxError:
        return False


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