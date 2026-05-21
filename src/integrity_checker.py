#!/usr/bin/env python3
"""
完整性校验模块
负责核心文件的哈希校验和记忆数据的签名校验
"""

import os
import hashlib
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any


class IntegrityChecker:
    """
    完整性校验器
    - 核心文件的哈希校验
    - 记忆数据的签名校验
    - 定期检查和告警
    """
    
    def __init__(self, project_root: str = None):
        """
        初始化完整性校验器
        
        Args:
            project_root: 项目根目录
        """
        if project_root is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        self.project_root = project_root
        self.integrity_dir = os.path.join(project_root, 'integrity')
        os.makedirs(self.integrity_dir, exist_ok=True)
        self.checksum_file = os.path.join(self.integrity_dir, 'checksums.json')
        self.core_files = self._get_core_files()
        self._load_checksums()
    
    def _get_core_files(self) -> List[str]:
        """
        获取核心文件列表
        
        Returns:
            核心文件列表
        """
        core_files = [
            'src/core.py',
            'src/evolution/engine.py',
            'src/evolution/executor.py',
            'src/evolution/proposer.py',
            'src/evolution/curator.py',
            'src/kairos/engine.py',
            'src/motivation_system.py',
            'src/goal_system.py',
            'src/sandbox_environment.py',
            'src/evolution_permission.py',
            'src/distributed_lock.py',
            'src/circuit_breaker.py',
            'src/integrity_checker.py',
            'src/config/default.yaml'
        ]
        return core_files
    
    def _load_checksums(self):
        """加载校验和"""
        if os.path.exists(self.checksum_file):
            try:
                with open(self.checksum_file, 'r', encoding='utf-8') as f:
                    self.checksums = json.load(f)
            except Exception:
                self.checksums = {}
        else:
            self.checksums = {}
    
    def _save_checksums(self):
        """保存校验和"""
        try:
            with open(self.checksum_file, 'w', encoding='utf-8') as f:
                json.dump(self.checksums, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def calculate_file_hash(self, file_path: str) -> Optional[str]:
        """
        计算文件哈希
        
        Args:
            file_path: 文件路径
        
        Returns:
            文件哈希值
        """
        try:
            full_path = os.path.join(self.project_root, file_path)
            if not os.path.exists(full_path):
                return None
            
            hasher = hashlib.sha256()
            with open(full_path, 'rb') as f:
                while True:
                    data = f.read(65536)
                    if not data:
                        break
                    hasher.update(data)
            return hasher.hexdigest()
        except Exception:
            return None
    
    def generate_checksums(self) -> Dict[str, str]:
        """
        生成所有核心文件的校验和
        
        Returns:
            校验和字典
        """
        checksums = {}
        for file_path in self.core_files:
            file_hash = self.calculate_file_hash(file_path)
            if file_hash:
                checksums[file_path] = file_hash
        
        self.checksums = checksums
        self._save_checksums()
        return checksums
    
    def verify_integrity(self) -> Dict[str, Any]:
        """
        验证核心文件的完整性
        
        Returns:
            验证结果
        """
        if not self.checksums:
            self.generate_checksums()
            if not self.checksums:
                return {
                    "status": "success",
                    "verified_files": 0,
                    "modified_files": [],
                    "missing_files": [],
                    "details": {},
                    "message": "No core files found for integrity baseline",
                }

        results = {
            "status": "success",
            "verified_files": 0,
            "modified_files": [],
            "missing_files": [],
            "details": {}
        }
        
        for file_path in self.core_files:
            current_hash = self.calculate_file_hash(file_path)
            expected_hash = self.checksums.get(file_path)
            
            if not current_hash:
                results["missing_files"].append(file_path)
                results["details"][file_path] = {
                    "status": "missing",
                    "expected_hash": expected_hash,
                    "current_hash": None
                }
            elif not expected_hash:
                results["details"][file_path] = {
                    "status": "new",
                    "expected_hash": None,
                    "current_hash": current_hash
                }
                results["verified_files"] += 1
            elif current_hash == expected_hash:
                results["details"][file_path] = {
                    "status": "ok",
                    "expected_hash": expected_hash,
                    "current_hash": current_hash
                }
                results["verified_files"] += 1
            else:
                results["modified_files"].append(file_path)
                results["details"][file_path] = {
                    "status": "modified",
                    "expected_hash": expected_hash,
                    "current_hash": current_hash
                }
        
        if results["modified_files"] or results["missing_files"]:
            results["status"] = "failed"
        
        return results
    
    def verify_memory_integrity(self) -> Dict[str, Any]:
        """
        验证记忆数据的完整性
        
        Returns:
            验证结果
        """
        memory_dir = os.path.join(self.project_root, 'memory')
        results = {
            "status": "success",
            "verified_files": 0,
            "modified_files": [],
            "missing_files": [],
            "details": {}
        }
        
        # 检查记忆数据文件
        memory_files = [
            'motivations.json',
            'goals.json',
            'sessions',
            'MEMORY.md'
        ]
        
        for file_path in memory_files:
            full_path = os.path.join(self.project_root, 'memory', file_path)
            if not os.path.exists(full_path):
                results["missing_files"].append(file_path)
                results["details"][file_path] = {
                    "status": "missing"
                }
            else:
                results["verified_files"] += 1
                results["details"][file_path] = {
                    "status": "ok"
                }
        
        if results["missing_files"]:
            results["status"] = "failed"
        
        return results
    
    def sign_memory_data(self, data: Dict[str, Any]) -> str:
        """
        签名记忆数据
        
        Args:
            data: 记忆数据
        
        Returns:
            签名
        """
        try:
            # 序列化数据
            data_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
            # 生成签名
            signature = hashlib.sha256(data_str.encode()).hexdigest()
            return signature
        except Exception:
            return None
    
    def verify_memory_signature(self, data: Dict[str, Any], signature: str) -> bool:
        """
        验证记忆数据签名
        
        Args:
            data: 记忆数据
            signature: 签名
        
        Returns:
            签名是否有效
        """
        try:
            # 生成签名
            data_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
            expected_signature = hashlib.sha256(data_str.encode()).hexdigest()
            return expected_signature == signature
        except Exception:
            return False
    
    def check_all_integrity(self) -> Dict[str, Any]:
        """
        检查所有完整性
        
        Returns:
            检查结果
        """
        results = {
            "timestamp": time.time(),
            "core_files": self.verify_integrity(),
            "memory_data": self.verify_memory_integrity()
        }
        
        # 保存检查结果
        result_file = os.path.join(self.integrity_dir, f'check_result_{int(time.time())}.json')
        try:
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        
        return results
    
    def update_checksums(self):
        """
        更新校验和
        """
        self.generate_checksums()
        print("[IntegrityChecker] 校验和已更新")
    
    def get_checksums(self) -> Dict[str, str]:
        """
        获取校验和
        
        Returns:
            校验和字典
        """
        return self.checksums


# 全局完整性校验器实例
integrity_checker = IntegrityChecker()


def get_integrity_checker() -> IntegrityChecker:
    """
    获取完整性校验器实例
    
    Returns:
        完整性校验器实例
    """
    return integrity_checker


def verify_integrity() -> Dict[str, Any]:
    """
    验证核心文件的完整性
    
    Returns:
        验证结果
    """
    return integrity_checker.verify_integrity()


def verify_memory_integrity() -> Dict[str, Any]:
    """
    验证记忆数据的完整性
    
    Returns:
        验证结果
    """
    return integrity_checker.verify_memory_integrity()


def check_all_integrity() -> Dict[str, Any]:
    """
    检查所有完整性
    
    Returns:
        检查结果
    """
    return integrity_checker.check_all_integrity()


def update_checksums():
    """
    更新校验和
    """
    integrity_checker.update_checksums()


def sign_memory_data(data: Dict[str, Any]) -> str:
    """
    签名记忆数据
    
    Args:
        data: 记忆数据
    
    Returns:
        签名
    """
    return integrity_checker.sign_memory_data(data)


def verify_memory_signature(data: Dict[str, Any], signature: str) -> bool:
    """
    验证记忆数据签名
    
    Args:
        data: 记忆数据
        signature: 签名
    
    Returns:
        签名是否有效
    """
    return integrity_checker.verify_memory_signature(data, signature)
