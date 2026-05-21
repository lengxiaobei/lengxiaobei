"""SkillsStore — 知识库持久化

将每次成功进化的经验沉淀为可复用的知识。
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class SkillsStore:
    """进化知识库 — 持久化成功经验"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.skills_dir = self.project_root / "skills" / "evolution"
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        improvement: Dict[str, Any],
        proposal: Any,
        source_code: str,
        new_code: str,
        test_result: Any,
    ):
        """记录一次成功的进化"""
        timestamp = datetime.now()
        date_str = timestamp.strftime("%Y-%m-%d")
        file_path = improvement.get("file", "unknown").replace("/", "_").replace(".py", "")
        issue = improvement.get("issue", "unknown")[:30].replace("/", "_")

        skill_filename = f"{date_str}_{file_path}_{issue}.md"
        if len(skill_filename) > 80:
            skill_filename = f"{date_str}_{file_path}.md"

        skill_path = self.skills_dir / skill_filename

        lines = source_code.split("\n") if source_code else []
        new_lines = new_code.split("\n") if new_code else []
        added = len(new_lines) - len(lines)

        content = f"""# Skill: {improvement.get('issue', '代码改进')}

## 时间
{timestamp.strftime('%Y-%m-%d %H:%M:%S')}

## 问题
{improvement.get('issue', '未知')}

## 类型
- 类型: {improvement.get('type', 'code_quality')}
- 优先级: {improvement.get('priority', 'medium')}
- 严重程度: {improvement.get('severity', 'minor')}

## 方案
策略: {getattr(proposal, 'strategy', 'N/A')}

方法: {getattr(proposal, 'approach', 'N/A')}

步骤:
{chr(10).join(f'- {s}' for s in getattr(proposal, 'steps', []))}

## 变更
- 修改文件: {improvement.get('file', 'unknown')}
- 变更行数: +{max(0, added)} / -{max(0, -added)}

## 验证
{self._format_test_result(test_result)}

## 经验
此次进化成功实施了代码改进。具体经验需要在后续实践中继续积累。
"""

        skill_path.write_text(content, encoding="utf-8")
        logger.info(f"[SkillsStore] 知识已保存: {skill_filename}")
        self._update_index()

    def load_context(self, max_skills: int = 10) -> str:
        """加载知识库上下文供 Curator 使用"""
        skill_files = sorted(
            [f for f in self.skills_dir.glob("*.md") if f.name != "INDEX.md"],
            reverse=True,
        )[:max_skills]

        if not skill_files:
            return "暂无历史进化记录。"

        parts = []
        for sf in skill_files:
            try:
                content = sf.read_text(encoding="utf-8")[:1500]
                parts.append(content)
            except Exception:
                pass

        return "\n\n---\n\n".join(parts)

    def _update_index(self):
        """更新知识库索引"""
        index_path = self.skills_dir / "INDEX.md"

        skill_files = sorted(
            [f for f in self.skills_dir.glob("*.md") if f.name != "INDEX.md"],
            reverse=True,
        )

        lines = [
            "# 进化知识库索引",
            "",
            "> 记录每次成功进化的经验，为 Curator 的全局审查提供历史上下文。",
            "",
            "## 进化记录",
            "",
        ]

        if skill_files:
            for sf in skill_files:
                name = sf.stem
                mtime = datetime.fromtimestamp(sf.stat().st_mtime)
                lines.append(f"- **[{name}]({sf.name})** — {mtime.strftime('%Y-%m-%d %H:%M')}")
        else:
            lines.append("暂无记录。成功进化后自动追加。")

        lines.extend(["", "---", "", "*本索引由 Curator 自动维护*"])
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _format_test_result(test_result) -> str:
        lines = []
        if test_result:
            passed = getattr(test_result, "passed", 0)
            failed = getattr(test_result, "failed", 0)
            errors = getattr(test_result, "errors", 0)
            lines.append(f"- 测试通过: {passed}")
            lines.append(f"- 测试失败: {failed}")
            lines.append(f"- 测试错误: {errors}")
            output = getattr(test_result, "output", "")
            if output:
                lines.append(f"\n```\n{output[:1000]}\n```")
        else:
            lines.append("- 未执行测试")
        return "\n".join(lines)