"""Executor — 精简执行器

写入: 备份 → 写入 → 回滚安全
"""

import os
import re
import shutil
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime

from .models import ImprovementRecord

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    status: str = "pending"
    file_path: str = ""
    backup_path: str = ""
    error: str = ""

    @property
    def success(self) -> bool:
        return self.status == "success"


class SafeExecutor:
    """精简执行器 — 备份 → 写入 → 回滚"""

    def __init__(self, project_root: str):
        self.project_root = project_root

    def execute(self, file_path: str, new_code: str,
                improvement: Optional[ImprovementRecord] = None) -> ExecutionResult:
        if not os.path.exists(file_path):
            return ExecutionResult(status="failed", file_path=file_path, error="文件不存在")

        is_newline_fix = improvement and "文件末尾缺少换行" in improvement.issue
        new_code = self._sanitize(new_code)
        if is_newline_fix:
            new_code = new_code if new_code.endswith("\n") else new_code + "\n"

        # ---- 备份 ----
        backup_path = file_path + f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(file_path, backup_path)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_code)

            logger.info(f"[Executor] 写入成功: {os.path.basename(file_path)}")
            return ExecutionResult(
                status="success", file_path=file_path,
                backup_path=backup_path,
            )
        except Exception as e:
            self._rollback_to(backup_path, file_path)
            return ExecutionResult(status="failed", file_path=file_path, error=str(e))

    def rollback(self, result: ExecutionResult):
        if result.backup_path and os.path.exists(result.backup_path):
            self._rollback_to(result.backup_path, result.file_path)
            logger.info(f"[Executor] 回滚完成: {os.path.basename(result.file_path)}")

    def cleanup(self, result: ExecutionResult):
        if result.backup_path and os.path.exists(result.backup_path):
            os.remove(result.backup_path)

    # ------------------------------------------------------------------
    # private
    # ------------------------------------------------------------------

    def _sanitize(self, code: str) -> str:
        if not code:
            return code
        wants_final_newline = code.endswith("\n")

        cb = re.compile(r"```(?:python|py|)\s*\n(.*?)\n```", re.DOTALL)
        matches = cb.findall(code)
        if matches:
            longest = max(matches, key=len)
            if len(longest) > 50:
                code = longest
                wants_final_newline = code.endswith("\n")

        if not matches:
            lines = code.split("\n")
            start = 0
            for i, line in enumerate(lines):
                s = line.strip()
                if s.startswith(("class ", "def ", "import ", "from ", '"""', "'''", "#", "@")):
                    start = i
                    break
            code = "\n".join(lines[start:])

        code = code.strip()
        code = re.sub(r"^```(?:python|py|)\s*\n?", "", code, flags=re.MULTILINE)
        code = re.sub(r"\n?```\s*$", "", code)

        fw = {
            "：": ":", "，": ",", "；": ";", "（": "(", "）": ")",
            "【": "[", "】": "]", "｛": "{", "｝": "}", "＂": '"', "＇": "'",
            "＝": "=", "＋": "+", "－": "-", "＊": "*", "／": "/",
            "＜": "<", "＞": ">", "！": "!", "？": "?", "　": " ",
            "。": ".", "、": ",", "《": "<", "》": ">",
            '"': '"', '"': '"', "’": "'", "‘": "'", "～": "~", "％": "%",
        }
        for k, v in fw.items():
            code = code.replace(k, v)

        lines = code.split("\n")
        cleaned = []
        for line in lines:
            s = line.strip()
            if not any(c in s for c in "=:+-*/<>[]{}()@.\\\"'"):
                if any("\u4e00" <= ch <= "\u9fff" for ch in s):
                    if not s.startswith("#") and not s.startswith('"') and not s.startswith("'"):
                        continue
            cleaned.append(line)
        sanitized = "\n".join(cleaned).strip()
        if wants_final_newline and sanitized and not sanitized.endswith("\n"):
            sanitized += "\n"
        return sanitized

    @staticmethod
    def _rollback_to(backup_path: str, target_path: str):
        shutil.copy2(backup_path, target_path)
        if os.path.exists(backup_path):
            os.remove(backup_path)
