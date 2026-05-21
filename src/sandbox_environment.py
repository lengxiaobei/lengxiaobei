"""
沙盒环境模块
提供安全的实验空间

核心功能：
- 隔离环境创建
- 代码执行安全
- 资源限制
- 实验管理
- 状态保存和恢复
- 快速回滚机制
"""

import os
import sys
import time
import json
import shutil
import tempfile
import subprocess
import resource
import signal
import traceback
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any
from enum import Enum


class SandboxStatus(Enum):
    """沙盒状态"""
    CREATED = "created"  # 已创建
    RUNNING = "running"  # 运行中
    PAUSED = "paused"  # 已暂停
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    DESTROYED = "destroyed"  # 已销毁


class ExperimentStatus(Enum):
    """实验状态"""
    PENDING = "pending"  # 待执行
    RUNNING = "running"  # 运行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


@dataclass
class Sandbox:
    """沙盒类"""
    id: str  # 沙盒ID
    name: str  # 沙盒名称
    description: str  # 沙盒描述
    path: str  # 沙盒路径
    status: SandboxStatus  # 沙盒状态
    created_at: float  # 创建时间
    updated_at: float  # 更新时间
    experiments: List[str] = field(default_factory=list)  # 实验ID列表
    resources: Dict[str, Any] = field(default_factory=dict)  # 资源限制
    tags: List[str] = field(default_factory=list)  # 标签

    def to_dict(self) -> Dict[str, Any]:
        """将沙盒转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "path": self.path,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "experiments": self.experiments,
            "resources": self.resources,
            "tags": self.tags
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Sandbox":
        """从字典创建沙盒"""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            path=data["path"],
            status=SandboxStatus(data["status"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            experiments=data.get("experiments", []),
            resources=data.get("resources", {}),
            tags=data.get("tags", [])
        )


@dataclass
class Experiment:
    """实验类"""
    id: str  # 实验ID
    sandbox_id: str  # 沙盒ID
    name: str  # 实验名称
    description: str  # 实验描述
    code: str  # 实验代码
    status: ExperimentStatus  # 实验状态
    created_at: float  # 创建时间
    updated_at: float  # 更新时间
    started_at: Optional[float] = None  # 开始时间
    completed_at: Optional[float] = None  # 完成时间
    output: Optional[str] = None  # 实验输出
    error: Optional[str] = None  # 实验错误
    exit_code: Optional[int] = None  # 退出代码
    tags: List[str] = field(default_factory=list)  # 标签

    def to_dict(self) -> Dict[str, Any]:
        """将实验转换为字典"""
        return {
            "id": self.id,
            "sandbox_id": self.sandbox_id,
            "name": self.name,
            "description": self.description,
            "code": self.code,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "output": self.output,
            "error": self.error,
            "exit_code": self.exit_code,
            "tags": self.tags
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Experiment":
        """从字典创建实验"""
        return cls(
            id=data["id"],
            sandbox_id=data["sandbox_id"],
            name=data["name"],
            description=data["description"],
            code=data["code"],
            status=ExperimentStatus(data["status"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            output=data.get("output"),
            error=data.get("error"),
            exit_code=data.get("exit_code"),
            tags=data.get("tags", [])
        )


class SandboxEnvironment:
    """沙盒环境类"""

    def __init__(self, project_root: str):
        """初始化沙盒环境"""
        self.project_root = project_root
        self.sandbox_dir = os.path.join(project_root, "sandbox")
        os.makedirs(self.sandbox_dir, exist_ok=True)
        self.sandboxes_file = os.path.join(self.sandbox_dir, "sandboxes.json")
        self.experiments_file = os.path.join(self.sandbox_dir, "experiments.json")
        self.sandboxes: Dict[str, Sandbox] = {}
        self.experiments: Dict[str, Experiment] = {}
        self._sandbox_id_counter = 0  # 初始化计数器
        self._experiment_id_counter = 0  # 初始化计数器
        self._load_data()

    def _load_data(self):
        """加载数据"""
        # 加载沙盒
        if os.path.exists(self.sandboxes_file):
            try:
                with open(self.sandboxes_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for sandbox_data in data:
                        sandbox = Sandbox.from_dict(sandbox_data)
                        self.sandboxes[sandbox.id] = sandbox
                        # 更新沙盒ID计数器
                        if sandbox.id.isdigit():
                            sandbox_id = int(sandbox.id)
                            if sandbox_id > self._sandbox_id_counter:
                                self._sandbox_id_counter = sandbox_id
            except Exception as e:
                print(f"[SandboxEnvironment] 加载沙盒失败: {e}")
        
        # 加载实验
        if os.path.exists(self.experiments_file):
            try:
                with open(self.experiments_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for experiment_data in data:
                        experiment = Experiment.from_dict(experiment_data)
                        self.experiments[experiment.id] = experiment
                        # 更新实验ID计数器
                        if experiment.id.isdigit():
                            experiment_id = int(experiment.id)
                            if experiment_id > self._experiment_id_counter:
                                self._experiment_id_counter = experiment_id
            except Exception as e:
                print(f"[SandboxEnvironment] 加载实验失败: {e}")

    def _save_data(self):
        """保存数据"""
        # 保存沙盒
        try:
            data = [sandbox.to_dict() for sandbox in self.sandboxes.values()]
            with open(self.sandboxes_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[SandboxEnvironment] 保存沙盒失败: {e}")
        
        # 保存实验
        try:
            data = [experiment.to_dict() for experiment in self.experiments.values()]
            with open(self.experiments_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[SandboxEnvironment] 保存实验失败: {e}")

    def _generate_sandbox_id(self) -> str:
        """生成沙盒ID"""
        self._sandbox_id_counter += 1
        return str(self._sandbox_id_counter)

    def _generate_experiment_id(self) -> str:
        """生成实验ID"""
        self._experiment_id_counter += 1
        return str(self._experiment_id_counter)

    def create_sandbox(
        self,
        name: str,
        description: str,
        resources: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> Sandbox:
        """创建新沙盒"""
        sandbox_id = self._generate_sandbox_id()
        sandbox_path = os.path.join(self.sandbox_dir, f"sandbox_{sandbox_id}")
        
        # 创建沙盒目录
        os.makedirs(sandbox_path, exist_ok=True)
        
        # 设置默认资源限制
        default_resources = {
            "max_cpu": 1.0,  # 最大CPU使用（核心数）
            "max_memory": 512 * 1024 * 1024,  # 最大内存使用（字节）
            "max_disk": 1024 * 1024 * 1024,  # 最大磁盘使用（字节）
            "max_time": 300,  # 最大执行时间（秒）
            "network_access": False  # 是否允许网络访问
        }
        if resources:
            default_resources.update(resources)
        
        sandbox = Sandbox(
            id=sandbox_id,
            name=name,
            description=description,
            path=sandbox_path,
            status=SandboxStatus.CREATED,
            created_at=time.time(),
            updated_at=time.time(),
            experiments=[],
            resources=default_resources,
            tags=tags or []
        )
        
        self.sandboxes[sandbox_id] = sandbox
        self._save_data()
        print(f"[SandboxEnvironment] 创建沙盒: {name} (ID: {sandbox_id})")
        return sandbox

    def get_sandbox(self, sandbox_id: str) -> Optional[Sandbox]:
        """获取沙盒"""
        return self.sandboxes.get(sandbox_id)

    def list_sandboxes(self, status: Optional[SandboxStatus] = None) -> List[Sandbox]:
        """列出沙盒"""
        result = []
        for sandbox in self.sandboxes.values():
            if status and sandbox.status != status:
                continue
            result.append(sandbox)
        # 按创建时间排序
        result.sort(key=lambda x: x.created_at, reverse=True)
        return result

    def update_sandbox(
        self,
        sandbox_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        resources: Optional[Dict[str, Any]] = None,
        status: Optional[SandboxStatus] = None
    ) -> Optional[Sandbox]:
        """更新沙盒"""
        if sandbox_id not in self.sandboxes:
            return None
        
        sandbox = self.sandboxes[sandbox_id]
        if name:
            sandbox.name = name
        if description:
            sandbox.description = description
        if resources:
            sandbox.resources.update(resources)
        if status:
            sandbox.status = status
        sandbox.updated_at = time.time()
        
        self._save_data()
        print(f"[SandboxEnvironment] 更新沙盒: {sandbox.name} (ID: {sandbox_id})")
        return sandbox

    def delete_sandbox(self, sandbox_id: str) -> bool:
        """删除沙盒"""
        if sandbox_id not in self.sandboxes:
            return False
        
        sandbox = self.sandboxes[sandbox_id]
        
        # 删除沙盒目录
        if os.path.exists(sandbox.path):
            try:
                shutil.rmtree(sandbox.path)
            except Exception as e:
                print(f"[SandboxEnvironment] 删除沙盒目录失败: {e}")
        
        # 删除关联的实验
        for experiment_id in sandbox.experiments:
            if experiment_id in self.experiments:
                del self.experiments[experiment_id]
        
        # 删除沙盒
        del self.sandboxes[sandbox_id]
        self._save_data()
        print(f"[SandboxEnvironment] 删除沙盒: {sandbox.name} (ID: {sandbox_id})")
        return True

    def create_experiment(
        self,
        sandbox_id: str,
        name: str,
        description: str,
        code: str,
        tags: Optional[List[str]] = None
    ) -> Optional[Experiment]:
        """创建新实验"""
        if sandbox_id not in self.sandboxes:
            return None
        
        sandbox = self.sandboxes[sandbox_id]
        if sandbox.status == SandboxStatus.DESTROYED:
            return None
        
        experiment_id = self._generate_experiment_id()
        experiment = Experiment(
            id=experiment_id,
            sandbox_id=sandbox_id,
            name=name,
            description=description,
            code=code,
            status=ExperimentStatus.PENDING,
            created_at=time.time(),
            updated_at=time.time(),
            tags=tags or []
        )
        
        self.experiments[experiment_id] = experiment
        sandbox.experiments.append(experiment_id)
        sandbox.updated_at = time.time()
        
        self._save_data()
        print(f"[SandboxEnvironment] 创建实验: {name} (ID: {experiment_id})")
        return experiment

    def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """获取实验"""
        return self.experiments.get(experiment_id)

    def list_experiments(
        self,
        sandbox_id: Optional[str] = None,
        status: Optional[ExperimentStatus] = None
    ) -> List[Experiment]:
        """列出实验"""
        result = []
        for experiment in self.experiments.values():
            if sandbox_id and experiment.sandbox_id != sandbox_id:
                continue
            if status and experiment.status != status:
                continue
            result.append(experiment)
        # 按创建时间排序
        result.sort(key=lambda x: x.created_at, reverse=True)
        return result

    def _run_experiment_in_docker(self, sandbox: Sandbox, experiment: Experiment, temp_file: str) -> tuple:
        """
        在Docker容器中运行实验
        返回: (stdout, stderr, exit_code)
        """
        # 检查是否安装了docker
        try:
            subprocess.run(['docker', '--version'], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("Docker is not installed or not available")

        # 创建一个临时的Dockerfile
        dockerfile_content = f"""
FROM python:3.9-slim
WORKDIR /app
COPY {os.path.basename(temp_file)} /app/
RUN chmod +x /app/{os.path.basename(temp_file)}
"""
        dockerfile_path = os.path.join(sandbox.path, "Dockerfile")
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)

        # 构建Docker镜像
        image_name = f"sandbox-{sandbox.id}-experiment-{experiment.id}"
        build_result = subprocess.run([
            'docker', 'build', '-t', image_name, '-f', dockerfile_path, sandbox.path
        ], capture_output=True, text=True)
        
        if build_result.returncode != 0:
            return "", f"Docker build failed: {build_result.stderr}", build_result.returncode

        # 准备Docker运行参数
        docker_cmd = [
            'docker', 'run',
            '--rm',  # 自动清理容器
            '--memory', str(sandbox.resources['max_memory']),  # 内存限制
            '--cpus', str(sandbox.resources['max_cpu']),  # CPU限制
            '--network', 'none' if not sandbox.resources['network_access'] else 'default',  # 网络限制
            '--ulimit', f'time={sandbox.resources["max_time"]}',  # 时间限制
            image_name,
            'python', os.path.basename(temp_file)
        ]

        # 运行容器
        try:
            result = subprocess.run(
                docker_cmd,
                timeout=sandbox.resources.get("max_time", 600),  # 总超时时间
                capture_output=True,
                text=True
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            # 强制停止容器
            subprocess.run(['docker', 'kill', f'{image_name}_container'], capture_output=True)
            return "", "Container execution timed out", -1
        finally:
            # 清理镜像
            subprocess.run(['docker', 'rmi', '-f', image_name], capture_output=True)

    def run_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """运行实验"""
        if experiment_id not in self.experiments:
            return None
        
        experiment = self.experiments[experiment_id]
        sandbox_id = experiment.sandbox_id
        
        if sandbox_id not in self.sandboxes:
            return None
        
        sandbox = self.sandboxes[sandbox_id]
        if sandbox.status == SandboxStatus.DESTROYED:
            return None
        
        # 更新实验状态
        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = time.time()
        experiment.updated_at = time.time()
        self._save_data()
        
        # 更新沙盒状态
        if sandbox.status != SandboxStatus.RUNNING:
            sandbox.status = SandboxStatus.RUNNING
            sandbox.updated_at = time.time()
            self._save_data()
        
        try:
            # 创建临时Python文件
            temp_file = os.path.join(sandbox.path, f"experiment_{experiment_id}.py")
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(experiment.code)
            
            # 使用Docker运行实验以增强安全性
            stdout, stderr, exit_code = self._run_experiment_in_docker(sandbox, experiment, temp_file)
            
            # 更新实验结果
            experiment.status = ExperimentStatus.COMPLETED if exit_code == 0 else ExperimentStatus.FAILED
            experiment.output = stdout
            experiment.error = stderr
            experiment.exit_code = exit_code
            experiment.completed_at = time.time()
            experiment.updated_at = time.time()
            
        except Exception as e:
            # 更新实验结果
            experiment.status = ExperimentStatus.FAILED
            experiment.error = str(e)
            experiment.exit_code = -1
            experiment.completed_at = time.time()
            experiment.updated_at = time.time()
            print(f"[SandboxEnvironment] 运行实验失败: {e}")
        
        # 更新沙盒状态
        if all(
            self.experiments[eid].status in [ExperimentStatus.COMPLETED, ExperimentStatus.FAILED, ExperimentStatus.CANCELLED]
            for eid in sandbox.experiments
        ):
            sandbox.status = SandboxStatus.COMPLETED
            sandbox.updated_at = time.time()
        
        self._save_data()
        print(f"[SandboxEnvironment] 运行实验: {experiment.name} (ID: {experiment_id}, 状态: {experiment.status.value})")
        return experiment

    def cancel_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """取消实验"""
        if experiment_id not in self.experiments:
            return None
        
        experiment = self.experiments[experiment_id]
        if experiment.status != ExperimentStatus.RUNNING:
            return None
        
        # 更新实验状态
        experiment.status = ExperimentStatus.CANCELLED
        experiment.updated_at = time.time()
        
        # 这里可以添加终止正在运行的实验进程的逻辑
        
        self._save_data()
        print(f"[SandboxEnvironment] 取消实验: {experiment.name} (ID: {experiment_id})")
        return experiment

    def delete_experiment(self, experiment_id: str) -> bool:
        """删除实验"""
        if experiment_id not in self.experiments:
            return False
        
        experiment = self.experiments[experiment_id]
        sandbox_id = experiment.sandbox_id
        
        # 从沙盒的实验列表中移除
        if sandbox_id in self.sandboxes:
            sandbox = self.sandboxes[sandbox_id]
            if experiment_id in sandbox.experiments:
                sandbox.experiments.remove(experiment_id)
                sandbox.updated_at = time.time()
        
        # 删除实验
        del self.experiments[experiment_id]
        self._save_data()
        print(f"[SandboxEnvironment] 删除实验: {experiment.name} (ID: {experiment_id})")
        return True

    def create_snapshot(self, sandbox_id: str, name: str) -> Optional[str]:
        """创建沙盒快照"""
        if sandbox_id not in self.sandboxes:
            return None
        
        sandbox = self.sandboxes[sandbox_id]
        if sandbox.status == SandboxStatus.DESTROYED:
            return None
        
        # 创建快照目录
        snapshot_dir = os.path.join(self.sandbox_dir, "snapshots")
        os.makedirs(snapshot_dir, exist_ok=True)
        
        # 生成快照ID
        snapshot_id = f"{sandbox_id}_{int(time.time())}"
        snapshot_path = os.path.join(snapshot_dir, f"snapshot_{snapshot_id}")
        
        # 复制沙盒目录
        try:
            shutil.copytree(sandbox.path, snapshot_path)
            print(f"[SandboxEnvironment] 创建沙盒快照: {name} (ID: {snapshot_id})")
            return snapshot_id
        except Exception as e:
            print(f"[SandboxEnvironment] 创建沙盒快照失败: {e}")
            return None

    def restore_snapshot(self, sandbox_id: str, snapshot_id: str) -> bool:
        """恢复沙盒快照"""
        if sandbox_id not in self.sandboxes:
            return False
        
        sandbox = self.sandboxes[sandbox_id]
        if sandbox.status == SandboxStatus.DESTROYED:
            return False
        
        # 快照路径
        snapshot_path = os.path.join(self.sandbox_dir, "snapshots", f"snapshot_{snapshot_id}")
        if not os.path.exists(snapshot_path):
            return False
        
        # 备份当前沙盒目录
        backup_path = os.path.join(self.sandbox_dir, f"backup_{sandbox_id}_{int(time.time())}")
        try:
            shutil.copytree(sandbox.path, backup_path)
        except Exception as e:
            print(f"[SandboxEnvironment] 备份沙盒失败: {e}")
            return False
        
        # 恢复快照
        try:
            shutil.rmtree(sandbox.path)
            shutil.copytree(snapshot_path, sandbox.path)
            print(f"[SandboxEnvironment] 恢复沙盒快照: {snapshot_id} 到沙盒 {sandbox.name} (ID: {sandbox_id})")
            return True
        except Exception as e:
            print(f"[SandboxEnvironment] 恢复沙盒快照失败: {e}")
            # 尝试恢复备份
            try:
                shutil.rmtree(sandbox.path)
                shutil.copytree(backup_path, sandbox.path)
                print(f"[SandboxEnvironment] 恢复备份成功")
            except Exception as e2:
                print(f"[SandboxEnvironment] 恢复备份失败: {e2}")
            return False

    def get_sandbox_statistics(self) -> Dict[str, Any]:
        """获取沙盒统计信息"""
        total_sandboxes = len(self.sandboxes)
        
        # 按状态统计沙盒
        status_stats = {}
        for status in SandboxStatus:
            status_stats[status.value] = sum(1 for sandbox in self.sandboxes.values() if sandbox.status == status)
        
        # 计算活跃沙盒数量
        active_sandboxes = sum(1 for sandbox in self.sandboxes.values() if sandbox.status == SandboxStatus.RUNNING)
        
        return {
            "total_sandboxes": total_sandboxes,
            "active_sandboxes": active_sandboxes,
            "status_stats": status_stats
        }

    def get_experiment_statistics(self) -> Dict[str, Any]:
        """获取实验统计信息"""
        total_experiments = len(self.experiments)
        
        # 按状态统计实验
        status_stats = {}
        for status in ExperimentStatus:
            status_stats[status.value] = sum(1 for experiment in self.experiments.values() if experiment.status == status)
        
        # 计算成功和失败的实验数量
        successful_experiments = sum(1 for experiment in self.experiments.values() if experiment.status == ExperimentStatus.COMPLETED)
        failed_experiments = sum(1 for experiment in self.experiments.values() if experiment.status == ExperimentStatus.FAILED)
        
        return {
            "total_experiments": total_experiments,
            "successful_experiments": successful_experiments,
            "failed_experiments": failed_experiments,
            "status_stats": status_stats
        }


def create_sandbox_environment(project_root: str) -> SandboxEnvironment:
    """创建沙盒环境实例"""
    return SandboxEnvironment(project_root)