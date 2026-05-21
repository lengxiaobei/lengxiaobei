"""
模型路由控制系统 - 照搬 Claude Code 设计
==========================================
核心特性：
- 根据任务类型动态选择模型
- 基于输入内容分析选择模型
- 模型性能和成本平衡
- 可配置的路由策略

参考 Claude Code 的模型路由控制实现
"""

import re
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Union


# ============================================================================
# 模型定义
# ============================================================================

@dataclass
class ModelInfo:
    """模型信息"""
    name: str
    context_window: int
    cost_per_1k: float
    speed: float  # 1-10，10 最快
    capabilities: List[str]
    max_output_tokens: Optional[int] = None
    is_default: bool = False


@dataclass
class ModelRoute:
    """模型路由"""
    pattern: str  # 正则表达式模式
    model_name: str
    priority: int = 10  # 优先级，数字越小优先级越高
    description: Optional[str] = None


@dataclass
class ModelRouterConfig:
    """模型路由器配置"""
    models: List[ModelInfo]
    routes: List[ModelRoute]
    default_model: str
    min_context_window: Optional[int] = None
    max_cost_per_query: Optional[float] = None


# ============================================================================
# 模型路由器
# ============================================================================

class ModelRouter:
    """模型路由器"""
    
    def __init__(self, config: ModelRouterConfig):
        self.config = config
        self._compile_routes()
        self._validate_config()
    
    def _compile_routes(self):
        """编译路由正则表达式"""
        self.compiled_routes = []
        for route in self.config.routes:
            try:
                pattern = re.compile(route.pattern, re.IGNORECASE)
                self.compiled_routes.append((pattern, route.model_name, route.priority))
            except re.error as e:
                print(f"Invalid route pattern {route.pattern}: {e}")
        
        # 按优先级排序
        self.compiled_routes.sort(key=lambda x: x[2])
    
    def _validate_config(self):
        """验证配置"""
        # 检查默认模型是否存在
        model_names = [m.name for m in self.config.models]
        if self.config.default_model not in model_names:
            raise ValueError(f"Default model {self.config.default_model} not found in models")
        
        # 检查路由中的模型是否存在
        for route in self.config.routes:
            if route.model_name not in model_names:
                raise ValueError(f"Model {route.model_name} in route not found in models")
    
    def route(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        根据提示和上下文选择模型
        
        Args:
            prompt: 提示内容
            context: 上下文信息
        
        Returns:
            模型名称
        """
        # 1. 首先根据路由规则选择模型
        for pattern, model_name, _ in self.compiled_routes:
            if pattern.search(prompt):
                # 检查模型是否满足上下文窗口要求
                if self._check_context_window(model_name, context):
                    return model_name
        
        # 2. 根据输入分析选择模型
        model_name = self._analyze_input(prompt, context)
        if model_name:
            return model_name
        
        # 3. 返回默认模型
        return self.config.default_model
    
    def _check_context_window(self, model_name: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """检查模型上下文窗口是否满足要求"""
        if not context:
            return True
        
        # 查找模型信息
        model_info = next((m for m in self.config.models if m.name == model_name), None)
        if not model_info:
            return False
        
        # 检查上下文长度
        context_length = context.get('context_length', 0)
        return model_info.context_window >= context_length
    
    def _analyze_input(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """根据输入分析选择模型"""
        # 分析提示长度
        prompt_length = len(prompt)
        
        # 分析提示内容
        analysis = self._analyze_prompt_content(prompt)
        
        # 根据分析结果选择模型
        for model in self.config.models:
            # 检查上下文窗口
            if self.config.min_context_window and model.context_window < self.config.min_context_window:
                continue
            
            # 检查成本
            if self.config.max_cost_per_query:
                estimated_cost = self._estimate_cost(prompt_length, model)
                if estimated_cost > self.config.max_cost_per_query:
                    continue
            
            # 检查能力
            if self._check_capabilities(model, analysis):
                return model.name
        
        return None
    
    def _analyze_prompt_content(self, prompt: str) -> Dict[str, Any]:
        """分析提示内容"""
        analysis = {
            'length': len(prompt),
            'has_code': bool(re.search(r'```[\s\S]*?```', prompt)),
            'has_json': bool(re.search(r'\{[\s\S]*?\}', prompt)),
            'has_xml': bool(re.search(r'<[a-zA-Z]+[\s\S]*?>[\s\S]*?</[a-zA-Z]+>', prompt)),
            'is_technical': bool(re.search(r'(code|program|debug|fix|implement|algorithm)', prompt, re.IGNORECASE)),
            'is_creative': bool(re.search(r'(write|story|poem|creative|imagine)', prompt, re.IGNORECASE)),
            'is_analytical': bool(re.search(r'(analyze|analyses|analysis|evaluate|assess)', prompt, re.IGNORECASE)),
        }
        
        return analysis
    
    def _check_capabilities(self, model: ModelInfo, analysis: Dict[str, Any]) -> bool:
        """检查模型能力是否满足需求"""
        capabilities = model.capabilities
        
        # 检查技术能力
        if analysis['is_technical'] and 'code' not in capabilities:
            return False
        
        # 检查创意能力
        if analysis['is_creative'] and 'creative' not in capabilities:
            return False
        
        # 检查分析能力
        if analysis['is_analytical'] and 'analytical' not in capabilities:
            return False
        
        # 检查代码能力
        if analysis['has_code'] and 'code' not in capabilities:
            return False
        
        # 检查 JSON 能力
        if analysis['has_json'] and 'json' not in capabilities:
            return False
        
        return True
    
    def _estimate_cost(self, prompt_length: int, model: ModelInfo) -> float:
        """估算成本"""
        # 简单估算：假设输出长度是输入长度的 1.5 倍
        total_tokens = prompt_length * 2.5  # 保守估计
        return (total_tokens / 1000) * model.cost_per_1k
    
    def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        """获取模型信息"""
        return next((m for m in self.config.models if m.name == model_name), None)
    
    def get_default_model(self) -> str:
        """获取默认模型"""
        return self.config.default_model
    
    def update_routes(self, routes: List[ModelRoute]):
        """更新路由规则"""
        self.config.routes = routes
        self._compile_routes()
    
    def add_route(self, route: ModelRoute):
        """添加路由规则"""
        self.config.routes.append(route)
        self._compile_routes()


# ============================================================================
# 预设模型和路由
# ============================================================================

DEFAULT_MODELS = [
    ModelInfo(
        name="claude-3-opus-20240229",
        context_window=200000,
        cost_per_1k=0.015,
        speed=7,
        capabilities=["code", "creative", "analytical", "json", "xml"],
        max_output_tokens=4096,
        is_default=True
    ),
    ModelInfo(
        name="claude-3-sonnet-20240229",
        context_window=200000,
        cost_per_1k=0.003,
        speed=8,
        capabilities=["code", "creative", "analytical", "json"],
        max_output_tokens=4096
    ),
    ModelInfo(
        name="claude-3-haiku-20240307",
        context_window=200000,
        cost_per_1k=0.00025,
        speed=10,
        capabilities=["code", "json"],
        max_output_tokens=4096
    ),
    ModelInfo(
        name="gpt-4-turbo",
        context_window=128000,
        cost_per_1k=0.01,
        speed=6,
        capabilities=["code", "creative", "analytical", "json", "xml"],
        max_output_tokens=4096
    ),
    ModelInfo(
        name="gpt-3.5-turbo",
        context_window=16000,
        cost_per_1k=0.0015,
        speed=9,
        capabilities=["code", "json"],
        max_output_tokens=4096
    )
]

DEFAULT_ROUTES = [
    ModelRoute(
        pattern=r'\b(code|program|debug|fix|implement|algorithm|syntax|compile|error|bug)\b',
        model_name="claude-3-opus-20240229",
        priority=1,
        description="Technical coding tasks"
    ),
    ModelRoute(
        pattern=r'\b(write|story|poem|creative|imagine|fiction|novel|poetry)\b',
        model_name="claude-3-opus-20240229",
        priority=2,
        description="Creative writing tasks"
    ),
    ModelRoute(
        pattern=r'\b(analyze|analyses|analysis|evaluate|assess|review|critique)\b',
        model_name="claude-3-opus-20240229",
        priority=3,
        description="Analytical tasks"
    ),
    ModelRoute(
        pattern=r'\b(json|xml|yaml|config|schema)\b',
        model_name="claude-3-sonnet-20240229",
        priority=4,
        description="Structured data tasks"
    ),
    ModelRoute(
        pattern=r'\b(quick|fast|summary|brief|simple)\b',
        model_name="claude-3-haiku-20240307",
        priority=5,
        description="Quick and simple tasks"
    )
]


# ============================================================================
# 核心功能
# ============================================================================

def create_model_router(
    models: Optional[List[ModelInfo]] = None,
    routes: Optional[List[ModelRoute]] = None,
    default_model: Optional[str] = None,
    min_context_window: Optional[int] = None,
    max_cost_per_query: Optional[float] = None
) -> ModelRouter:
    """
    创建模型路由器
    
    Args:
        models: 模型列表
        routes: 路由规则列表
        default_model: 默认模型
        min_context_window: 最小上下文窗口
        max_cost_per_query: 每查询最大成本
    
    Returns:
        模型路由器实例
    """
    # 使用默认值
    if not models:
        models = DEFAULT_MODELS
    
    if not routes:
        routes = DEFAULT_ROUTES
    
    if not default_model:
        # 找到默认模型
        default_model = next((m.name for m in models if m.is_default), models[0].name)
    
    config = ModelRouterConfig(
        models=models,
        routes=routes,
        default_model=default_model,
        min_context_window=min_context_window,
        max_cost_per_query=max_cost_per_query
    )
    
    return ModelRouter(config)


def route_model(prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
    """
    便捷函数：根据提示选择模型
    
    Args:
        prompt: 提示内容
        context: 上下文信息
    
    Returns:
        模型名称
    """
    router = create_model_router()
    return router.route(prompt, context)


def get_model_info(model_name: str) -> Optional[ModelInfo]:
    """
    便捷函数：获取模型信息
    
    Args:
        model_name: 模型名称
    
    Returns:
        模型信息
    """
    router = create_model_router()
    return router.get_model_info(model_name)


def create_model_info(
    name: str,
    context_window: int,
    cost_per_1k: float,
    speed: float,
    capabilities: List[str],
    max_output_tokens: Optional[int] = None,
    is_default: bool = False
) -> ModelInfo:
    """
    创建模型信息
    
    Args:
        name: 模型名称
        context_window: 上下文窗口大小
        cost_per_1k: 每 1000 token 的成本
        speed: 速度等级 (1-10)
        capabilities: 模型能力列表
        max_output_tokens: 最大输出 token 数
        is_default: 是否为默认模型
    
    Returns:
        模型信息实例
    """
    return ModelInfo(
        name=name,
        context_window=context_window,
        cost_per_1k=cost_per_1k,
        speed=speed,
        capabilities=capabilities,
        max_output_tokens=max_output_tokens,
        is_default=is_default
    )


def create_model_route(
    pattern: str,
    model_name: str,
    priority: int = 10,
    description: Optional[str] = None
) -> ModelRoute:
    """
    创建模型路由
    
    Args:
        pattern: 正则表达式模式
        model_name: 模型名称
        priority: 优先级
        description: 描述
    
    Returns:
        模型路由实例
    """
    return ModelRoute(
        pattern=pattern,
        model_name=model_name,
        priority=priority,
        description=description
    )
