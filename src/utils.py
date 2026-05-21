"""
公共工具模块 — JSON 解析、原子写入、CRUD 基类
==============================================

消除 goal_system / motivation_system / self_assessment / llm_client 中的重复逻辑。
"""

import json
import os
import logging
import threading
import time
from typing import Dict, Any, List, Type, TypeVar, Optional

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ============================================================================
# JSON 提取 — 统一替代各处 find('{')/rfind('}') 和简易花括号计数
# ============================================================================

def extract_json(text: str) -> Any:
    """
    从 LLM 响应中提取 JSON，支持 markdown fence 和嵌套对象。

    优先尝试直接解析，失败后按花括号深度匹配（跳过字符串内的花括号）。
    """
    clean = text.strip()

    # 去除 markdown fence
    if clean.startswith("```json"):
        clean = clean[7:]
    elif clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()

    # 直接解析
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # 按花括号深度提取（处理字符串内的花括号）
    start = clean.find("{")
    if start == -1:
        # 尝试数组
        start = clean.find("[")
        if start != -1:
            try:
                return json.loads(clean[start:])
            except json.JSONDecodeError:
                pass
        raise json.JSONDecodeError("No JSON object found", clean, 0)

    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(clean)):
        c = clean[i]
        if escape_next:
            escape_next = False
            continue
        if c == "\\":
            escape_next = True
            continue
        if c == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(clean[start : i + 1])
                except json.JSONDecodeError:
                    break

    # 最后尝试：从第一个 { 到最后一个 }
    end = clean.rfind("}")
    if end > start:
        try:
            return json.loads(clean[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("Unclosed JSON object", clean, start)


# ============================================================================
# 原子写入 — 先写临时文件再 rename，防止写入中断导致数据丢失
# ============================================================================

def atomic_write_json(path: str, data: Any, indent: int = 2, ensure_ascii: bool = False):
    """原子写入 JSON 文件"""
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
        os.replace(tmp_path, path)
    except Exception as e:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise e


def load_json(path: str, default: Any = None) -> Any:
    """安全加载 JSON 文件"""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"加载 JSON 失败 {path}: {e}")
        return default


# ============================================================================
# JSONFileStore — 轻量级 JSON 文件 CRUD 基类
# ============================================================================

class JSONFileStore:
    """
    JSON 文件持久化基类，提供 _load / _save / ID 生成 / 事务支持。

    子类只需定义：
      - self._file_path: str
      - self._items: Dict[str, <item>]
      - item_class: Type  (有 from_dict / to_dict 方法)
    """

    def __init__(self):
        self._id_counter: int = 0
        self._backup: Dict = {}
        self._transaction_active: bool = False
        self._lock = threading.Lock()

    def _next_id(self) -> str:
        with self._lock:
            self._id_counter += 1
            return str(self._id_counter)

    def _sync_id_counter(self, item_id: str):
        """从已有 item ID 同步计数器"""
        if item_id.isdigit():
            with self._lock:
                self._id_counter = max(self._id_counter, int(item_id))

    def _load_items(self, path: str, item_class: Type[T], key_field: str = "id") -> Dict[str, T]:
        """从 JSON 文件加载 items"""
        data = load_json(path, default=[])
        items = {}
        if isinstance(data, list):
            for item_data in data:
                try:
                    obj = item_class.from_dict(item_data)
                    key = getattr(obj, key_field)
                    items[key] = obj
                    if key.isdigit():
                        self._sync_id_counter(key)
                except Exception as e:
                    logger.warning(f"加载条目失败: {e}")
        return items

    def _save_items(self, path: str, items: Dict[str, Any]):
        """原子写入 items 到 JSON 文件"""
        data = [v.to_dict() for v in items.values()]
        atomic_write_json(path, data)

    # ---- 事务支持 ----

    def _start_transaction(self):
        import copy
        self._backup = copy.deepcopy(self._items) if hasattr(self, '_items') else {}
        self._transaction_active = True

    def _commit_transaction(self):
        self._backup.clear()
        self._transaction_active = False

    def _rollback_transaction(self):
        if hasattr(self, '_items'):
            self._items = self._backup
        self._backup = {}
        self._transaction_active = False
