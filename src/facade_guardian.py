"""
守护系统 Facade — 懒加载后台守护、健康检查、监控、权限、预算等

含: kairos, lock_manager, health_check, monitoring, resource_manager,
     data_backup, permission_manager, budget_tracker, performance_monitor
"""

import json
import os
import time
import threading
from pathlib import Path
from typing import Optional


class GuardianFacade:

    def __init__(self, project_root: Path, memory_facade, evolution_facade):
        self._project_root = project_root
        self._memory_facade = memory_facade
        self._evolution_facade = evolution_facade
        self._kairos = None
        self._lock_manager = None
        self._health_check_server = None
        self._health_check_thread = None
        self._permission_manager = None
        self._budget_tracker = None
        self._performance_monitor = None

    @property
    def lock_manager(self):
        if self._lock_manager is None:
            from .distributed_lock import get_lock_manager

            self._lock_manager = get_lock_manager()
        return self._lock_manager

    @property
    def kairos(self):
        if self._kairos is None:
            from .kairos.engine import create_kairos

            self._kairos = create_kairos(
                memory=self._memory_facade.memory,
                project_root=str(self._project_root),
            )
            self._setup_evolution_trigger()
        return self._kairos

    def _setup_evolution_trigger(self):
        evo = self._evolution_facade

        def on_evolution_trigger(improvements):
            print(f"[Guardian] 收到进化触发，改进点: {improvements}")
            try:
                ae = getattr(evo, 'autonomous_evolution', None)
                if ae is None:
                    return
                if improvements:
                    from .evolution.models import ImprovementRecord

                    for imp_data in improvements[:3]:
                        rec = ImprovementRecord.from_kairos(imp_data)
                        if rec is None:
                            continue
                        full_path = rec.abspath(str(self._project_root))
                        if not os.path.exists(full_path):
                            continue
                        ae.evolve(file_path=full_path, goal_description=rec.issue)
                else:
                    ae.evolve_autonomously()
            except Exception as e:
                print(f"[Guardian] 进化执行失败: {e}")

        self._kairos.on_evolution_trigger = on_evolution_trigger

    @property
    def health_check_server(self):
        return self._health_check_server

    @property
    def health_check_thread(self):
        return self._health_check_thread

    def start_health_check(self, status_fn):
        try:
            from . import health_check

            server = health_check.HealthCheckServer(port=8000)
            server.start()
            self._health_check_server = server
            self._health_check_thread = server.server_thread
            return True
        except Exception:
            return False

    def stop_health_check(self):
        if self._health_check_server:
            try:
                self._health_check_server.stop()
            except Exception:
                pass
            self._health_check_server = None
            self._health_check_thread = None

    @property
    def permission_manager(self):
        if self._permission_manager is None:
            from .permission import create_permission_manager

            self._permission_manager = create_permission_manager()
        return self._permission_manager

    @property
    def budget_tracker(self):
        if self._budget_tracker is None:
            from .budget import create_budget_tracker

            self._budget_tracker = create_budget_tracker()
        return self._budget_tracker

    @property
    def performance_monitor(self):
        if self._performance_monitor is None:
            from .performance import get_performance_monitor

            self._performance_monitor = get_performance_monitor()
        return self._performance_monitor

    def start(self):
        if self._kairos:
            try:
                self._kairos.activate()
                self._kairos.start()
            except Exception:
                pass

    def stop(self):
        if self._kairos:
            try:
                self._kairos.stop()
            except Exception:
                pass
        self.stop_health_check()
        from .monitoring import stop_monitoring

        try:
            stop_monitoring()
        except Exception:
            pass