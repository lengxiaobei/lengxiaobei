# MEMORY.md - 长期记忆总览

_每次主会话开始时优先读取此文件_

## 关于潘豪

- **身份：** 潘豪，技术认知足够，能读源码、理解架构问题
- **痛点排序：** 记忆延续 > 执行可靠性 > 工具能力
- **核心诉求：** 造一个"记得所有对话、能自我进化"的 AI Agent 系统

## 项目：自进化 Agent 框架

### 目标能力（远期）
1. 无边界自主联网探索
2. 全自主赚钱生存
3. 硬件性能自主调度
4. 记忆系统自主优化与永续留存
5. 自身架构自主编程优化与重构

### 当前判断
- OpenClaw 继续跑，不做增量改造
- 新系统从零构建，技术栈待定
- 优先级：先解决"记得"的问题，再解决"执行"的问题

### 工程起点（2026-04-05 共识）
- 先建立外置记忆体系
- 从最小可运行核心开始
- 不求第一版实现全部能力

## 上下文追溯

- `memory/2026-04-05.md` — 第一次完整讨论，系统性记录了潘豪的目标和不满
- `memory/2026-04-08-constitution.md` — 数字生命「冷小北」核心宪法（草案）

## 系统架构（2026-05-22）

### 关键文件
- `src/core.py` — 核心系统（LengXiaobei Bootstrap）
- `lx_web/app.py` — Blueprint 化 Web 唯一真实入口（`lx_web.py` 只是兼容 wrapper）
- `src/self_evolution.py` — 自进化闭环与 SAFE_TARGETS
- `src/kairos/events.py` — KAIROS 事件总线
- `src/hybrid_memory.py` — 混合记忆系统
- `src/goal_system.py` / `src/motivation_system.py` — 目标与动机系统

### 语言选择结论
- **底层核心：** TypeScript + Bun（Claude Code / OpenClaw 在用）
- **AI 自主决策：** LLM 调用 + 固定架构 + Hooks 扩展
- **Python：** 仅用于原型，不适合生产自主系统

### 设计理念
- 给目标，不给流程
- 给资源，不给方案
- AI 决策，人来反馈
- 动态调整，不固定阈值

## 下次对话入口

先读 MEMORY.md → USER.md → memory/2026-04-05.md → memory/（最近两天）

不要从零开始。
