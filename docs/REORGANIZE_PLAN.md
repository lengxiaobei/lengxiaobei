# lengxiaobei 项目目录整理方案

## 当前问题

### 1. 根目录混乱
- ❌ 测试文件散落各处 (24h_test.py, quick_test.py, test_*.py 等)
- ❌ 文档文件过多 (20+ 个 .md 文件在根目录)
- ❌ 备份文件直接放在根目录 (backups/)
- ❌ 构建产物在根目录 (build/)
- ❌ 虚拟环境在根目录 (venv/)

### 2. 备份文件过多
- ❌ backups/ 目录有多个大型 zip 文件
- ❌ memory/backups/ 有 20+ 个备份文件
- ❌ 配置文件备份散落

### 3. 缓存和临时文件
- ❌ src/__pycache__/ 占用空间
- ❌ build/ 目录有编译产物
- ❌ Rust target/ 目录很大

### 4. 日志文件分散
- ❌ logs/ 目录有大量日志
- ❌ memory/logs/ 也有日志
- ❌ 需要统一归档

### 5. 测试文件分散
- ❌ 根目录有测试文件
- ❌ test_scripts/ 目录
- ❌ tests/ 目录
- ❌ 需要整合

## 整理后的目录结构

```
lengxiaobei/
├── .claude/                      # Claude 配置
├── .trae/                        # Trae IDE 配置
├── .pytest_cache/                # pytest 缓存 (保留)
├── .gitignore                    # Git 忽略文件
├── README.md                     # 项目说明
├── requirements.txt              # Python 依赖
├── config.json                   # 主配置文件
├── start.sh                      # 启动脚本
├── daemon.py                     # 守护进程
│
├── src/                          # 源代码 (保持)
│   ├── __init__.py
│   ├── core.py                   # 核心引擎
│   ├── memory.py                 # 记忆系统
│   ├── llm.py                    # LLM 路由
│   ├── config.py                 # 配置管理
│   ├── config_optimized.py       # 优化配置
│   ├── error_handling.py         # 错误处理
│   ├── error_handling_optimized.py
│   ├── resource_manager.py       # 资源管理
│   ├── resource_manager_optimized.py
│   ├── mcp/                      # MCP 模块
│   ├── memory/                   # 记忆数据
│   └── config/                   # 配置文件
│
├── agents/                       # Agent 相关模块 (新建)
│   ├── autonomous_evolution.py   # 自主进化
│   ├── forked_agent.py           # 分身 Agent
│   ├── dev_team.py               # 开发团队
│   └── coordinator.py            # 协调器
│
├── services/                     # 服务层 (新建)
│   ├── memory_service.py         # 记忆服务
│   ├── llm_service.py            # LLM 服务
│   ├── tool_service.py           # 工具服务
│   └── bridge_service.py         # 桥接服务
│
├── systems/                      # 子系统 (新建)
│   ├── kairos.py                 # KAIROS 守护
│   ├── motivation_system.py      # 动机系统
│   ├── goal_system.py            # 目标系统
│   ├── self_assessment.py        # 自我评估
│   └── constitution.py           # 宪法系统
│
├── integrations/                 # 集成模块 (新建)
│   ├── integration.py            # 综合集成
│   ├── mcp.py                    # MCP 集成
│   ├── mcp_server.py             # MCP 服务器
│   └── remote_control.py.disabled
│
├── tools/                        # 工具模块 (新建)
│   ├── tool_registry.py          # 工具注册
│   ├── tool_builder.py           # 工具构建
│   ├── lsp.py                    # LSP 支持
│   ├── vim.py                    # Vim 模式
│   └── plugin.py                 # 插件系统
│
├── utils/                        # 工具函数 (新建)
│   ├── debug.py                  # 调试工具
│   ├── performance.py            # 性能分析
│   ├── health_check.py           # 健康检查
│   ├── monitoring.py             # 监控
│   ├── logging_config.py         # 日志配置
│   └── data_backup.py            # 数据备份
│
├── models/                       # 数据模型 (新建)
│   ├── state.py                  # 状态管理
│   ├── enums.py                  # 枚举定义
│   ├── json_schema.py            # JSON Schema
│   └── budget.py                 # 预算管理
│
├── memory_layer/                 # 记忆层 (Rust)
│   ├── src/
│   ├── Cargo.toml
│   └── target/
│
├── control_layer/                # 控制层 (Rust)
│   ├── src/
│   ├── Cargo.toml
│   └── target/
│
├── bridge/                       # 桥接模块 (统一)
│   ├── c/                        # C 实现
│   ├── rust/                     # Rust 实现
│   ├── ts/                       # TypeScript 实现
│   └── go/                       # Go 实现
│
├── tests/                        # 测试目录 (统一)
│   ├── unit/                     # 单元测试
│   ├── integration/              # 集成测试
│   ├── regression/               # 回归测试
│   └── fixtures/                 # 测试数据
│
├── scripts/                      # 脚本工具 (统一)
│   ├── run_evolution.py          # 运行进化
│   ├── quick_approve.py          # 快速审批
│   └── reset_circuit_breaker.py  # 重置断路器
│
├── docs/                         # 文档目录
│   ├── README.md                 # 文档索引
│   ├── DESIGN.md                 # 设计文档
│   ├── SOUL.md                   # 灵魂文档
│   ├── IDENTITY.md               # 身份文档
│   ├── USER.md                   # 用户文档
│   ├── CONSTITUTION.md           # 宪法文档
│   ├── MEMORY.md                 # 记忆文档
│   ├── LEARN.md                  # 学习记录
│   ├── FIXES.md                  # 修复记录
│   ├── OPTIMIZATION_PLAN.md      # 优化计划
│   ├── OPTIMIZATION_SUMMARY.md   # 优化总结
│   └── archived/                 # 归档文档
│       ├── CLAUDE_CODE_*.md      # Claude Code 相关
│       ├── IMPLEMENTATION_*.md   # 实现相关
│       └── ANALYSIS_*.md         # 分析相关
│
├── memory/                       # 记忆数据
│   ├── memory.db                 # SQLite 数据库
│   ├── faiss_index.bin           # FAISS 索引
│   ├── MEMORY.md                 # 记忆文档
│   ├── logs/                     # 日志
│   │   └── 2026/
│   │       └── 04/
│   ├── team/                     # 团队数据
│   │   ├── members.json
│   │   ├── tasks.json
│   │   └── activities.json
│   ├── checkpoints/              # 检查点
│   ├── evolution_backups/        # 进化备份
│   └── backups/                  # 记忆备份
│
├── backups/                      # 系统备份
│   ├── archives/                 # 归档备份 (移动 zip 文件)
│   │   ├── backup_*.zip
│   │   └── goals.json.backup-*
│   └── latest/                   # 最新备份 (保留最近的)
│
├── logs/                         # 日志文件
│   ├── app/                      # 应用日志
│   ├── daemon/                   # 守护进程日志
│   ├── monitoring/               # 监控日志
│   └── archived/                 # 归档日志
│
├── reports/                      # 报告输出
│   ├── evolution/                # 进化报告
│   ├── monitoring/               # 监控报告
│   └── daily/                    # 日报
│
├── config/                       # 配置文件
│   ├── config.json               # 主配置
│   ├── default.yaml              # 默认配置
│   ├── development.yaml          # 开发环境
│   ├── production.yaml           # 生产环境
│   └── config_history.json       # 配置历史
│
├── goals/                        # 目标管理
│   └── goals.json
│
├── motivation/                   # 动机系统
│   ├── motivations.json
│   └── rewards.json
│
├── assessment/                   # 能力评估
│   ├── abilities.json
│   ├── assessments.json
│   └── errors.json
│
├── learning/                     # 学习系统
│   ├── knowledge.json
│   ├── experiences.json
│   └── opportunities.json
│
├── permissions/                  # 权限管理
│   └── permission_requests.json
│
├── state/                        # 状态管理
│   └── circuit_breaker_state.json
│
├── integrity/                    # 完整性检查
│   └── check_result_*.json
│
├── lx-desktop/                   # 桌面应用
│   ├── main.js
│   ├── preload.js
│   ├── package.json
│   ├── renderer/
│   └── assets/
│
├── trae-plugin-lengxiaobei/      # Trae 插件
│   ├── src/
│   ├── package.json
│   └── README.md
│
├── build/                        # 构建产物
│   ├── bridge                    # 桥接编译产物
│   ├── bridge_c
│   ├── bridge_rust
│   ├── bridge_ts
│   └── pytest.ini
│
├── venv/                         # Python 虚拟环境
│
└── tmp/                          # 临时文件 (新建)
    ├── pycache/                  # 移动 __pycache__
    └── archives/                 # 临时归档
```

## 整理步骤

### 第一阶段：创建新目录结构
1. 创建新的分类目录 (agents/, services/, systems/, tools/, utils/, models/)
2. 创建归档目录 (docs/archived/, logs/archived/, backups/archives/)

### 第二阶段：移动源代码
1. 将 agent 相关移动到 agents/
2. 将服务层代码移动到 services/
3. 将子系统移动到 systems/
4. 将工具模块移动到 tools/
5. 将工具函数移动到 utils/
6. 将数据模型移动到 models/

### 第三阶段：整理文档
1. 将分析类文档移动到 docs/archived/
2. 保留核心文档在 docs/
3. 更新文档引用路径

### 第四阶段：清理备份和日志
1. 将旧备份 zip 移动到 backups/archives/
2. 归档旧日志到 logs/archived/
3. 清理 __pycache__

### 第五阶段：整理测试
1. 统一测试文件到 tests/
2. 脚本移动到 scripts/
3. 删除重复测试

## 注意事项

1. **保留 .gitignore 规则**: 确保新目录结构被正确忽略
2. **更新导入路径**: 移动源文件后需要更新 import 语句
3. **备份重要数据**: 整理前先备份 memory/ 和 config/
4. **测试验证**: 整理后运行测试确保功能正常
5. **渐进式执行**: 分阶段执行，每阶段验证

## 清理建议

### 可以删除的文件
- src/__pycache__/ - Python 字节码缓存
- build/pytest.ini - 测试配置
- 超过 30 天的备份 zip 文件
- 重复的测试文件

### 需要保留的文件
- memory/memory.db - 核心记忆数据
- config.json - 主配置
- 所有 .py 源代码文件
- 核心文档 (SOUL.md, DESIGN.md 等)

## 预期效果

- ✅ 根目录文件减少 70%
- ✅ 目录结构清晰，按功能分类
- ✅ 文档有序归档，易于查找
- ✅ 测试文件统一管理
- ✅ 备份和日志规范归档
- ✅ 便于后续维护和扩展
