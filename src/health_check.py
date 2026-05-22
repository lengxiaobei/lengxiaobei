"""
健康检查系统
=============
为各层提供健康检查端点，便于系统状态监控
"""

import asyncio
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from typing import Dict, Any, List


class HealthCheckHandler(BaseHTTPRequestHandler):
    """健康检查 HTTP 处理程序"""
    
    def do_GET(self):
        """处理 GET 请求"""
        if self.path == '/health':
            self._handle_health_check()
        elif self.path == '/metrics':
            self._handle_metrics()
        else:
            self.send_error(404, "Not Found")
    
    def _handle_health_check(self):
        """处理健康检查请求"""
        health_status = HealthCheckService.get_health_status()
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        response = {
            "status": "healthy" if all(component["status"] == "healthy" for component in health_status) else "unhealthy",
            "timestamp": time.time(),
            "components": health_status,
            "degraded": HealthCheckService.is_degraded(),
        }
        
        self.wfile.write(json.dumps(response, indent=2).encode('utf-8'))
    
    def _handle_metrics(self):
        """处理指标请求"""
        metrics = HealthCheckService.get_metrics()
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        self.wfile.write(json.dumps(metrics, indent=2).encode('utf-8'))


class HealthCheckService:
    """健康检查服务"""

    _degraded = False
    _degraded_reason = ""

    @classmethod
    def set_degraded(cls, reason: str = ""):
        cls._degraded = True
        cls._degraded_reason = reason

    @classmethod
    def clear_degraded(cls):
        cls._degraded = False
        cls._degraded_reason = ""

    @classmethod
    def is_degraded(cls) -> bool:
        return cls._degraded
    
    # 组件健康状态
    _component_status = {
        "core": {"status": "healthy", "last_check": time.time()},
        "memory": {"status": "healthy", "last_check": time.time()},
        "control": {"status": "healthy", "last_check": time.time()},
        "llm": {"status": "healthy", "last_check": time.time()}
    }
    
    # 性能指标
    _metrics = {
        "response_times": [],
        "throughput": 0,
        "error_rate": 0,
        "memory_usage": 0,
        "cpu_usage": 0
    }
    
    @classmethod
    def update_component_status(cls, component: str, status: str, message: str = ""):
        """更新组件健康状态"""
        if component in cls._component_status:
            cls._component_status[component] = {
                "status": status,
                "last_check": time.time(),
                "message": message
            }
    
    @classmethod
    def get_health_status(cls) -> List[Dict[str, Any]]:
        """获取所有组件的健康状态"""
        return [
            {"name": component, **status}
            for component, status in cls._component_status.items()
        ]
    
    @classmethod
    def get_metrics(cls) -> Dict[str, Any]:
        """获取性能指标"""
        # 集成 PerformanceMonitor 的指标
        try:
            from .performance import get_performance_monitor
            performance_monitor = get_performance_monitor()
            performance_metrics = {}
            
            # 获取关键函数的性能统计
            for metric_name in ["chat_duration", "think_duration", "store_duration", "search_duration"]:
                stats = performance_monitor.get_stats(metric_name)
                if stats:
                    performance_metrics[metric_name] = stats
        except ImportError:
            performance_metrics = {}
        
        return {
            "timestamp": time.time(),
            "metrics": cls._metrics,
            "performance": performance_metrics
        }
    
    @classmethod
    def update_metrics(cls, response_time: float = None, error: bool = False):
        """更新性能指标"""
        if response_time is not None:
            cls._metrics["response_times"].append(response_time)
            # 只保留最近100个值
            if len(cls._metrics["response_times"]) > 100:
                cls._metrics["response_times"] = cls._metrics["response_times"][-100:]
        
        if error:
            cls._metrics["error_rate"] = min(1.0, (cls._metrics["error_rate"] * 99 + 1) / 100)
        else:
            cls._metrics["error_rate"] = max(0.0, (cls._metrics["error_rate"] * 99) / 100)


class HealthCheckServer:
    """健康检查服务器"""
    
    def __init__(self, host: str = '127.0.0.1', port: int = 8000):
        self.host = host
        self.port = port
        self.server = None
        self.server_thread = None
        self.running = False
    
    def start(self):
        """启动健康检查服务器。端口冲突时自动尝试 8001, 8002。"""
        if self.running:
            return

        for offset in range(3):
            port = self.port + offset
            try:
                self.server = HTTPServer((self.host, port), HealthCheckHandler)
                self.port = port
                self.running = True

                self.server_thread = threading.Thread(target=self._run_server, daemon=True)
                self.server_thread.start()

                print(f"[HealthCheck] 健康检查服务器启动在 http://{self.host}:{self.port}")
                return
            except OSError as e:
                if e.errno == 48:  # Address already in use
                    if offset < 2:
                        print(f"[HealthCheck] 端口 {port} 被占用，尝试 {port + 1}...")
                    else:
                        print(f"[HealthCheck] 所有端口 ({self.port}-{self.port + 2}) 被占用，跳过启动")
                else:
                    print(f"[HealthCheck] 启动失败: {e}")
                    break
    
    def stop(self):
        """停止健康检查服务器"""
        if not self.running:
            return
        
        self.running = False
        if self.server:
            self.server.shutdown()
        if self.server_thread:
            self.server_thread.join(timeout=5)
        
        print("[HealthCheck] 健康检查服务器已停止")
    
    def _run_server(self):
        """运行服务器"""
        while self.running:
            try:
                self.server.serve_forever(poll_interval=1)
            except Exception as e:
                if self.running:
                    print(f"[HealthCheck] 服务器错误: {e}")
                break


# 全局健康检查服务器实例
health_check_server = HealthCheckServer()


def start_health_check_server():
    """启动健康检查服务器"""
    health_check_server.start()


def stop_health_check_server():
    """停止健康检查服务器"""
    health_check_server.stop()


def get_health_service():
    """获取健康检查服务"""
    return HealthCheckService
