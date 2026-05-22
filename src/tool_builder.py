"""
Tool Builder — 工具自动生成器
============================
当遇到未知需求时，自动生成新工具。

流程：
1. 分析需求 → 2. 生成代码 → 3. 沙盒测试 → 4. 注册工具
"""

import os
import sys
import ast
import json
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .llm import chat, route
from .tool_registry import ToolSpec


class ToolBuilder:
    """
    工具构建器
    
    核心能力：将自然语言需求转化为可执行工具
    """
    
    def __init__(self, project_root: str, registry):
        self.project_root = Path(project_root)
        self.registry = registry
        self.tools_dir = self.project_root / "generated_tools"
        self.tools_dir.mkdir(exist_ok=True)
        
        # 构建提示词模板
        self._init_prompts()
    
    def _init_prompts(self):
        """初始化提示词模板"""
        self.tool_generation_prompt = """你是一个专业的 Python 工具开发专家。

请根据以下需求，生成一个完整的 Python 工具模块。

需求描述：
{requirement}

生成要求：
1. 模块必须包含 TOOL_SPEC 字典，描述工具的元数据
2. 模块必须包含 run() 函数，作为工具的入口点
3. 代码必须健壮，包含适当的错误处理
4. 函数必须有清晰的文档字符串
5. 只使用标准库，如需第三方库请注释说明

TOOL_SPEC 格式示例：
```python
TOOL_SPEC = {{
    "name": "tool_name",
    "description": "工具的简短描述",
    "parameters": {{
        "type": "object",
        "properties": {{
            "param1": {{"type": "string", "description": "参数1的描述"}},
            "param2": {{"type": "integer", "description": "参数2的描述"}}
        }},
        "required": ["param1"]
    }},
    "returns": "string",
    "examples": ["示例用法1", "示例用法2"],
    "author": "generated",
    "created_at": "{timestamp}",
    "version": "1.0"
}}
```

请直接输出完整的 Python 代码，不要包含任何解释或 markdown 标记：
"""
    
    def analyze_need(self, query: str) -> Tuple[bool, str]:
        """
        分析需求是否需要新工具
        
        Returns:
            (是否需要新工具, 分析理由)
        """
        # 1. 先检查现有工具是否能处理
        existing_tools = self.registry.find_tools(query, limit=3)
        
        if existing_tools:
            # 有匹配的工具，检查匹配度
            best_match = existing_tools[0]
            # 简单启发式：如果描述包含查询关键词，认为可以处理
            query_words = set(query.lower().split())
            desc_words = set(best_match.spec.description.lower().split())
            overlap = query_words & desc_words
            
            if len(overlap) >= min(2, len(query_words)):
                return False, f"现有工具 '{best_match.spec.name}' 可以处理此需求"
        
        # 2. 分析需求复杂度
        # 简单查询不需要新工具
        simple_patterns = ["你好", "hi", "hello", "谢谢", "再见", "你是谁"]
        if any(p in query.lower() for p in simple_patterns):
            return False, "简单对话，不需要工具"
        
        # 3. 需要新工具的情况
        tool_indicators = [
            "计算", "查询", "搜索", "分析", "获取", "发送",
            "calculate", "search", "query", "analyze", "fetch", "send",
            "统计", "转换", "格式化", "验证", "检查"
        ]
        
        if any(ind in query.lower() for ind in tool_indicators):
            return True, "检测到可能需要工具处理的能力"
        
        return False, "无法确定是否需要新工具"
    
    def generate_tool(self, requirement: str) -> Optional[Tuple[str, ToolSpec]]:
        """
        根据需求生成工具代码
        
        Returns:
            (代码内容, ToolSpec) 或 None
        """
        print(f"\n🔨 生成工具处理需求: {requirement[:50]}...")
        
        # 构建提示词
        prompt = self.tool_generation_prompt.format(
            requirement=requirement,
            timestamp=datetime.now().isoformat()
        )
        
        # 调用 LLM 生成代码
        try:
            response = chat(
                prompt=prompt,
                system="你是一个专业的 Python 工具开发专家。只输出代码，不输出解释。",
                model=route(requirement),
                temperature=0.3,  # 低温度，更确定性
            )
            
            # 提取代码（去除可能的 markdown 标记）
            code = self._extract_code(response)
            
            # 解析 TOOL_SPEC
            tool_spec = self._extract_tool_spec(code)
            if not tool_spec:
                print("  ❌ 生成的代码缺少 TOOL_SPEC")
                return None
            
            print(f"  ✅ 生成工具: {tool_spec.name}")
            return code, tool_spec
            
        except Exception as e:
            print(f"  ❌ 生成失败: {e}")
            return None
    
    def _extract_code(self, response: str) -> str:
        """
        从 LLM 响应中提取代码
        """
        # 去除 markdown 代码块标记
        code = response.strip()
        
        # 去除  <think> 标签
        if ' <think>' in code:
            code = code.split('</think>')[-1].strip()
        
        if code.startswith("```python"):
            code = code[9:]
        elif code.startswith("```"):
            code = code[3:]
        
        if code.endswith("```"):
            code = code[:-3]
        
        return code.strip()
    
    def _extract_tool_spec(self, code: str) -> Optional[ToolSpec]:
        """
        从代码中提取 TOOL_SPEC
        """
        try:
            # 使用 ast 模块解析代码
            tree = ast.parse(code)
            
            # 查找 TOOL_SPEC 赋值语句
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "TOOL_SPEC":
                            # 提取字典内容
                            if isinstance(node.value, ast.Dict):
                                # 构建字典
                                spec_dict = {}
                                for key_node, value_node in zip(node.value.keys, node.value.values):
                                    # 提取键
                                    if isinstance(key_node, ast.Constant):
                                        key = key_node.value
                                    else:
                                        continue
                                    
                                    # 提取值
                                    if isinstance(value_node, ast.Constant):
                                        value = value_node.value
                                    elif isinstance(value_node, ast.Dict):
                                        # 处理嵌套字典
                                        def dict_from_ast(dict_node):
                                            result = {}
                                            for k, v in zip(dict_node.keys, dict_node.values):
                                                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                                                    result[k.value] = v.value
                                                elif isinstance(k, ast.Constant) and isinstance(v, ast.Dict):
                                                    result[k.value] = dict_from_ast(v)
                                                elif isinstance(k, ast.Constant) and isinstance(v, ast.List):
                                                    result[k.value] = [elem.value for elem in v.elts if isinstance(elem, ast.Constant)]
                                            return result
                                        value = dict_from_ast(value_node)
                                    elif isinstance(value_node, ast.List):
                                        # 处理列表
                                        value = [elem.value for elem in value_node.elts if isinstance(elem, ast.Constant)]
                                    else:
                                        continue
                                    
                                    spec_dict[key] = value
                                
                                if spec_dict:
                                    return ToolSpec(**spec_dict)
        except Exception as e:
            print(f"  ⚠️  解析 TOOL_SPEC 失败: {e}")
            # 打印生成的代码以便调试
            print("  生成的代码:")
            print(code)
        
        return None
    
    def validate_tool(self, code: str, tool_spec: ToolSpec) -> Tuple[bool, List[str]]:
        """
        验证生成的工具代码
        
        Returns:
            (是否有效, 问题列表)
        """
        issues = []
        
        # 1. 语法检查
        try:
            ast.parse(code)
        except SyntaxError as e:
            issues.append(f"语法错误: {e}")
            return False, issues
        
        # 2. 检查必需元素
        if "def run(" not in code:
            issues.append("缺少 run() 函数")
        
        if "TOOL_SPEC" not in code:
            issues.append("缺少 TOOL_SPEC")
        
        # 3. 安全检查
        dangerous = ["eval(", "exec(", "__import__", "os.system", "subprocess.call"]
        for d in dangerous:
            if d in code:
                issues.append(f"发现潜在危险操作: {d}")
        
        # 4. 沙盒测试
        if not issues:
            test_passed, test_issues = self._sandbox_test(code, tool_spec)
            if not test_passed:
                issues.extend(test_issues)
        
        return len(issues) == 0, issues
    
    def _sandbox_test(self, code: str, tool_spec: ToolSpec) -> Tuple[bool, List[str]]:
        """
        在沙盒中测试工具
        
        使用临时文件和子进程隔离执行
        """
        issues = []
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            # 1. 测试能否导入
            result = subprocess.run(
                [sys.executable, "-c", f"import sys; sys.path.insert(0, '{self.tools_dir}'); exec(open('{temp_file}').read()); print('IMPORT_OK')"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                issues.append(f"导入失败: {result.stderr}")
                return False, issues
            
            # 2. 测试 run 函数是否存在
            test_script = f"""
import sys
sys.path.insert(0, '{self.tools_dir}')
exec(open('{temp_file}').read())

# 检查 run 函数
if 'run' not in dir():
    print("MISSING_RUN")
    sys.exit(1)

# 尝试获取函数签名
import inspect
sig = inspect.signature(run)
print(f"RUN_SIGNATURE: {{sig}}")
print("SANDBOX_OK")
"""
            result = subprocess.run(
                [sys.executable, "-c", test_script],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if "SANDBOX_OK" not in result.stdout:
                issues.append(f"沙盒测试失败: {result.stderr or result.stdout}")
            
        except subprocess.TimeoutExpired:
            issues.append("沙盒测试超时")
        except Exception as e:
            issues.append(f"沙盒测试异常: {e}")
        finally:
            # 清理临时文件
            try:
                os.unlink(temp_file)
            except OSError:
                pass
        
        return len(issues) == 0, issues
    
    def save_tool(self, code: str, tool_spec: ToolSpec) -> str:
        """
        保存工具到文件
        
        Returns:
            文件路径
        """
        # 生成文件名
        safe_name = "".join(c if c.isalnum() else "_" for c in tool_spec.name)
        filename = f"tool_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
        filepath = self.tools_dir / filename
        
        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(code)
        
        print(f"  💾 工具已保存: {filepath}")
        return str(filepath)
    
    def build_tool(self, requirement: str) -> Optional[ToolSpec]:
        """
        完整的工具构建流程
        
        Returns:
            成功返回 ToolSpec，失败返回 None
        """
        print(f"\n🏗️  ToolBuilder: 开始构建工具")
        print(f"   需求: {requirement[:60]}...")
        
        # 1. 生成代码
        result = self.generate_tool(requirement)
        if not result:
            print("  ❌ 代码生成失败")
            return None
        
        code, tool_spec = result
        
        # 2. 验证
        valid, issues = self.validate_tool(code, tool_spec)
        if not valid:
            print(f"  ❌ 验证失败:")
            for issue in issues:
                print(f"     - {issue}")
            return None
        
        print(f"  ✅ 验证通过")
        
        # 3. 保存
        filepath = self.save_tool(code, tool_spec)
        
        # 4. 注册到 registry
        from .tool_registry import Tool
        tool = Tool(spec=tool_spec, func=None, source_file=filepath)
        self.registry.register(tool)
        
        print(f"  ✅ 工具已注册: {tool_spec.name}")
        
        return tool_spec
