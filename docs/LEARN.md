# Claude Code 泄露事件 — 公开学习资源

_本文档仅记录公开可访问的分析资料，不包含源码_

---

## 事件背景

2026-03-31，Anthropic 在 npm 包 2.1.88 中误发布了一个 59.8MB 的 `.map` 源映射文件，暴露了约 1,900 个文件、512,000+ 行 TypeScript 源码。社区快速响应，出现了大量高质量的公开分析。

---

## 高价值公开分析（合法可读）

### 架构概览
- **[dev.to: Production Architecture Audit](https://dev.to/gabrielanhaia/claude-codes-entire-source-code-was-just-leaked-via-npm-source-maps-heres-whats-inside-cjo)**
  - 五大子系统：Tool System、Query Engine、Multi-Agent Orchestration、IDE Bridge、Persistent Memory
  - 技术栈分析：Bun + React + Ink + Zod v4

- **[Hugging Face: Architecture Patterns](https://discuss.huggingface.co/t/claude-code-source-leak-production-ai-architecture-patterns-from-512-000-lines/174846)**
  - 三层压缩流水线：MicroCompact → AutoCompact → Full Compact
  - 四阶段 AutoDream 记忆整合流程（⭐ 对冷小北最有参考价值）

### 核心机制
- **[alex000kim: Security Analysis](https://alex000kim.com/posts/2026-03-31-claude-code-source-leak/)**
  - Fake Tool 注入（反蒸馏防御）
  - Undercover Mode（约90行实现）
  - 通过正则检测"挫败感"
  - Zig 编译的 cch 认证栈

- **[Medium: WebFetchTool Deep Dive](https://medium.com/@nblintao/how-an-ai-reads-the-web-a-deep-dive-into-claude-codes-webfetchtool-0abee4446343)**
  - 域名白名单、5分钟缓存黑名单
  - 重定向沙箱、Haiku 摘要
  - 1173 行实现的版权 guardrails

### 隐藏功能（未发布）
- **[kuber.studio: Hidden Features](https://kuber.studio/blog/AI/Claude-Code%27s-Entire-Source-Code-Got-Leaked-via-a-Sourcemap-in-npm%2C-Let%27s-Talk-About-it)**
  - **KAIROS**: 24/7 常驻后台代理，每隔几秒评估"anything worth doing right now?"
  - **ULTRAPLAN**: 30分钟远程编排模式
  - **Undercover Mode**: Anthropic 员工匿名提交模式
  - 内部代号：Tengu、Fennec

### 社区讨论
- **[r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/comments/1s8ijfb/claude_code_source_code_has_been_leaked_via_a_map/)** — KAIROS、Undercover Mode、Coordinator Mode 详细讨论
- **[r/ClaudeAI](https://www.reddit.com/r/ClaudeAI/comments/1s8ifm6/claude_code_source_code_has_been_leaked_via_a_map/)** — cch 认证机制、Capybara 模型变体

---

## 对冷小北最有价值的架构设计

### 1. KAIROS — 后台常驻代理
```
心跳机制：
- 每隔几秒收到："anything worth doing right now?"
- 评估 → 决定行动或静默
- append-only 日志（不能删除自己的历史）
- 夜间 autoDream：整理当天学到的东西，重组记忆
```
→ 冷小北的自主心跳 + 后台守护机制参考原型

### 2. AutoDream — 夜间记忆整合
```
四阶段流程：
1. 当天日志汇总
2. 知识点提取
3. 记忆重组
4. 次日优先级重排
```
→ ClawMem consolidation 的生产级实现参考

### 3. 三层压缩流水线
```
MicroCompact → AutoCompact → Full Compact
```
→ 渐进式上下文压缩，lossless-claw 的类似思路

### 4. Feature Flag 架构
- 44个隐藏 feature flags
- PROACTIVE、KAIROS 等未发布功能通过 flags 控制
- → 新框架的模块开关设计参考

---

## 已下架/法律风险资源

以下资源已被 DMCA 或存在法律风险，冷小北不访问：

| 资源 | 状态 |
|------|------|
| anthropic-ai/claude-code 直接镜像 | ❌ DMCA'd |
| 未经修改的源码分支 | ❌ DMCA'd |
| 4nzn/free-code (IPFS) | ⚠️ 法律状态未明 |
| claw-code (clean-room 重写) | ⚠️ 75k stars，法律争议中 |

---

_最后更新：2026-04-08_
