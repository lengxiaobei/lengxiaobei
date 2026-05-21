# 自进化 MVP 本地运行

这条路径只做一件事：学习其他 Agent 的长处，然后尝试把 lesson 转成一次小步源码改进。

## 运行

```bash
python3 scripts/lx_self_evolve.py "学习 Claude Code 的任务规划能力"
```

带参考 URL：

```bash
python3 scripts/lx_self_evolve.py "学习 OpenHands 的工具执行循环" --url https://github.com/All-Hands-AI/OpenHands
```

应用下一条未处理 lesson：

```bash
python3 scripts/lx_self_evolve.py --apply-pending
```

## 输出文件

- `memory/agent_lessons.json`: 学到的 Agent 能力
- `memory/self_evolution_runs.json`: 每次自进化运行记录

## 最小边界

- 禁止自主修改 `SOUL.md` / `CONSTITUTION.md`
- 修改 `src/core.py`、执行器、权限、进化引擎等核心文件时会阻断
- 每次改源码后会运行 `compileall` 和 `tests/test_core_modules.py`
- 测试失败时复用现有进化引擎回滚机制
