"""
冷小北 CLI 入口
================
lx doctor   — 系统诊断
lx onboard  — 首次安装引导
lx daemon   — 启动后台守护进程
lx status   — 查看运行状态
lx version  — 版本信息
"""

import argparse
import os
import signal
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def cmd_doctor(args):
    """运行系统诊断"""
    from src.doctor import run_diagnostic
    ok = run_diagnostic(project_root=PROJECT_ROOT, quick=args.quick)
    sys.exit(0 if ok else 1)


def cmd_onboard(args):
    """首次安装引导"""
    print("\n🦞 冷小北 — 首次安装引导\n")

    checks = []

    # 1. Python
    v = sys.version_info
    ok = v >= (3, 10)
    checks.append(("Python 版本", ok, f"{v.major}.{v.minor}.{v.micro}"))
    print(f"  {'✅' if ok else '❌'} Python {v.major}.{v.minor}.{v.micro}")

    # 2. 依赖
    deps = {"yaml": "PyYAML", "httpx": "httpx", "psutil": "psutil", "flask": "Flask"}
    missing = []
    for mod, pkg in deps.items():
        try:
            __import__(mod)
            print(f"  ✅ {pkg}")
        except ImportError:
            print(f"  ❌ {pkg} — pip install {pkg}")
            missing.append(pkg)

    if missing:
        print(f"\n  缺少依赖，运行: pip install {' '.join(missing)}")
        install = input("\n  是否现在安装? [Y/n] ").strip().lower()
        if install != "n":
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
            print("  ✅ 依赖安装完成")

    # 3. 配置目录
    config_dir = os.path.join(PROJECT_ROOT, "config")
    if os.path.isdir(config_dir):
        print(f"  ✅ config/ 目录存在")
    else:
        print(f"  ⚠️  config/ 目录不存在，创建默认配置...")
        os.makedirs(config_dir, exist_ok=True)

    # 4. 记忆目录
    memory_dir = os.path.join(PROJECT_ROOT, "memory")
    os.makedirs(memory_dir, exist_ok=True)
    print(f"  ✅ memory/ 目录就绪")

    # 5. LLM API Key 引导
    print("\n  --- LLM 配置 ---")
    config_path = os.path.expanduser("~/.openclaw/openclaw.json")
    if os.path.exists(config_path):
        print(f"  ✅ 检测到 OpenClaw 配置: {config_path}")
        print(f"     冷小北会自动读取其中的 API Key")
    else:
        print(f"  ⚠️  未检测到 ~/.openclaw/openclaw.json")
        print(f"     冷小北需要至少一个 LLM provider 的 API Key")
        print(f"     支持的 provider: minimax, volcengine, bailian, anthropic")
        print(f"     配置方式: 在 ~/.openclaw/openclaw.json 中添加 provider")

    # 6. 运行诊断
    print("\n  --- 运行快速诊断 ---")
    from src.doctor import run_diagnostic
    run_diagnostic(project_root=PROJECT_ROOT, quick=True)

    print("\n🦞 安装引导完成！")
    print("  启动守护进程: lx daemon")
    print("  系统诊断:     lx doctor")
    print("")


def cmd_daemon(args):
    """启动后台守护进程"""
    from src.core import LengXiaobei

    print(f"\n{'='*50}")
    print("🦞 冷小北 · 守护进程")
    print(f"{'='*50}")

    running = True

    def on_signal(signum, frame):
        nonlocal running
        running = False
        print(f"\n收到信号 {signum}，准备退出...")

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    agent = LengXiaobei()
    agent.start()

    print(f"PID: {os.getpid()}")
    print(f"健康检查: http://localhost:8000/health")
    print("按 Ctrl+C 退出\n")

    try:
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        agent.stop()
        print("守护进程已退出")


def cmd_status(args):
    """查看运行状态"""
    try:
        import httpx
        resp = httpx.get("http://localhost:8000/health", timeout=5)
        if resp.status_code == 200:
            print("✅ 守护进程正在运行")
            print(resp.text)
        else:
            print(f"⚠️  健康检查返回 {resp.status_code}")
    except Exception:
        print("❌ 守护进程未运行 (无法连接 localhost:8000)")
        print("  启动: lx daemon")


def cmd_version(args):
    """版本信息"""
    print("冷小北 · Leng Xiaobei")
    print("版本: Phase 2.1")
    print("定位: 数字生命体 — 自演化 AI Agent")


def main():
    parser = argparse.ArgumentParser(
        prog="lx",
        description="冷小北 — 数字生命体 · 自演化 AI Agent",
    )
    sub = parser.add_subparsers(dest="command", help="可用命令")

    p = sub.add_parser("doctor", help="系统诊断")
    p.add_argument("--quick", action="store_true", help="快速模式")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("onboard", help="首次安装引导")
    p.set_defaults(func=cmd_onboard)

    p = sub.add_parser("daemon", help="启动守护进程")
    p.set_defaults(func=cmd_daemon)

    p = sub.add_parser("status", help="查看运行状态")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("version", help="版本信息")
    p.set_defaults(func=cmd_version)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()