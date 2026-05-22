"""
LLM 路由器 — Phase 1
自动选择最合适的模型

路由策略:
- 代码任务 → qwen3-coder-plus / ark-code-latest
- 强推理/思考 → qwen3.5-plus / deepseek-v3.2
- 常规对话 → MiniMax-M2.7 (快速，便宜)
- 超长上下文 → doubao-seed-2.0-pro / kimi-k2.5

优化内容:
1. 分级超时 - 根据任务复杂度动态设置超时时间
2. 动态优先级 - 根据历史性能调整模型顺序
3. 性能统计 - 记录每个模型的成功率和响应时间
4. 缓存机制 - 可配置缓存减少重复调用
5. 更好的错误分类和重试策略
"""

import os
import json
import requests
import time
import statistics
from typing import Dict, Any, List, Optional, Tuple

from .performance import measure_performance


# ============================================================================
# API Key 加载 — 三层优先级: 环境变量 > 项目配置 > OpenClaw 配置
# ============================================================================

def _load_keys() -> dict:
    """三层加载 API keys，后加载的覆盖前面的。优先级: env > project config > openclaw"""
    keys = {}

    # Tier 3: OpenClaw 配置（最低优先级）
    oc_config = os.path.expanduser("~/.openclaw/openclaw.json")
    if os.path.exists(oc_config):
        try:
            with open(oc_config) as f:
                cfg = json.load(f)
            for name, prov in cfg.get("models", {}).get("providers", {}).items():
                key = prov.get("apiKey") or prov.get("api_key") or ""
                if key:
                    keys[name] = key
        except Exception:
            pass

    # Tier 2: 项目配置文件 config/default.yaml
    try:
        import yaml
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "config", "default.yaml")
        if os.path.exists(config_path):
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            for name, prov in cfg.get("models", {}).get("providers", {}).items():
                key = prov.get("api_key", "")
                if key and key not in ("sk-xxx", "xxx", "YOUR_API_KEY"):
                    keys[name] = key
    except Exception:
        pass

    # Tier 1: 环境变量（最高优先级）
    env_key = os.environ.get("LLM_API_KEY", "")
    if env_key:
        default_provider = os.environ.get("LLM_PROVIDER", "minimax")
        keys[default_provider] = env_key

    return keys


def _load_enabled_models() -> List[str]:
    """从配置文件读取启用的模型列表"""
    try:
        import yaml
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "config", "default.yaml")
        if os.path.exists(config_path):
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            enabled = cfg.get("models", {}).get("enabled", [])
            if enabled:
                return enabled
    except Exception:
        pass
    return list(MODELS.keys())  # 全部启用


_PROVIDER_KEYS = _load_keys()
_warned_providers: set = set()


def _get_key(provider: str) -> str:
    """获取 provider API key，缺 key 时每个 provider 仅警告一次。"""
    key = _PROVIDER_KEYS.get(provider, "")
    if key:
        return key
    if provider not in _warned_providers:
        _warned_providers.add(provider)
        print(f"[LLM] 未找到 provider {provider} 的 API key（仅提示一次）")
    return ""


def has_any_key() -> bool:
    """是否有至少一个可用的 API key"""
    return any(bool(k) for k in _PROVIDER_KEYS.values())


def reload_keys():
    """重新加载 API keys（配置变更后调用）"""
    global _PROVIDER_KEYS, _warned_providers
    _PROVIDER_KEYS = _load_keys()
    _warned_providers = set()


# ============================================================================
# 模型配置
# ============================================================================
MODELS = {
    "minimax/MiniMax-M2.7": {
        "provider": "minimax",
        "base_url": "https://api.minimax.chat/v1",
        "context_window": 196608,
        "max_output": 32768,
        "strengths": ["speed", "general"],
        "cost_tier": 1,
    },
    "minimax/MiniMax-M2.7-highspeed": {
        "provider": "minimax",
        "base_url": "https://api.minimax.chat/v1",
        "context_window": 196608,
        "max_output": 32768,
        "strengths": ["speed", "general"],
        "cost_tier": 1,
    },
    "minimax/MiniMax-M2.5": {
        "provider": "minimax",
        "base_url": "https://api.minimax.chat/v1",
        "context_window": 196608,
        "max_output": 32768,
        "strengths": ["speed", "general"],
        "cost_tier": 1,
    },
    "minimax/MiniMax-M2.5-highspeed": {
        "provider": "minimax",
        "base_url": "https://api.minimax.chat/v1",
        "context_window": 196608,
        "max_output": 32768,
        "strengths": ["speed", "general"],
        "cost_tier": 1,
    },
    "volcengine/doubao-seed-2.0-pro": {
        "provider": "volcengine",
        "base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
        "context_window": 262144,
        "max_output": 65536,
        "strengths": ["long_context", "speed"],
        "cost_tier": 2,
    },
    "volcengine/deepseek-v3.2": {
        "provider": "volcengine",
        "base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
        "context_window": 262144,
        "max_output": 32768,
        "strengths": ["reasoning", "analysis"],
        "cost_tier": 2,
    },
    "volcengine/ark-code-latest": {
        "provider": "volcengine",
        "base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
        "context_window": 262144,
        "max_output": 65536,
        "strengths": ["coding"],
        "cost_tier": 2,
    },
    "bailian/qwen3.5-plus": {
        "provider": "bailian",
        "base_url": "https://coding.dashscope.aliyuncs.com/v1",
        "context_window": 1000000,
        "max_output": 65536,
        "strengths": ["reasoning", "thinking", "planning"],
        "cost_tier": 3,
    },
    "bailian/qwen3-coder-plus": {
        "provider": "bailian",
        "base_url": "https://coding.dashscope.aliyuncs.com/v1",
        "context_window": 1000000,
        "max_output": 65536,
        "strengths": ["coding", "code_generation"],
        "cost_tier": 3,
    },
    "bailian/qwen3-coder-go": {
        "provider": "bailian",
        "base_url": "https://coding.dashscope.aliyuncs.com/v1",
        "context_window": 1000000,
        "max_output": 65536,
        "strengths": ["coding", "go", "code_generation"],
        "cost_tier": 3,
    },
    "bailian/kimi-k2.5": {
        "provider": "bailian",
        "base_url": "https://coding.dashscope.aliyuncs.com/v1",
        "context_window": 262144,
        "max_output": 32768,
        "strengths": ["long_context", "multimodal"],
        "cost_tier": 3,
    },
    "bailian/glm-5": {
        "provider": "bailian",
        "base_url": "https://coding.dashscope.aliyuncs.com/v1",
        "context_window": 202752,
        "max_output": 16384,
        "strengths": ["reasoning", "analysis"],
        "cost_tier": 3,
    },
    "anthropic/claude-3-opus-20240229": {
        "provider": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "context_window": 200000,
        "max_output": 4096,
        "strengths": ["code", "creative", "analytical", "json", "xml"],
        "cost_tier": 4,
    },
    "anthropic/claude-3-sonnet-20240229": {
        "provider": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "context_window": 200000,
        "max_output": 4096,
        "strengths": ["code", "creative", "analytical", "json"],
        "cost_tier": 3,
    },
    "anthropic/claude-3-haiku-20240307": {
        "provider": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "context_window": 200000,
        "max_output": 4096,
        "strengths": ["code", "json"],
        "cost_tier": 1,
    },
}

DEFAULT_MODEL = "minimax/MiniMax-M2.7"

# ============================================================================
# 超时配置 - 分级超时根据任务类型
# ============================================================================
TIMEOUT_CONFIG = {
    "general": 60,          # 常规任务
    "coding": 180,          # 代码任务（复杂生成需要更长时间）
    "reasoning": 180,       # 推理任务
    "analysis": 240,        # 分析任务（可能需要大规模代码分析）
    "planning": 240,        # 规划任务
    "long_context": 180,    # 长上下文任务
}

# 重试配置
RETRY_CONFIG = {
    "default_max_retries": 2,
    "default_retry_delay": 2,
    "backoff_factor": 1.5,  # 指数退避因子
}

# ============================================================================
# 性能统计 - 动态优先级调整
# ============================================================================

class ModelPerformanceStats:
    """模型性能统计，用于动态调整优先级"""
    def __init__(self, max_history: int = 100):
        self.stats: Dict[str, Dict[str, Any]] = {}
        self.max_history = max_history
        self._init_stats()
    
    def _init_stats(self):
        """初始化统计数据"""
        for model_name in MODELS:
            self.stats[model_name] = {
                "total_calls": 0,
                "success_calls": 0,
                "timeouts": 0,
                "errors": 0,
                "response_times": [],
                "last_success": None,
                "consecutive_failures": 0,
            }
    
    def record_success(self, model_name: str, response_time: float):
        """记录成功调用"""
        if model_name not in self.stats:
            return
        s = self.stats[model_name]
        s["total_calls"] += 1
        s["success_calls"] += 1
        s["response_times"].append(response_time)
        s["last_success"] = time.time()
        s["consecutive_failures"] = 0
        
        # 保持历史大小
        if len(s["response_times"]) > self.max_history:
            s["response_times"] = s["response_times"][-self.max_history:]
    
    def record_timeout(self, model_name: str):
        """记录超时"""
        if model_name not in self.stats:
            return
        s = self.stats[model_name]
        s["total_calls"] += 1
        s["timeouts"] += 1
        s["consecutive_failures"] += 1
    
    def record_error(self, model_name: str):
        """记录错误"""
        if model_name not in self.stats:
            return
        s = self.stats[model_name]
        s["total_calls"] += 1
        s["errors"] += 1
        s["consecutive_failures"] += 1
    
    def get_success_rate(self, model_name: str) -> float:
        """获取成功率"""
        if model_name not in self.stats:
            return 0.0
        s = self.stats[model_name]
        if s["total_calls"] == 0:
            return 0.5  # 新模型中性评分
        return s["success_calls"] / s["total_calls"]
    
    def get_average_response_time(self, model_name: str) -> float:
        """获取平均响应时间"""
        if model_name not in self.stats:
            return 60.0
        s = self.stats[model_name]
        if not s["response_times"]:
            return 60.0
        return statistics.mean(s["response_times"])
    
    def get_score(self, model_name: str) -> float:
        """
        获取综合评分（用于排序）
        评分越高越好 = 成功率权重(0.7) + (1/平均时间)权重(0.3)
        """
        if model_name not in self.stats:
            return 0.0
        
        success_rate = self.get_success_rate(model_name)
        avg_time = self.get_average_response_time(model_name)
        
        # 如果从未成功过，给低分但保留一点机会
        if success_rate == 0:
            return 0.1
        
        # 时间评分：越快分数越高，归一化到 0-1
        time_score = 1.0 / (1.0 + avg_time / 60.0)
        
        # 综合评分
        return 0.7 * success_rate + 0.3 * time_score
    
    def get_consecutive_failures(self, model_name: str) -> int:
        """获取连续失败次数"""
        if model_name not in self.stats:
            return 0
        return self.stats[model_name]["consecutive_failures"]
    
    def get_stats_summary(self, model_name: str) -> str:
        """获取统计摘要"""
        if model_name not in self.stats:
            return f"{model_name}: 无数据"
        s = self.stats[model_name]
        sr = self.get_success_rate(model_name) * 100
        at = self.get_average_response_time(model_name)
        score = self.get_score(model_name)
        return f"{model_name}: 总调用={s['total_calls']}, 成功率={sr:.1f}%, 平均响应={at:.1f}s, 评分={score:.3f}"

# 全局统计实例
_model_stats = ModelPerformanceStats()

def get_model_stats() -> ModelPerformanceStats:
    """获取全局模型统计实例"""
    return _model_stats

# ============================================================================
# 任务分类 & 路由
# ============================================================================
def classify_task(query: str) -> list:
    """分析任务类型"""
    q = query.lower()
    cats = []
    if any(k in q for k in ["代码", "code", "bug", "python", "写程序", "排序", "算法", "函数", "class ", "编程", "实现", "refactor", "debug", "写个", "优化", "重构", "复杂度", "complexity", "改进", "improve", "优化代码", "重构代码", "代码优化", "代码重构", "进化", "evolution", "self-evolution", "自主进化"]):
        cats.append("coding")
    if any(k in q for k in ["推理", "reasoning", "为什么", "why", "逻辑", "prove", "思考", "怎么", "如何", "原因"]):
        cats.append("reasoning")
    if any(k in q for k in ["分析", "analysis", "比较", "evaluate", "研究", "评估", "review", "code review", "review"]):
        cats.append("analysis")
    if any(k in q for k in ["长文", "总结", "summarize", "大文件", "文档", "全文"]):
        cats.append("long_context")
    if any(k in q for k in ["计划", "plan", "规划", "设计", "architecture", "方案", "roadmap"]):
        cats.append("planning")
    if not cats:
        cats = ["general"]
    return cats


def _get_timeout_for_task(categories: List[str]) -> float:
    """根据任务类型获取超时时间"""
    # 使用最长的超时时间（如果有多个分类）
    max_timeout = TIMEOUT_CONFIG["general"]
    for cat in categories:
        if cat in TIMEOUT_CONFIG and TIMEOUT_CONFIG[cat] > max_timeout:
            max_timeout = TIMEOUT_CONFIG[cat]
    return max_timeout


def _predict_prompt_complexity(prompt: str) -> float:
    """根据prompt长度预测复杂度，更长的提示需要更长超时"""
    length = len(prompt)
    if length > 10000:  # 超过1万字符，增加超时
        return 1.5  # 放大系数
    elif length > 5000:
        return 1.2
    else:
        return 1.0


def get_timeout(categories: List[str], prompt: str) -> float:
    """获取最终超时时间"""
    base_timeout = _get_timeout_for_task(categories)
    complexity_factor = _predict_prompt_complexity(prompt)
    return base_timeout * complexity_factor


def _has_key(provider: str) -> bool:
    """provider 是否有有效 key"""
    key = _get_key(provider)
    return bool(key and key not in ["", "sk-...", "YOUR_API_KEY"])


def route(query: str, context_length: int = 0) -> str:
    """根据任务类型自动选择最合适的模型"""
    cats = classify_task(query)
    q = query.lower()

    # Go代码生成 → qwen3-coder-go
    if "coding" in cats and any(k in q for k in ["go", "golang", "go语言"]):
        if _has_key("bailian"):
            return "bailian/qwen3-coder-go"
    # 代码 → qwen3-coder-plus
    elif "coding" in cats:
        if _has_key("bailian"):
            return "bailian/qwen3-coder-plus"
        if _has_key("volcengine"):
            return "volcengine/ark-code-latest"
        # 如果没有代码模型，使用强推理模型
        if _has_key("bailian"):
            return "bailian/qwen3.5-plus"
        if _has_key("volcengine"):
            return "volcengine/deepseek-v3.2"

    # 强推理/规划
    if "reasoning" in cats or "planning" in cats:
        if _has_key("bailian"):
            return "bailian/qwen3.5-plus"
        if _has_key("volcengine"):
            return "volcengine/deepseek-v3.2"

    # 分析
    if "analysis" in cats:
        if _has_key("bailian"):
            return "bailian/glm-5"
        if _has_key("volcengine"):
            return "volcengine/deepseek-v3.2"

    # 超长上下文
    if "long_context" in cats or context_length > 150000:
        if _has_key("bailian"):
            return "bailian/kimi-k2.5"
        if _has_key("volcengine"):
            return "volcengine/doubao-seed-2.0-pro"

    # 默认 → 优先使用bailian模型
    if _has_key("bailian"):
        return "bailian/qwen3.5-plus"
    if _has_key("volcengine"):
        return "volcengine/deepseek-v3.2"
    # 最后才使用MiniMax
    if _has_key("minimax"):
        return DEFAULT_MODEL

    # 兜底
    return DEFAULT_MODEL


def get_candidate_models(prompt: str) -> Tuple[List[str], List[str]]:
    """
    获取候选模型列表，按性能动态排序
    
    Returns:
        (unique_models, categories)
    """
    # 获取初始模型
    initial_model = route(prompt)
    cats = classify_task(prompt)
    
    # 根据任务类型生成备选模型
    candidate_models = []
    
    if "coding" in cats:
        # 检查是否是Go相关任务
        q_lower = prompt.lower()
        if any(k in q_lower for k in ["go", "golang", "go语言"]):
            candidate_models.extend(["bailian/qwen3-coder-go", "anthropic/claude-3-opus-20240229", "anthropic/claude-3-sonnet-20240229", "bailian/qwen3-coder-plus", "volcengine/ark-code-latest"])
        else:
            candidate_models.extend(["anthropic/claude-3-opus-20240229", "anthropic/claude-3-sonnet-20240229", "bailian/qwen3-coder-plus", "volcengine/ark-code-latest", "bailian/qwen3.5-plus"])
    elif "reasoning" in cats or "planning" in cats:
        candidate_models.extend(["anthropic/claude-3-opus-20240229", "bailian/qwen3.5-plus", "anthropic/claude-3-sonnet-20240229", "volcengine/deepseek-v3.2"])
    elif "analysis" in cats:
        candidate_models.extend(["anthropic/claude-3-opus-20240229", "bailian/glm-5", "anthropic/claude-3-sonnet-20240229", "bailian/qwen3.5-plus"])
    elif "long_context" in cats:
        candidate_models.extend(["bailian/kimi-k2.5", "volcengine/doubao-seed-2.0-pro", "anthropic/claude-3-opus-20240229"])
    
    # 添加默认模型作为最后选择
    candidate_models.extend(["anthropic/claude-3-haiku-20240307", "bailian/qwen3.5-plus", "volcengine/deepseek-v3.2", "minimax/MiniMax-M2.7", "minimax/MiniMax-M2.7-highspeed", "minimax/MiniMax-M2.5", "minimax/MiniMax-M2.5-highspeed"])
    
    # 去重并确保初始模型在最前面
    unique_models = []
    seen = set()
    if initial_model not in seen:
        unique_models.append(initial_model)
        seen.add(initial_model)
    for m in candidate_models:
        if m not in seen and _has_key(MODELS[m]["provider"]):
            unique_models.append(m)
            seen.add(m)
    
    # 动态排序：根据性能评分重新排序（跳过初始模型保持原路由策略）
    # 对剩余模型按性能评分降序排列，这样成功率高响应快的优先尝试
    if len(unique_models) > 1:
        # 如果模型有连续多次失败，放到最后
        def sort_key(model_name):
            failures = _model_stats.get_consecutive_failures(model_name)
            if failures >= 3:  # 连续失败3次以上降低优先级
                return (-1, 0)  # 放到最后
            score = _model_stats.get_score(model_name)
            return (failures < 3, score)
        
        # 只重新排序除第一个外的模型
        rest = sorted(unique_models[1:], key=sort_key, reverse=True)
        unique_models = [unique_models[0]] + rest
    
    return unique_models, cats


# ============================================================================
# 缓存机制 - 减少重复调用
# ============================================================================

import threading as _threading

_response_cache_lock = _threading.Lock()
_response_cache: Dict[str, Dict[str, Any]] = {}
"""简单的内存缓存，key = (model + hash(prompt + system))"""

MAX_CACHE_SIZE = 50  # 最大缓存条目

def _get_cache_key(model: str, prompt: str, system: Optional[str]) -> str:
    """生成缓存key"""
    import hashlib
    content = f"{model}:{prompt}"
    if system:
        content += f":{system}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def get_cached_response(model: str, prompt: str, system: Optional[str]) -> Optional[str]:
    """获取缓存响应"""
    key = _get_cache_key(model, prompt, system)
    with _response_cache_lock:
        if key in _response_cache:
            entry = _response_cache[key]
            # 检查缓存是否过期（1小时过期）
            if time.time() - entry["timestamp"] > 3600:
                del _response_cache[key]
                return None
            return entry["content"]
    return None

def cache_response(model: str, prompt: str, system: Optional[str], content: str):
    """缓存响应"""
    with _response_cache_lock:
        # 如果缓存满了，删除最旧的
        if len(_response_cache) >= MAX_CACHE_SIZE:
            oldest_key = min(_response_cache.keys(), key=lambda k: _response_cache[k]["timestamp"])
            del _response_cache[oldest_key]

        key = _get_cache_key(model, prompt, system)
        _response_cache[key] = {
            "content": content,
            "timestamp": time.time(),
        }

# ============================================================================
# LLM 调用
# ============================================================================
@measure_performance
def chat(
    prompt: str,
    model: str = None,
    system: str = None,
    context: list = None,
    temperature: float = 0.7,
    max_tokens: int = None,
    use_cache: bool = True,
) -> str:
    """
    调用 LLM API

    Args:
        prompt: 用户输入
        model: 模型 ID（None = 自动路由）
        system: 系统提示词
        context: 对话历史 [(role, content), ...]
        temperature: 温度
        max_tokens: 最大输出 token
        use_cache: 是否使用缓存（默认启用）

    Returns:
        模型回复文本
    """
    # 获取候选模型列表（已按动态优先级排序）
    if model is None:
        unique_models, cats = get_candidate_models(prompt)
    else:
        unique_models = [model]
        cats = classify_task(prompt)
    
    # 计算超时时间（分级）
    timeout = get_timeout(cats, prompt)

    # 如果没有可用模型，直接返回（避免刷屏日志）
    available = [m for m in unique_models if MODELS.get(m) and _get_key(MODELS[m]["provider"])]
    if not available:
        return "[调用失败] 所有模型服务暂时不可用，请先配置至少一个 LLM provider 的 API Key"

    print(f"[LLM] 任务分类: {cats}, 可用模型: {len(available)}/{len(unique_models)}")

    # 尝试所有备选模型
    for model in available:
        cfg = MODELS[model]
        api_key = _get_key(cfg["provider"])  # 静默获取（已过滤过）

        # 检查缓存
        if use_cache:
            cached = get_cached_response(model, prompt, system)
            if cached is not None:
                return cached
        
        # 构建消息
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        if context:
            for role, content in context:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": prompt})
        
        url = f"{cfg['base_url']}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Anthropic API 使用不同的认证头和请求格式
        if cfg.get("provider") == "anthropic":
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
            del headers["Authorization"]
            url = f"{cfg['base_url']}/messages"
            payload = {
                "model": model.split("/")[-1],
                "messages": [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"],
                "temperature": temperature,
            }
            if system:
                payload["system"] = system
            if max_tokens:
                payload["max_tokens"] = max_tokens
            elif cfg.get("max_output"):
                payload["max_tokens"] = cfg["max_output"]
            if "max_tokens" not in payload:
                payload["max_tokens"] = 4096
        else:
            payload = {
                "model": model.split("/")[-1],
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens:
                payload["max_tokens"] = max_tokens
            elif cfg.get("max_output"):
                payload["max_tokens"] = cfg["max_output"]
        
        try:
            # 重试配置 - 指数退避
            max_retries = RETRY_CONFIG["default_max_retries"]
            retry_delay = RETRY_CONFIG["default_retry_delay"]
            backoff_factor = RETRY_CONFIG["backoff_factor"]
            
            for attempt in range(max_retries):
                try:
                    start_time = time.time()
                    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
                    response_time = time.time() - start_time
                    
                    # 记录成功
                    if resp.status_code == 200:
                        data = resp.json()
                        result = None
                        # OpenAI 兼容格式
                        if "choices" in data and data["choices"]:
                            result = data["choices"][0]["message"]["content"].strip()
                        # Anthropic 格式
                        elif "content" in data and data["content"]:
                            result = data["content"][0]["text"].strip()
                        if result:
                            _model_stats.record_success(model, response_time)
                            print(f"[LLM] 模型 {model} 调用成功，耗时 {response_time:.1f}秒")
                            if use_cache:
                                cache_response(model, prompt, system, result)
                            return result
                    
                    # 检查响应状态码，特别处理常见的速率限制错误
                    if resp.status_code in [429, 529]:  # 速率限制错误
                        if attempt < max_retries - 1:
                            # 使用更长的延迟来应对速率限制
                            current_delay = retry_delay * (backoff_factor ** attempt) * 5  # 速率限制时延迟更久
                            print(f"[LLM] 收到 {resp.status_code} 速率限制错误，{current_delay:.1f}秒后重试 ({attempt + 1}/{max_retries})...")
                            time.sleep(current_delay)
                            continue
                        else:
                            _model_stats.record_error(model)
                            print(f"[LLM] 模型 {model} 速率限制，尝试下一个模型...")
                            break
                    elif resp.status_code == 520 or resp.status_code >= 500:
                        # 服务器错误，重试
                        if attempt < max_retries - 1:
                            current_delay = retry_delay * (backoff_factor ** attempt)
                            print(f"[LLM] 收到 {resp.status_code} 错误，{current_delay:.1f}秒后重试 ({attempt + 1}/{max_retries})...")
                            time.sleep(current_delay)
                            continue
                        else:
                            _model_stats.record_error(model)
                            print(f"[LLM] 模型 {model} 多次失败，尝试下一个模型...")
                            break
                    elif resp.status_code >= 400:
                        # 客户端错误，通常不需要重试
                        print(f"[LLM] 收到 {resp.status_code} 客户端错误，尝试下一个模型...")
                        _model_stats.record_error(model)
                        break
                    
                    # 其他错误，抛出异常
                    resp.raise_for_status()
                    
                    # 解析响应
                    data = resp.json()
                    
                    if "choices" in data and data["choices"]:
                        result = data["choices"][0]["message"]["content"].strip()
                        _model_stats.record_success(model, response_time)
                        print(f"[LLM] 模型 {model} 调用成功，耗时 {response_time:.1f}秒")
                        if use_cache:
                            cache_response(model, prompt, system, result)
                        return result
                    _model_stats.record_error(model)
                    print(f"[LLM] 模型 {model} 响应异常，尝试下一个模型...")
                    break
                    
                except requests.exceptions.Timeout:
                    _model_stats.record_timeout(model)
                    if attempt < max_retries - 1:
                        current_delay = retry_delay * (backoff_factor ** attempt)
                        print(f"[LLM] 请求超时，{current_delay:.1f}秒后重试 ({attempt + 1}/{max_retries})...")
                        time.sleep(current_delay)
                        continue
                    else:
                        print(f"[LLM] 模型 {model} 超时，尝试下一个模型...")
                        break
                except requests.exceptions.HTTPError as e:
                    _model_stats.record_error(model)
                    error_msg = str(e)
                    if e.response is not None:
                        error_msg += f" | {e.response.text[:200]}"
                    if e.response is not None and e.response.status_code in [429, 529]:  # 速率限制
                        if attempt < max_retries - 1:
                            current_delay = retry_delay * (backoff_factor ** attempt) * 5  # 速率限制时延迟更久
                            print(f"[LLM] 速率限制错误 {e.response.status_code}：{error_msg}，{current_delay:.1f}秒后重试 ({attempt + 1}/{max_retries})...")
                            time.sleep(current_delay)
                            continue
                        else:
                            print(f"[LLM] 模型 {model} 速率限制：{error_msg}，尝试下一个模型...")
                            break
                    if attempt < max_retries - 1:
                        current_delay = retry_delay * (backoff_factor ** attempt)
                        print(f"[LLM] HTTP 错误 {e.response.status_code}：{error_msg}，{current_delay:.1f}秒后重试 ({attempt + 1}/{max_retries})...")
                        time.sleep(current_delay)
                        continue
                    else:
                        print(f"[LLM] 模型 {model} HTTP 错误：{error_msg}，尝试下一个模型...")
                        break
                except Exception as e:
                    _model_stats.record_error(model)
                    if attempt < max_retries - 1:
                        current_delay = retry_delay * (backoff_factor ** attempt)
                        print(f"[LLM] 错误: {e}，{current_delay:.1f}秒后重试 ({attempt + 1}/{max_retries})...")
                        time.sleep(current_delay)
                        continue
                    else:
                        print(f"[LLM] 模型 {model} 异常: {e}，尝试下一个模型...")
                        break
        except Exception as e:
            _model_stats.record_error(model)
            print(f"[LLM] 模型 {model} 系统异常: {e}，尝试下一个模型...")
            continue
    
    # 所有模型都失败
    return "[调用失败] 所有模型服务暂时不可用，请稍后再试"


def model_status() -> str:
    """返回所有模型的可用状态和性能统计"""
    lines = ["模型状态:"]
    for mid, cfg in MODELS.items():
        has = "✅" if _has_key(cfg["provider"]) else "❌"
        summary = _model_stats.get_stats_summary(mid)
        lines.append(f"  {has} {summary} ({cfg['provider']}, 上下文:{cfg['context_window']//1024}K)")
    return "\n".join(lines)


def get_performance_report() -> str:
    """获取详细性能报告"""
    lines = ["模型性能评分（评分越高越优先尝试）:"]
    all_models = list(MODELS.keys())
    # 按评分排序
    scored = [(m, _model_stats.get_score(m), _model_stats.get_success_rate(m), _model_stats.get_average_response_time(m)) for m in all_models if _has_key(MODELS[m]["provider"])]
    scored.sort(key=lambda x: x[1], reverse=True)
    
    for m, score, sr, art in scored:
        sr_pct = sr * 100
        lines.append(f"  {score:.3f} | {m:30s} | 成功率: {sr_pct:5.1f}% | 平均响应: {art:5.1f}s")
    
    return "\n".join(lines)


def clear_cache():
    """清空响应缓存"""
    global _response_cache
    _response_cache.clear()
    print("[LLM] 缓存已清空")


def reset_stats():
    """重置性能统计"""
    _model_stats._init_stats()
    print("[LLM] 性能统计已重置")
