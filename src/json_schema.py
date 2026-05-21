"""
JSON Schema 验证系统 - 照搬 Claude Code 设计
==========================================
核心特性：
- JSON Schema 验证
- 结构化输出验证
- 错误提示和修复建议
- 支持复杂数据结构

参考 Claude Code 的 JSON Schema 验证实现
"""

import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Union

# 尝试导入 jsonschema 库
try:
    import jsonschema
    from jsonschema import validate, ValidationError, SchemaError
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    # 提供降级实现
    class ValidationError(Exception):
        pass
    
    class SchemaError(Exception):
        pass


# ============================================================================
# 类型定义
# ============================================================================

@dataclass
class SchemaValidationResult:
    """Schema 验证结果"""
    valid: bool
    errors: List[str] = field(default_factory=list)
    data: Optional[Any] = None
    schema: Optional[Dict[str, Any]] = None


@dataclass
class SchemaConfig:
    """Schema 配置"""
    strict: bool = True  # 严格模式
    allow_extra_properties: bool = False  # 是否允许额外属性
    error_message_format: str = "detailed"  # detailed | simple


# ============================================================================
# 核心功能
# ============================================================================

class JsonSchemaValidator:
    """JSON Schema 验证器"""
    
    def __init__(self, config: Optional[SchemaConfig] = None):
        self.config = config or SchemaConfig()
    
    def validate(self, data: Any, schema: Dict[str, Any]) -> SchemaValidationResult:
        """
        验证数据是否符合 Schema
        
        Args:
            data: 要验证的数据
            schema: JSON Schema
        
        Returns:
            验证结果
        """
        if not JSONSCHEMA_AVAILABLE:
            # 降级模式：简单验证
            errors = self._simple_validate(data, schema)
            if errors:
                return SchemaValidationResult(
                    valid=False,
                    errors=errors,
                    data=data,
                    schema=schema
                )
            else:
                return SchemaValidationResult(
                    valid=True,
                    data=data,
                    schema=schema
                )
        
        try:
            # 构建验证器
            validator = self._create_validator(schema)
            
            # 验证数据
            validator.validate(data)
            
            return SchemaValidationResult(
                valid=True,
                data=data,
                schema=schema
            )
        except ValidationError as e:
            errors = self._format_validation_error(e)
            return SchemaValidationResult(
                valid=False,
                errors=errors,
                data=data,
                schema=schema
            )
        except SchemaError as e:
            return SchemaValidationResult(
                valid=False,
                errors=[f"Invalid schema: {str(e)}"],
                schema=schema
            )
        except Exception as e:
            return SchemaValidationResult(
                valid=False,
                errors=[f"Validation error: {str(e)}"],
                data=data,
                schema=schema
            )
    
    def _simple_validate(self, data: Any, schema: Dict[str, Any]) -> List[str]:
        """简单验证实现（降级模式）"""
        errors = []
        
        # 验证类型
        expected_type = schema.get('type')
        if expected_type:
            if expected_type == 'string' and not isinstance(data, str):
                errors.append(f"Expected string, got {type(data).__name__}")
            elif expected_type == 'number' and not isinstance(data, (int, float)):
                errors.append(f"Expected number, got {type(data).__name__}")
            elif expected_type == 'integer' and not isinstance(data, int):
                errors.append(f"Expected integer, got {type(data).__name__}")
            elif expected_type == 'boolean' and not isinstance(data, bool):
                errors.append(f"Expected boolean, got {type(data).__name__}")
            elif expected_type == 'array' and not isinstance(data, list):
                errors.append(f"Expected array, got {type(data).__name__}")
            elif expected_type == 'object' and not isinstance(data, dict):
                errors.append(f"Expected object, got {type(data).__name__}")
        
        # 验证对象
        if isinstance(data, dict) and schema.get('type') == 'object':
            properties = schema.get('properties', {})
            required = schema.get('required', [])
            
            # 验证必需属性
            for prop_name in required:
                if prop_name not in data:
                    errors.append(f"Missing required property: {prop_name}")
            
            # 验证属性类型
            for prop_name, prop_schema in properties.items():
                if prop_name in data:
                    prop_errors = self._simple_validate(data[prop_name], prop_schema)
                    errors.extend([f"{prop_name}: {error}" for error in prop_errors])
        
        # 验证数组
        elif isinstance(data, list) and schema.get('type') == 'array':
            items_schema = schema.get('items', {})
            for i, item in enumerate(data):
                item_errors = self._simple_validate(item, items_schema)
                errors.extend([f"[i]: {error}" for error in item_errors])
        
        return errors
    
    def _create_validator(self, schema: Dict[str, Any]):
        """创建验证器"""
        if not JSONSCHEMA_AVAILABLE:
            raise RuntimeError("jsonschema library is not available")
        
        # 构建验证器配置
        validator_kwargs = {}
        
        if not self.config.allow_extra_properties:
            # 添加 additionalProperties: false 到所有对象
            schema = self._add_additional_properties_false(schema)
        
        # 使用 jsonschema 库创建验证器
        return jsonschema.Draft202012Validator(schema, **validator_kwargs)
    
    def _add_additional_properties_false(self, schema: Any) -> Any:
        """为所有对象添加 additionalProperties: false"""
        if isinstance(schema, dict):
            if schema.get('type') == 'object':
                if 'additionalProperties' not in schema:
                    schema['additionalProperties'] = False
            
            # 递归处理嵌套结构
            for key, value in schema.items():
                schema[key] = self._add_additional_properties_false(value)
        elif isinstance(schema, list):
            for i, item in enumerate(schema):
                schema[i] = self._add_additional_properties_false(item)
        
        return schema
    
    def _format_validation_error(self, error: ValidationError) -> List[str]:
        """格式化验证错误"""
        errors = []
        
        if self.config.error_message_format == "detailed":
            # 详细错误信息
            if hasattr(error, 'path'):
                errors.append(f"Validation error at '{'/'.join(map(str, error.path))}': {str(error)}")
            else:
                errors.append(f"Validation error: {str(error)}")
            if hasattr(error, 'context') and error.context:
                for ctx in error.context:
                    errors.append(f"  - {str(ctx)}")
        else:
            # 简单错误信息
            errors.append(str(error))
        
        return errors
    
    def validate_json_string(self, json_string: str, schema: Dict[str, Any]) -> SchemaValidationResult:
        """
        验证 JSON 字符串是否符合 Schema
        
        Args:
            json_string: JSON 字符串
            schema: JSON Schema
        
        Returns:
            验证结果
        """
        try:
            # 解析 JSON
            data = json.loads(json_string)
            return self.validate(data, schema)
        except json.JSONDecodeError as e:
            return SchemaValidationResult(
                valid=False,
                errors=[f"Invalid JSON: {str(e)}"],
                schema=schema
            )
    
    def generate_schema(self, data: Any) -> Dict[str, Any]:
        """
        根据数据生成 JSON Schema
        
        Args:
            data: 数据
        
        Returns:
            JSON Schema
        """
        return self._infer_schema(data)
    
    def _infer_schema(self, data: Any) -> Dict[str, Any]:
        """推断 Schema"""
        if data is None:
            return {"type": "null"}
        elif isinstance(data, bool):
            return {"type": "boolean"}
        elif isinstance(data, int):
            return {"type": "integer"}
        elif isinstance(data, float):
            return {"type": "number"}
        elif isinstance(data, str):
            return {"type": "string"}
        elif isinstance(data, list):
            if not data:
                return {"type": "array", "items": {}}
            # 推断数组项的类型
            item_schema = self._infer_schema(data[0])
            return {"type": "array", "items": item_schema}
        elif isinstance(data, dict):
            properties = {}
            for key, value in data.items():
                properties[key] = self._infer_schema(value)
            return {
                "type": "object",
                "properties": properties,
                "required": list(properties.keys())
            }
        else:
            return {}
    
    def fix_validation_errors(self, data: Any, schema: Dict[str, Any]) -> Any:
        """
        尝试修复验证错误
        
        Args:
            data: 数据
            schema: JSON Schema
        
        Returns:
            修复后的数据
        """
        # 这里实现简单的修复逻辑，实际项目中可能需要更复杂的修复策略
        return self._fix_data(data, schema)
    
    def _fix_data(self, data: Any, schema: Dict[str, Any]) -> Any:
        """修复数据"""
        if not schema:
            return data
        
        expected_type = schema.get('type')
        
        # 类型转换
        if expected_type == 'string' and not isinstance(data, str):
            return str(data)
        elif expected_type == 'number' and not isinstance(data, (int, float)):
            try:
                return float(data)
            except (ValueError, TypeError):
                return 0
        elif expected_type == 'integer' and not isinstance(data, int):
            try:
                return int(data)
            except (ValueError, TypeError):
                return 0
        elif expected_type == 'boolean' and not isinstance(data, bool):
            if data in ['true', 'True', '1', 1]:
                return True
            elif data in ['false', 'False', '0', 0]:
                return False
            else:
                return False
        elif expected_type == 'array' and not isinstance(data, list):
            return [data]
        elif expected_type == 'object' and not isinstance(data, dict):
            return {}
        
        # 处理对象
        if expected_type == 'object' and isinstance(data, dict):
            properties = schema.get('properties', {})
            required = schema.get('required', [])
            
            # 添加缺失的必需属性
            for prop_name in required:
                if prop_name not in data:
                    prop_schema = properties.get(prop_name, {})
                    data[prop_name] = self._get_default_value(prop_schema)
            
            # 处理属性
            for prop_name, prop_schema in properties.items():
                if prop_name in data:
                    data[prop_name] = self._fix_data(data[prop_name], prop_schema)
        
        # 处理数组
        elif expected_type == 'array' and isinstance(data, list):
            items_schema = schema.get('items', {})
            for i, item in enumerate(data):
                data[i] = self._fix_data(item, items_schema)
        
        return data
    
    def _get_default_value(self, schema: Dict[str, Any]) -> Any:
        """获取默认值"""
        if 'default' in schema:
            return schema['default']
        
        # 根据类型返回默认值
        expected_type = schema.get('type')
        if expected_type == 'string':
            return ''
        elif expected_type == 'number':
            return 0.0
        elif expected_type == 'integer':
            return 0
        elif expected_type == 'boolean':
            return False
        elif expected_type == 'array':
            return []
        elif expected_type == 'object':
            return {}
        else:
            return None


# ============================================================================
# 便捷函数
# ============================================================================

def create_json_schema_validator(
    strict: bool = True,
    allow_extra_properties: bool = False,
    error_message_format: str = "detailed"
) -> JsonSchemaValidator:
    """
    创建 JSON Schema 验证器
    
    Args:
        strict: 严格模式
        allow_extra_properties: 是否允许额外属性
        error_message_format: 错误消息格式
    
    Returns:
        JSON Schema 验证器实例
    """
    config = SchemaConfig(
        strict=strict,
        allow_extra_properties=allow_extra_properties,
        error_message_format=error_message_format
    )
    return JsonSchemaValidator(config)


def validate_json(data: Any, schema: Dict[str, Any]) -> SchemaValidationResult:
    """
    便捷函数：验证 JSON 数据
    
    Args:
        data: 数据
        schema: JSON Schema
    
    Returns:
        验证结果
    """
    validator = create_json_schema_validator()
    return validator.validate(data, schema)


def validate_json_string(json_string: str, schema: Dict[str, Any]) -> SchemaValidationResult:
    """
    便捷函数：验证 JSON 字符串
    
    Args:
        json_string: JSON 字符串
        schema: JSON Schema
    
    Returns:
        验证结果
    """
    validator = create_json_schema_validator()
    return validator.validate_json_string(json_string, schema)


def generate_schema(data: Any) -> Dict[str, Any]:
    """
    便捷函数：根据数据生成 JSON Schema
    
    Args:
        data: 数据
    
    Returns:
        JSON Schema
    """
    validator = create_json_schema_validator()
    return validator.generate_schema(data)


def fix_validation_errors(data: Any, schema: Dict[str, Any]) -> Any:
    """
    便捷函数：修复验证错误
    
    Args:
        data: 数据
        schema: JSON Schema
    
    Returns:
        修复后的数据
    """
    validator = create_json_schema_validator()
    return validator.fix_validation_errors(data, schema)


# ============================================================================
# 预设 Schema
# ============================================================================

# 常见的预设 Schema
PRESET_SCHEMAS = {
    "user": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "email": {"type": "string", "format": "email"},
            "age": {"type": "integer", "minimum": 0},
            "active": {"type": "boolean"}
        },
        "required": ["id", "name", "email"]
    },
    "task": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "status": {"type": "string", "enum": ["todo", "in_progress", "completed"]},
            "priority": {"type": "integer", "minimum": 1, "maximum": 5},
            "due_date": {"type": "string", "format": "date"}
        },
        "required": ["id", "title", "status"]
    },
    "product": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "price": {"type": "number", "minimum": 0},
            "stock": {"type": "integer", "minimum": 0},
            "categories": {"type": "array", "items": {"type": "string"}},
            "tags": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["id", "name", "price"]
    }
}

def get_preset_schema(name: str) -> Optional[Dict[str, Any]]:
    """
    获取预设 Schema
    
    Args:
        name: Schema 名称
    
    Returns:
        预设 Schema
    """
    return PRESET_SCHEMAS.get(name)
