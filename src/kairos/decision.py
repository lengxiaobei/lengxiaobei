"""
KAIROS 自主决策引擎
"""

import time
import asyncio
from typing import Dict, List


def make_decision(state, config, daily_log, on_evolution_trigger,
                  gather_observations_fn, evaluate_observations_fn,
                  make_informed_decision_fn, trigger_evolution_fn,
                  trigger_optimization_fn, trigger_learning_fn,
                  record_decision_fn, active_monitoring_fn):
    """自主决策是否触发进化 - 主动循环模式"""
    try:
        now = time.time()
        state.last_decision_time = now

        if now - state.last_evolution_time < config.evolution_cooldown:
            active_monitoring_fn()
            return

        observations = gather_observations_fn()
        evaluation = evaluate_observations_fn(observations)
        decision = make_informed_decision_fn(evaluation)

        if decision['action'] == 'evolve':
            state.pending_improvements = decision['improvements']
            trigger_evolution_fn()
        elif decision['action'] == 'optimize':
            trigger_optimization_fn(decision['targets'])
        elif decision['action'] == 'learn':
            trigger_learning_fn(decision['topics'])

        record_decision_fn(decision, evaluation)
    except Exception as e:
        print(f"[KAIROS] Failed to make decision: {e}")


def active_monitoring(state, daily_log, memory):
    """主动监控系统状态"""
    if hasattr(memory, 'conn'):
        try:
            cursor = memory.conn.execute("SELECT COUNT(*) FROM memories")
            count = cursor.fetchone()[0]
            usage = min(count / 1000 * 100, 100)
            if usage > 80:
                daily_log.append_entry_sync(
                    "system_alert",
                    f"记忆系统使用率过高: {usage:.1f}%"
                )
        except Exception as e:
            print(f"[KAIROS] Failed to check memory stats: {e}")


def gather_observations(state, get_historical_decisions_fn, get_memory_insights_fn):
    """收集观察数据"""
    return {
        'system_metrics': state.system_metrics,
        'performance_issues': state.performance_issues,
        'memory_issues': state.memory_issues,
        'code_issues': state.code_issues,
        'uptime': time.time() - state.start_time,
        'idle_time': time.time() - state.last_interaction_time,
        'historical_decisions': get_historical_decisions_fn(),
        'memory_insights': get_memory_insights_fn()
    }


def evaluate_observations(observations, generate_specific_suggestion_fn, calculate_decision_success_rate_fn):
    """评估观察数据"""
    evaluation = {
        'needs_evolution': False,
        'needs_optimization': False,
        'needs_learning': False,
        'improvements': [],
        'optimization_targets': [],
        'learning_topics': []
    }

    if observations['performance_issues']:
        evaluation['needs_evolution'] = True
        evaluation['improvements'].append({
            'type': 'performance',
            'issues': observations['performance_issues'],
            'priority': 'high'
        })

    if observations['memory_issues']:
        evaluation['needs_evolution'] = True
        evaluation['improvements'].append({
            'type': 'memory',
            'issues': observations['memory_issues'],
            'priority': 'high'
        })

    if observations['code_issues']:
        evaluation['needs_evolution'] = True
        for issue in observations['code_issues']:
            file_path = "unknown"
            if ":" in issue:
                parts = issue.split(":")
                if len(parts) > 1:
                    file_path = parts[1].strip().split(" ")[0]
            suggestion = generate_specific_suggestion_fn(file_path)
            evaluation['improvements'].append({
                'file_path': file_path,
                'type': 'code',
                'description': issue,
                'suggestion': suggestion,
                'severity': 'medium',
                'priority': 'medium'
            })

    if observations['uptime'] > 3600 * 24:
        evaluation['needs_evolution'] = True
        evaluation['improvements'].append({
            'type': 'maintenance',
            'issues': ['系统运行时间过长，需要维护'],
            'priority': 'low'
        })

    if observations['historical_decisions']:
        success_rate = calculate_decision_success_rate_fn(observations['historical_decisions'])
        if success_rate < 0.7:
            evaluation['needs_learning'] = True
            evaluation['learning_topics'].append('决策策略优化')

    if observations['memory_insights']:
        for insight in observations['memory_insights']:
            if '优化' in insight.get('content', '') or '改进' in insight.get('content', ''):
                evaluation['needs_optimization'] = True
                evaluation['optimization_targets'].append(insight['content'])

    return evaluation


def make_informed_decision(evaluation):
    """基于评估结果做出决策"""
    decision = {
        'action': 'monitor',
        'improvements': [],
        'targets': [],
        'topics': []
    }

    if evaluation['needs_evolution']:
        decision['action'] = 'evolve'
        decision['improvements'] = evaluation['improvements']
    elif evaluation['needs_optimization']:
        decision['action'] = 'optimize'
        decision['targets'] = evaluation['optimization_targets']
    elif evaluation['needs_learning']:
        decision['action'] = 'learn'
        decision['topics'] = evaluation['learning_topics']

    return decision


def get_memory_stats(memory):
    if hasattr(memory, 'conn'):
        try:
            cursor = memory.conn.execute("SELECT COUNT(*) FROM memories")
            count = cursor.fetchone()[0]
            return {'count': count, 'usage': min(count / 1000 * 100, 100)}
        except Exception:
            pass
    return {'count': 0, 'usage': 0}


def get_historical_decisions(memory):
    try:
        if hasattr(memory, 'search'):
            decisions = memory.search("KAIROS决策", limit=10)
            return decisions
    except Exception:
        pass
    return []


def get_memory_insights(memory):
    try:
        if hasattr(memory, 'search'):
            insights = memory.search("优化 OR 改进 OR 学习", limit=5)
            return insights
    except Exception:
        pass
    return []


def calculate_decision_success_rate(historical_decisions):
    if not historical_decisions:
        return 1.0
    success_count = sum(1 for d in historical_decisions if '成功' in d.get('content', ''))
    return success_count / len(historical_decisions)