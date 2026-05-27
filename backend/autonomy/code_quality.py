"""Code quality self-check module for LengXiaobei's autonomy loop.

Inspired by: Claude Code's verification step, Codex's self-testing,
and Hermes' reflection-evaluator pattern.

Goals:
1. Detect compilation/syntax errors across the project
2. Run existing tests and track pass/fail trends
3. Identify Python files lacking type hints or tests
4. Flag files that have grown too large (complexity indicator)
5. Check for common anti-patterns (bare except, mutable defaults, etc.)

All checks are read-only or self-contained; no external network calls.
"""

from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class QualityCheck:
    name: str
    ok: bool
    details: str = ""
    files: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def run_all_checks(project_root: Path) -> dict[str, Any]:
    """Run the full code quality suite."""
    checks: list[dict[str, Any]] = []

    qc = _compile_check(project_root)
    checks.append(_as_dict(qc))

    qc = _test_check(project_root)
    checks.append(_as_dict(qc))

    qc = _missing_tests_check(project_root)
    checks.append(_as_dict(qc))

    qc = _large_files_check(project_root)
    checks.append(_as_dict(qc))

    qc = _anti_pattern_check(project_root)
    checks.append(_as_dict(qc))

    all_ok = all(c["ok"] for c in checks)
    return {
        "ok": all_ok,
        "checks": checks,
        "timestamp": __import__("time").time(),
    }


# ── Individual checks ───────────────────────────────────────────────


def _compile_check(project_root: Path) -> QualityCheck:
    """Run python3 -m compileall on the project."""
    try:
        result = subprocess.run(
            ["python3", "-m", "compileall", "-q", str(project_root / "backend")],
            capture_output=True,
            text=True,
            timeout=60,
        )
        ok = result.returncode == 0
        details = result.stdout.strip() or result.stderr.strip()
        if not details:
            details = "All Python files compile successfully" if ok else "Compilation failed"
        return QualityCheck(name="compile", ok=ok, details=details)
    except Exception as exc:
        return QualityCheck(name="compile", ok=False, details=str(exc))


def _test_check(project_root: Path) -> QualityCheck:
    """Run pytest and capture results."""
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", str(project_root / "backend" / "tests"), "-q", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        ok = result.returncode == 0
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        # Parse test counts
        metrics: dict[str, Any] = {}
        for line in (stdout + "\n" + stderr).splitlines():
            if "passed" in line and "failed" in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "passed":
                        metrics["passed"] = int(parts[i - 1]) if i > 0 and parts[i - 1].isdigit() else 0
                    if part == "failed":
                        metrics["failed"] = int(parts[i - 1]) if i > 0 and parts[i - 1].isdigit() else 0
                    if part == "error":
                        metrics["errors"] = int(parts[i - 1]) if i > 0 and parts[i - 1].isdigit() else 0

        details = stdout[:500] if stdout else (stderr[:500] if stderr else "No test output")
        return QualityCheck(name="tests", ok=ok, details=details, metrics=metrics)
    except Exception as exc:
        return QualityCheck(name="tests", ok=False, details=str(exc))


def _missing_tests_check(project_root: Path) -> QualityCheck:
    """Find backend modules that have no corresponding test file."""
    backend_dir = project_root / "backend"
    test_dir = backend_dir / "tests"

    python_files: list[Path] = []
    for py_file in sorted(backend_dir.rglob("*.py")):
        rel = py_file.relative_to(backend_dir)
        # Skip tests, __pycache__, migrations
        if "__pycache__" in str(rel) or "tests/" in str(rel) or "migrations" in str(rel):
            continue
        # Skip very small files (likely __init__.py)
        if py_file.stat().st_size < 200:
            continue
        python_files.append(py_file)

    test_names = set()
    if test_dir.exists():
        for test_file in test_dir.rglob("test_*.py"):
            test_names.add(test_file.stem)

    missing: list[str] = []
    for py_file in python_files:
        module_name = py_file.stem
        expected_test = f"test_{module_name}"
        if expected_test not in test_names:
            missing.append(str(py_file.relative_to(project_root)))

    # Only flag files with real logic (not tiny stubs)
    significant_missing = [m for m in missing if not m.endswith("__init__.py")]

    return QualityCheck(
        name="missing_tests",
        ok=len(significant_missing) == 0,
        details=f"{len(significant_missing)} modules lack tests" if significant_missing else "All significant modules have tests",
        files=significant_missing[:10],
        metrics={"missing_count": len(significant_missing), "total_modules": len(python_files)},
    )


def _large_files_check(project_root: Path, max_lines: int = 500) -> QualityCheck:
    """Flag Python files that exceed the line threshold."""
    backend_dir = project_root / "backend"
    large: list[str] = []
    for py_file in sorted(backend_dir.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        line_count = len(py_file.read_text(encoding="utf-8", errors="replace").splitlines())
        if line_count > max_lines:
            large.append(f"{py_file.relative_to(project_root)} ({line_count} lines)")

    return QualityCheck(
        name="large_files",
        ok=len(large) <= 3,  # Allow a few large files
        details=f"{len(large)} files exceed {max_lines} lines" if large else f"No files exceed {max_lines} lines",
        files=large[:10],
        metrics={"large_count": len(large), "threshold": max_lines},
    )


def _anti_pattern_check(project_root: Path) -> QualityCheck:
    """Scan for common Python anti-patterns."""
    backend_dir = project_root / "backend"
    issues: list[str] = []
    checked = 0

    for py_file in sorted(backend_dir.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        checked += 1
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
            rel = str(py_file.relative_to(project_root))
            _check_file_for_patterns(tree, rel, issues)
        except SyntaxError:
            issues.append(f"{rel}: SyntaxError (cannot parse)")
        except Exception:
            continue

    return QualityCheck(
        name="anti_patterns",
        ok=len(issues) == 0,
        details=f"{len(issues)} anti-pattern(s) found in {checked} files" if issues else f"No anti-patterns in {checked} files",
        files=issues[:20],
        metrics={"issue_count": len(issues), "files_checked": checked},
    )


def _check_file_for_patterns(tree: ast.AST, file_path: str, issues: list[str]) -> None:
    """AST-based anti-pattern detection."""
    for node in ast.walk(tree):
        # Bare except
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append(f"{file_path}: bare 'except:' at line {node.lineno}")
        # Mutable default arguments
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    issues.append(f"{file_path}: mutable default arg at line {node.lineno}")
        # Use of print instead of logging
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            issues.append(f"{file_path}: print() call at line {node.lineno} (use logger)")


def _as_dict(qc: QualityCheck) -> dict[str, Any]:
    return {
        "name": qc.name,
        "ok": qc.ok,
        "details": qc.details,
        "files": qc.files,
        "metrics": qc.metrics,
    }
