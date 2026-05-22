"""Verifier — 测试验证

分三级验证策略:
1. 针对性测试：找到匹配的 test 文件运行
2. 编译检查：全量 compile() 确保无语法错误
3. 全量 pytest（仅在针对性测试通过后运行，可选）
"""

import os
import re
import sys
import subprocess
import logging
import shutil
from dataclasses import dataclass
from typing import Optional, List, Tuple
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
    level: str = "unknown"  # targeted / compile / full_pytest / skipped

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.errors == 0

    @property
    def summary(self) -> str:
        return f"[{self.level}] passed={self.passed} failed={self.failed} errors={self.errors} skipped={self.skipped}"


class PytestVerifier:
    """分三级验证的测试验证器"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.test_dir = self.project_root / "tests"

    def verify(self, target_file: Optional[str] = None) -> TestResult:
        """验证修改后的文件

        策略:
        1. 如果有 target_file，先找匹配的 test 文件针对性测试
        2. 否则编译检查所有 src/*.py
        3. 最后跑全量 pytest（如果有 tests/ 目录）
        """
        # Level 1: 针对性测试
        if target_file:
            test_file = self._find_matching_test(target_file)
            if test_file and os.path.exists(test_file):
                result = self._run_single_test(test_file)
                result.level = "targeted"
                if result.success:
                    logger.info(f"[Verifier] targeted test passed: {test_file}")
                    # 编译检查作为补充
                    compile_result = self._full_compile_check()
                    if not compile_result.success:
                        logger.warning(f"[Verifier] compile check found issues")
                        return compile_result
                    return result
                else:
                    logger.warning(f"[Verifier] targeted test failed: {result.summary}")
                    return result

        # Level 2: 编译检查
        compile_result = self._full_compile_check(target_file)
        compile_result.level = "compile"
        if not compile_result.success:
            logger.warning(f"[Verifier] compile check failed: {compile_result.summary}")
            return compile_result

        # Level 3: 全量 pytest（如果有测试目录）
        if self.test_dir.exists():
            result = self._run_pytest()
            result.level = "full_pytest"
            return result

        # 没有测试目录，编译通过就 OK
        logger.info(f"[Verifier] no tests/ dir, compile check passed => success")
        return compile_result

    def _find_matching_test(self, target_file: str) -> Optional[str]:
        """找到匹配目标文件的测试文件

        映射规则:
        - src/evolution/engine.py -> tests/test_evolution.py
        - src/core.py -> tests/test_core_modules.py
        - src/kairos/engine.py -> tests/test_kairos.py
        - src/facade_guardian.py -> tests/test_guardian.py
        """
        target = Path(target_file)
        target_name = target.stem  # e.g. "engine" from "engine.py"

        # 优先: 直接匹配 test_<module>.py
        candidates = [
            f"test_{target_name}.py",
            f"test_{target.parent.name}.py" if target.parent.name != "src" else None,
        ]

        # 从目录推断 test 文件
        parent_name = target.parent.name
        dir_to_test = {
            "evolution": "test_evolution.py",
            "kairos": "test_kairos.py",
            "core": "test_core_modules.py",
            "guardian": "test_guardian.py",
        }
        if parent_name in dir_to_test:
            candidates.append(dir_to_test[parent_name])

        for c in candidates:
            if c is None:
                continue
            test_path = self.test_dir / c
            if test_path.exists():
                return str(test_path)

            # Also check tests/unit/
            unit_path = self.test_dir / "unit" / c
            if unit_path.exists():
                return str(unit_path)

        return None

    def _run_single_test(self, test_file: str) -> TestResult:
        """运行单个测试文件"""
        pytest_bin = shutil.which("pytest")
        if pytest_bin:
            cmd = [pytest_bin, test_file, "-v", "--tb=short"]
        else:
            cmd = [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"]

        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)
            result = subprocess.run(
                cmd, cwd=str(self.project_root),
                capture_output=True, text=True, timeout=120, env=env,
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
            return TestResult(failed=1, errors=1, error_detail="test timeout (120s)")
        except Exception as e:
            return TestResult(failed=1, errors=1, error_detail=str(e))

    def _run_pytest(self) -> TestResult:
        """运行全量 pytest"""
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
            return TestResult(failed=1, errors=1, error_detail="test timeout (300s)")
        except Exception as e:
            return TestResult(failed=1, errors=1, error_detail=str(e))

    # ------------------------------------------------------------------
    # compile check
    # ------------------------------------------------------------------

    def _full_compile_check(self, target_file: Optional[str] = None) -> TestResult:
        """全量 compile() 检查所有 src/*.py"""
        passed = 0
        failed = 0
        errors = []

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
                logger.warning(f"[Verifier] syntax error: {fpath}: {e}")
                failed += 1
                errors.append(f"{os.path.basename(fpath)}: line {e.lineno}: {e.msg}")

        return TestResult(
            passed=passed, failed=failed,
            error_detail="; ".join(errors[:5]) if errors else "",
        )

    # ------------------------------------------------------------------
    # import check — quick sanity
    # ------------------------------------------------------------------

    def verify_imports(self) -> TestResult:
        """验证关键模块可以正常 import"""
        modules = [
            "src.core", "src.llm",
            "src.evolution.engine", "src.evolution.executor",
            "src.evolution.verifier", "src.evolution.proposer",
            "src.evolution.models", "src.evolution.curator",
            "src.circuit_breaker",
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
    # pytest output parsing
    # ------------------------------------------------------------------

    _SHORT_SUMMARY = re.compile(
        r"(\d+)\s+passed[,;]?\s*(?:(\d+)\s+failed[,;]?\s*)?(?:(\d+)\s+errors?[,;]?\s*)?(?:(\d+)\s+skipped)?"
    )
    _TEST_RESULT_LINE = re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED)\s")

    def _parse_pytest_output(self, output: str) -> Tuple[int, int, int, int]:
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