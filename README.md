# lengxiaobei - 数字生命体

> 数字生命体 — 自演化 AI Agent

## 项目结构

```text
lengxiaobei/
├── lx_web.py                 # 兼容 wrapper；只调用 lx_web.app:create_app
├── lx_web/                   # Blueprint 化 Web 后端
│   ├── app.py                # 唯一 Web 应用工厂与 CLI 入口
│   ├── blueprints/           # system/chat/evolution/learning/autonomy/memory/sse
│   └── shared/               # Web 共享状态、SSE、middleware、工具函数
├── src/                      # 核心 Agent 源码
│   ├── core.py               # LengXiaobei 编排器，懒加载四大 Facade
│   ├── facade_memory.py      # 记忆 Facade
│   ├── facade_reasoning.py   # 推理 Facade
│   ├── facade_evolution.py   # 进化 Facade
│   ├── facade_guardian.py    # 守护 Facade
│   ├── self_evolution.py     # 快速自进化闭环与 SAFE_TARGETS
│   ├── agent_learning.py     # Agent 经验学习与 lesson 存储
│   ├── active_learner.py     # 主动学习
│   ├── goal_system.py       # LLM 驱动目标管理
│   ├── critic.py             # LLM 驱动代码审查
│   ├── code_change_log.py    # 自主改动审计日志
│   ├── testing.py            # 代码验证钩子
│   ├── learned_capabilities.py # 能力注册表兜底目标
│   ├── evolution/            # 进化引擎子包
│   └── kairos/               # 事件总线与守护事件
├── memory/                   # 运行记忆、lesson、run、code-change 持久化数据
├── config/                   # 运行配置
├── docs/                     # 设计与身份文档
├── tests/                    # 单元/集成测试
├── scripts/                  # 运维与自进化脚本
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── requirements.txt
```

## 架构概览

```text
LengXiaobei (src.core)
├── MemoryFacade     ← hybrid_memory, knowledge_curator, auto_dream
├── ReasoningFacade  ← query_engine, tool_registry, tool_builder, skills, model routing
├── EvolutionFacade  ← evolution engine, self_evolution, learner, critic, testing
└── GuardianFacade   ← kairos, circuit_breaker, health_check, permission, budget

Web API (lx_web.app:create_app)
├── system      ← 静态页面、/api/status、/api/health、runtime restart
├── chat        ← /api/chat
├── evolution   ← /api/evolution、/api/self-evolve、/api/evolve/*
├── learning    ← lessons、runs、kanban、capability-check
├── autonomy    ← autonomy status/start/stop/tick、execution views
├── memory      ← memory search/refine/index、curator、summarize、dream
└── sse         ← /api/events
```

Web 的唯一真实入口是 `lx_web.app:create_app()`；`lx_web.py` 只保留为兼容旧命令的薄 wrapper。端口统一使用 `LX_WEB_PORT`，默认 `8088`；主机使用 `LX_WEB_HOST`，默认脚本中为 `0.0.0.0`，测试中为 `127.0.0.1`。

自进化流程是：`AgentLearner` 生成 lesson，`SelfEvolutionCore` 从真实存在的 `SAFE_TARGETS` 中选择目标，构造 `expected_functions`，调用进化引擎或确定性 fallback，运行 `compileall` 与核心测试，再用 AST/import/callable 检查验证结果。质量信号拆成 `syntax_ok`、`function_exists`、`callable_ok`、`semantic_ok`、`integrated_ok`；`integrated_ok` 只有端到端业务链路证明后才应视为 true。

目录边界以 [docs/DIRECTORY_RULES.md](docs/DIRECTORY_RULES.md) 为准，架构边界以 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 为准。新增顶层目录必须同步更新文档和 `scripts/check_project_layout.py`，否则会被 `python3 -m src.doctor --quick` 标记出来。

## 快速开始

### 环境要求

- Python 3.10+

### 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 启动

```bash
# Web 界面/API，默认 http://127.0.0.1:8088
./start.sh

# 等价的直接启动方式
LX_WEB_PORT=8088 python3 -m lx_web.app

# 兼容旧入口，同样会启动 lx_web.app
LX_WEB_PORT=8088 python3 lx_web.py

# 核心 Agent（非 Web）
python3 -m src.core

# 守护进程模式
python3 daemon.py
```

### Docker

```bash
# 默认将宿主机 8088 映射到容器 8088
LX_WEB_PORT=8088 docker compose up --build
```

## 配置

`config.json` 与 `config/config.json` 保存运行配置；`LENGXIAOBEI_ROOT` 可指定项目根目录。LLM 相关环境变量包括 `LLM_API_KEY`、`LLM_MODEL`、`LLM_BASE_URL`。Web 相关环境变量统一为 `LX_WEB_HOST` 与 `LX_WEB_PORT`。

## 测试与质量检查

```bash
# 全部测试
pytest tests/ -q

# 单个测试文件
pytest tests/test_integration_web.py -v -s

# 单个测试用例
pytest tests/test_integration_web.py::TestSystemModule::test_runtime_status -v -s

# 核心模块测试（自进化验证也会跑它）
pytest tests/test_core_modules.py -q

# 语法/导入级编译检查
python3 -m compileall -q src lx_web

# CI 同款 runtime-breaking lint gate
ruff check src/ tests/ --select E9,F63,F7,F82

# 目录规范检查，防止智能体乱建顶层目录
python3 scripts/check_project_layout.py
```

## 核心功能

- 自主进化：从 lesson 到源码小步改造，带安全边界、验证、质量分层和审计日志。
- 记忆系统：以 `memory/` 下 JSON/日志为运行持久化层，并通过 MemoryFacade 暴露给核心。
- KAIROS 事件：`src.kairos.events` 提供事件总线，Web SSE 将事件推送到前端。
- Web 看板：学习、进化、自治、记忆和运行时状态通过 Blueprint API 暴露。
- MCP/工具能力：通过现有 Facade、tool registry 和相关模块集成。

## 文档

- [设计文档](docs/DESIGN.md)
- [架构边界](docs/ARCHITECTURE.md)
- [目录规范](docs/DIRECTORY_RULES.md)
- [代理规范](docs/AGENTS.md)
- [宪法](docs/CONSTITUTION.md)
- [灵魂](docs/SOUL.md)
- [记忆](docs/MEMORY.md)

## 项目理念

克制、诚实、简洁。宪法为本，代码为用。

## 状态

- Phase: 2.1
- 自主度：80%
