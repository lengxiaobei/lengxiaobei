"""
KAIROS 系统监控与代码分析模块
"""

import os
import ast
import json
import time
from typing import Dict, List

from ..llm import chat


def monitor_system(state, config, daily_log):
    """监控系统性能"""
    try:
        import psutil
        cpu_usage = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        state.system_metrics = {
            'cpu_usage': cpu_usage,
            'memory_usage': memory.percent,
            'disk_usage': disk.percent,
            'response_time': 0.0
        }

        state.performance_issues = []
        if cpu_usage > config.performance_threshold:
            state.performance_issues.append(f"CPU 使用率过高: {cpu_usage:.1f}%")

        state.memory_issues = []
        if memory.percent > config.memory_threshold:
            state.memory_issues.append(f"内存使用率过高: {memory.percent:.1f}%")

        if state.performance_issues or state.memory_issues:
            issues = state.performance_issues + state.memory_issues
            daily_log.append_entry_sync(
                "system_alert",
                f"系统性能问题: {'; '.join(issues)}"
            )
    except Exception as e:
        print(f"[KAIROS] Failed to monitor system: {e}")


def analyze_code(state, config, daily_log, project_root, memory, generate_specific_suggestion_fn,
                 get_file_modification_count_fn, is_recently_processed_fn):
    """分析代码复杂度和潜在问题"""
    try:
        print("[KAIROS] Analyzing code...")
        state.code_issues = []
        state.code_complexity = {}
        analysis_results = []

        src_dir = project_root / "src"
        for py_file in src_dir.rglob("*.py"):
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    code = f.read()

                lines_count = code.count('\n') + 1
                functions = code.count('def ')
                classes = code.count('class ')
                complexity_val = functions + classes * 2

                relative_path = str(py_file.relative_to(project_root))
                state.code_complexity[relative_path] = complexity_val

                modification_count = get_file_modification_count_fn(relative_path)
                recently_processed = is_recently_processed_fn(relative_path, days=1)

                analysis_results.append({
                    'file_path': relative_path,
                    'complexity': complexity_val,
                    'modification_count': modification_count,
                    'recently_processed': recently_processed
                })

                if complexity_val > config.complexity_threshold and not recently_processed:
                    state.code_issues.append(f"代码复杂度高: {relative_path} ({complexity_val})")
                    state.pending_improvements.append({
                        'file_path': relative_path,
                        'type': 'complexity',
                        'description': f"代码复杂度高: {relative_path} ({complexity_val})",
                        'suggestion': generate_specific_suggestion_fn(relative_path),
                        'severity': 'high' if complexity_val > 80 else 'medium',
                        'priority': 'high' if complexity_val > 80 else 'medium'
                    })
            except Exception as e:
                print(f"[KAIROS] Failed to analyze {py_file}: {e}")

        print(f"[KAIROS] 代码分析结果:")
        print(f"[KAIROS] 分析文件数: {len(analysis_results)}")
        high_cplx = [r for r in analysis_results if r['complexity'] > 80]
        medium_cplx = [r for r in analysis_results if 50 < r['complexity'] <= 80]
        print(f"[KAIROS] 高复杂度文件: {len(high_cplx)}")
        print(f"[KAIROS] 中等复杂度文件: {len(medium_cplx)}")

        sorted_files = sorted(analysis_results, key=lambda x: x['complexity'], reverse=True)[:5]
        print(f"[KAIROS] 复杂度最高的5个文件:")
        for i, f_info in enumerate(sorted_files, 1):
            print(f"[KAIROS]   {i}. {f_info['file_path']} - 复杂度: {f_info['complexity']}")

        if state.code_issues:
            daily_log.append_entry_sync(
                "code_alert",
                f"代码问题: {'; '.join(state.code_issues[:3])}"
            )

        state.last_code_analysis = time.time()
    except Exception as e:
        print(f"[KAIROS] Failed to analyze code: {e}")


def analyze_code_quality(project_root, calculate_complexity_fn):
    """分析核心文件代码质量"""
    issues = []
    try:
        core_files = [
            os.path.join(project_root, 'src', 'core.py'),
            os.path.join(project_root, 'src', 'autonomous_evolution.py'),
            os.path.join(project_root, 'src', 'kairos.py')
        ]
        for file_path in core_files:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    code = f.read()
                tree = ast.parse(code)
                functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
                for func in functions:
                    complexity_val = calculate_complexity_fn(func)
                    if complexity_val > 10:
                        issues.append(f"函数 {func.name} 复杂度过高: {complexity_val}")
    except Exception as e:
        print(f"[KAIROS] Code analysis failed: {e}")
    return issues


def calculate_complexity(node):
    """计算函数复杂度"""
    complexity_val = 1
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)):
            complexity_val += 1
        elif isinstance(child, ast.FunctionDef):
            complexity_val += calculate_complexity(child)
    return complexity_val


def get_file_modification_count(memory, file_path: str) -> int:
    try:
        if hasattr(memory, 'search'):
            modifications = memory.search(f"修改文件 {file_path}", limit=100)
            return len(modifications)
    except Exception as e:
        print(f"[KAIROS] Failed to get file modification count: {e}")
    return 0


def is_recently_processed(memory, file_path: str, days: int = 1) -> bool:
    try:
        if hasattr(memory, 'search'):
            recent_evolutions = memory.search("进化成功完成", limit=50)
            time_threshold = time.time() - (days * 24 * 3600)
            for evolution in recent_evolutions:
                content = evolution.get('content', '')
                timestamp = evolution.get('timestamp', 0)
                if timestamp > time_threshold and file_path in content:
                    return True
    except Exception as e:
        print(f"[KAIROS] Failed to check if file was recently processed: {e}")
    return False


def generate_specific_suggestion(file_path):
    """通过 LLM 生成具体的修复建议"""
    if file_path == "unknown":
        return "考虑拆分成多个小函数，提高代码可读性和可维护性"

    file_name = file_path.split("/")[-1]

    prompt = f"""你是代码重构专家。请为以下文件生成一条具体、可操作的改进建议。

文件路径: {file_path}
文件名: {file_name}

要求:
- 建议应具体到函数名和拆分方案
- 考虑文件的用途和功能领域
- 如果合适，可以建议使用特定编程语言重构

返回JSON: {{"suggestion": "具体建议文本"}}
只返回JSON。"""

    try:
        response = chat(prompt, system="你是代码重构专家。只返回JSON。", temperature=0.3)
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(response[json_start:json_end])
            suggestion = data.get("suggestion", "")
            if suggestion:
                return suggestion
    except Exception:
        pass

    return f"将 {file_name} 中的大函数拆分为多个小函数，提高代码可读性和可维护性"


def llm_analyze_system_metrics(metrics: Dict) -> List[Dict]:
    """通过 LLM 分析系统指标并生成改进点"""
    cpu = metrics.get('cpu_usage', 0)
    mem = metrics.get('memory_usage', 0)
    disk = metrics.get('disk_usage', 0)

    prompt = f"""你是系统性能分析专家。请分析以下系统指标并生成改进建议。

系统指标:
- CPU使用率: {cpu:.1f}%
- 内存使用率: {mem:.1f}%
- 磁盘使用率: {disk:.1f}%

判断原则:
- CPU > 80% 需要关注性能优化
- 内存 > 80% 需要关注内存管理
- 磁盘 > 90% 需要关注清理
- 资源使用正常时不需要生成改进点

返回JSON:
{{
    "improvements": [
        {{"type": "performance", "issues": ["CPU使用率偏高，建议优化..."], "priority": "high"}}
    ]
}}
如果资源正常，返回空数组。只返回JSON。"""

    try:
        response = chat(prompt, system="你是系统性能分析AI。只返回JSON。", temperature=0.2)
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(response[json_start:json_end])
            return data.get("improvements", [])
    except Exception:
        pass

    result = []
    if cpu > 80:
        result.append({'type': 'performance', 'issues': ['CPU使用率过高'], 'priority': 'high'})
    if mem > 80:
        result.append({'type': 'performance', 'issues': ['内存使用率过高'], 'priority': 'high'})
    if disk > 90:
        result.append({'type': 'maintenance', 'issues': ['磁盘空间不足'], 'priority': 'high'})
    return result