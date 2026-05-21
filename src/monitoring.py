#!/usr/bin/env python3
"""
监控与告警系统
"""

import time
import threading
from typing import Dict, Any, List, Optional

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False

from .logging_config import get_logger, log_info, log_warning, log_error


class Monitor:
    """系统监控器"""
    
    def __init__(self, interval: int = 60):
        self.interval = interval
        self.running = False
        self.thread = None
        self.logger = get_logger('monitoring')
        self.metrics = {
            'cpu_usage': [],
            'memory_usage': [],
            'disk_usage': [],
            'network_io': [],
            'system_load': []
        }
        self.alerts = []
    
    def start(self):
        """启动监控"""
        if not HAS_PSUTIL:
            log_info(self.logger, "psutil 未安装，跳过系统监控")
            return
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._monitor_loop)
            self.thread.daemon = True
            self.thread.start()
            log_info(self.logger, "监控系统已启动")
    
    def stop(self):
        """停止监控"""
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join()
            log_info(self.logger, "监控系统已停止")
    
    def _monitor_loop(self):
        """监控循环"""
        while self.running:
            try:
                metrics = self._collect_metrics()
                self._update_metrics(metrics)
                self._check_alerts(metrics)
                time.sleep(self.interval)
            except Exception as e:
                log_error(self.logger, f"监控循环出错: {e}", exc_info=True)
                time.sleep(self.interval)
    
    def _collect_metrics(self) -> Dict[str, Any]:
        """收集系统指标"""
        if not HAS_PSUTIL:
            return {'timestamp': time.time(), 'cpu_usage': 0, 'memory_usage': 0,
                    'disk_usage': 0, 'network_io': {'bytes_sent': 0, 'bytes_recv': 0},
                    'system_load': [0, 0, 0]}
        metrics = {
            'timestamp': time.time(),
            'cpu_usage': psutil.cpu_percent(interval=1),
            'memory_usage': psutil.virtual_memory().percent,
            'disk_usage': psutil.disk_usage('/').percent,
            'network_io': {
                'bytes_sent': psutil.net_io_counters().bytes_sent,
                'bytes_recv': psutil.net_io_counters().bytes_recv
            },
            'system_load': psutil.getloadavg()
        }
        return metrics
    
    def _update_metrics(self, metrics: Dict[str, Any]):
        """更新指标历史"""
        for key, value in metrics.items():
            if key in self.metrics:
                if isinstance(value, dict):
                    # 对于网络IO等复杂指标，只保留最新值
                    self.metrics[key] = [value]
                else:
                    # 对于简单指标，保留最近10个值
                    self.metrics[key].append(value)
                    if len(self.metrics[key]) > 10:
                        self.metrics[key] = self.metrics[key][-10:]
    
    def _check_alerts(self, metrics: Dict[str, Any]):
        """检查告警条件"""
        alerts = []
        
        # CPU 使用率告警
        if metrics['cpu_usage'] > 80:
            alerts.append({
                'level': 'warning',
                'message': f'CPU 使用率过高: {metrics["cpu_usage"]}%',
                'timestamp': metrics['timestamp']
            })
        
        # 内存使用率告警
        if metrics['memory_usage'] > 85:
            alerts.append({
                'level': 'warning',
                'message': f'内存使用率过高: {metrics["memory_usage"]}%',
                'timestamp': metrics['timestamp']
            })
        
        # 磁盘使用率告警
        if metrics['disk_usage'] > 90:
            alerts.append({
                'level': 'critical',
                'message': f'磁盘使用率过高: {metrics["disk_usage"]}%',
                'timestamp': metrics['timestamp']
            })
        
        # 记录告警
        for alert in alerts:
            self.alerts.append(alert)
            if len(self.alerts) > 50:
                self.alerts = self.alerts[-50:]
            
            if alert['level'] == 'critical':
                log_error(self.logger, alert['message'])
            else:
                log_warning(self.logger, alert['message'])
    
    def get_metrics(self) -> Dict[str, List[Any]]:
        """获取当前指标"""
        return self.metrics.copy()
    
    def get_alerts(self) -> List[Dict[str, Any]]:
        """获取告警列表"""
        return self.alerts.copy()
    
    def clear_alerts(self):
        """清空告警列表"""
        self.alerts = []


# 全局监控器
monitor = Monitor()


def start_monitoring(interval: int = 60):
    """启动监控"""
    monitor.interval = interval
    monitor.start()


def stop_monitoring():
    """停止监控"""
    monitor.stop()


def get_system_metrics() -> Dict[str, List[Any]]:
    """获取系统指标"""
    return monitor.get_metrics()


def get_system_alerts() -> List[Dict[str, Any]]:
    """获取系统告警"""
    return monitor.get_alerts()


def clear_system_alerts():
    """清空系统告警"""
    monitor.clear_alerts()
