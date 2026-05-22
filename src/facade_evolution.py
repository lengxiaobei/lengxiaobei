"""
进化系统 Facade — 懒加载进化引擎、熔断器、审查/测试等

含: autonomous_evolution, curator, verifier, circuit_breaker, learner, code_critic, code_tester
"""

from pathlib import Path
from typing import Optional


class EvolutionFacade:

    def __init__(self, project_root: Path, memory_dir: Path, memory_facade):
        self._project_root = project_root
        self._memory_dir = memory_dir
        self._memory_facade = memory_facade
        self._autonomous_evolution = None
        self._auto_evolution = None
        self._curator = None
        self._verifier = None
        self._constitution = None
        self._evolution_permission = None
        self._circuit_breaker = None
        self._learner = None
        self._code_critic = None
        self._code_tester = None

    @property
    def constitution(self):
        if self._constitution is None:
            from .constitution import get_constitution

            self._constitution = get_constitution(str(self._memory_dir))
        return self._constitution

    @property
    def learner(self):
        if self._learner is None:
            from .learner import Learner

            self._learner = Learner(str(self._memory_dir))
        return self._learner

    @property
    def autonomous_evolution(self):
        if self._autonomous_evolution is None:
            from .evolution.engine import create_autonomous_evolution_engine

            self._autonomous_evolution = create_autonomous_evolution_engine(
                project_root=str(self._project_root),
                circuit_breaker=self.circuit_breaker,
            )
        return self._autonomous_evolution

    @property
    def auto_evolution(self):
        if self._auto_evolution is None:
            self._auto_evolution = self.autonomous_evolution
        return self._auto_evolution

    @property
    def curator(self):
        if self._curator is None:
            self._curator = self.autonomous_evolution.curator
        return self._curator

    @property
    def verifier(self):
        if self._verifier is None:
            self._verifier = self.autonomous_evolution.verifier
        return self._verifier

    @property
    def evolution_permission(self):
        if self._evolution_permission is None:
            from .evolution.config import Config
            from .evolution_permission import create_evolution_permission_manager

            self._evolution_permission = create_evolution_permission_manager(
                str(self._project_root), auto_approve=Config.get_auto_approve()
            )
        return self._evolution_permission

    @property
    def circuit_breaker(self):
        if self._circuit_breaker is None:
            from .circuit_breaker import CircuitBreaker
            self._circuit_breaker = CircuitBreaker("autonomous_evolution")
        return self._circuit_breaker

    @property
    def code_critic(self):
        if self._code_critic is None:
            from .critic import CodeCritic

            self._code_critic = CodeCritic(str(self._project_root))
        return self._code_critic

    @property
    def code_tester(self):
        if self._code_tester is None:
            from .testing import CodeTester

            self._code_tester = CodeTester(str(self._project_root))
        return self._code_tester
