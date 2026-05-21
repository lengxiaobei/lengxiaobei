#!/usr/bin/env python3
"""
快速批准权限请求脚本
"""
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.evolution_permission import create_evolution_permission_manager

def approve_pending_requests():
    """批准所有待处理的权限请求"""
    manager = create_evolution_permission_manager()
    manager.pending_requests = manager._load_requests()
    
    pending = [req for req in manager.pending_requests if req.status == 'pending']
    
    if not pending:
        print("没有待处理的权限请求")
        return
    
    print(f"找到 {len(pending)} 个待处理的权限请求:")
    for req in pending:
        print(f"  - 请求ID: {req.id}, 文件: {req.file_path}, 风险等级: {req.risk_level}")
        manager.approve_request(req.id)
    
    print("所有权限请求已批准")

if __name__ == "__main__":
    approve_pending_requests()