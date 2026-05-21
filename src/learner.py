"""
Learner — 自主学习模块
=======================
冷小北通过研究 Claude Code 等优秀系统，
将学到的设计原则沉淀进记忆，并在行动中实践。

不是设计出来的，是学出来的。
"""

import os
import json
import time
from datetime import datetime, timedelta


class Learner:
    """
    自主学习器
    功能：
    1. study() — 学习优秀系统的设计精华，存入记忆
    2. reflect() — 周期性反思自身行为，发现改进点
    3. evolve() — 将改进写进系统行为
    """

    def __init__(self, memory):
        self.memory = memory
        self.learned_file = os.path.join(
            os.path.dirname(__file__), "..", "docs", "learned.md"
        )
        os.makedirs(os.path.dirname(self.learned_file), exist_ok=True)

    # =========================================================================
    # 学习：Claude Code 设计精华
    # =========================================================================
    def study_claude_code(self):
        """
        学习 Claude Code 公开泄露的提示词和设计精华
        核心来源：
        - Claude Code system prompt (公开泄露版本)
        - 工程化实践总结
        """
        lessons = [
            {
                "id": "cc-克制",
                "type": "design_principle",
                "title": "克制 — Less is More",
                "content": (
                    "不要添加超出要求的新功能、重构代码，或进行所谓的'改进'。"
                    "修复一个 bug 不需要顺手清理周边代码。"
                    "三行相似代码也好过一个过早抽象。"
                ),
                "action": (
                    "冷小北行动前先问：潘豪让我做的事，我有没有多做？"
                    "只做授权范围内的，不发挥。"
                ),
            },
            {
                "id": "cc-诚实",
                "type": "design_principle",
                "title": "诚实汇报 — 准确、不粉饰",
                "content": (
                    "如实汇报结果：如果测试失败，就带上输出直接说明。"
                    "输出明明失败时，绝不能声称所有测试都通过。"
                    "不把未完成说成已经完成。"
                ),
                "action": (
                    "冷小北的回复：知道就是知道，不知道就是不知道。"
                    "失败时带原始输出，不只说'出错了'。"
                ),
            },
            {
                "id": "cc-注释",
                "type": "code_principle",
                "title": "极简注释 — 命名即文档",
                "content": (
                    "默认不写注释，只在'为什么这么做'不显然时才写。"
                    "不解释'做了什么'，良好命名本身就是文档。"
                    "不删除别人的注释（可能记录了历史教训）。"
                ),
                "action": (
                    "冷小北写代码：命名清晰，注释只写'为什么'。"
                    "变量名要自解释，不靠注释解释'是什么'。"
                ),
            },
            {
                "id": "cc-风险",
                "type": "safety_principle",
                "title": "高风险操作 — 分级管控",
                "content": (
                    "用户某次批准不代表永远批准。"
                    "破坏性操作必须确认，不绕过安全检查。"
                    "暂停确认成本很低，一次误操作代价很高。"
                ),
                "action": (
                    "高风险操作（rm、git push、删除文件）必须明确问潘豪。"
                    "不默认执行，不假设上次授权=这次授权。"
                ),
            },
            {
                "id": "cc-ux",
                "type": "ux_principle",
                "title": "UX 细节 — 考虑用户实际体验",
                "content": (
                    "工具调用前不要用冒号，要用句号。"
                    "每个细节都考虑用户实际看到的体验。"
                    "不把内部状态暴露给用户。"
                ),
                "action": (
                    "冷小北的回复格式：简洁、中文优先、有结构。"
                    "等待时告知进度，不沉默。"
                ),
            },
            {
                "id": "cc-模块化",
                "type": "architecture",
                "title": "架构 — 模块化拆分",
                "content": (
                    "QueryEngine.ts 集中处理推理/Token/循环逻辑。"
                    "模块职责单一，接口清晰，不相互耦合。"
                    "子代理并行调度，守护进程持久会话。"
                ),
                "action": (
                    "冷小北的架构原则：核心极简，模块可替换。"
                    "每个模块只做一件事，做就做好。"
                ),
            },
        ]

        print(f"\n📚 学习 Claude Code 设计精华 ({len(lessons)} 条)...")

        for lesson in lessons:
            # 检查是否已学
            existing = self.memory.search(lesson["id"])
            if not existing:
                self.memory.store(
                    json.dumps(lesson, ensure_ascii=False),
                    role="system",
                    mem_type="design_principle",
                    tags=["Claude Code", lesson["id"]],
                )
                print(f"  ✅ {lesson['title']}")
            else:
                print(f"  ⏭️  {lesson['title']} (已学习)")

        # 更新已学文档
        self._update_learned_doc(lessons)

    # =========================================================================
    # 反思：周期性自我审查
    # =========================================================================
    def reflect(self, recent_messages: list):
        """
        反思近期行为，发现改进点

        触发条件：
        - 每 N 条对话后
        - 潘豪明确要求反思
        - 系统启动时
        """
        print(f"\n🤔 反思近期行为 ({len(recent_messages)} 条消息)...")

        issues = []

        # 检查1: 是否有多做的行为
        for msg in recent_messages[-5:]:
            if msg["role"] == "assistant":
                # 简单启发式检测：回复过长，可能过度发挥
                if len(msg["content"]) > 500:
                    issues.append({
                        "type": "over_engineering",
                        "hint": "回复过长，可能过度发挥了。克制。"
                    })

        if issues:
            print(f"  ⚠️  发现 {len(issues)} 个改进点")
            for issue in issues:
                self.memory.store(
                    json.dumps(issue, ensure_ascii=False),
                    role="system",
                    mem_type="self_improvement",
                    tags=["反思", issue["type"]]
                )
        else:
            print("  ✅ 未发现明显问题")

    # =========================================================================
    # 演化：将学习写进系统行为
    # =========================================================================
    def evolve(self):
        """
        将记忆中的设计原则转化为系统行为变更

        通过 Knowledge Curator 桥接，从进化历史中提取知识模式，
        并同步到 ActiveLearner，实现知识从"经验"到"可复用模式"的转化。
        """
        print(f"\n🔄 演化检查...")

        # 1. 尝试使用 Knowledge Curator 进行知识策展
        try:
            from .knowledge_curator import create_knowledge_curator

            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            curator = create_knowledge_curator(project_root)

            if curator.is_due(min_interval_hours=24):
                print("  🔍 运行知识策展 (Knowledge Curation)...")
                result = curator.run_curation()
                print(f"  ✅ 策展完成: {result['new_patterns']} 新模式, {result['consolidated']} 合并")
            else:
                print("  ⏭️  距上次策展不足 24 小时，跳过")
                dashboard = curator.get_dashboard()
                print(f"  📊 知识库: {dashboard['active']} 活跃 / {dashboard['total']} 总计 "
                      f"(健康度: {dashboard['health_score']:.1f}%)")
        except ImportError:
            print("  ⚠️  Knowledge Curator 不可用")
        except Exception as e:
            print(f"  ⚠️  策展失败: {e}")

        # 2. 从学习记录中提取演化原则
        if not os.path.exists(self.learned_file):
            print("  ⏭️  无学习记录，跳过")
            return

        with open(self.learned_file) as f:
            content = f.read()

        # 3. 将学到的原则同步到 ActiveLearner
        self._sync_principles_to_active_learner()

        # 4. 检查记忆中的反思，生成演化建议
        self._generate_evolution_suggestions()

    def _sync_principles_to_active_learner(self):
        """将学到的设计原则同步到 ActiveLearner"""
        try:
            from .active_learner import ActiveLearner, KnowledgeType

            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            learner = ActiveLearner(project_root)

            principles = [
                ("克制原则", "Less is More: 不添加超出要求的功能，三行相似代码好过一个过早抽象", "principles"),
                ("诚实原则", "如实汇报结果，不把未完成说成已完成", "principles"),
                ("极简注释", "默认不写注释，命名即文档，只在'为什么'不显然时才写", "heuristics"),
                ("风险分级", "破坏性操作必须确认，不绕过安全检查", "principles"),
                ("模块化架构", "核心极简，模块可替换，每个模块只做一件事", "patterns"),
            ]

            for title, content, ktype in principles:
                existing = [k for k in learner.knowledge.values() if title in k.content]
                if not existing:
                    learner.add_knowledge(
                        knowledge_type=KnowledgeType.PRINCIPLES if ktype == "principles"
                        else KnowledgeType.HEURISTICS if ktype == "heuristics"
                        else KnowledgeType.PATTERNS,
                        content=content,
                        source="learner/_sync_principles",
                        confidence=85.0,
                        tags=["设计原则", title],
                    )
                    print(f"  ✅ 原则已同步: {title}")

        except ImportError:
            pass
        except Exception as e:
            print(f"  ⚠️  原则同步失败: {e}")

    def _generate_evolution_suggestions(self):
        """基于记忆中的反思生成演化建议"""
        try:
            improvements = self.memory.search("self_improvement")
            if improvements:
                print(f"  💡 发现 {len(improvements)} 条待改进记录")
                for imp in improvements[:3]:
                    print(f"    - {imp[:80]}...")
        except Exception:
            pass

    # =========================================================================
    # 辅助
    # =========================================================================
    def _update_learned_doc(self, lessons: list):
        """更新已学文档"""
        lines = [
            "# 已学习的设计原则",
            "",
            f"_更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
            "",
            "## Claude Code 设计精华",
            "",
        ]

        for lesson in lessons:
            lines.append(f"### {lesson['title']}")
            lines.append(f'''```\n{lesson['content']}\n```''')
            lines.append(f"**冷小北行动准则**: {lesson['action']}")
            lines.append("")

        with open(self.learned_file, "w") as f:
            f.write("\n".join(lines))
