"""
lx doctor — 冷小北系统诊断工具
================================
检查配置、依赖、记忆库、权限、熔断器、测试状态、MCP 可用性。

用法:
    python -m src.doctor          # 完整诊断
    python -m src.doctor --quick  # 快速检查
"""

import json
import os
import subprocess
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str = ""
    details: List[str] = field(default_factory=list)
    severity: str = "info"  # ok | warn | error


class Doctor:
    """系统诊断器"""

    def __init__(self, project_root: Optional[str] = None, quick: bool = False):
        if project_root is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.root = Path(project_root)
        self.quick = quick
        self.results: List[CheckResult] = []
        self.passed = 0
        self.warnings = 0
        self.errors = 0

    def check(self, name: str, condition: bool, message: str = "",
              details: List[str] = None, severity: str = "error") -> bool:
        passed = condition
        if not condition and severity == "error":
            self.errors += 1
        elif not condition and severity == "warn":
            self.warnings += 1
        else:
            self.passed += 1

        self.results.append(CheckResult(
            name=name, passed=passed, message=message,
            details=details or [], severity="ok" if passed else severity,
        ))
        return passed

    def run(self) -> bool:
        print(f"\n{'='*50}")
        print("冷小北 系统诊断 (lx doctor)")
        print(f"{'='*50}\n")

        self._check_python()
        self._check_dependencies()
        self._check_config()
        self._check_project_layout()
        self._check_api_keys()
        self._check_memory_db()
        self._check_permissions()
        self._check_circuit_breaker()

        if not self.quick:
            self._check_mcp()
            self._check_tests()
            self._check_directory_permissions()

        self._print_summary()
        return self.errors == 0

    # ---- Python 环境 ----

    def _check_python(self):
        v = sys.version_info
        ok = v >= (3, 10)
        self.check("Python 版本", ok,
                   f"Python {v.major}.{v.minor}.{v.micro}",
                   ["需要 Python 3.10+"] if not ok else [],
                   "error" if not ok else "ok")

    # ---- 依赖 ----

    def _check_dependencies(self):
        req_file = self.root / "requirements.txt"
        if not self.check("requirements.txt 存在", req_file.exists(),
                          "依赖声明文件", severity="warn"):
            return

        deps = {"pyyaml": "yaml", "httpx": "httpx", "faiss-cpu": "faiss",
                "sentence-transformers": "sentence_transformers",
                "psutil": "psutil"}
        # 只检查核心依赖
        core = ["yaml", "httpx", "psutil"]
        missing = []
        for mod_name in core:
            pkg = [k for k, v in deps.items() if v == mod_name][0]
            try:
                __import__(mod_name)
            except ImportError:
                missing.append(pkg)

        self.check("核心 Python 依赖", len(missing) == 0,
                   "全部就绪" if not missing else f"缺少: {', '.join(missing)}",
                   missing, "error" if missing else "ok")

    # ---- 配置 ----

    def _check_config(self):
        config_dir = self.root / "config"
        if not self.check("config/ 目录存在", config_dir.is_dir(),
                          severity="error"):
            return

        for env_file in ["default.yaml", "development.yaml"]:
            path = config_dir / env_file
            if path.exists():
                try:
                    import yaml
                    with open(path) as f:
                        data = yaml.safe_load(f)
                    keys = list(data.keys()) if data else []
                    self.check(f"config/{env_file} 可解析",
                               True, f"顶级键: {', '.join(keys[:5])}")
                except Exception as e:
                    self.check(f"config/{env_file} 解析", False,
                               f"解析失败: {e}", severity="error")
            else:
                self.check(f"config/{env_file}", False,
                           "文件不存在", severity="warn")

    # ---- 项目目录结构 ----

    def _check_project_layout(self):
        script = self.root / "scripts" / "check_project_layout.py"
        if not script.is_file():
            self.check("项目目录规范", False,
                       "scripts/check_project_layout.py 不存在", severity="warn")
            return

        try:
            proc = subprocess.run(
                [sys.executable, str(script), "--root", str(self.root)],
                cwd=str(self.root),
                text=True,
                capture_output=True,
                timeout=20,
            )
        except Exception as exc:
            self.check("项目目录规范", False, f"检查失败: {exc}", severity="warn")
            return

        output = (proc.stdout + proc.stderr).strip()
        details = output.splitlines()[:12] if output else []
        self.check(
            "项目目录规范",
            proc.returncode == 0,
            "通过" if proc.returncode == 0 else "存在不合规目录/构建产物",
            details,
            "error" if proc.returncode != 0 else "ok",
        )

    # ---- API Keys ----

    def _check_api_keys(self):
        try:
            from .llm import _PROVIDER_KEYS, MODELS
            providers_found = [name for name, key in _PROVIDER_KEYS.items() if key]
            providers_config = set(cfg["provider"] for cfg in MODELS.values())
            missing = providers_config - set(providers_found)

            self.check("LLM API Keys",
                       len(providers_found) > 0,
                       f"已配置: {', '.join(providers_found)}" if providers_found else "无 API Key",
                       [f"缺少 provider: {m}" for m in missing] if missing else [],
                       "warn" if not providers_found else "ok")
        except Exception as e:
            self.check("LLM 配置加载", False, str(e), severity="error")

        # 检查 SearXNG
        searxng_url = os.environ.get("SEARXNG_BASE_URL", "")
        searxng_key = os.environ.get("SEARXNG_API_KEY", "")
        has_search = bool(searxng_url and searxng_key)
        self.check("联网搜索 (SearXNG)", has_search,
                   "已配置" if has_search else "未配置 — 联网搜索不可用",
                   severity="warn" if not has_search else "ok")

    # ---- 记忆数据库 ----

    def _check_memory_db(self):
        db_path = self.root / "memory" / "memory.db"
        if not db_path.exists():
            self.check("记忆数据库", False,
                       f"{db_path} 不存在", severity="warn")
            return

        try:
            conn = sqlite3.connect(str(db_path))
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [t[0] for t in tables]

            count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            conn.close()

            self.check("记忆数据库",
                       len(table_names) > 0,
                       f"表: {', '.join(table_names)}, 记忆数: {count}",
                       severity="ok")
        except Exception as e:
            self.check("记忆数据库", False, f"无法读取: {e}", severity="error")

    # ---- 权限 ----

    def _check_permissions(self):
        try:
            from .permission import PermissionManager
            pm = PermissionManager()
            rules_count = sum(
                len(v) for v in pm.always_allow_rules.values()
            ) + sum(len(v) for v in pm.always_deny_rules.values())
            self.check("权限管理器",
                       True,
                       f"就绪, {rules_count} 条规则",
                       severity="ok")
        except Exception as e:
            self.check("权限管理器", False, str(e), severity="warn")

    # ---- 熔断器 ----

    def _check_circuit_breaker(self):
        try:
            from .hard_boundary import HardBoundary
            hb = HardBoundary()
            self.check("硬边界", True,
                       f"状态: 正常",
                       severity="ok")
        except Exception as e:
            self.check("硬边界", False, str(e), severity="warn")

    # ---- MCP ----

    def _check_mcp(self):
        mcp_config = self.root / ".trae" / "mcp-config.json"
        if not mcp_config.exists():
            self.check("MCP 配置", False,
                       ".trae/mcp-config.json 不存在", severity="warn")
            return

        try:
            with open(mcp_config) as f:
                data = json.load(f)
            methods = data.get("methods", []) if isinstance(data, dict) else []
            self.check("MCP 配置", True,
                       f"{len(methods)} 个方法: {', '.join(m.get('name', '?') for m in methods[:5])}",
                       severity="ok")
        except Exception as e:
            self.check("MCP 配置", False, str(e), severity="error")

    # ---- 测试 ----

    def _check_tests(self):
        test_dir = self.root / "tests"
        if not test_dir.is_dir():
            self.check("测试目录", False,
                       "tests/ 目录不存在", severity="warn")
            return

        test_files = list(test_dir.glob("test_*.py")) + list(test_dir.glob("*_test.py"))
        self.check("测试文件",
                   len(test_files) > 0,
                   f"{len(test_files)} 个测试文件",
                   severity="warn" if len(test_files) == 0 else "ok")

    # ---- 目录权限 ----

    def _check_directory_permissions(self):
        dirs = ["memory", "learning", "assessment", "logs"]
        for d in dirs:
            path = self.root / d
            if not path.exists():
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    self.check(f"目录 {d}/", True, "已自动创建", severity="ok")
                except Exception as e:
                    self.check(f"目录 {d}/", False, f"创建失败: {e}", severity="error")
            else:
                writable = os.access(str(path), os.W_OK)
                self.check(f"目录 {d}/ 可写", writable,
                           severity="error" if not writable else "ok")

    # ---- 输出 ----

    def _print_summary(self):
        print(f"\n{'─'*50}")
        icon = lambda s: "✅" if s == "ok" else ("⚠️" if s == "warn" else "❌")
        for r in self.results:
            print(f"  {icon(r.severity)} {r.name}: {r.message}")
            for d in r.details:
                print(f"     └─ {d}")

        total = len(self.results)
        print(f"\n{'='*50}")
        print(f"结果: {self.passed} 通过, {self.warnings} 警告, {self.errors} 错误")
        if self.errors == 0:
            print("系统状态: 健康 ✅")
        else:
            print(f"系统状态: 需要修复 ❌ ({self.errors} 项)")
        print(f"{'='*50}\n")


def run_diagnostic(project_root: str = None, quick: bool = False) -> bool:
    return Doctor(project_root, quick).run()


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="冷小北系统诊断")
    p.add_argument("--quick", action="store_true", help="快速模式")
    args = p.parse_args()
    ok = run_diagnostic(quick=args.quick)
    sys.exit(0 if ok else 1)
