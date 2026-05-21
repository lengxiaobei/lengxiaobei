"""Curator — 策展人机制

以代码库整体视角定期审查，批量发现优化机会。
特性:
- 三级调度: 快速检查(5min) / 增量审查(30min) / 全量审查(12h)
- 去重: 同一 file+issue 签名 N 天内不重复触发
- 空闲门控: idle 期内不触发新的审查
"""

import os
import ast
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from collections import OrderedDict

from .llm_client import chat_json

logger = logging.getLogger(__name__)


class Improvement:
    """改进机会 — Curator 内部类型，外出时转为 ImprovementRecord"""

    def __init__(self, type: str = "", file: str = "", issue: str = "",
                 priority: str = "medium", suggestion: str = "",
                 severity: str = "minor", category: str = "optimization",
                 confidence: float = 0.8):
        self.type = type
        self.file = file
        self.issue = issue
        self.priority = priority
        self.suggestion = suggestion
        self.severity = severity
        self.category = category
        self.confidence = confidence

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Improvement":
        return cls(
            type=data.get("type", "code_quality"),
            file=data.get("file", ""),
            issue=data.get("issue", ""),
            priority=data.get("priority", "medium"),
            suggestion=data.get("suggestion", ""),
            severity=data.get("severity", "minor"),
            category=data.get("category", "optimization"),
            confidence=data.get("confidence", 0.8),
        )


class Curator:
    """策展人 — 定时审查 + 去重"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.src_dir = self.project_root / "src"
        self.skills_dir = self.project_root / "skills" / "evolution"

        self._last_full_review: float = 0
        self._last_incremental_review: float = 0
        self._last_quick_check: float = 0

        # 去重: signature → 最后触发时间
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._seen_max = 200
        self._seen_ttl = 7 * 24 * 3600

    # ------------------------------------------------------------------
    # 调度判断
    # ------------------------------------------------------------------

    def should_full_review(self) -> bool:
        return time.time() - self._last_full_review > 12 * 3600

    def should_incremental_review(self) -> bool:
        return time.time() - self._last_incremental_review > 30 * 60

    def should_quick_check(self) -> bool:
        return time.time() - self._last_quick_check > 5 * 60

    # ------------------------------------------------------------------
    # 去重
    # ------------------------------------------------------------------

    def is_duplicate(self, signature: str) -> bool:
        self._gc_seen()
        return signature in self._seen

    def mark_seen(self, signature: str):
        self._seen[signature] = time.time()
        while len(self._seen) > self._seen_max:
            self._seen.popitem(last=False)

    def _gc_seen(self):
        cutoff = time.time() - self._seen_ttl
        expired = [k for k, v in self._seen.items() if v < cutoff]
        for k in expired:
            del self._seen[k]

    # ------------------------------------------------------------------
    # 审查方法
    # ------------------------------------------------------------------

    def review(self) -> List[Improvement]:
        logger.info("[Curator] 全量审查...")
        skills_context = self._load_skills_context()
        code_summary = self._collect_codebase_summary()
        prompt = self._build_review_prompt(code_summary, skills_context)

        try:
            data = chat_json(
                prompt,
                system="你是资深代码审查专家。只返回JSON。",
                temperature=0.4,
                fallback={"improvements": []},
            )
            improvements = []
            for item in data.get("improvements", []):
                imp = Improvement.from_dict(item)
                if imp.confidence >= 0.65 and imp.file:
                    improvements.append(imp)

            improvements.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.priority, 1))
            self._last_full_review = time.time()
            logger.info(f"[Curator] 全量审查完成，发现 {len(improvements)} 个改进点")
            return improvements
        except Exception as e:
            logger.error(f"[Curator] 全量审查失败: {e}")
            return []

    def quick_check(self) -> List[Improvement]:
        issues = []
        for root, dirs, files in os.walk(self.src_dir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "venv", "node_modules")]
            for f in files:
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    has_syntax_error = False
                    try:
                        with open(fpath, "r", encoding="utf-8") as fh:
                            ast.parse(fh.read(), filename=fpath)
                    except SyntaxError as e:
                        issues.append(Improvement(
                            type="bug", file=os.path.relpath(fpath, self.project_root),
                            issue=f"语法错误: {e}", priority="high",
                            severity="critical", category="bug", confidence=1.0,
                        ))
                        has_syntax_error = True
                    except UnicodeDecodeError:
                        continue
                    if has_syntax_error:
                        continue
                    if self._missing_final_newline(fpath):
                        issues.append(Improvement(
                            type="code_quality",
                            file=os.path.relpath(fpath, self.project_root),
                            issue="文件末尾缺少换行，补齐 POSIX 文本文件结尾",
                            priority="low",
                            suggestion="在文件末尾追加一个换行符，不改变代码逻辑",
                            severity="minor",
                            category="cleanup",
                            confidence=0.95,
                        ))
        self._last_quick_check = time.time()
        return issues

    @staticmethod
    def _missing_final_newline(file_path: str) -> bool:
        try:
            with open(file_path, "rb") as fh:
                content = fh.read()
            return bool(content) and not content.endswith(b"\n")
        except OSError:
            return False

    def incremental_review(self) -> List[Improvement]:
        recent_files = self._get_recently_modified_files(hours=24)
        if not recent_files:
            self._last_incremental_review = time.time()
            return []

        code_summary = self._collect_files_summary(recent_files)
        prompt = f"""你是代码审查专家。请审查以下最近修改的文件，找出具体改进点。

{code_summary}

返回JSON: {{"improvements": [{{"type": "类型", "file": "文件路径", "issue": "问题描述", "priority": "high/medium/low", "suggestion": "改进建议", "severity": "critical/major/minor", "category": "bug/optimization/cleanup", "confidence": 0.8}}]}}
只返回JSON。"""

        try:
            data = chat_json(prompt, temperature=0.3, fallback={"improvements": []})
            self._last_incremental_review = time.time()
            return [Improvement.from_dict(i) for i in data.get("improvements", [])]
        except Exception as e:
            logger.error(f"[Curator] 增量审查失败: {e}")
            return []

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _load_skills_context(self) -> str:
        index_path = self.skills_dir / "INDEX.md"
        if not index_path.exists():
            return ""
        try:
            return index_path.read_text(encoding="utf-8")[:3000]
        except Exception:
            return ""

    def _collect_codebase_summary(self) -> str:
        return self._collect_files_summary(self._all_py_files())

    def _all_py_files(self) -> List[str]:
        files = []
        for root, dirs, fs in os.walk(self.src_dir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "venv", "node_modules")]
            for f in fs:
                if f.endswith(".py"):
                    files.append(os.path.join(root, f))
        return files

    def _collect_files_summary(self, files: List[str]) -> str:
        parts = []
        total = 0
        infos = []
        for fpath in files:
            try:
                with open(fpath) as f:
                    content = f.read()
                infos.append({
                    "path": os.path.relpath(fpath, self.project_root),
                    "content": content,
                    "lines": len(content.splitlines()),
                })
            except Exception:
                pass
        infos.sort(key=lambda x: x["lines"], reverse=True)

        for fi in infos:
            if total >= 25000:
                parts.append(f"\n### {fi['path']} ({fi['lines']}行) - 已跳过")
                continue
            content = fi["content"]
            if len(content) > 3000:
                content = self._extract_definitions(content)
            if len(content) > 2500:
                content = content[:2500] + "\n# ..."
            parts.append(f"\n### {fi['path']} ({fi['lines']}行)\n```python\n{content}\n```")
            total += len(content)
        return "\n".join(parts)

    @staticmethod
    def _extract_definitions(content: str) -> str:
        try:
            tree = ast.parse(content)
            extracted = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    start = node.lineno - 1
                    end = getattr(node, "end_lineno", start + 10)
                    extracted.extend(content.split("\n")[start:end])
                    extracted.append("")
            result = "\n".join(extracted)
            return result[:6000] if len(result) > 6000 else result
        except Exception:
            return content[:4000]

    def _get_recently_modified_files(self, hours: int = 24) -> List[str]:
        cutoff = time.time() - hours * 3600
        recent = []
        for root, dirs, fs in os.walk(self.src_dir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "venv")]
            for f in fs:
                if f.endswith(".py"):
                    fpath = os.path.join(root, f)
                    try:
                        if os.path.getmtime(fpath) > cutoff:
                            recent.append(fpath)
                    except OSError:
                        pass
        return recent

    def _build_review_prompt(self, code_summary: str, skills_context: str) -> str:
        return f"""你是资深代码审查专家。请以全局视角审查代码库，找出具体的跨文件改进机会。

## 历史经验
{skills_context}

## 代码库摘要
{code_summary}

## 审查重点
1. 跨文件的代码复用和重复逻辑
2. 模块间的不一致问题
3. 未被调用的死代码和改进机会
4. 错误处理和边界条件
5. 过度复杂的设计

请返回 5-8 个具体、可操作的改进点：

```json
{{
  "improvements": [
    {{
      "type": "complexity/performance/security/code_quality/architecture",
      "file": "文件路径(相对项目根目录)",
      "issue": "具体问题描述",
      "priority": "high/medium/low",
      "suggestion": "详细改进建议",
      "severity": "critical/major/minor",
      "category": "bug/optimization/cleanup/security/architecture",
      "confidence": 0.9
    }}
  ]
}}
```

只返回JSON。"""
