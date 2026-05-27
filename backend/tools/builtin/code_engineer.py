"""Code engineering tools and workflow engine.

参考来源：Claude Code / Codex / Aider 的工作方式：
1. 读代码理解上下文
2. 规划修改
3. 精确编辑（非全文覆盖）
4. 运行验证（编译/测试）
5. 失败时分析并修复

植入目标：让 lengxiaobei 拥有自我修改源码的能力，不依赖外部 Claude API。
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend.config import get_settings
from backend.tools.builtin import filesystem


# ── Low-level code tools ────────────────────────────────────────────

def search_files(pattern: str, path: str = ".", root: Path | None = None) -> dict[str, Any]:
    """Search for a pattern in project files using ripgrep or grep.

    Returns matching lines with file paths and line numbers.
    """
    target_root = root or Path(".")
    target = filesystem._resolve_project_path(path, target_root)

    # Try ripgrep first, fall back to grep
    for cmd_name in ["rg", "grep"]:
        cmd_path = _which(cmd_name)
        if cmd_path:
            break
    else:
        return {"error": "no search tool found (rg or grep)", "matches": []}

    if cmd_name == "rg":
        cmd = [
            str(cmd_path), "-n", "--with-filename", "--color=never", "--max-count", "50",
            "-g", "!*.lock", "-g", "!node_modules", "-g", "!__pycache__",
            pattern, str(target),
        ]
    else:
        cmd = [
            str(cmd_path), "-rn", "--color=never", "--max-count=50",
            "--exclude-dir=node_modules", "--exclude-dir=__pycache__",
            "--exclude-dir=.git", "--exclude=*.lock",
            pattern, str(target),
        ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        matches = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            # Parse "path:line:text" or "path-line-text" (rg format)
            parts = line.split(":", 2)
            if len(parts) >= 3:
                file_path, lineno, text = parts[0], parts[1], parts[2]
                matches.append({"file": file_path, "line": int(lineno) if lineno.isdigit() else 0, "text": text})
        return {"pattern": pattern, "matches": matches, "total": len(matches)}
    except subprocess.TimeoutExpired:
        return {"error": "search timeout", "matches": []}
    except Exception as exc:
        return {"error": str(exc), "matches": []}


def _which(cmd: str) -> Path | None:
    """Find command in PATH."""
    try:
        result = subprocess.run(["which", cmd], capture_output=True, text=True)
        path = result.stdout.strip()
        return Path(path) if path else None
    except Exception:
        return None


# ── CodeEngineer workflow ───────────────────────────────────────────

@dataclass
class CodeTask:
    """A code modification task."""

    description: str
    target_files: list[str] = field(default_factory=list)
    max_iterations: int = 3


@dataclass
class CodeStep:
    """One step in the code engineering plan."""

    action: str  # "read" | "edit" | "write" | "run" | "verify"
    file: str = ""
    old_string: str = ""
    new_string: str = ""
    command: list[str] = field(default_factory=list)
    reason: str = ""


class CodeEngineer:
    """Software engineering agent inspired by Claude Code / Codex.

    Workflow:
        1. Analyze task with LLM -> generate plan
        2. Execute plan step by step
        3. Run verification (compile / test / lint)
        4. If verification fails, analyze error and retry
        5. Repeat up to max_iterations
    """

    def __init__(
        self,
        project_root: Path,
        llm_chat: Callable[..., Any],
        dispatcher: Any | None = None,
    ):
        self.project_root = Path(project_root)
        self.llm_chat = llm_chat
        self.dispatcher = dispatcher

    def execute(self, task: CodeTask) -> dict[str, Any]:
        """Execute a code modification task end-to-end."""
        iterations = []
        current_description = task.description

        for i in range(task.max_iterations):
            # Step 1: Plan
            plan = self._plan(current_description, task.target_files)

            # Step 2: Execute plan
            execution_log = self._execute_plan(plan)

            # Step 3: Verify
            verification = self._verify()

            iteration = {
                "iteration": i + 1,
                "plan": [self._step_to_dict(s) for s in plan],
                "execution": execution_log,
                "verification": verification,
            }
            iterations.append(iteration)

            if verification.get("ok"):
                return {
                    "ok": True,
                    "iterations": iterations,
                    "summary": f"Task completed in {i + 1} iteration(s)",
                }

            # Prepare for retry with error context
            current_description = self._build_retry_prompt(
                task.description, execution_log, verification
            )

        return {
            "ok": False,
            "iterations": iterations,
            "summary": f"Task failed after {task.max_iterations} iterations",
        }

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def _plan(self, description: str, target_files: list[str]) -> list[CodeStep]:
        """Use LLM to generate an execution plan."""
        context = self._gather_context(description, target_files)
        prompt = self._planning_prompt(description, context)

        try:
            response = self.llm_chat(prompt)
        except Exception as exc:
            # Fallback: basic plan for simple edits
            return self._fallback_plan(description, target_files)

        return self._parse_plan(response)

    def _gather_context(self, description: str, target_files: list[str]) -> str:
        """Read relevant files to provide context for planning."""
        chunks = []
        for pattern in target_files[:5]:
            try:
                text = filesystem.read_text(pattern, self.project_root, limit=6000)
                chunks.append(f"--- {pattern} ---\n{text[:3000]}\n")
            except Exception:
                continue
        if not chunks:
            # Try to find relevant files via search
            search = search_files(description[:30], root=self.project_root)
            for match in (search.get("matches") or [])[:3]:
                file_path = match.get("file", "")
                if file_path:
                    try:
                        rel = str(Path(file_path).relative_to(self.project_root.resolve()))
                        text = filesystem.read_text(rel, self.project_root, limit=4000)
                        chunks.append(f"--- {rel} ---\n{text[:2000]}\n")
                    except Exception:
                        continue
        return "\n".join(chunks) or "No target files provided."

    def _planning_prompt(self, description: str, context: str) -> str:
        return (
            "You are a software engineering agent. Analyze the task and generate a precise plan.\n\n"
            f"Task: {description}\n\n"
            f"Relevant code context:\n{context}\n\n"
            "Generate a plan as a JSON array of steps. Each step has:\n"
            '  {"action": "read|edit|write|run|verify", "file": "path", "old_string": "...", "new_string": "...", "command": ["cmd", "args"], "reason": "..."}\n\n'
            "Rules:\n"
            "- Use 'read' to examine files before editing\n"
            "- Use 'edit' with precise old_string/new_string for surgical changes\n"
            "- Use 'write' only for creating new files\n"
            "- Use 'run' for commands like ['python3', '-m', 'compileall', '.']\n"
            "- Use 'verify' for test commands\n"
            "- old_string must match exactly once in the file\n"
            'Output ONLY the JSON array, no markdown fences.'
        )

    def _parse_plan(self, response: str) -> list[CodeStep]:
        """Parse LLM response into a list of CodeSteps."""
        # Strip markdown fences if present
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.endswith("```"):
            text = text.rsplit("\n", 1)[0] if "\n" in text else ""
        text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON array from text
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    return []
            else:
                return []

        steps = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict):
                continue
            steps.append(CodeStep(
                action=item.get("action", ""),
                file=item.get("file", ""),
                old_string=item.get("old_string", ""),
                new_string=item.get("new_string", ""),
                command=item.get("command", []),
                reason=item.get("reason", ""),
            ))
        return steps

    def _fallback_plan(self, description: str, target_files: list[str]) -> list[CodeStep]:
        """Generate a minimal plan when LLM is unavailable."""
        steps = []
        for f in target_files:
            steps.append(CodeStep(action="read", file=f, reason="Examine target file"))
        steps.append(CodeStep(
            action="run",
            command=["python3", "-m", "compileall", "-q", "."],
            reason="Verify syntax",
        ))
        return steps

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _execute_plan(self, plan: list[CodeStep]) -> list[dict[str, Any]]:
        log = []
        for step in plan:
            result: dict[str, Any] = {"action": step.action, "ok": False}
            try:
                if step.action == "read":
                    content = filesystem.read_text(step.file, self.project_root, limit=12000)
                    result = {"action": "read", "file": step.file, "ok": True, "content_preview": content[:500]}
                elif step.action == "edit":
                    result = filesystem.edit_text(step.file, step.old_string, step.new_string, self.project_root)
                    result["action"] = "edit"
                    result["file"] = step.file
                    result["ok"] = True
                elif step.action == "write":
                    result = filesystem.write_text(step.file, step.new_string, self.project_root)
                    result["action"] = "write"
                    result["ok"] = True
                elif step.action == "run":
                    result = self._run_command(step.command)
                    result["action"] = "run"
                elif step.action == "verify":
                    result = self._run_command(step.command)
                    result["action"] = "verify"
                else:
                    result = {"action": step.action, "ok": False, "error": f"unknown action: {step.action}"}
            except Exception as exc:
                result = {"action": step.action, "ok": False, "error": str(exc)}
            log.append(result)
        return log

    def _run_command(self, command: list[str]) -> dict[str, Any]:
        """Run a shell command inside the project root."""
        if not command:
            return {"ok": False, "error": "empty command"}
        try:
            result = subprocess.run(
                command,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return {
                "ok": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:2000],
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "command timeout"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def _verify(self) -> dict[str, Any]:
        """Run standard verification: Python compile check, then project-specific check."""
        # Check 1: Python syntax
        compile_result = self._run_command(["python3", "-m", "compileall", "-q", "."])
        if not compile_result["ok"]:
            return {"ok": False, "stage": "compile", **compile_result}

        # Check 2: Try to run tests if pytest exists
        test_result = self._run_command(["python3", "-m", "pytest", "backend/tests/", "-q", "--tb=short"])
        # pytest may return non-zero if no tests, that's OK
        if "error" in test_result and "No module named" in test_result.get("error", ""):
            return {"ok": True, "stage": "compile_only", "compile": compile_result}

        return {"ok": test_result["ok"], "stage": "tests", "compile": compile_result, "tests": test_result}

    def _build_retry_prompt(self, original: str, execution_log: list[dict[str, Any]], verification: dict[str, Any]) -> str:
        """Build a prompt for retrying with error context."""
        errors = [item for item in execution_log if not item.get("ok")]
        error_text = "\n".join(f"- {e.get('action')}: {e.get('error', 'unknown')}" for e in errors)
        if not error_text:
            error_text = verification.get("stderr", "") or verification.get("error", "verification failed")
        return (
            f"Original task: {original}\n\n"
            f"Previous attempt failed with:\n{error_text}\n\n"
            "Please generate a corrected plan."
        )

    def _step_to_dict(self, step: CodeStep) -> dict[str, Any]:
        return {
            "action": step.action,
            "file": step.file,
            "old_string": step.old_string,
            "new_string": step.new_string,
            "command": step.command,
            "reason": step.reason,
        }
