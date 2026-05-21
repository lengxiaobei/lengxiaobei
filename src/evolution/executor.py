"""Executor — 安全执行 + 治理内嵌

写入前: 权限审批 + Constitution 合规
写入: 备份 → 回滚安全
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
    signature: str = ""
    error: str = ""
    sandbox_result: Optional[Dict[str, Any]] = None

    @property
    def success(self) -> bool:
        return self.status == "success"


class SafeExecutor:
    """安全执行器 — 权限前置 → 备份 → 写入 → 签名"""

    def __init__(self, project_root: str, permission_manager=None, constitution=None):
        self.project_root = project_root
        self.permission_manager = permission_manager
        self.constitution = constitution

    def execute(self, file_path: str, new_code: str,
                improvement: Optional[ImprovementRecord] = None) -> ExecutionResult:
        if not os.path.exists(file_path):
            return ExecutionResult(status="failed", file_path=file_path, error="文件不存在")

        is_newline_fix = improvement and "文件末尾缺少换行" in improvement.issue
        new_code = self._sanitize(new_code)
        if is_newline_fix:
            new_code = new_code if new_code.endswith("\n") else new_code + "\n"
        if not self._validate_code_safety(new_code):
            return ExecutionResult(status="failed", file_path=file_path, error="代码验证失败")

        # ---- 治理: 权限审批（写入前） ----
        if self.permission_manager:
            try:
                risk = getattr(improvement, 'risk_level', 'medium') if improvement else 'medium'
                allowed = self._check_permission(file_path, risk, improvement)
                if not allowed:
                    return ExecutionResult(status="failed", file_path=file_path, error="permission_denied")
            except Exception as e:
                logger.warning(f"[Executor] 权限检查异常: {e}")

        # ---- 治理: Constitution 合规（写入前） ----
        if self.constitution and hasattr(self.constitution, 'validate_change'):
            try:
                desc = improvement.issue if improvement else ""
                ok = self.constitution.validate_change(file_path, desc, new_code)
                if not ok:
                    return ExecutionResult(status="failed", file_path=file_path, error="constitution_violation")
            except Exception as e:
                logger.warning(f"[Executor] Constitution 检查异常: {e}")

        # ---- 备份 ----
        backup_path = file_path + f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(file_path, backup_path)

        try:
            with open(backup_path) as f:
                old_content = f.read()

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_code)

            # 事后签名（审计用）
            signature = ""
            if self.permission_manager:
                try:
                    signature = self.permission_manager.sign_code_change(
                        file_path, old_content, new_code
                    )
                except Exception:
                    pass

            logger.info(f"[Executor] 写入成功: {os.path.basename(file_path)}")
            return ExecutionResult(
                status="success", file_path=file_path,
                backup_path=backup_path, signature=signature,
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

    def _check_permission(self, file_path: str, risk_level: str, improvement: Optional[ImprovementRecord] = None) -> bool:
        pm = self.permission_manager
        if hasattr(pm, 'check_permission'):
            return pm.check_permission(file_path, "write", risk_level)
        if hasattr(pm, 'is_allowed'):
            return pm.is_allowed(file_path)
        if hasattr(pm, 'require_approval'):
            approved = pm.require_approval(file_path, "write", risk_level)
            if not approved:
                logger.warning(f"[Executor] 权限被拒: {file_path}")
            return approved
        return True

    def _validate_code_safety(self, code: str) -> bool:
        if not code or not code.strip():
            logger.error("[Executor] 空代码")
            return False
        bad = ["[调用失败]", "模型服务暂时不可用", "I cannot", "I'm unable"]
        if any(kw in code for kw in bad):
            logger.error("[Executor] LLM 服务异常")
            return False
        try:
            compile(code, "<evolution>", "exec")
            return True
        except SyntaxError as e:
            logger.error(f"[Executor] 语法错误: {e}")
            return False

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
