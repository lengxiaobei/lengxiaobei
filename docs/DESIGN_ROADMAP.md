# 冷小北设计路线图

_最后更新: 2026-05-21_

## 一句话方向

冷小北走"轻内核、强治理、可插拔能力、主动记忆"路线。

内核保持四 Facade 编排（MemoryFacade / ReasoningFacade / EvolutionFacade / GuardianFacade），能力通过工具/插件/MCP 扩展，进化必须经过可审计的提案、权限、测试和回滚链。

## 独特定位

数字生命体 + 自演化 + 宪法治理。不照搬任何一个项目。

## 三个参考项目的借鉴取舍

| 项目 | 值得借 | 不借 |
|---|---|---|
| OpenClaw | Gateway 多通道入口、onboarding/doctor、安全默认值、sandbox | 多通道大平台形态 |
| Hermes Agent | 闭环学习→技能沉淀、cron、子代理委派、provider 可切换 | 通用 agent runtime |
| OpenHuman | "先构建用户上下文再行动"、Memory Tree、token compression | 大 UI、118+ 集成 |

## 优先级路线图

### P0 — 稳定内核
- [ ] `lx doctor` — 检查记忆库、配置漂移、权限策略、熔断状态、MCP 可用性
- [ ] `lx onboard` — 检查 Python/Rust/依赖/配置/模型 key/目录权限
- [ ] 进化审计记录 — PlanRecord、PatchPreview、RiskScore、VerificationEvidence、RollbackRef
- [ ] 工具权限 manifest — tool.yaml: 权限级别、参数 schema、审批要求
- [ ] 结构化日志

### P1 — 增强记忆
- [ ] Memory Tree 分层: raw_event → episode → knowledge → profile
- [ ] 记忆压缩策略
- [ ] 会话搜索
- [ ] 用户/项目画像

### P2 — 能力插件化
- [ ] 工具/技能/MCP 统一 manifest，支持启停、权限、版本、测试
- [ ] SkillCard: trigger、procedure、tools_required、risk、tests、last_success

### P3 — 主动性
- [ ] KAIROS 事件总线: memory.updated、code.changed、test.failed、budget.warning
- [ ] 低风险自主任务队列

### P4 — 体验层
- [ ] 轻量状态面板（lx_web.py）
- [ ] 多通道 Gateway
- [ ] 可选桌面/聊天入口

## 核心取舍

冷小北最有价值的路线是"一个有宪法、有记忆、有自我修正能力的个人工程生命体"。先把治理链和记忆链打牢，后面的能力扩展才不会把它冲散。

不要变成 OpenClaw 的多通道大平台，不要变成 Hermes 的通用 agent runtime，不要急着追 OpenHuman 的大 UI。