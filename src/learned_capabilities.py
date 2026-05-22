"""Learned capabilities registry.

This module is the safe first landing zone for lessons absorbed from other
agents. Self-evolution can update it without touching identity, safety, or
runtime-critical files.
"""

from __future__ import annotations

from typing import Any, Dict, List


LEARNED_CAPABILITIES: List[Dict[str, Any]] = []


def list_learned_capabilities() -> List[Dict[str, Any]]:
    """Return learned capabilities in insertion order."""
    return list(LEARNED_CAPABILITIES)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779387081',
    'topic': '自主学习openhands的，进化能力',
    'source': 'OpenHands',
    'capability': '小粒度代码自进化闭环能力',
    'pattern': '执行代码自修改时严格限定单轮变更代码行数阈值，变更前先生成对应单元测试用例，变更后立即跑测，通过则提交版本并记录收益，未通过则自动回滚代码并留存失败原因作为经验项',
    'adaptation': '给现有代码修改模块新增3个轻量钩子：1.单轮变更强制校验行数不超过30行；2.变更前自动生成对应入参验证用例；3.变更跑测失败自动调用git回滚并写入本地经验日志，无需改动核心架构',
    'goal': '给src/learned_capabilities.py中的现有代码修改逻辑新增3个轻量校验钩子：单轮变更代码行数强制校验不超过30行、变更前自动生成对应入参验证单元测试用例、变更跑测失败自动调用git回滚并写入本地经验日志',
    'created_at': 1779387081.109916}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779387712',
    'topic': '学习openhands的记忆方面长处',
    'source': 'OpenHands (OpenDevin)',
    'capability': '分层情景记忆与事件流压缩',
    'pattern': 'OpenHands 用 EventStream 记录所有 action/observation，并通过 condenser（如 '
               'LLMSummarizingCondenser）在上下文超限前把旧事件压缩成摘要事件保留在流中，既保留长程线索又控制 token',
    'adaptation': '在冷小北加一个轻量 episode 日志：每次交互追加 {time, intent, action, result} 到 jsonl，达到阈值N条时调用一次 '
                  'LLM 把旧条目压成一段 summary 事件写回，原始条目归档；查询记忆时优先读 summary+最近N条',
    'goal': '在src/learned_capabilities.py中新增适配OpenHands事件流压缩经验的轻量分层情景记忆逻辑，每次交互完成后追加含time、intent、action、result字段的条目到本地episode.jsonl日志，当日志条目数达阈值10条时复用项目现有LLM能力将最早的7条压缩为单条summary事件写回日志，原始旧条目归档到同目录archive子文件夹，记忆查询优先读取最新summary加最近3条未压缩条目，全程不改动现有核心架构与安全规则',
    'created_at': 1779387712.9464011}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779420788',
    'topic': '自主学习 OpenHands 的任务拆解、工作区执行和错误恢复能力，并提炼一个可落地改进',
    'source': 'OpenHands',
    'capability': '编程任务分层拆解-原子执行-回溯式错误恢复能力',
    'pattern': '将用户编程需求拆解为绑定可落地校验规则的原子子任务，每次仅在工作区执行单步原子操作，执行后立即触发校验，失败则自动回溯调整拆解粒度或修复路径，不跨步累积错误',
    'adaptation': '最小化吸收方案：1. 任务拆分模块新增「每个子任务必填1条可快速验证的校验规则」的约束；2. '
                  '工作区执行模块新增「执行后先校验再进入下一子任务」的前置逻辑；3. 错误处理模块新增「校验失败仅回退当前单步操作而非全量重置」的规则',
    'goal': '为src/learned_capabilities.py中的编程任务分层拆解能力模块新增「子任务必填1条可快速验证的校验规则」的约束校验、「单步原子操作执行后先校验再进入下一子任务」的前置逻辑及「校验失败仅回退当前单步操作」的错误处理规则',
    'created_at': 1779420788.662026}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779420993',
    'topic': '自主学习 Aider 的 git 感知代码修改、最小补丁和提交前验证能力，并提炼一个可落地改进',
    'source': 'Aider',
    'capability': 'Git感知的最小补丁生成与提交前自动验证能力',
    'pattern': '先读取Git工作区状态、文件diff上下文定位修改范围，仅生成覆盖需求的最小增量代码补丁，修改完成后自动调用项目校验命令（lint/单测），校验不通过则自动回滚到修改前状态并记录问题',
    'adaptation': '新增轻量Git上下文读取逻辑，代码生成前先拉取当前仓库diff与暂存状态限定修改范围，代码输出后自动触发项目基础校验，校验失败自动回滚对应文件并留存错误日志',
    'goal': '在src/learned_capabilities.py中新增轻量的Git工作区diff与暂存状态读取、修改完成后触发本地预设校验命令、校验失败自动回滚对应文件并记录错误日志的逻辑，实现Git感知的最小补丁生成前置约束与修改后自动校验回滚基础能力',
    'created_at': 1779420993.84972}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779421753',
    'topic': '自主学习 Continue 的 IDE 上下文、代码库索引和开发者交互设计能力，并提炼一个可落地改进',
    'source': 'Continue',
    'capability': 'IDE实时上下文自动感知与轻量增量索引能力',
    'pattern': '通过监听IDE文件变更、光标位置、编辑历史事件，仅对变动文件做增量语义索引，交互时自动将当前激活文件、光标选区、最近编辑记录作为默认上下文注入，无需开发者手动粘贴提供',
    'adaptation': '最小化落地：先为代码交互模块新增轻量IDE事件钩子，仅抓取当前激活文件路径、光标选中代码段、最近2次编辑内容，作为请求时的自动附加上下文，暂不实现全量代码库索引，优先覆盖实时编辑场景',
    'goal': '在 src/learned_capabilities.py '
            '中添加一个轻量级的IDE事件监听器函数，自动获取当前激活文件路径、光标选中代码段和最近2次编辑内容，作为交互请求的默认上下文注入。',
    'created_at': 1779421753.509583}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779423619',
    'topic': '自主学习 AutoGen 的多 Agent 协作、角色分工和任务交接机制，并提炼一个可落地改进',
    'source': 'AutoGen',
    'capability': '多Agent任务交接与角色分工',
    'pattern': '通过定义专门角色（如规划者、执行者、审查者）并在对话中动态分配和交接任务，实现任务分解与协作',
    'adaptation': '冷小北可在现有任务处理模块中引入角色抽象层，将复杂任务分解为子任务，分配给内部角色模拟执行，先从小规模任务试点测试',
    'goal': '在src/learned_capabilities.py中添加一个简单的角色抽象函数，用于将任务分解为子任务并模拟角色分工执行，从小规模任务开始试点。',
    'created_at': 1779423619.331761}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779424270',
    'topic': '自主学习 Claude Code 的计划执行、工具调用反馈和长任务汇报体验，并提炼一个可落地改进',
    'source': 'Claude Code',
    'capability': '工具调用反馈循环',
    'pattern': '工具调用后自动解析返回反馈，根据反馈调整后续步骤或重试错误操作',
    'adaptation': '在现有工具调用模块中嵌入反馈解析逻辑，并添加简单重试机制',
    'goal': '在 src/learned_capabilities.py 的工具调用函数中，嵌入反馈解析逻辑并添加简单重试机制，当工具调用返回错误时自动重试最多一次操作。',
    'created_at': 1779424270.027346}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779425072',
    'topic': '自主学习 OpenHands 的任务拆解、工作区执行和错误恢复能力，并提炼一个可落地改进',
    'source': 'OpenHands',
    'capability': '错误恢复能力',
    'pattern': '模块化错误处理，记录错误上下文（如输入、状态、异常），自动分析错误原因并尝试预设或动态生成的替代解决方案',
    'adaptation': '在现有任务执行模块中添加一个轻量级错误处理插件，先实现简单的错误记录和尝试修复逻辑，逐步扩展',
    'goal': '在 src/learned_capabilities.py '
            '中添加一个轻量级错误处理函数，用于捕获任务执行异常、记录上下文（输入、状态和异常信息），并尝试预设的替代解决方案以提升鲁棒性。',
    'created_at': 1779425072.1803572}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779425858',
    'topic': '自主学习 Aider 的 git 感知代码修改、最小补丁和提交前验证能力，并提炼一个可落地改进',
    'source': 'Aider',
    'capability': 'Git-Aware Minimal Patch with Pre-Commit Validation',
    'pattern': '在修改代码时，先检查 git 仓库状态，只针对变更文件生成最小化差异补丁，并在提交前自动运行测试、lint 等验证步骤。',
    'adaptation': '冷小北可以先实现一个独立的 git '
                  '感知模块，在生成代码修改时自动限制文件范围，集成补丁生成功能，并添加轻量级预提交验证（如运行简单测试或检查）。这可以通过最小化添加新模块来实现，不涉及核心改动。',
    'goal': '在 src/learned_capabilities.py 中添加一个独立函数，用于检查 git '
            '仓库状态、仅针对变更文件生成最小化差异补丁，并集成轻量级预提交验证（如运行简单测试或 lint 检查）。',
    'created_at': 1779425858.7489579}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779426679',
    'topic': '自主学习 Continue 的 IDE 上下文、代码库索引和开发者交互设计能力，并提炼一个可落地改进',
    'source': 'GitHub Copilot',
    'capability': '上下文感知的代码建议生成',
    'pattern': '通过整合 IDE 当前上下文、代码库索引和开发者交互模式，动态提供相关代码建议',
    'adaptation': '冷小北先实现一个轻量级版本，基于当前文件内容和简单关键词索引生成建议，再逐步扩展到完整代码库索引和交互优化',
    'goal': '在 src/learned_capabilities.py 中添加一个轻量级函数，基于当前文件内容解析关键词并生成简单的代码建议，以初步实现上下文感知功能。',
    'created_at': 1779426679.795562}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779427481',
    'topic': '自主学习 AutoGen 的多 Agent 协作、角色分工和任务交接机制，并提炼一个可落地改进',
    'source': 'AutoGen',
    'capability': '动态角色分配与任务交接协议',
    'pattern': '根据任务类型自动分配Agent角色，并通过标准化消息格式实现无缝任务交接',
    'adaptation': '在冷小北的Agent管理模块中添加角色分配接口，并扩展现有消息协议支持任务交接',
    'goal': '在 src/learned_capabilities.py 中添加一个函数 '
            'assign_role_by_task_type，实现基于任务类型字符串的动态角色分配，使用内部字典映射以支持多Agent协作中的角色自动分配。',
    'created_at': 1779427481.3882298}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779428290',
    'topic': '自主学习 Claude Code 的计划执行、工具调用反馈和长任务汇报体验，并提炼一个可落地改进',
    'source': 'Claude Code',
    'capability': 'Task Decomposition and Progress Feedback',
    'pattern': '将复杂任务分解为清晰的子任务序列，实时调用工具执行并反馈中间结果，通过结构化汇报保持任务进度透明。',
    'adaptation': '冷小北可在现有任务执行模块中引入一个轻量级状态跟踪器，从小任务开始模拟分解和反馈循环，逐步测试和迭代。',
    'goal': '在src/learned_capabilities.py中添加一个轻量级TaskTracker类，用于记录任务分解的子步骤和实时进度，便于反馈和错误检测。',
    'created_at': 1779428290.526498}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779429095',
    'topic': '自主学习 OpenHands 的任务拆解、工作区执行和错误恢复能力，并提炼一个可落地改进',
    'source': 'OpenHands',
    'capability': '错误恢复能力',
    'pattern': '当任务执行失败时，能够自动检测错误、分析根因、回滚到上一个稳定状态，并尝试替代策略',
    'adaptation': '在冷小北的执行引擎中集成轻量级错误检测和回滚机制，通过小步修改逐步测试',
    'goal': '在src/learned_capabilities.py中添加一个轻量级函数，用于检测任务执行错误、记录错误状态并触发回滚到上一个稳定状态，作为错误恢复能力的小步集成。',
    'created_at': 1779429095.4438558}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779429914',
    'topic': '自主学习 Aider 的 git 感知代码修改、最小补丁和提交前验证能力，并提炼一个可落地改进',
    'source': 'Aider',
    'capability': 'Git感知最小补丁生成与验证',
    'pattern': 'Aider在修改代码时自动检测git仓库状态，生成最小化代码差异（如仅修改必要行），并在提交前运行验证测试（如linters或单元测试），确保更改准确且可追溯。',
    'adaptation': '冷小北可最小化吸收此能力，先添加一个轻量级模块来检测git状态（如使用GitPython库），再集成最小补丁生成算法（如基于diff），最后在修改流程中添加简单的验证钩子（如运行现有测试）。实现时先修改一个文件进行试点测试。',
    'goal': '在src/learned_capabilities.py中添加一个函数，使用subprocess检测当前目录是否为git仓库状态，作为Git感知功能的轻量级起点。',
    'created_at': 1779429914.9461849}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779430731',
    'topic': '自主学习 Continue 的 IDE 上下文、代码库索引和开发者交互设计能力，并提炼一个可落地改进',
    'source': 'Continue',
    'capability': 'IDE上下文实时感知与代码库索引集成',
    'pattern': '通过插件或API与IDE深度集成，自动获取当前文件、光标位置、选中代码等上下文，并查询代码库索引以提供精准建议',
    'adaptation': '冷小北可以引入一个轻量级模块监听IDE事件（如文件切换、编辑），提取上下文信息，并逐步集成索引查询接口，最小化修改现有核心逻辑',
    'goal': '在src/learned_capabilities.py中添加一个轻量级IDEContextMonitor类，用于监听文件切换和编辑事件，提取当前文件路径、光标位置和选中代码，并存储到内部状态以供后续代码辅助使用。',
    'created_at': 1779430731.1855948}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779431575',
    'topic': '自主学习 AutoGen 的多 Agent 协作、角色分工和任务交接机制，并提炼一个可落地改进',
    'source': 'AutoGen',
    'capability': '结构化多轮任务委托与结果汇总',
    'pattern': '主Agent（Assistant）定义明确任务并拆分，委托给专门化的子Agent（如UserProxy， Coder， '
               'Planner）执行；子Agent专注于单一职责（如编写/执行代码、提供信息）；所有交互通过结构化的消息（含特定字段如`task`, `result`, '
               '`status`）在明确的对话上下文中进行；主Agent最终汇总子Agent的输出并决定下一步或向用户报告。',
    'adaptation': '为冷小北设计一个最简版的「任务执行器」接口。当主对话逻辑判断任务可分解时（如“查找信息并生成报告”），不再自行穷举所有步骤，而是创建一个`TaskExecutor`实例，传递一个结构化的`task_definition`（含`goal`, '
                  '`required_info`, `output_format`）。主逻辑监听该执行器返回的`task_result`消息，并基于此继续对话或生成最终回复。',
    'goal': '在 src/learned_capabilities.py 中新增一个 TaskExecutor 类，定义 execute 方法接收包含 '
            'goal、required_info、output_format 的 task_definition 并返回 task_result，实现最简任务执行接口。',
    'created_at': 1779431575.7816699}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779432401',
    'topic': '自主学习 Claude Code 的计划执行、工具调用反馈和长任务汇报体验，并提炼一个可落地改进',
    'source': 'Claude Code',
    'capability': '阶段性任务进度汇报',
    'pattern': '在执行多步骤任务时，每完成一个关键步骤（如工具调用、计划分解）就输出简洁的进度摘要，包括当前状态、剩余任务和潜在问题。',
    'adaptation': '在现有任务执行循环中添加一个轻量级汇报钩子，在每个步骤结束时调用，输出到日志或用户界面，无需修改核心逻辑。',
    'goal': '在src/learned_capabilities.py中添加一个轻量级log_progress_summary函数，当任务执行循环的每个步骤结束时调用，输出当前状态、剩余任务和潜在问题的摘要到日志。',
    'created_at': 1779432401.023606}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779433241',
    'topic': '自主学习 OpenHands 的任务拆解、工作区执行和错误恢复能力，并提炼一个可落地改进',
    'source': 'OpenHands',
    'capability': '层次化任务拆解能力',
    'pattern': '将复杂任务动态分解为可执行子任务序列，每个子任务有独立上下文和错误处理，并支持重规划',
    'adaptation': '冷小北可在现有任务执行模块中添加一个轻量级分解器，先从线性分解开始，逐步集成反馈循环',
    'goal': '在 src/learned_capabilities.py '
            '中添加一个轻量级的线性任务分解函数，将输入任务动态拆分为子任务列表，每个子任务附带独立上下文和基础错误处理机制。',
    'created_at': 1779433241.537676}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779434119',
    'topic': '自主学习 Aider 的 git 感知代码修改、最小补丁和提交前验证能力，并提炼一个可落地改进',
    'source': 'Aider',
    'capability': 'Git-aware minimal patch generation with pre-commit validation',
    'pattern': '在修改代码时，首先解析git状态以理解上下文，然后生成仅针对必要更改的最小补丁，并在提交前自动运行测试或验证钩子以确保正确性。',
    'adaptation': '冷小北可在现有代码修改模块中集成git状态分析、最小补丁算法（如使用diff库）和预提交测试钩子，通过添加新函数或装饰器实现，避免核心结构变更。',
    'goal': '在src/learned_capabilities.py中添加一个辅助函数git_minimal_patch_generator，使用标准库subprocess和difflib解析git差异并生成最小代码补丁，以提升修改精确性和可追溯性。',
    'created_at': 1779434119.991584}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779434985',
    'topic': '自主学习 Continue 的 IDE 上下文、代码库索引和开发者交互设计能力，并提炼一个可落地改进',
    'source': 'Continue',
    'capability': '代码库索引与上下文理解能力',
    'pattern': '通过增量索引本地代码库，构建向量数据库，实现快速的代码片段检索和上下文相关建议生成',
    'adaptation': '冷小北可以添加一个轻量级索引模块，定期扫描项目文件，提取代码片段并存储为嵌入向量，在交互时检索相关上下文以增强响应',
    'goal': '在src/learned_capabilities.py中添加一个轻量级索引函数，用于增量扫描项目文件、提取代码片段并存储为简单向量，以增强上下文检索和建议生成能力。',
    'created_at': 1779434985.209676}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779435836',
    'topic': '自主学习 AutoGen 的多 Agent 协作、角色分工和任务交接机制，并提炼一个可落地改进',
    'source': 'GitHub Copilot Agent (GitHub Next)',
    'capability': '任务导向的结构化思维链 (Structured Chain-of-Thought for Task Execution)',
    'pattern': '面对一个明确的编码任务（如“为这个函数编写测试用例”），它首先进行结构化分析，输出类似“**Thought**: '
               '我需要理解函数`add`的逻辑和边界。**Action**: 分析函数签名、文档和上下文代码。**Observation**: '
               '函数接受两个整数，返回它们的和。**Thought**: 测试应覆盖正常值、零值和大数。**Action**: '
               '生成测试用例代码。”的思考过程，然后才执行具体的代码生成或修改动作。',
    'adaptation': '冷小北可在现有的`TaskExecutor`或类似模块中，引入一个轻量的“思考-行动”观察循环。核心改动是：在执行主要动作（如调用LLM生成代码、读取文件）前，先强制要求输出一个简短的、结构化的思考段落（如“分析输入 '
                  '-> 规划步骤 -> 预期输出”），并将此段落记录到任务日志中。这无需改变核心LLM接口，只需在任务执行流程中添加一个预处理和记录步骤。',
    'goal': '在src/learned_capabilities.py的TaskExecutor类中，添加一个轻量的预处理方法，在执行主要动作前生成并记录结构化思考段落到任务日志。',
    'created_at': 1779435836.963768}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779436706',
    'topic': '自主学习 Claude Code 的计划执行、工具调用反馈和长任务汇报体验，并提炼一个可落地改进',
    'source': 'Claude Code',
    'capability': '工具调用反馈增强',
    'pattern': '在工具调用过程中，自动提供实时状态更新、参数确认和结果摘要，并集成错误处理和日志记录',
    'adaptation': '在冷小北现有的工具调用函数中添加一个轻量级反馈包装器，用于记录调用前后状态并输出结构化日志，无需重写核心逻辑',
    'goal': '在 src/learned_capabilities.py 的工具调用函数中，添加一个轻量级反馈包装器，记录调用前后状态并输出结构化日志，以增强反馈和调试能力。',
    'created_at': 1779436706.440206}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779437577',
    'topic': '自主学习 OpenHands 的任务拆解、工作区执行和错误恢复能力，并提炼一个可落地改进',
    'source': 'OpenHands',
    'capability': '错误恢复能力',
    'pattern': '在工作区执行任务时，实时监控错误输出，使用预训练模型分析错误类型，并执行预设恢复动作如重试、参数调整或代码修补',
    'adaptation': '在冷小北的现有任务执行流程中插入一个轻量级错误恢复层，通过配置文件定义常见错误的恢复策略，实现模块化集成',
    'goal': '在 src/learned_capabilities.py '
            '中添加一个轻量级错误恢复模块，通过配置文件定义常见错误策略，监控任务执行输出并自动应用恢复动作如重试或参数调整，以增强适应性而不修改现有架构。',
    'created_at': 1779437577.495528}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779438419',
    'topic': '自主学习 Aider 的 git 感知代码修改、最小补丁和提交前验证能力，并提炼一个可落地改进',
    'source': 'Aider',
    'capability': 'Git-Aware Minimal Patch Generation',
    'pattern': 'Aider uses Git API to detect repository state, analyze file diffs, and generate '
               'precise minimal patches that only modify necessary code lines, integrated with '
               'context-aware changes.',
    'adaptation': 'Leng Xiaobei can add a lightweight module to read Git status and diffs, then '
                  'optimize code modification workflows to output only essential patches, starting '
                  'with small integration tests.',
    'goal': '在 src/learned_capabilities.py 中添加一个函数，用于读取 Git 状态并分析文件差异，生成仅修改必要代码行的最小补丁，以优化修改工作流。',
    'created_at': 1779438419.808214}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779442634',
    'topic': '自主学习 Continue 的 IDE 上下文、代码库索引和开发者交互设计能力，并提炼一个可落地改进',
    'source': 'GitHub Copilot',
    'capability': '上下文感知建议更新',
    'pattern': '在IDE中实时监听代码上下文变化，并基于代码库索引和开发者交互历史，动态更新和提供相关代码建议。',
    'adaptation': '冷小北可以先在IDE集成模块中添加事件监听器，捕获代码变更事件，然后连接到一个简单的代码库索引服务，提供基本的上下文建议功能，通过小步测试和回滚确保稳定性。',
    'goal': '在 src/active_learner.py 中新增函数 provide_context_suggestion，根据输入代码上下文字符串返回相关代码建议或 '
            'None，以模拟上下文感知建议更新功能',
    'created_at': 1779442634.791339}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779444884',
    'topic': '新增一个自我反思工具模块，用于分析系统日志、工具调用历史和用户反馈，以识别设计模式中的问题，并在用户询问时输出具体建议',
    'source': 'self_reflection',
    'capability': '诊断设计缺陷',
    'pattern': '在 src/critic.py 中添加一个函数 '
               'diagnose_design_defects()，用于分析系统日志、工具调用历史和用户反馈，识别设计模式中的问题，并在用户询问时输出具体建议',
    'adaptation': '[\'在 src/critic.py 中定义 diagnose_design_defects 函数，并实现日志、历史和反馈的读取与分析逻辑。\', "在 '
                  'src/learned_capabilities.py 中注册新能力 \'diagnose_design_defects\'，以便系统在用户询问时调用。", '
                  "'通过入口如 lx_web.py 或 daemon.py 集成该函数，确保在需要时触发自我反思。']",
    'goal': '在 src/critic.py 中新增函数 diagnose_design_defects，用于分析系统日志、工具调用历史和用户反馈，识别设计模式中的问题并输出具体建议',
    'created_at': 1779444884.2732108}
)

LEARNED_CAPABILITIES.append(
{   'id': 'lesson_1779463833',
    'topic': '参考优秀 Agent 控制台设计，改进冷小北 Web 界面的可用性、状态反馈和按钮交互',
    'source': 'ChatGPT',
    'capability': '状态反馈与按钮交互优化',
    'pattern': '在响应生成时显示加载动画（如旋转图标），并为交互按钮（如复制、编辑）提供即时视觉反馈（如颜色变化或短暂动画）。',
    'adaptation': '冷小北可先在 Web 界面中添加一个简单的 CSS 加载动画，然后优化 JavaScript 中按钮事件的处理，以实现即时反馈。',
    'goal': '在 src/learned_capabilities.py 中新增函数 toggle_loading_indicator，用于在响应生成时切换加载动画的显示状态',
    'created_at': 1779463833.064218}
)
