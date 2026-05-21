"""
记忆系统 Facade - 懒加载所有记忆相关组件

含: hybrid_memory, knowledge_curator, auto_dream
"""

import threading
from pathlib import Path


class _MemoryConfig:
    """记忆配置封装，替代匿名 SimpleConfig"""
    def __init__(self, memory_dir: str):
        self.memory_dir = memory_dir


class MemoryFacade:

    def __init__(self, project_root: Path, memory_dir: Path):
        self._project_root = project_root
        self._memory_dir = memory_dir
        self._hybrid_memory = None
        self._memory = None
        self._knowledge_curator = None
        self._auto_dream = None
        self._lock = threading.RLock()

    @property
    def hybrid_memory(self):
        if self._hybrid_memory is None:
            with self._lock:
                if self._hybrid_memory is None:
                    from . import hybrid_memory as hm
                    self._hybrid_memory = hm.HybridMemory(_MemoryConfig(str(self._memory_dir)))
        return self._hybrid_memory

    @property
    def memory(self):
        if self._memory is None:
            with self._lock:
                if self._memory is None:
                    self._memory = self.hybrid_memory
        return self._memory

    @property
    def knowledge_curator(self):
        if self._knowledge_curator is None:
            with self._lock:
                if self._knowledge_curator is None:
                    from . import knowledge_curator as kc
                    self._knowledge_curator = kc.create_knowledge_curator(
                        str(self._project_root)
                    )
        return self._knowledge_curator

    @property
    def auto_dream(self):
        if self._auto_dream is None:
            with self._lock:
                if self._auto_dream is None:
                    from .auto_dream import AutoDreamV2
                    self._auto_dream = AutoDreamV2(
                        memory=self.memory,
                        project_root=str(self._project_root),
                    )
        return self._auto_dream