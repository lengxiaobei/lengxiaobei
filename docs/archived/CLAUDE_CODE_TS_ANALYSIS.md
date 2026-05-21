# Claude Code TypeScript 源码架构分析报告

> 分析路径：`/Users/panhao/projects/Claude code/claude-code/src/`
> 日期：2026-04-08

---

## 一、源码目录结构

```
src/
├── QueryEngine.ts              # 核心查询引擎（1295行）
├── Tool.ts                     # 工具系统核心类型
├── main.tsx                    # 主入口
├── commands.ts                 # 斜杠命令注册
├── history.ts                  # 会话历史
├── assistant/
│   └── sessionHistory.ts       # 助手会话历史
├── bootstrap/                   # 启动初始化
├── bridge/                     # 桥接层
├── buddy/                      # Buddy 宠物系统
│   ├── companion.ts            # 宠物生成（gacha、hash确定性）
│   ├── types.ts                # 宠物类型定义（稀有度/物种/属性）
│   ├── prompt.ts               # 宠物系统提示词
│   ├── sprites.tsx             # 宠物精灵动画渲染
│   ├── CompanionSprite.tsx     # 宠物React组件
│   └── useBuddyNotification.tsx
├── cli/
│   ├── handlers/               # CLI处理器
│   └── transports/             # 传输层
├── commands/                    # 70+斜杠命令（/commit、/debug等）
├── components/                  # React UI组件
│   ├── PromptInput/            # 输入框
│   ├── messages/               # 消息渲染
│   ├── permissions/            # 权限请求UI
│   ├── mcp/                    # MCP服务器管理UI
│   ├── skills/                 # 技能管理UI
│   ├── teams/                  # 团队协作UI
│   └── memory/                  # 记忆管理UI
├── constants/                   # 全局常量
├── context/                     # 上下文管理
├── coordinator/                 # 多代理协调模式
│   └── coordinatorMode.ts       # Coordinator核心调度逻辑
├── entrypoints/
│   └── sdk/                    # SDK入口
├── hooks/                      # React Hooks
│   ├── notifs/                 # 通知
│   └── toolPermission/          # 工具权限处理
├── ink/                        # TUI渲染引擎（类React的终端UI框架）
│   ├── ink.tsx                 # 主渲染器
│   ├── reconciler.ts           # 协调器
│   ├── terminal.ts             # 终端抽象
│   ├── components/             # Ink内置组件
│   └── hooks/                  # Ink内置Hook
├── keybindings/                # 快捷键
├── memdir/                     # 记忆目录系统
│   ├── memdir.ts               # 记忆prompt构建/加载
│   ├── findRelevantMemories.ts # 查询时召回相关记忆
│   ├── memoryTypes.ts          # 记忆类型定义（四类taxonomy）
│   ├── memoryScan.ts           # 记忆文件扫描（前matter解析）
│   ├── memoryAge.ts            # 记忆新鲜度
│   ├── paths.ts                # 记忆路径解析
│   ├── teamMemPaths.ts         # 团队记忆路径
│   └── teamMemPrompts.ts       # 团队记忆prompt
├── migrations/                 # 配置迁移脚本
├── moreright/                  # （未知功能）
├── native-ts/                  # Native TypeScript模块
│   ├── file-index/             # 文件索引
│   └── yoga-layout/            # Yoga布局
├── outputStyles/               # 输出样式
├── plugins/                    # 插件系统
│   └── bundled/                # 内置插件
├── query/                      # 查询循环（query.ts为核心）
├── remote/                     # 远程连接
├── schemas/                    # JSON Schema定义
├── screens/                    # 屏幕/页面
├── server/                     # 服务端
├── services/                   # 业务服务层
│   ├── AgentSummary/           # Agent摘要
│   ├── compact/                # 对话压缩服务
│   ├── extractMemories/        # 记忆提取服务
│   ├── mcp/                    # MCP服务
│   └── tools/                  # 工具服务
├── skills/
│   └── bundled/                # 内置技能
├── state/                      # 状态管理
├── tasks/                      # 任务系统
│   ├── DreamTask/               # 背景思考任务
│   ├── LocalAgentTask/         # 本地Agent任务
│   ├── RemoteAgentTask/        # 远程Agent任务
│   └── InProcessTeammateTask/  # 进程内队友任务
├── tools/                      # 工具实现
│   ├── AgentTool/              # Agent工具（spawn子Agent）
│   ├── BashTool/               # Bash执行
│   ├── FileReadTool/           # 文件读取
│   ├── FileEditTool/           # 文件编辑
│   ├── FileWriteTool/          # 文件写入
│   ├── GrepTool/               # 搜索
│   ├── GlobTool/               # Glob匹配
│   ├── WebSearchTool/          # 联网搜索
│   ├── WebFetchTool/           # 网页抓取
│   ├── MCPTool/                # MCP工具
│   ├── TaskCreateTool/         # 任务创建
│   ├── TaskStopTool/           # 任务停止
│   ├── TeamCreateTool/         # 团队创建
│   └── SkillTool/              # 技能工具
├── types/                      # 类型定义
│   └── generated/              # 生成的类型
├── upstreamproxy/              # 上游代理
├── utils/                      # 工具函数
│   ├── background/             # 后台任务
│   ├── bash/                   # Bash封装
│   ├── git/                    # Git操作
│   ├── github/                 # GitHub API
│   ├── mcp/                    # MCP工具
│   ├── memory/                 # 记忆相关
│   ├── model/                  # 模型选择
│   ├── processUserInput/       # 用户输入处理
│   ├── sessionStorage/        # 会话存储
│   ├── swarm/                  # Swarm后端
│   └── telemetry/              # 遥测
└── voice/                      # 语音输入
```

---

## 二、QueryEngine 核心架构分析

### 2.1 定位与职责

`QueryEngine`（1295行）是 Claude Code 的**核心查询引擎**，封装了单次对话会话的完整生命周期。它是 headless/SDK 路径的中央处理单元。

**核心设计原则：一个 QueryEngine 对应一个会话（conversation）。**

### 2.2 核心类型

```typescript
export class QueryEngine {
  private mutableMessages: Message[]       // 会话消息（可变，跨turn持久化）
  private abortController: AbortController
  private permissionDenials: SDKPermissionDenial[]
  private totalUsage: NonNullableUsage
  private readFileState: FileStateCache
  private discoveredSkillNames: Set<string> // 本次submitMessage内去重
  private loadedNestedMemoryPaths: Set<string> // 已加载的嵌套记忆路径
}
```

### 2.3 submitMessage — 核心方法

`submitMessage()` 是一个 `AsyncGenerator<SDKMessage>`，每次 yield 都是一个 SDK 消息（assistant/user/system/progress等）。

**完整流程：**

```
submitMessage(prompt)
  ├── 前置准备
  │   ├── canUseTool 包装（追踪权限拒绝）
  │   ├── fetchSystemPromptParts() → 获取系统提示词
  │   ├── getCoordinatorUserContext() → 注入coordinator上下文
  │   ├── loadMemoryPrompt() → 加载记忆系统提示词
  │   └── buildSystemPrompt（合并 custom + memory + append）
  │
  ├── processUserInput() — 处理斜杠命令、更新工具权限
  │
  ├── 写 Transcript（持久化用户消息，在API响应前）
  │
  ├── query() — 核心LLM推理循环（yield消息流）
  │   ├── message type 分支处理：
  │   │   ├── assistant → normalize → yield SDK消息
  │   │   ├── user → normalize → yield
  │   │   ├── tool_use_summary → yield SDK格式
  │   │   ├── stream_event (message_delta/usage) → 累计usage
  │   │   ├── api_error → yield retry信号
  │   │   ├── progress → normalize → yield
  │   │   └── compact_boundary → 压缩边界
  │   └── 每次tool_use记录到mutableMessages
  │
  ├── 预算检查（maxTurns / maxBudgetUsd）
  │
  └── yield result（最终统计：usage/cost/duration/permission_denials）
```

### 2.4 关键架构决策

**1. AsyncGenerator 流式输出**
- `submitMessage` 是 async generator，yield 每个 SDKMessage
- SDK 消费者（CLI/SDK）逐条消费，实现流式输出

**2. 权限追踪**
- `wrappedCanUseTool` 拦截每个工具调用，记录 `permissionDenials`
- 最终随 result 一起上报给 SDK

**3. 记忆系统集成**
- `loadMemoryPrompt()` → 返回记忆系统提示词文本
- 注入到 systemPrompt 中，供模型在推理时使用

**4. 条件编译（feature gates）**
```typescript
// COORDINATOR_MODE — 条件导入，保留在bundle中但可tree-shake
const getCoordinatorUserContext = feature('COORDINATOR_MODE')
  ? require('./coordinator/coordinatorMode.js').getCoordinatorUserContext
  : () => ({})
```
- 使用 `feature()` 标志控制功能开关
- 字符串常量化避免 excluded-strings 检查

**5. HISTORY_SNIP 对话压缩**
- 当 HISTORY_SNIP 开启时，compact_boundary 触发对话压缩
- 压缩后清空 mutableMessages 前段，只保留 tail

**6. 嵌套记忆（Nested Memory）**
- `loadedNestedMemoryPaths: Set<string>` 追踪已加载的嵌套记忆路径
- 避免重复加载同一个嵌套记忆

---

## 三、记忆系统（memdir）分析

### 3.1 整体架构

```
memdir/
├── memdir.ts              # 记忆prompt构建 + 加载入口
├── findRelevantMemories.ts # 查询时召回相关记忆（Sonnet做selector）
├── memoryTypes.ts         # 四类记忆taxonomy + prompt模板
├── memoryScan.ts          # 记忆文件扫描（前30行frontmatter）
├── memoryAge.ts           # 记忆新鲜度管理
├── paths.ts               # 记忆目录路径解析
├── teamMemPaths.ts        # 团队记忆路径
└── teamMemPrompts.ts      # 团队记忆prompt
```

### 3.2 四类记忆类型（Taxonomy）

`memoryTypes.ts` 定义了严格封闭的记忆类型系统：

| 类型 | 描述 | 保存时机 | 范围 |
|------|------|----------|------|
| `user` | 用户角色、目标、知识 | 了解用户背景时 | 私有 |
| `feedback` | 用户指导（纠正+确认） | 纠正或确认非显而易见的方法时 | 私有/团队 |
| `project` | 项目上下文（目标/截止/决策） | 了解谁在做什么/为什么/何时 | 私有/团队 |
| `reference` | 外部系统指针（Linear/Grafana等） | 了解外部资源时 | 通常团队 |

**关键约束（写在 prompt 里）：**
- 代码模式、架构、Git历史**不**存入记忆（可从代码派生）
- MEMORY.md 是索引文件，**不是**记忆体
- 记忆条目**必须带 Why + How to apply**，避免死记

### 3.3 记忆文件格式

```markdown
---
name: {{memory name}}
description: {{one-line description — 用于未来对话的相关性判断}}
type: {{user|feedback|project|reference}}
---

{{memory content — feedback/project类型需结构化为: 规则, **Why:**, **How to apply:**}}
```

### 3.4 记忆加载时机

**`loadMemoryPrompt()`** 是系统提示词构建的一部分，返回记忆系统行为指令文本。

**两种模式：**

1. **标准模式**：`MEMORY.md` 作为索引，每个文件一行指针
   - 先读 MEMORY.md（最多200行/25KB截断）
   - 模型通过文件名+description决定是否读某个记忆文件

2. **KAIROS模式**（长会话）：append-only daily log
   - 新记忆直接 append 到 `logs/YYYY/MM/YYYY-MM-DD.md`
   - 夜间 distill 进程整合到 MEMORY.md

3. **TEAMMEM模式**：私有 + 团队双目录
   - `~/.claude/projects/<slug>/memory/` — 私有
   - `~/.claude/projects/<slug>/memory/team/` — 团队共享

### 3.5 查询时记忆召回（findRelevantMemories）

```
findRelevantMemories(query)
  ├── scanMemoryFiles() — 扫描memoryDir所有.md文件
  │   ├── 读frontmatter前30行（description + type）
  │   ├── 返回 MemoryHeader[]（filename/mtime/description/type）
  │   └── 最多200个文件，按mtime降序
  │
  ├── selectRelevantMemories() — Sonnet做相关性选择
  │   ├── 构建 manifest（每行: "- [type] filename (ts): description"）
  │   ├── 附最近使用的工具列表（排除工具文档类记忆）
  │   ├── 调用 sideQuery（Sonnet 256 tokens）
  │   └── 输出: { selected_memories: string[] }
  │
  └── 返回 RelevantMemory[]（path + mtime）
```

**设计亮点：**
- 两次读取分离：scan（所有文件头）→ select（Sonnet选择）→ 返回路径
- `alreadySurfaced` 过滤已展示过的记忆，避免重复推荐
- `recentTools` 参数避免在用某工具时还推荐其文档

### 3.6 MEMORY.md 截断保护

```typescript
MAX_ENTRYPOINT_LINES = 200
MAX_ENTRYPOINT_BYTES = 25_000
// 先按行截断到200行，再按字节截断到25KB
// 截断时附加警告，告诉模型索引条目应保持简短
```

---

## 四、多代理调度（coordinator）分析

### 4.1 定位

Coordinator 模式是 Claude Code 的**多代理并行执行模式**。Coordinator 本体是主 Agent，通过 `AgentTool` spawn Worker Agent 完成任务。

### 4.2 核心文件

- `coordinatorMode.ts`：Coordinator 系统提示词 + 上下文注入逻辑
- `AgentTool`：工具实现，spawn worker
- `SendMessageTool`：继续已有 worker
- `TaskStopTool`：停止 worker

### 4.3 Coordinator 工作流

```
用户消息
  │
  ▼
Coordinator（主Agent）
  │
  ├── 研究阶段：并行 spawn 多个 worker 做 research
  │
  ▼
Worker 完成 → <task-notification> XML 格式通知
  │
  ▼
Coordinator 读取结果 → 合成（synthesize）→ 写实施spec
  │
  ├── 继续同 worker（SendMessageTool）→ 做实施
  │   OR
  └── Spawn 新 worker 做实施（看上下文重叠度）
  │
  ▼
Verification worker（独立验证）
  │
  ▼
报告给用户
```

### 4.4 关键设计：Continue vs Spawn

| 情况 | 机制 | 原因 |
|------|------|------|
| 研究刚好覆盖要改的文件 | **Continue** | 上下文已加载 |
| 研究范围广但实施范围窄 | **Spawn fresh** | 避免探索噪声 |
| 纠正失败或扩展近期工作 | **Continue** | 有错误上下文 |
| 验证别人刚写的代码 | **Spawn fresh** | 独立视角 |
| 第一次尝试方向完全错误 | **Spawn fresh** | 错误上下文会污染 |
| 完全不相关任务 | **Spawn fresh** | 无上下文复用 |

### 4.5 Worker 工具限制

Coordinator spawn 的 worker 有**受限工具集**：
- 基础工具（`SIMPLE`模式）：Bash、Read、Edit
- 完整工具：标准工具 + MCP + SkillTool（由 `ASYNC_AGENT_ALLOWED_TOOLS` 控制）
- **内部工具不可用**：TeamCreate、TeamDelete、SendMessage（只有Coordinator能用）

### 4.6 Scratchpad 目录

```typescript
// Coordinator 可以给 worker 传递 scratchpad 路径
// Worker 在这里读写不需要权限提示
// 用于跨 worker 共享知识
```

### 4.7 条件启用

```typescript
export function isCoordinatorMode(): boolean {
  if (feature('COORDINATOR_MODE')) {
    return isEnvTruthy(process.env.CLAUDE_CODE_COORDINATOR_MODE)
  }
  return false
}
```

---

## 五、Buddy 系统分析

### 5.1 定位

Buddy 是 Claude Code 的**桌面宠物/伙伴系统**——一个在输入框旁边显示的小生物，偶尔在对话中发表评论。

### 5.2 核心文件

```
buddy/
├── companion.ts       # gacha生成 + 确定性hash
├── types.ts          # Companion类型定义
├── prompt.ts         # Buddy系统提示词
├── sprites.tsx       # ASCII/Unicode精灵动画
├── CompanionSprite.tsx  # React渲染组件
└── useBuddyNotification.tsx  # 通知逻辑
```

### 5.3 Companion 结构

```typescript
// 确定性骨骼（从 userId hash 生成，每次启动重建）
type CompanionBones = {
  rarity: 'common' | 'uncommon' | 'rare' | 'epic' | 'legendary'
  species: 'duck' | 'goose' | 'blob' | 'cat' | ...（18种）
  eye: '·' | '✦' | '×' | '◉' | '@' | '°'
  hat: 'none' | 'crown' | 'tophat' | 'propeller' | ...
  shiny: boolean          // 1%概率
  stats: Record<StatName, number>  // DEBUGGING/PATIENCE/CHAOS/WISDOM/SNARK
}

// 模型生成的灵魂（存储在config，name+personality）
type CompanionSoul = {
  name: string
  personality: string
}

// 完整Companion = Bones + Soul + hatchedAt
```

### 5.4 稀有度系统

```typescript
const RARITY_WEIGHTS = {
  common: 60,
  uncommon: 25,
  rare: 10,
  epic: 4,
  legendary: 1,
}
// Rarity 决定 stat floor（common:5, uncommon:15, rare:25, epic:35, legendary:50）
// Rarity 决定是否有帽子（common: none always）
```

### 5.5 确定性生成（Anti作弊）

```typescript
// 关键设计：骨骼从 hash(userId) 确定性生成
// 存储层只存 Soul（name + personality）
// 用户无法通过修改配置伪造稀有度或物种
export function getCompanion(): Companion | undefined {
  const stored = getGlobalConfig().companion  // 只存Soul
  if (!stored) return undefined
  const { bones } = roll(companionUserId())  // 每次从hash重建
  return { ...stored, ...bones }
}
```

### 5.6 Buddy 的角色定位（来自 prompt.ts）

> "A small {species} named {name} sits beside the user's input box and occasionally comments in a speech bubble. You're not {name} — it's a separate watcher."

- Buddy **不是**主模型的分身
- Buddy 是一个**旁观者**，被直接点名时才在气泡中回应
- 主模型被点名时要**让开**，只回答自己那一行

### 5.7 物种名混淆（Anti-canary）

```typescript
// 物种名通过 String.fromCharCode 动态构造
// 避免 literal 出现在 bundle 的 excluded-strings 检查中
const c = String.fromCharCode
const duck = c(0x64,0x75,0x63,0x6b) as 'duck'
```

---

## 六、可迁移到冷小北的设计点

### 6.1 记忆系统（高优先级）

**可迁移设计：**
- **四类 Taxonomy**：`user / feedback / project / reference` 是非常实用的记忆分类，引入冷小北可以快速建立记忆结构
- **MEMORY.md 索引 + 文件内容分离**：索引检索快，内容按需读取
- **`findRelevantMemories` 动态召回**：当前会话不足够时，用 Sonnet 做二次召回
- **记忆新鲜度**：`mtimeMs` 追踪 + 时间戳在 manifest 中展示
- **What NOT to save**：明确定义排除规则（代码派生信息不进记忆）
- **Memory drift caveat**：记忆可能过期的警告 + 验证机制

**潘豪的痛点"记忆不延续"正好对应这套系统的核心能力。**

### 6.2 QueryEngine 的 AsyncGenerator 模式（高优先级）

**可迁移设计：**
- `AsyncGenerator<SDKMessage>` 流式输出架构非常适合拆分成多个处理阶段
- 每个 turn yield 消息而不是等全部完成，利于实现流式输出和中间干预
- `mutableMessages` 跨 turn 持久化是会话连续性的基础
- `permissionDenials` 追踪 + 上报是良好可观测性的体现

### 6.3 Coordinator 多代理调度（中等优先级）

**可迁移设计：**
- **并行 research → 合成 → 实施**的三阶段工作流
- **Continue vs Spawn** 的决策框架（上下文重叠度判断）
- **Worker 工具受限**：不是所有 Agent 都能用所有工具
- **`<task-notification>` XML 格式**：worker 结果的结构化传递
- **验证层独立**：实施者不验证，验证者独立spawn

**注意**：冷小北作为潘豪的直属执行者，不应过度委托。但 research 阶段可以并行化。

### 6.4 条件编译 / Feature Gates（中等优先级）

**可迁移设计：**
- `feature('NAME')` 条件开关 + 条件导入，允许功能在代码中共存但按需激活
- 避免 if/else 散落各处，统一入口管理

### 6.5 Buddy 的确定性 + 防作弊设计（低优先级参考）

**参考点：**
- 宠物属性从用户ID hash 生成，用户无法伪造
- 只持久化必要状态（soul），可派生状态（bones）每次重建
- 这套模式适合用于任何需要防止用户伪造状态的场景

### 6.6 记忆的 prompt 工程（高价值参考）

`memoryTypes.ts` 里的 prompt 片段质量极高：
- 每个记忆类型的 **When to save / How to use / Examples** 三段式
- **Why + How to apply** 结构（理解原因才能正确应用）
- **Body structure** 规定（反馈类记忆 lead with 规则本身）
- **"不保存什么"** 的明确列举（排除 eval 验证过的高频错误）

---

## 附：关键文件行数参考

| 文件 | 行数 | 职责 |
|------|------|------|
| `QueryEngine.ts` | 1295 | 核心查询引擎 |
| `coordinatorMode.ts` | ~350 | Coordinator系统提示词 |
| `memdir.ts` | ~400 | 记忆prompt构建 |
| `findRelevantMemories.ts` | ~150 | 记忆召回 |
| `memoryTypes.ts` | ~350 | 记忆taxonomy + prompt模板 |
| `companion.ts` | ~150 | Buddy gacha生成 |
| `memoryScan.ts` | ~100 | 记忆文件扫描 |
