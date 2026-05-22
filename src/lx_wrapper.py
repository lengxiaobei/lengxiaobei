#!/usr/bin/env python3
"""
冷小北入口包装模块
统一入口，委托给 src.core.LengXiaobei
"""

import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.core import LengXiaobei as _LengXiaobei

# 直接导出，不再保留 mock 回退
LengXiaobei = _LengXiaobei

__all__ = ["LengXiaobei"]
