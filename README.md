# lengxiaobei - 数字生命体

> 数字生命体 — 自演化 AI Agent

## 项目结构

```
lengxiaobei/
├── src/                      # 核心源代码 (唯一源码入口)
│   ├── core.py               # 编排器 (四 Facade 懒加载)
│   ├── facade_memory.py      # 记忆 Facade
│   ├── facade_reasoning.py   # 推理 Facade
│   ├── facade_evolution.py   # 进化 Facade
│   ├── facade_guardian.py    # 守护 Facade
│   ├── autonomous_evolution.py  # 重导出模块 → 实际实现在 evolution/
│   ├── evolution/            # 进化子包
│   │   ├── models.py         #   数据模型 (77行)
│   │   ├── config.py         #   配置 & LLM 助手 (101行)
│   │   ├── preparation.py    #   输入验证 & 提示构建 (261行)
│   │   ├── execution.py      #   执行引擎 & 沙箱 (243行)
│   │   └── engine.py         #   主编排器 (2094行)
│   ├── constitution.py       # 宪法系统 (原则与合规检查)
│   ├── evolution_permission.py  # 进化权限 (白名单 + 签名校验 + 人工审批)
│   ├── circuit_breaker.py    # 熔断保护 (连续失败/资源超限暂停)
│   ├── query_engine.py       # 查询引擎 V2
│   ├── hybrid_memory.py      # 混合记忆 (SQLite + 向量)
│   ├── memory.py             # 基础记忆
│   ├── llm.py                # LLM 路由
│   ├── config.py             # 配置管理
│   ├── config_manager.py     # 多源配置管理
│   ├── kairos.py             # KAIROS 后台守护
│   ├── auto_dream.py         # AutoDream 夜间整理
│   ├── mcp/                  # MCP 协议子包
│   └── ...
│
├── models/                   # 数据模型 (enums, budget, state, etc.)
├── prompts/                  # 角色与行为 MD (CRITIC.md, KAIROS.md, BUDDY.md, TEAM.md)
├── memory/                   # 记忆持久化数据
├── config/                   # 配置文件 (YAML/JSON)
├── docs/                     # 设计文档
├── tests/                    # 测试 (unit/integration/regression)
│   └── unit/
│       ├── test_constitution.py
│       ├── test_circuit_breaker.py
│       └── test_evolution_permission.py
├── scripts/                  # 运维脚本
│   ├── quick_approve.py
│   ├── reset_circuit_breaker.py
│   └── run_evolution.py
├── control_layer/            # Rust 控制层 (进程守护 + HTTP 状态)
├── config.json               # 运行时配置文件
└── requirements.txt          # Python 依赖
```

## 架构概览

```
LengXiaobei (编排器)
├── MemoryFacade     ← 记忆: hybrid_memory, knowledge_curator, auto_dream
├── ReasoningFacade  ← 推理: query_engine, tool_registry, tool_builder, skills, model_router
├── EvolutionFacade  ← 进化: autonomous_evolution, constitution, learner, critic, tester
└── GuardianFacade   ← 守护: kairos, circuit_breaker, health_check, permission, budget
```

### 安全链

| 层级 | 作用 |
|------|------|
| 宪法 (constitution) | 原则与合规检查 |
| 进化权限 (evolution_permission) | 目录白名单、签名校验、人工审批 |
| 熔断 (circuit_breaker) | 连续失败 / 资源超限暂停进化 |

## 快速开始

### 环境要求

- Python 3.8+
- Rust 1.70+ (控制层可选)

### 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 环境配置 (可选)

为了获得更好的模型下载体验并避免警告，建议配置 Hugging Face Token。

1.  访问 [Hugging Face Tokens 页面](https://huggingface.co/settings/tokens) 创建一个 Token。
2.  在您的 `~/.bashrc`, `~/.zshrc` 或其他 shell 配置文件中设置环境变量:

    ```bash
    export HF_TOKEN=your-huggingface-token-here
    ```



### 启动方式

```bash
# 手动模式
python3 -m src.core

# 守护进程模式
python3 daemon.py

# 启动脚本
./start.sh
```

## 配置

编辑 `config.json`:

```json
{
  "llm": {
    "model": "MiniMax-M2.7",
    "api_key": "your-api-key"
  },
  "memory_dir": "./memory",
  "autonomy_level": 80,
  "log_level": "INFO"
}
```

支持环境变量 `LENGXIAOBEI_ROOT` 指定项目根目录。

## 测试

```bash
pytest tests/unit/        # 单元测试 (宪法、熔断、权限、进化)
pytest tests/integration/ # 集成测试
pytest tests/             # 全部测试
```

## 核心功能

- **自主进化**: 代码自主优化，宪法约束 + 权限审批 + 熔断保护
- **记忆系统**: SQLite + FAISS 向量数据库，四层记忆架构
- **KAIROS 守护**: 后台常驻代理，定期状态评估与主动任务
- **AutoDream**: 夜间记忆整理与知识点提取
- **QueryEngine V2**: 会话、工具、权限、用量管理
- **MCP 协议**: Model Context Protocol 集成

## 文档

- [设计文档](docs/DESIGN.md)
- [代理规范](docs/AGENTS.md)
- [宪法](docs/CONSTITUTION.md)
- [灵魂](docs/SOUL.md)
- [记忆](docs/MEMORY.md)

## 项目理念

**克制、诚实、简洁。宪法为本，代码为用。**

## 状态

- Phase: 2 (KAIROS 守护模式)
- 自主度：80%

---

**冷小北 · 2026**