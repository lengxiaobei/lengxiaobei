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
