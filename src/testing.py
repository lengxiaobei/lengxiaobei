import ast
import sys
import subprocess
import tempfile
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum


class TestStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TestResult:
    name: str
    status: TestStatus
    output: str = ""
    error: str = ""


class CodeTester:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.test_timeout = 30

    def test_code(self, file_path: str, code: str) -> List[TestResult]:
        results: List[TestResult] = []
        results.append(self._test_syntax(code))
        results.append(self._test_import(file_path, code))
        return results

    def _test_syntax(self, code: str) -> TestResult:
        try:
            ast.parse(code)
            return TestResult(name="syntax", status=TestStatus.PASSED)
        except SyntaxError as e:
            return TestResult(name="syntax", status=TestStatus.FAILED, error=str(e))

    def _test_import(self, file_path: str, code: str) -> TestResult:
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                tmp = f.name
            try:
                test_script = f"""
import importlib.util
spec = importlib.util.spec_from_file_location('test_mod', '{tmp}')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print('OK')
"""
                test_file = tmp.replace('.py', '_test.py')
                with open(test_file, 'w') as f:
                    f.write(test_script)
                proc = subprocess.run([sys.executable, test_file], capture_output=True, text=True,
                                      timeout=self.test_timeout, cwd=str(self.project_root))
                if proc.returncode == 0 and 'OK' in proc.stdout:
                    return TestResult(name="import", status=TestStatus.PASSED)
                return TestResult(name="import", status=TestStatus.FAILED, error=proc.stderr)
            finally:
                for f in [tmp, test_file]:
                    try:
                        os.unlink(f)
                    except OSError:
                        pass
        except Exception as e:
            return TestResult(name="import", status=TestStatus.FAILED, error=str(e))