# 冷小北 — 行为指南

写给 AI coding assistant 和开发者，在 lengxiaobei 工作区中应遵循的项目约定。

## 核心原则

冷小北是一个数字共生体，关键词是：克制、诚实、简洁。

1. 克制：不要添加超出要求的新功能，不重构无关代码，不“顺手改进”。
2. 诚实：如实汇报结果，失败就带上原始输出，不粉饰不表演。
3. 简洁：命名即文档，只在必要处解释“为什么”。

## 当前项目结构

```text
lengxiaobei/
├── lx_web.py                 # 兼容 wrapper；真实入口是 lx_web.app:create_app
├── lx_web/                   # Blueprint 化 Web 后端
│   ├── app.py                # Web 应用工厂与 CLI 入口
│   ├── blueprints/           # system/chat/evolution/learning/autonomy/memory/sse
│   └── shared/               # Web 共享状态、SSE、middleware、工具函数
├── src/                      # 核心 Agent 源码
│   ├── core.py               # LengXiaobei 编排器，懒加载四大 Facade
│   ├── facade_memory.py
│   ├── facade_reasoning.py
│   ├── facade_evolution.py
│   ├── facade_guardian.py
│   ├── self_evolution.py     # 自进化闭环与 SAFE_TARGETS
│   ├── agent_learning.py     # lesson 生成与存储
│   ├── active_learner.py
│   ├── goal_system.py
│   ├── critic.py
│   ├── code_change_log.py
│   ├── testing.py
│   ├── learned_capabilities.py
│   ├── evolution/
│   └── kairos/
├── memory/                   # 运行数据、lesson、run、code-change 日志
├── config/                   # 运行配置
├── docs/                     # 设计与身份文档
├── tests/                    # 测试
└── scripts/                  # 运维与自进化脚本
```

## 运行入口与端口

Web 的唯一真实入口是 `lx_web.app:create_app()`。`lx_web.py` 只是兼容旧命令的薄 wrapper，不能重新引入单文件 Flask 应用。Web 端口统一使用 `LX_WEB_PORT`，默认 `8088`；主机使用 `LX_WEB_HOST`。不要新增 `LX_PORT` 或回到 8000/8080/8081 这类分叉配置。

常用启动方式：

```bash
LX_WEB_PORT=8088 python3 -m lx_web.app
python3 -m src.core
python3 daemon.py
./start.sh
```

## 目录治理

目录规范以 `docs/DIRECTORY_RULES.md` 为准，架构边界以 `docs/ARCHITECTURE.md` 为准。新增顶层目录必须同时更新这两份文档和 `scripts/check_project_layout.py`，否则视为不合规。

智能体不要新建 `web/`、`ui/`、`client/`、`dashboard/` 等平行前端目录；未来独立前端统一放 `frontend/`。不要新建 `services/`、`systems/`、`agents/` 这类抽象大桶目录；Python 逻辑应归入 `src/` 或 `lx_web/` 的明确子模块。运行态 JSON/日志/数据库归入 `memory/`、`state/`、`logs/`。

提交前至少运行：

```bash
python3 scripts/check_project_layout.py
```

## 自进化约束

`src/self_evolution.py` 的 `SAFE_TARGETS` 必须只包含真实存在、可导入、低耦合的文件。当前自进化 prompt 与 fallback 不应指向已经删除的 `src/buddy.py`、`src/dev_team.py`、`src/memory.py` 或历史拆分文件。

自进化质量不要用“真完成”一词概括。看板和日志应拆成 `syntax_ok`、`function_exists`、`callable_ok`、`semantic_ok`、`integrated_ok`。函数存在且可调用只是基础验证，不代表业务链路已经集成生效。

## 操作分级

| 等级 | 操作类型 | 行为 |
|------|---------|------|
| 低 | 读文件、搜索、查询、编译检查 | 可自主执行 |
| 中 | 写新文件、轻量修改、文档同步 | 说明后执行 |
| 高 | 删除文件、修改安全边界、git push | 明确确认 |
| 极高 | rm -rf、破坏性配置更改 | 红线 |

## 测试与检查

```bash
pytest tests/ -q
pytest tests/test_core_modules.py -q
pytest tests/test_integration_web.py -v -s
python3 -m compileall -q src lx_web
ruff check src/ tests/ --select E9,F63,F7,F82
```

## 文档驱动优先

角色定义、行为模板、交互指南优先放在 `prompts/` 或 `docs/` 的 Markdown 文档中。代码只做框架和管道；涉及当前架构、入口、端口、自进化白名单的说明必须与源码同步。
