"""
Skills 技能系统 — 照搬 Claude Code 设计
====================================
核心功能：
- 模块化的技能管理和扩展
- 支持内置技能和自定义技能
- 技能的注册、加载和执行
- 与系统的深度集成
"""

import os
import json
import importlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, AsyncGenerator


# ============================================================================# 技能基类# ============================================================================

@dataclass
class Skill:
    """技能基类"""
    name: str  # 技能名称
    description: str  # 技能描述
    when_to_use: str  # 使用时机
    user_invocable: bool = True  # 是否可由用户调用
    is_enabled: Callable[[], bool] = lambda: True  # 是否启用
    get_prompt: Callable[[Optional[str]], str] = lambda args: ""  # 获取提示词
    on_execute: Optional[Callable[[Dict[str, Any]], Any]] = None  # 执行回调


# ============================================================================# 技能管理器# ============================================================================

class SkillManager:
    """
    技能管理器
    功能：
    1. 注册和管理技能
    2. 加载内置技能和自定义技能
    3. 执行技能
    4. 技能发现和搜索
    5. 集成外部系统功能
    """
    
    def __init__(self, project_root: str, integration_manager=None):
        self.project_root = Path(project_root)
        self.skills_dir = self.project_root / "skills"
        self.bundled_skills_dir = self.skills_dir / "bundled"
        self.skills_dir.mkdir(exist_ok=True)
        self.bundled_skills_dir.mkdir(exist_ok=True)
        
        # 技能存储
        self.skills: Dict[str, Skill] = {}
        
        # 集成管理器
        self.integration_manager = integration_manager
        
        # 加载内置技能
        self._load_bundled_skills()
        # 加载自定义技能
        self._load_custom_skills()
        # 加载外部系统技能
        if self.integration_manager:
            self._load_external_skills()
    
    def _load_bundled_skills(self):
        """加载内置技能"""
        # 内置技能
        bundled_skills = [
            self._create_remember_skill(),
            self._create_verify_skill(),
            self._create_loop_skill(),
            self._create_stuck_skill(),
            self._create_debug_skill()
        ]
        
        for skill in bundled_skills:
            self.register_skill(skill)
    
    def _load_custom_skills(self):
        """加载自定义技能"""
        # 扫描 skills 目录下的自定义技能
        for skill_file in self.skills_dir.glob("*.py"):
            if skill_file.name == "__init__.py":
                continue
        
            try:
                # 动态导入技能
                module_name = f"skills.{skill_file.stem}"
                module = importlib.import_module(module_name)
                
                # 检查模块是否有 register_skill 函数
                if hasattr(module, "register_skill"):
                    module.register_skill(self)
            except Exception as e:
                print(f"[Skills] 加载自定义技能失败 {skill_file.name}: {e}")
    
    def register_skill(self, skill: Skill):
        """注册技能"""
        self.skills[skill.name] = skill
        print(f"[Skills] 注册技能: {skill.name}")
    
    def unregister_skill(self, name: str):
        """注销技能"""
        if name in self.skills:
            del self.skills[name]
            print(f"[Skills] 注销技能: {name}")
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """获取技能"""
        return self.skills.get(name)
    
    def list_skills(self) -> List[str]:
        """列出所有技能"""
        return list(self.skills.keys())
    
    def search_skills(self, query: str) -> List[str]:
        """搜索技能"""
        results = []
        for name, skill in self.skills.items():
            if query.lower() in name.lower() or query.lower() in skill.description.lower():
                results.append(name)
        return results
    
    async def execute_skill(self, name: str, args: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> Any:
        """执行技能"""
        skill = self.get_skill(name)
        if not skill:
            print(f"[Skills] 技能不存在: {name}")
            return None
        
        if not skill.is_enabled():
            print(f"[Skills] 技能未启用: {name}")
            return None
        
        print(f"[Skills] 执行技能: {name}")
        
        # 获取提示词
        prompt = skill.get_prompt(args)
        
        if skill.on_execute:
            # 使用自定义执行回调
            return await skill.on_execute(context or {"prompt": prompt, "args": args})
        else:
            # 默认执行方式：调用LLM
            from .llm import chat, route
            
            response = chat(
                prompt=prompt,
                system="你是一个技能执行助手",
                model=route(prompt),
                temperature=0.3
            )
            
            return response
    
    def _create_remember_skill(self) -> Skill:
        """创建记忆技能"""
        def get_prompt(args: Optional[str]) -> str:
            prompt = """# 记忆整理

## 目标
回顾用户的记忆内容，生成清晰的整理建议，按操作类型分组。不要直接修改，而是提出建议供用户批准。

## 步骤

### 1. 收集所有记忆层
读取项目根目录的 MEMORY.md 文件（如果存在）。你的自动记忆内容已经在系统提示中 — 在那里查看。

### 2. 分类每个记忆条目
对于自动记忆中的每个实质性条目，确定最佳目的地：

| 目的地 | 适合内容 | 示例 |
|---|---|---|
| **MEMORY.md** | 项目惯例和所有贡献者应遵循的指令 | "使用 Python 3.14", "API 路由使用 kebab-case", "测试命令是 python -m pytest", "优先使用函数式风格" |
| **团队记忆** | 适用于整个组织的知识（仅当团队记忆已配置时） | "部署 PR 通过 #deploy-queue", " staging 环境在 staging.internal", "平台团队负责基础设施" |
| **保持在自动记忆中** | 工作笔记、临时上下文或不明确适合其他地方的条目 | 会话特定的观察、不确定的模式 |

### 3. 识别清理机会
扫描所有层寻找：
- **重复项**：自动记忆中已捕获在 MEMORY.md 中的条目 → 建议从自动记忆中删除
- **过时项**：被较新自动记忆条目反驳的 MEMORY.md 条目 → 建议更新较旧的层
- **冲突**：任何两层之间的矛盾 → 建议解决，注明哪个更新

### 4. 呈现报告
按操作类型分组输出结构化报告：
1. **提升** — 要移动的条目，包括目的地和理由
2. **清理** — 重复项、过时条目、需要解决的冲突
3. **歧义** — 需要用户输入目的地的条目
4. **无需操作** — 应保持不变的条目的简要说明

如果自动记忆为空，请说明并主动提出清理 MEMORY.md。

## 规则
- 在进行任何更改之前，先提出所有建议
- 未经明确用户批准，不要修改文件
- 除非目标不存在，否则不要创建新文件
- 询问歧义条目 — 不要猜测
"""
            if args:
                prompt += f"\n## 用户附加上下文\n\n{args}"
            return prompt
        
        return Skill(
            name="remember",
            description="回顾自动记忆条目并提出提升到 MEMORY.md 或共享记忆的建议。还能检测跨记忆层的过时、冲突和重复条目。",
            when_to_use="当用户想要回顾、组织或提升他们的自动记忆条目时使用。也适用于清理 MEMORY.md 中的过时或冲突条目。",
            get_prompt=get_prompt
        )
    
    def _create_verify_skill(self) -> Skill:
        """创建验证技能"""
        def get_prompt(args: Optional[str]) -> str:
            prompt = """# 验证执行

## 目标
验证给定的任务或操作是否成功完成，并提供详细的验证报告。

## 步骤

### 1. 分析任务
理解用户要求验证的具体任务或操作。

### 2. 执行验证
根据任务类型执行适当的验证步骤：
- **代码修改**：检查语法、运行测试、验证功能
- **文件操作**：确认文件存在、检查内容、验证权限
- **系统操作**：检查服务状态、验证配置、测试功能

### 3. 生成报告
提供详细的验证报告，包括：
- 验证步骤
- 发现的问题
- 成功标准
- 建议的下一步

## 规则
- 提供客观、详细的验证结果
- 不要假设成功，要实际验证
- 如果发现问题，提供具体的修复建议
"""
            if args:
                prompt += f"\n## 验证任务\n\n{args}"
            return prompt
        
        return Skill(
            name="verify",
            description="验证给定的任务或操作是否成功完成，并提供详细的验证报告。",
            when_to_use="当用户想要验证代码修改、文件操作或系统操作是否成功完成时使用。",
            get_prompt=get_prompt
        )
    
    def _create_loop_skill(self) -> Skill:
        """创建循环技能"""
        def get_prompt(args: Optional[str]) -> str:
            prompt = """# 循环执行

## 目标
对一组项目执行重复操作，直到满足条件或处理完所有项目。

## 步骤

### 1. 分析任务
理解用户要求执行的循环操作和目标项目。

### 2. 执行循环
按照用户指定的操作对每个项目执行：
- 处理单个项目
- 检查终止条件
- 继续或停止循环

### 3. 生成报告
提供循环执行的详细报告，包括：
- 处理的项目数
- 成功和失败的项目
- 执行时间
- 任何遇到的错误

## 规则
- 清晰记录循环的每次迭代
- 如果遇到错误，继续处理其他项目
- 提供详细的执行报告
"""
            if args:
                prompt += f"\n## 循环任务\n\n{args}"
            return prompt
        
        return Skill(
            name="loop",
            description="对一组项目执行重复操作，直到满足条件或处理完所有项目。",
            when_to_use="当用户需要对多个项目执行相同操作时使用，如处理文件列表、测试多个场景等。",
            get_prompt=get_prompt
        )
    
    def _create_stuck_skill(self) -> Skill:
        """创建卡住技能"""
        def get_prompt(args: Optional[str]) -> str:
            prompt = """# 解决卡住问题

## 目标
帮助用户解决他们在任务中遇到的卡住问题，提供具体的解决方案。

## 步骤

### 1. 分析问题
理解用户遇到的具体问题和上下文。

### 2. 识别原因
分析可能导致问题的原因：
- 技术障碍
- 知识 gaps
- 资源限制
- 流程问题

### 3. 提供解决方案
根据问题原因提供具体的解决方案：
- 技术解决方案
- 替代方法
- 资源建议
- 流程改进

### 4. 验证解决方案
提供验证解决方案是否有效的方法。

## 规则
- 提供具体、可操作的建议
- 考虑多种可能的解决方案
- 解释解决方案的原理
- 提供验证步骤
"""
            if args:
                prompt += f"\n## 卡住问题\n\n{args}"
            return prompt
        
        return Skill(
            name="stuck",
            description="帮助用户解决他们在任务中遇到的卡住问题，提供具体的解决方案。",
            when_to_use="当用户在任务中遇到障碍或卡住，需要帮助和解决方案时使用。",
            get_prompt=get_prompt
        )
    
    def _create_debug_skill(self) -> Skill:
        """创建调试技能"""
        def get_prompt(args: Optional[str]) -> str:
            prompt = """# 代码调试

## 目标
帮助用户调试代码问题，识别错误原因并提供修复建议。

## 步骤

### 1. 分析错误
理解用户遇到的错误信息和上下文。

### 2. 识别问题
分析可能导致错误的代码问题：
- 语法错误
- 逻辑错误
- 运行时错误
- 性能问题

### 3. 提供修复建议
根据问题类型提供具体的修复建议：
- 代码修改
- 最佳实践
- 调试技巧
- 测试建议

### 4. 验证修复
提供验证修复是否有效的方法。

## 规则
- 提供具体、可操作的修复建议
- 解释错误的根本原因
- 提供测试和验证步骤
- 考虑边界情况和最佳实践
"""
            if args:
                prompt += f"\n## 调试问题\n\n{args}"
            return prompt
        
        return Skill(
            name="debug",
            description="帮助用户调试代码问题，识别错误原因并提供修复建议。",
            when_to_use="当用户遇到代码错误或性能问题，需要帮助调试和修复时使用。",
            get_prompt=get_prompt
        )
    
    def _load_external_skills(self):
        """加载外部系统技能"""
        if not self.integration_manager:
            return
        
        # 获取可用的外部功能
        available_functions = self.integration_manager.get_available_functions()
        
        # 加载 OpenClaw 功能作为技能
        for function_name in available_functions.get("openclaw", []):
            skill_name = f"openclaw_{function_name}"
            
            def create_execute_callback(system, func):
                async def execute_callback(context):
                    args = context.get("args", "")
                    if system == "openclaw":
                        return self.integration_manager.call_openclaw(func, args=args)
                    else:
                        return self.integration_manager.call_claude_code(func, args=args)
                return execute_callback
            
            skill = Skill(
                name=skill_name,
                description=f"OpenClaw 功能: {function_name}",
                when_to_use=f"当需要使用 OpenClaw 的 {function_name} 功能时使用。",
                on_execute=create_execute_callback("openclaw", function_name)
            )
            self.register_skill(skill)
        
        # 加载 Claude Code 功能作为技能
        for function_name in available_functions.get("claude_code", []):
            skill_name = f"claude_code_{function_name}"
            
            def create_execute_callback(system, func):
                async def execute_callback(context):
                    args = context.get("args", "")
                    if system == "openclaw":
                        return self.integration_manager.call_openclaw(func, args=args)
                    else:
                        return self.integration_manager.call_claude_code(func, args=args)
                return execute_callback
            
            skill = Skill(
                name=skill_name,
                description=f"Claude Code 功能: {function_name}",
                when_to_use=f"当需要使用 Claude Code 的 {function_name} 功能时使用。",
                on_execute=create_execute_callback("claude_code", function_name)
            )
            self.register_skill(skill)


# ============================================================================# 便捷函数# ============================================================================

def create_skill_manager(project_root: str, integration_manager=None) -> SkillManager:
    """创建技能管理器"""
    return SkillManager(project_root, integration_manager)
