"""
冷小北核心模块入口
python3 -m src.core 将启动核心守护进程
"""

import sys
import os
import time
import signal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import LengXiaobei


def main():
    print(f"\n{'='*50}")
    print("🦞 冷小北 · 核心守护进程")
    print(f"{'='*50}")

    running = True

    def on_signal(signum, frame):
        nonlocal running
        print(f"\n收到信号 {signum}，准备退出...")
        running = False

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    agent = LengXiaobei()
    agent.start()

    print("核心守护进程已启动，等待信号...")
    print("按 Ctrl+C 退出\n")

    try:
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        agent.stop()
        print("核心守护进程已退出")


if __name__ == "__main__":
    main()