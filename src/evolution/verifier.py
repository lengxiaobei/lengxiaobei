"""Verifier — 测试验证

基于 pytest 的强制测试验证，确保进化的可靠性。
测试不通过时禁止 cleanup 备份文件。
"""

import os
import re
import sys
import subprocess
import logging
import shutil
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration: float = 0.0
    output: str = ""
    error_detail: str = ""

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.errors == 0

    @property
    def summary(self) -> str:
        return f"passed={self.passed} failed={self.failed} errors={self.errors} skipped={self.skipped}"


class PytestVerifier:
    """基于 pytest 的测试验证器"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.test_dir = self.project_root / "tests"

    def verify(self, target_file: Optional[str] = None) -> TestResult:
        if not self.test_dir.exists():
            logger.info("[Verifier] tests/ 目录不存在，执行全量编译检查")
            return self._full_compile_check(target_file)

        return self._run_pytest()

    def verify_imports(self) -> TestResult:
        modules = [
            "src.core", "src.llm",
            "src.evolution.engine", "src.evolution.curator",
            "src.evolution.proposer", "src.evolution.executor",
            "src.evolution.verifier", "src.evolution.llm_client",
            "src.evolution.models", "src.evolution.skills_store",
            "src.circuit_breaker", "src.integrity_checker",
            "src.constitution", "src.evolution_permission",
        ]
        passed = 0
        failed = 0
        output_lines = []
        for mod in modules:
            try:
                __import__(mod)
                output_lines.append(f"PASS {mod}")
                passed += 1
            except Exception as e:
                output_lines.append(f"FAIL {mod}: {e}")
                failed += 1
        return TestResult(passed=passed, failed=failed, output="\n".join(output_lines))

    # ------------------------------------------------------------------
    # pytest parsing
    # ------------------------------------------------------------------

    _SHORT_SUMMARY = re.compile(
        r"(\d+)\s+passed[,;]?\s*(?:(\d+)\s+failed[,;]?\s*)?(?:(\d+)\s+errors?[,;]?\s*)?(?:(\d+)\s+skipped)?"
    )

    _TEST_RESULT_LINE = re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED)\s")

    def _run_pytest(self) -> TestResult:
        pytest_bin = shutil.which("pytest")
        if pytest_bin:
            cmd = [pytest_bin, str(self.test_dir), "-v", "--tb=short"]
        else:
            cmd = [sys.executable, "-m", "pytest", str(self.test_dir), "-v", "--tb=short"]
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)
            result = subprocess.run(
                cmd, cwd=str(self.project_root),
                capture_output=True, text=True, timeout=300, env=env,
            )

            output = result.stdout + result.stderr
            passed, failed, errs, skipped = self._parse_pytest_output(output)

            if result.returncode != 0 and passed == 0 and failed == 0 and errs == 0:
                failed = 1

            short_tail = "\n".join(output.split("\n")[-25:])

            return TestResult(
                passed=passed, failed=failed, errors=errs, skipped=skipped,
                output=short_tail,
                error_detail=result.stderr[:1000] if result.stderr else "",
            )
        except subprocess.TimeoutExpired:
            return TestResult(failed=1, errors=1, error_detail="测试超时 (300s)")
        except Exception as e:
            return TestResult(failed=1, errors=1, error_detail=str(e))

    def _parse_pytest_output(self, output: str):
        passed = 0
        failed = 0
        errs = 0
        skipped = 0

        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue
            if "===" in line:
                m = self._SHORT_SUMMARY.search(line)
                if m:
                    g = m.groups()
                    if g[0]:
                        passed = int(g[0])
                    if g[1]:
                        failed = int(g[1])
                    if g[2]:
                        errs = int(g[2])
                    if g[3]:
                        skipped = int(g[3])

        if passed == 0 and failed == 0 and errs == 0:
            for line in output.split("\n"):
                line = line.strip()
                m = self._TEST_RESULT_LINE.match(line)
                if not m:
                    continue
                status = m.group(1)
                if status == "PASSED":
                    passed += 1
                elif status == "FAILED":
                    failed += 1
                elif status == "ERROR":
                    errs += 1
                elif status == "SKIPPED":
                    skipped += 1

        return passed, failed, errs, skipped

    # ------------------------------------------------------------------
    # fallback: full compile check
    # ------------------------------------------------------------------

    def _full_compile_check(self, target_file: Optional[str] = None) -> TestResult:
        passed = 0
        failed = 0

        files_to_check = []
        if target_file and os.path.exists(target_file):
            files_to_check = [target_file]
        else:
            src_dir = self.project_root / "src"
            for root, dirs, files in os.walk(src_dir):
                dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "venv", "node_modules")]
                for f in files:
                    if f.endswith(".py"):
                        files_to_check.append(os.path.join(root, f))

        for fpath in files_to_check:
            try:
                with open(fpath) as f:
                    compile(f.read(), fpath, "exec")
                passed += 1
            except SyntaxError as e:
                logger.warning(f"[Verifier] 语法错误: {fpath}: {e}")
                failed += 1

        return TestResult(passed=passed, failed=failed)

    def should_rollback(self, result: TestResult, score: float = 0) -> bool:
        if result.errors > 0:
            return True
        if result.failed > 0:
            return True
        return False
