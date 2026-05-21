# 冷小北 · Leng Xiaobei

数字生命体 — 自演化 AI Agent

## 架构

```
lengxiaobei/
├── src/
│   ├── core.py      # 核心引擎（Phase 1 主循环）
│   ├── memory.py    # 记忆系统（SQLite）
│   ├── learner.py   # 自主学习模块
│   ├── llm.py       # 模型路由
│   └── config.py    # 配置
├── memory/          # 记忆数据库
├── docs/
│   ├── DESIGN.md    # 设计原则
│   └── LEARN.md     # 学习记录
└── daemon.py        # Phase 2 KAIROS 守护进程
```

## Phase 1 vs Phase 2

### Phase 1 — 手动模式
手动启动，对话驱动。启动后等待用户输入，退出后保存记忆。

```bash
cd ~/projects/lengxiaobei
python3 -m src.core
```

**特点：**
- 主动式：需要潘豪发起对话
- 即时响应：每次输入立即处理
- 适合：实时交互、单次任务

### Phase 2 — KAIROS 守护模式
后台常驻代理，主动评估"anything worth doing right now?"

```bash
cd ~/projects/lengxiaobei
python3 daemon.py
```

**特点：**
- 被动触发：守护进程持续运行，定期评估状态
- 后台任务：可执行夜间整理、主动汇报等
- 夜间 autoDream：凌晨 3:30 自动整理当日学到的东西
- append-only 日志：不删除自己的历史

**KAIROS 心跳机制：**
- 每 60 秒评估一次当前状态
- 优雅退出（SIGTERM）：保存记忆后关闭
- 状态持久化：重启后恢复上下文

## autoDream 四阶段

每晚凌晨 3:30 自动执行：

1. **日志汇总** — 收集当天所有交互记录
2. **知识点提取** — 从日志提取有价值的信息点
3. **记忆重组** — 整合进长期记忆
4. **次日优先级** — 设定明日关注点

## 运行要求

- Python 3.8+
- 依赖：`pip install -r requirements.txt`
- 环境变量：`MINIMAX_API_KEY`（可选，用于 LLM 调用）

## 项目理念

克制、诚实、简洁。宪法为本，代码为用。
