# 冷小北增强版整合指南

## 📋 架构概览

```
冷小北 (核心) + OpenClaw (全部功能) + Claude Code (全部功能)
```

**冷小北 保留：**
- 进化引擎
- KAIROS 决策
- GEPA 循环
- SKILL 持久化

**冷小北 可调用：**
- OpenClaw 的全部功能
- Claude Code 的全部功能

**原则：有就用，没有才自己写**

---

## 🔗 集成模块 (`src/integration.py`)

集成模块负责连接冷小北与 OpenClaw 和 Claude Code 两个外部系统。

### 主要组件

1. **OpenClawIntegration** - OpenClaw 集成
   - `analyze_code(code)` - 分析代码
   - `generate_code(prompt)` - 生成代码
   - `optimize_performance(code)` - 优化性能
   - `security_scan(target)` - 安全扫描

2. **ClaudeCodeIntegration** - Claude Code 集成
   - `code_completion(code)` - 代码补全
   - `debug_assistant(error, context)` - 调试助手
   - `documentation_generator(target)` - 文档生成
   - `test_generator(code)` - 测试生成

3. **IntegrationManager** - 集成管理器
   - 自动检测 OpenClaw 和 Claude Code 的路径
   - 提供统一的调用接口
   - 管理外部系统功能的可用性

### 使用方法

```python
from src.core import LengXiaobei

# 初始化冷小北
lxb = LengXiaobei()

# 调用 OpenClaw 功能
result = lxb.call_openclaw('analyze_code', code='print("Hello")')

# 调用 Claude Code 功能
result = lxb.call_claude_code('code_completion', code='def hello():')

# 获取可用功能列表
functions = lxb.get_available_functions()
```

## 🧰 技能系统集成

技能系统现在可以加载外部系统的功能作为技能：

```python
# 列出所有技能（包括外部系统技能）
skills = lxb.skill_manager.list_skills()

# 外部系统技能命名格式：
# - openclaw_<功能名>
# - claude_code_<功能名>
```

## 🎯 整合的核心功能

### 1. **增强版 QueryEngine** (`src/query_engine.py`)
- 基于 Claude Code 的 QueryEngine.ts 设计
- 异步生成器查询循环
- 工具调用与权限管理
- 记忆系统集成
- 宪法合规检查
- 用量追踪与预算管理

### 2. **增强版宪法系统** (`src/constitution.py`)
- 分层宪法原则（克制、诚实、简洁、汇报、外部验证层）
- 行动合规性检查
- 风险评估（LOW/MEDIUM/HIGH/CRITICAL）
- 决策边界管理

### 3. **增强版自动进化系统** (`src/auto_evolution.py`)
- 自主发现代码改进点（静态分析 + LLM深度分析）
- 生成安全的代码修改方案
- 多层验证机制（语法、导入、集成测试）
- 自动回滚
- 进化历史学习

### 4. **工具系统**（已增强）
- 动态工具注册中心
- 工具自动生成器
- 工具沙盒验证

## 🚀 使用方法

### 启动系统

```bash
cd ~/projects/lengxiaobei
python3 -m src.core
```

### 测试集成功能

```bash
cd ~/projects/lengxiaobei
python3 test_integration.py
```

### 新增命令

#### 集成调用

```python
# 调用 OpenClaw
lxb.call_openclaw('analyze_code', code='your code here')

# 调用 Claude Code
lxb.call_claude_code('code_completion', code='your code here')
```

#### 自进化命令

```
/self discover    - 发现代码改进点
/self auto        - 运行自动进化循环
/self history     - 查看进化历史
```

## 🔒 安全机制

### 宪法约束

所有操作都受宪法五大原则约束：
1. **克制** - 只做授权范围内的事
2. **诚实** - 如实汇报，不粉饰
3. **简洁** - 有主见，不废话
4. **汇报** - 重大决策前征询意见
5. **外部验证层** - 潘豪做最终决策

### 权限系统

集成模块使用 `src/evolution_permission.py` 进行权限管理：
- 低风险操作自动允许
- 高风险操作需要人工审批
- 所有变更都有签名和验证

## 📁 新增/修改的文件

### 新增
- `src/integration.py` - 集成模块
- `test_integration.py` - 集成测试

### 修改
- `src/core.py` - 添加集成管理器和技能系统初始化
- `src/skills.py` - 添加外部系统技能加载

## 🎉 总结

冷小北 + OpenClaw + Claude Code = 一套系统

- 冷小北保留核心能力（进化、KAIROS、GEPA、SKILL持久化）
- 通过集成模块调用外部系统的全部功能
- 遵循"有就用，没有才自己写"的原则
