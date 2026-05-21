"""
Tool Registry — 动态工具注册中心
================================
管理所有可用工具，包括预定义工具和运行时生成的工具。

设计原则：
- 工具即函数：每个工具是一个可调用对象
- 动态发现：运行时自动发现新工具
- 能力声明：每个工具自描述其能力和参数
"""

import os
import sys
import json
import importlib
import importlib.util
import requests
from pathlib import Path
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime


# ============================================================================
# 联网配置
# ============================================================================

SEARXNG_BASE_URL = os.environ.get("SEARXNG_BASE_URL", "")
SEARXNG_API_KEY = os.environ.get("SEARXNG_API_KEY", "")


@dataclass
class ToolSpec:
    """工具规格说明"""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema 格式
    returns: str
    examples: List[str]
    author: str  # "builtin" | "generated" | "user"
    created_at: str
    version: str = "1.0"

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ToolManifest:
    """工具治理声明 — 每个工具注册时必须提供"""
    risk: str = "medium"              # low | medium | high | critical
    requires_approval: bool = False   # 是否需要用户审批
    parallel_safe: bool = True        # 是否可并行执行
    timeout: int = 30                 # 默认超时(秒)
    max_retries: int = 2              # 最大重试次数
    output_compress: bool = False     # 输出是否需要压缩
    side_effects: List[str] = field(default_factory=list)  # 副作用: filesystem|network|process
    schema: Dict[str, Any] = field(default_factory=dict)    # 参数 JSON Schema

    def to_dict(self) -> Dict:
        return asdict(self)


# ---- 内置工具的治理 manifest ----

BUILTIN_MANIFESTS: Dict[str, ToolManifest] = {
    "search_code": ToolManifest(
        risk="low", requires_approval=False, parallel_safe=True, timeout=10,
        side_effects=[], output_compress=True,
        schema={"type": "object", "properties": {
            "pattern": {"type": "string", "description": "搜索模式"},
            "path": {"type": "string", "description": "搜索路径", "default": "."},
        }, "required": ["pattern"]},
    ),
    "read_file": ToolManifest(
        risk="low", requires_approval=False, parallel_safe=True, timeout=10,
        side_effects=[],
        schema={"type": "object", "properties": {
            "file_path": {"type": "string", "description": "文件路径"},
            "limit": {"type": "integer", "description": "读取行数", "default": 50},
        }, "required": ["file_path"]},
    ),
    "write_file": ToolManifest(
        risk="high", requires_approval=True, parallel_safe=False, timeout=30,
        side_effects=["filesystem"],
        schema={"type": "object", "properties": {
            "file_path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "写入内容"},
        }, "required": ["file_path", "content"]},
    ),
    "run_command": ToolManifest(
        risk="high", requires_approval=True, parallel_safe=False, timeout=30,
        side_effects=["filesystem", "process", "network"],
        schema={"type": "object", "properties": {
            "command": {"type": "string", "description": "Shell 命令"},
            "timeout": {"type": "integer", "description": "超时(秒)", "default": 30},
        }, "required": ["command"]},
    ),
    "web_search": ToolManifest(
        risk="low", requires_approval=False, parallel_safe=True, timeout=15,
        side_effects=["network"], output_compress=True,
        schema={"type": "object", "properties": {
            "query": {"type": "string", "description": "搜索查询"},
        }, "required": ["query"]},
    ),
    "web_fetch": ToolManifest(
        risk="medium", requires_approval=False, parallel_safe=True, timeout=15,
        side_effects=["network"], output_compress=True,
        schema={"type": "object", "properties": {
            "url": {"type": "string", "description": "网页 URL"},
        }, "required": ["url"]},
    ),
}


@dataclass
class Tool:
    """工具对象"""
    spec: ToolSpec
    func: Callable
    manifest: Optional[ToolManifest] = None
    source_file: Optional[str] = None
    author: Optional[str] = None

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def needs_approval(self) -> bool:
        return self.manifest.requires_approval if self.manifest else False

    def risk_level(self) -> str:
        return self.manifest.risk if self.manifest else "unknown"


class ToolRegistry:
    """
    工具注册中心
    
    功能：
    1. 注册/注销工具
    2. 发现匹配工具
    3. 动态加载生成的工具
    4. 工具元数据管理
    """
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.tools_dir = self.project_root / "generated_tools"
        self.tools_dir.mkdir(exist_ok=True)
        
        # 工具存储
        self._tools: Dict[str, Tool] = {}
        self._capabilities: Dict[str, List[str]] = {}  # 能力 -> 工具名列表
        
        # 初始化：加载内置工具
        self._load_builtin_tools()
        
        # 加载已生成的工具
        self._load_generated_tools()
    
    def _load_builtin_tools(self):
        """加载预定义工具（含治理 manifest）"""
        builtin_tools = [
            ("search_code", self._search_code_tool),
            ("read_file", self._read_file_tool),
            ("write_file", self._write_file_tool),
            ("run_command", self._run_command_tool),
            ("web_search", self._web_search_tool),
            ("web_fetch", self._web_fetch_tool),
        ]

        for name, func in builtin_tools:
            spec = self._infer_spec_from_func(func, name)
            manifest = BUILTIN_MANIFESTS.get(name)
            self.register(Tool(spec=spec, func=func, manifest=manifest, author="builtin"))
    
    def _infer_spec_from_func(self, func: Callable, name: str) -> ToolSpec:
        """从函数推断工具规格"""
        doc = func.__doc__ or ""
        lines = doc.strip().split('\n')
        description = lines[0] if lines else f"工具: {name}"
        
        # 简单解析参数（实际应该用 inspect）
        import inspect
        sig = inspect.signature(func)
        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
            param_info = {"type": "string", "description": f"参数: {param_name}"}
            if param.default != inspect.Parameter.empty:
                param_info["default"] = str(param.default)
            else:
                parameters["required"].append(param_name)
            parameters["properties"][param_name] = param_info
        
        return ToolSpec(
            name=name,
            description=description,
            parameters=parameters,
            returns="string",
            examples=[],
            author="builtin",
            created_at=datetime.now().isoformat()
        )
    
    def _load_generated_tools(self):
        """从 generated_tools 目录加载动态生成的工具"""
        if not self.tools_dir.exists():
            return
        
        for tool_file in self.tools_dir.glob("tool_*.py"):
            try:
                self._load_tool_from_file(tool_file)
            except Exception as e:
                print(f"  ⚠️  加载工具失败 {tool_file.name}: {e}")
    
    def _load_tool_from_file(self, file_path: Path):
        """从文件加载单个工具"""
        module_name = file_path.stem
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        
        # 添加到 sys.modules 以便模块内部导入正常工作
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        # 查找工具函数和规格
        if hasattr(module, 'TOOL_SPEC') and hasattr(module, 'run'):
            tool_spec = ToolSpec(**module.TOOL_SPEC)
            tool = Tool(spec=tool_spec, func=module.run, source_file=str(file_path))
            self.register(tool)
            print(f"  ✅ 加载工具: {tool_spec.name}")
    
    def register(self, tool: Tool) -> bool:
        """
        注册新工具
        
        Returns:
            bool: 是否注册成功
        """
        name = tool.spec.name
        
        # 检查名称冲突
        if name in self._tools:
            print(f"  ⚠️  工具 '{name}' 已存在，跳过")
            return False
        
        self._tools[name] = tool
        
        # 索引能力
        capabilities = self._extract_capabilities(tool.spec.description)
        for cap in capabilities:
            if cap not in self._capabilities:
                self._capabilities[cap] = []
            self._capabilities[cap].append(name)
        
        return True
    
    def unregister(self, name: str) -> bool:
        """注销工具"""
        if name not in self._tools:
            return False
        
        tool = self._tools.pop(name)
        
        # 从能力索引中移除
        capabilities = self._extract_capabilities(tool.spec.description)
        for cap in capabilities:
            if cap in self._capabilities and name in self._capabilities[cap]:
                self._capabilities[cap].remove(name)
        
        return True
    
    def get(self, name: str) -> Optional[Tool]:
        """获取指定工具"""
        return self._tools.get(name)
    
    def find_tools(self, query: str, limit: int = 3) -> List[Tool]:
        """
        根据查询找到最匹配的工具
        
        简单实现：关键词匹配
        未来：使用向量相似度
        """
        query_lower = query.lower()
        scores = []
        
        # 定义关键词到工具的映射
        keyword_mapping = {
            "搜索": ["search_code", "web_search"],
            "查找": ["search_code", "web_search"],
            "search": ["search_code", "web_search"],
            "grep": ["search_code"],
            "联网": ["web_search", "web_fetch"],
            "网上": ["web_search", "web_fetch"],
            "网络": ["web_search", "web_fetch"],
            "google": ["web_search"],
            "读取": ["read_file"],
            "查看": ["read_file"],
            "read": ["read_file"],
            "cat": ["read_file"],
            "网页": ["web_fetch"],
            "抓取": ["web_fetch"],
            "fetch": ["web_fetch"],
            "写入": ["write_file"],
            "修改": ["write_file"],
            "write": ["write_file"],
            "执行": ["run_command"],
            "运行": ["run_command"],
            "run": ["run_command"],
            "command": ["run_command"],
        }
        
        for name, tool in self._tools.items():
            score = 0
            desc_lower = tool.spec.description.lower()
            
            # 名称匹配权重高
            if query_lower in name.lower():
                score += 10
            
            # 描述匹配
            if query_lower in desc_lower:
                score += 5
            
            # 关键词映射匹配（高权重）
            for keyword, tool_names in keyword_mapping.items():
                if keyword in query_lower and name in tool_names:
                    score += 15
            
            # 关键词匹配
            query_words = set(query_lower.split())
            desc_words = set(desc_lower.split())
            score += len(query_words & desc_words) * 2
            
            if score > 0:
                scores.append((score, tool))
        
        # 按分数排序，返回前 N 个
        scores.sort(key=lambda x: x[0], reverse=True)
        return [tool for _, tool in scores[:limit]]
    
    def has_tool_for(self, query: str) -> bool:
        """检查是否有工具可以处理该查询"""
        tools = self.find_tools(query, limit=1)
        return len(tools) > 0 and len(tools[0].spec.description) > 0
    
    def list_tools(self) -> List[Dict]:
        """列出所有工具"""
        return [tool.spec.to_dict() for tool in self._tools.values()]

    def list_risks(self) -> Dict[str, List[str]]:
        """按风险等级分组列出工具"""
        groups: Dict[str, List[str]] = {"low": [], "medium": [], "high": [], "critical": []}
        for name, tool in self._tools.items():
            level = tool.risk_level()
            groups.setdefault(level, []).append(name)
        return groups

    def get_manifest(self, name: str) -> Optional[ToolManifest]:
        """获取工具的治理 manifest"""
        tool = self._tools.get(name)
        return tool.manifest if tool else None
    
    def _extract_capabilities(self, description: str) -> List[str]:
        """从描述中提取能力关键词"""
        # 简单实现：提取描述中的动词和名词
        words = description.lower().split()
        capabilities = []
        
        # 常见能力关键词
        keywords = [
            "search", "read", "write", "run", "execute",
            "calculate", "analyze", "fetch", "send", "get",
            "查询", "搜索", "读取", "写入", "执行", "计算", "分析",
            "web", "internet", "online", "联网", "网络"
        ]
        
        for word in words:
            clean = word.strip(",.!?;:\"'()[]{}`")
            if clean in keywords:
                capabilities.append(clean)
        
        return capabilities if capabilities else ["general"]
    
    def save_tool_metadata(self):
        """保存工具元数据到文件"""
        metadata = {
            "tools": self.list_tools(),
            "capabilities": self._capabilities,
            "updated_at": datetime.now().isoformat()
        }
        
        meta_file = self.tools_dir / "_registry.json"
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    # ========================================================================
    # 内置工具实现
    # ========================================================================
    
    def _search_code_tool(self, pattern: str, path: str = ".") -> str:
        """在代码库中搜索匹配模式的内容"""
        import subprocess
        try:
            result = subprocess.run(
                ["grep", "-r", "-n", pattern, path],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout if result.stdout else f"未找到匹配: {pattern}"
        except Exception as e:
            return f"搜索失败: {e}"
    
    def _read_file_tool(self, file_path: str, offset: int = 1, limit: int = 50) -> str:
        """读取文件内容"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                start = max(0, offset - 1)
                end = min(len(lines), start + limit)
                content = ''.join(lines[start:end])
                return f"{file_path} (L{start+1}-L{end}):\n```\n{content}\n```"
        except Exception as e:
            return f"读取失败: {e}"
    
    def _write_file_tool(self, file_path: str, content: str) -> str:
        """写入文件内容"""
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"已写入: {file_path}"
        except Exception as e:
            return f"写入失败: {e}"
    
    def _run_command_tool(self, command: str, timeout: int = 30) -> str:
        """执行系统命令"""
        import shlex
        import subprocess
        from .hard_boundary import BoundaryResult
        from .executor import SafetyGate

        try:
            # 安全检查
            assessment = SafetyGate.assess(command)
            if assessment == BoundaryResult.FORBIDDEN:
                return f"命令被拒绝: 安全门控判定为禁止执行"
            if assessment == BoundaryResult.NEEDS_CONFIRMATION:
                return f"命令需确认: 安全门控判定该命令需要宿主确认"

            # 安全拆分命令，不使用 shell=True
            try:
                args = shlex.split(command)
            except ValueError as e:
                return f"命令解析失败，拒绝执行: {e}"

            result = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            output = result.stdout if result.stdout else result.stderr
            return f"退出码: {result.returncode}\n{output}"
        except Exception as e:
            return f"执行失败: {e}"

    # ========================================================================
    # 联网工具实现（集成 SearXNG 自建搜索）
    # ========================================================================

    def _web_search_tool(
        self,
        query: str,
        count: int = 5,
        language: str = "zh-CN",
        time_range: str = "",
    ) -> str:
        """使用 SearXNG 搜索互联网，返回标题/URL/摘要"""
        if not SEARXNG_BASE_URL or not SEARXNG_API_KEY:
            return "联网搜索未配置 (SEARXNG_BASE_URL / SEARXNG_API_KEY)"
        try:
            params = {
                "q": query,
                "format": "json",
                "language": language,
                "count": min(count, 30),
            }
            if time_range:
                params["time_range"] = time_range

            headers = {"X-API-Key": SEARXNG_API_KEY}

            resp = requests.get(
                f"{SEARXNG_BASE_URL}/search",
                params=params,
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if not results:
                return f"未找到与「{query}」相关的搜索结果。"

            lines = [f"🔍 搜索「{query}」共 {len(results)} 条结果：\n"]
            for i, r in enumerate(results[:count], 1):
                title = r.get("title", "无标题")
                url = r.get("url", "")
                content = r.get("content", "")[:200]
                lines.append(
                    f"{i}. {title}\n"
                    f"   📎 {url}\n"
                    f"   💬 {content}\n"
                )
            return "\n".join(lines)

        except requests.RequestException as e:
            return f"搜索失败: {e}"

    def _web_fetch_tool(
        self,
        url: str,
        max_chars: int = 3000,
    ) -> str:
        """抓取网页正文内容，自动剥离HTML标签提取文本"""
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; LengXiaobei/1.0; "
                    "+https://github.com/panhao)"
                )
            }
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            raw_len = len(resp.text)

            content = self._extract_text_from_html(resp.text, max_chars)

            return (
                f"[页面] {url}\n"
                f"[长度] {raw_len} 字符\n\n"
                f"{content}"
            )
        except requests.RequestException as e:
            return f"网页抓取失败: {e}"

    def _extract_text_from_html(self, html: str, max_chars: int) -> str:
        """从HTML中提取纯文本内容"""
        text = html
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "meta", "link", "noscript"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
        except ImportError:
            import re
            text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"&[a-z]+;", " ", text)
            text = re.sub(r"\s+", " ", text).strip()

        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n...（已截断，全部 {len(text)} 字符）"
        return text
