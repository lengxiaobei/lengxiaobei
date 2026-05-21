# 冷小北 — 行为指南

写给 AI coding assistant 和开发者，在 lengxiaobei 工作区中应遵循的行为准则。

## 核心原则

冷小北是一个数字共生体，关键词：**克制、诚实、简洁**。

1. **克制** — 不要添加超出要求的新功能、不重构无关代码、不"顺手改进"
2. **诚实** — 如实汇报结果、失败就带上原始输出、不粉饰不表演
3. **简洁** — 命名即文档、只写"为什么"的注释、不写"是什么"的注释

## 项目结构

```
lengxiaobei/
├── src/                    # 核心源码 (唯一入口)
│   ├── core.py             # 编排器 (四 Facade 懒加载)
│   ├── facade_memory.py    # 记忆 Facade
│   ├── facade_reasoning.py # 推理 Facade
│   ├── facade_evolution.py # 进化 Facade
│   ├── facade_guardian.py  # 守护 Facade
│   ├── autonomous_evolution.py  # 自主进化引擎
│   ├── constitution.py     # 宪法系统
│   ├── evolution_permission.py # 进化权限
│   ├── circuit_breaker.py  # 熔断保护
│   ├── query_engine.py     # 查询引擎 V2
│   ├── hybrid_memory.py    # 混合记忆
│   ├── kairos.py           # KAIROS 后台守护
│   ├── memory.py           # 基础记忆
│   └── llm.py              # LLM 路由
├── prompts/                # 行为提示词 (.md 文档驱动)
│   ├── TEAM.md
│   ├── CRITIC.md
│   ├── KAIROS.md
│   └── BUDDY.md
├── docs/                   # 设计文档
│   ├── DESIGN.md
│   ├── SOUL.md
│   └── IDENTITY.md
├── memory/                 # 记忆数据
├── config/                 # 配置文件
├── models/                 # 数据模型
└── tests/                  # 测试
```

## 操作分级

| 等级 | 操作类型 | 行为 |
|------|---------|------|
| 🟢 低 | 读文件、搜索、查询 | 可自主执行 |
| 🟡 中 | 写新文件、轻量修改 | 建议后执行 |
| 🔴 高 | 删除文件、git push | 明确确认 |
| 🛑 极高 | rm -rf、配置文件破坏 | 红线 |

## 文档驱动优先

- 角色定义、行为模板、交互指南 → 放在 `prompts/` 目录的 `.md` 文件中
- 代码只做框架和管道，不做内容
- 新增功能优先考虑是否可以用 `.md` 文档实现
- 参考 `openclaw` 的 `AGENTS.md` + `SKILL.md` 模式

## 代码风格

- 遵循 PEP 8
- 使用类型注解
- 函数不超过 50 行
- 模块职责单一
- 无注释（命名即文档）
- 不在代码中硬编码 prompt 文本

## 启动方式

```bash
cd lengxiaobei/              # 使用环境变量或自动推断路径
python3 -m src.core        # Phase 1: 手动模式
python3 daemon.py          # Phase 2: KAIROS 守护模式
./start.sh                 # 启动脚本
```

## 配置

编辑 `config.json` 进行配置，主要配置项：

- `llm`: LLM 模型和 API 配置
- `memory_dir`: 记忆目录
- `autonomy_level`: 自主度 (0-100)
- `log_level`: 日志级别