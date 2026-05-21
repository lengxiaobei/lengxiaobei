"""Evolution configuration and LLM helpers."""
import os
import json
from typing import List, Optional
from ..config import config_manager

def _get_project_llm_models() -> List[str]:
    """从项目 config.json 的 llm 配置中读取模型列表"""
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            llm_cfg = cfg.get("llm", {})
            model = llm_cfg.get("model", "")
            if model:
                print(f"[Evolution] 使用项目配置的 LLM 模型: {model}")
                return [model]
    except Exception:
        pass
    fallback = ["MiniMax-M2.7", "qwen3.5-plus", "deepseek-v3.2", "qwen3-coder-plus"]
    print(f"[Evolution] 使用默认 LLM 模型列表: {fallback}")
    return fallback


def _call_claude_code(prompt: str, project_root: str = None) -> Optional[str]:
    """尝试调用 Claude Code，失败返回 None"""
    if project_root is None:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from ..integration import create_integration_manager
        integration_manager = create_integration_manager(project_root)
        if integration_manager.is_claude_code_available():
            result = integration_manager.call_claude_code("llm_chat", prompt=prompt)
            if result.get("success"):
                return result.get("stdout", "")
    except Exception:
        pass
    return None


class Config:
    """配置管理器"""
    _cache = {}

    @classmethod
    def get_llm_models(cls):
        """从配置文件获取LLM模型列表"""
        if "llm_models" not in cls._cache:
            config_models = config_manager.get("evolution.llm_models", None)
            if config_models is None:
                config_models = _get_project_llm_models()
            # 不再做硬编码映射，让 llm.chat 自己处理模型路由
            cls._cache["llm_models"] = config_models
        return cls._cache["llm_models"]

    @classmethod
    def get_team_roles(cls):
        """从配置文件获取团队角色"""
        if "team_roles" not in cls._cache:
            cls._cache["team_roles"] = config_manager.get("evolution.team_roles", [
                ("architect", "架构师", "你是一位资深软件架构师,擅长分析代码架构问题并提供专业建议。"),
                ("generator", "开发者", "你是一位经验丰富的软件开发者,擅长编写高质量代码和实施解决方案。"),
                ("critic", "批评者", "你是一位严谨的代码审查者,擅长发现代码中的问题和潜在风险。"),
                ("tester", "测试者", "你是一位专业的软件测试工程师,擅长设计测试用例和验证代码质量。")
            ])
        return cls._cache["team_roles"]

    @classmethod
    def get_max_code_length(cls):
        """获取最大代码长度限制"""
        if "max_code_length" not in cls._cache:
            cls._cache["max_code_length"] = config_manager.get("evolution.max_code_length", 10000)
        return cls._cache["max_code_length"]

    @classmethod
    def get_max_json_parse_attempts(cls):
        """获取JSON解析最大尝试次数"""
        if "max_json_parse_attempts" not in cls._cache:
            cls._cache["max_json_parse_attempts"] = config_manager.get("evolution.max_json_parse_attempts", 3)
        return cls._cache["max_json_parse_attempts"]

    @classmethod
    def get_max_problems_to_show(cls):
        """获取显示问题的最大数量"""
        if "max_problems_to_show" not in cls._cache:
            cls._cache["max_problems_to_show"] = config_manager.get("evolution.max_problems_to_show", 10)
        return cls._cache["max_problems_to_show"]

    @classmethod
    def get_default_confidence(cls):
        """获取默认置信度"""
        if "default_confidence" not in cls._cache:
            cls._cache["default_confidence"] = config_manager.get("evolution.default_confidence", 0.7)
        return cls._cache["default_confidence"]

    @classmethod
    def get_autonomy_level(cls):
        """获取自主等级:low=需要确认, medium=高风险沙箱, high=完全自主"""
        if "autonomy_level" not in cls._cache:
            cls._cache["autonomy_level"] = config_manager.get("evolution.autonomy_level", "medium")
        return cls._cache["autonomy_level"]

    @classmethod
    def get_auto_approve(cls):
        """自主进化是否非交互审批。默认开启，由安全边界和验证链兜底。"""
        if "auto_approve" not in cls._cache:
            cls._cache["auto_approve"] = bool(config_manager.get("evolution.auto_approve", True))
        return cls._cache["auto_approve"]
