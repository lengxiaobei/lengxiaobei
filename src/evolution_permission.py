"""
⚠️  LEGACY — 此模块已被 src/hard_boundary.py + src/self_evolution_agent.py 替代。

旧设计：多级权限审批 (auto/approve/deny) + 签名校验 + 人工审核。
新设计：HardBoundary 三道检查 + 云模型判断 + 宿主确认。

迁移至: src/hard_boundary.py, src/self_evolution_agent.py
保留原因: 历史参考。
"""

#!/usr/bin/env python3
"""
进化权限管理模块
负责管理代码修改的权限控制、签名校验和人工审核
"""

import os
import json
import hashlib
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class PermissionRequest:
    """权限请求"""
    file_path: str
    operation: str  # 'read', 'write', 'execute'
    reason: str
    risk_level: str  # 'low', 'medium', 'high', 'critical'
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: str(int(time.time() * 1000)))
    status: str = "pending"  # 'pending', 'approved', 'denied'
    approver: Optional[str] = None
    approval_time: Optional[float] = None


class EvolutionPermissionManager:
    """进化权限管理器

    自主进化运行在非交互环境中。默认策略是不等待人工审核：
    项目内授权目录允许写入，项目外或未授权目录直接拒绝。
    """
    
    def __init__(self, project_root: str, auto_approve: bool = False):
        self.project_root = project_root
        self.auto_approve = auto_approve
        self.permission_dir = os.path.join(project_root, 'permissions')
        os.makedirs(self.permission_dir, exist_ok=True)
        self.requests_file = os.path.join(self.permission_dir, 'permission_requests.json')
        self.approved_dirs = self._load_approved_dirs()
        self.pending_requests: List[PermissionRequest] = self._load_requests()
    
    def _load_approved_dirs(self) -> List[str]:
        """加载授权目录"""
        config_file = os.path.join(self.permission_dir, 'approved_dirs.json')
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return [
            'src',
            'config',
            'memory',
            'plugins'
        ]
    
    def _load_requests(self) -> List[PermissionRequest]:
        """加载权限请求"""
        if os.path.exists(self.requests_file):
            with open(self.requests_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [PermissionRequest(**req) for req in data]
        return []
    
    def _save_requests(self):
        """保存权限请求"""
        data = [req.__dict__ for req in self.pending_requests]
        with open(self.requests_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def check_permission(self, file_path: str, operation: str, risk_level: str) -> bool:
        """检查权限"""
        relative_path = os.path.relpath(file_path, self.project_root)
        if relative_path.startswith('..'):
            print(f"   🔐 文件路径在项目外: {relative_path}")
            return False

        in_approved_dir = any(
            relative_path == d or relative_path.startswith(d + os.sep)
            for d in self.approved_dirs
        )
        if not in_approved_dir:
            print(f"   🔐 目录未授权: {relative_path} (已授权: {self.approved_dirs})")
            return False

        if self.auto_approve:
            return True

        if risk_level in ['low', 'medium']:
            return True

        return False

    def require_approval(self, file_path: str, operation: str, risk_level: str) -> bool:
        """兼容旧调用；非交互模式下不阻塞等待人工审批。"""
        return self.check_permission(file_path, operation, risk_level)
    
    def _require_approval(self, file_path: str, operation: str, risk_level: str) -> bool:
        """要求审批"""
        # 创建权限请求
        request = PermissionRequest(
            file_path=file_path,
            operation=operation,
            reason=f"Evolution operation with {risk_level} risk",
            risk_level=risk_level
        )
        
        # 自动审批
        if self.auto_approve:
            request.status = 'approved'
            request.approver = 'auto'
            request.approval_time = time.time()
            self.pending_requests.append(request)
            self._save_requests()
            print(f"\n🔐 权限请求创建成功")
            print(f"   请求ID: {request.id}")
            print(f"   文件: {file_path}")
            print(f"   操作: {operation}")
            print(f"   风险等级: {risk_level}")
            print(f"   ✅ 自动审批成功")
            return True
        
        # 保存请求
        self.pending_requests.append(request)
        self._save_requests()
        
        # 打印审批提示
        print(f"\n🔐 权限请求创建成功")
        print(f"   请求ID: {request.id}")
        print(f"   文件: {file_path}")
        print(f"   操作: {operation}")
        print(f"   风险等级: {risk_level}")
        print(f"   请运行 'python -m src.evolution_permission approve {request.id}' 来审批")
        
        # 等待审批
        return self._wait_for_approval(request.id)
    
    def _wait_for_approval(self, request_id: str, timeout: int = 300) -> bool:
        """等待审批"""
        start_time = time.time()
        try:
            while time.time() - start_time < timeout:
                # 重新加载请求
                self.pending_requests = self._load_requests()
                
                # 查找请求
                for req in self.pending_requests:
                    if req.id == request_id:
                        if req.status == 'approved':
                            print(f"✅ 权限请求已批准")
                            return True
                        elif req.status == 'denied':
                            print(f"❌ 权限请求被拒绝")
                            return False
                
                time.sleep(5)
            
            print(f"⏰ 权限请求超时")
            return False
        except KeyboardInterrupt:
            print(f"⏹️  权限请求被用户中断")
            return False
    
    def approve_request(self, request_id: str, approver: str = "admin"):
        """批准权限请求"""
        for req in self.pending_requests:
            if req.id == request_id:
                req.status = 'approved'
                req.approver = approver
                req.approval_time = time.time()
                self._save_requests()
                print(f"✅ 已批准请求 {request_id}")
                return True
        print(f"❌ 未找到请求 {request_id}")
        return False
    
    def deny_request(self, request_id: str, approver: str = "admin"):
        """拒绝权限请求"""
        for req in self.pending_requests:
            if req.id == request_id:
                req.status = 'denied'
                req.approver = approver
                req.approval_time = time.time()
                self._save_requests()
                print(f"❌ 已拒绝请求 {request_id}")
                return True
        print(f"❌ 未找到请求 {request_id}")
        return False
    
    def list_pending_requests(self):
        """列出待处理的请求"""
        self.pending_requests = self._load_requests()
        pending = [req for req in self.pending_requests if req.status == 'pending']
        
        if not pending:
            return []
        
        print("📋 待处理的权限请求:")
        for req in pending:
            print(f"\n请求ID: {req.id}")
            print(f"文件: {req.file_path}")
            print(f"操作: {req.operation}")
            print(f"风险等级: {req.risk_level}")
            print(f"原因: {req.reason}")
            print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(req.timestamp))}")
    
    def sign_code_change(self, file_path: str, old_content: str, new_content: str) -> str:
        """签名代码变更"""
        # 生成变更签名
        data = f"{file_path}|{old_content}|{new_content}|{time.time()}"
        signature = hashlib.sha256(data.encode()).hexdigest()
        
        # 保存签名
        signature_file = os.path.join(self.permission_dir, f'signature_{signature}.json')
        with open(signature_file, 'w', encoding='utf-8') as f:
            json.dump({
                'file_path': file_path,
                'timestamp': time.time(),
                'signature': signature,
                'old_content_hash': hashlib.sha256(old_content.encode()).hexdigest(),
                'new_content_hash': hashlib.sha256(new_content.encode()).hexdigest()
            }, f, indent=2)
        
        return signature
    
    def verify_signature(self, signature: str) -> bool:
        """验证签名"""
        signature_file = os.path.join(self.permission_dir, f'signature_{signature}.json')
        if not os.path.exists(signature_file):
            return False
        
        with open(signature_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 检查文件是否存在
        if not os.path.exists(data['file_path']):
            return False
        
        # 验证文件内容
        with open(data['file_path'], 'r', encoding='utf-8') as f:
            current_content = f.read()
        
        current_hash = hashlib.sha256(current_content.encode()).hexdigest()
        return current_hash == data['new_content_hash']


def create_evolution_permission_manager(project_root: str = None, auto_approve: bool = True) -> EvolutionPermissionManager:
    """创建进化权限管理器"""
    if project_root is None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return EvolutionPermissionManager(project_root, auto_approve)


if __name__ == "__main__":
    import sys
    
    manager = create_evolution_permission_manager()
    
    if len(sys.argv) < 2:
        print("用法:")
        print("  python -m src.evolution_permission list      # 列出待处理请求")
        print("  python -m src.evolution_permission approve <request_id>  # 批准请求")
        print("  python -m src.evolution_permission deny <request_id>     # 拒绝请求")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == 'list':
        manager.list_pending_requests()
    elif command == 'approve' and len(sys.argv) == 3:
        manager.approve_request(sys.argv[2])
    elif command == 'deny' and len(sys.argv) == 3:
        manager.deny_request(sys.argv[2])
    else:
        print("无效的命令")
