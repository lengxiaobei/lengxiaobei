#!/usr/bin/env python3
"""Run the fast self-evolution MVP locally.

Examples:
  python3 scripts/lx_self_evolve.py "学习 Claude Code 的任务规划能力"
  python3 scripts/lx_self_evolve.py "学习 OpenHands 的工具执行循环" --url https://github.com/All-Hands-AI/OpenHands
  python3 scripts/lx_self_evolve.py --apply-pending
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core import LengXiaobei  # noqa: E402
from src.self_evolution import SelfEvolutionCore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="冷小北快速自进化 MVP")
    parser.add_argument("topic", nargs="?", help="学习/进化方向")
    parser.add_argument("--url", default="", help="可选参考 URL")
    parser.add_argument("--apply-pending", action="store_true", help="应用下一条 pending lesson")
    args = parser.parse_args()

    lxb = LengXiaobei(ROOT)
    core = SelfEvolutionCore(str(ROOT), lxb.evolution_facade.autonomous_evolution)

    if args.apply_pending:
        result = core.evolve_from_lessons()
    else:
        if not args.topic:
            parser.error("需要 topic，或使用 --apply-pending")
        result = core.self_evolve(args.topic, url=args.url)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in ("success", "verified") else 1


if __name__ == "__main__":
    raise SystemExit(main())
