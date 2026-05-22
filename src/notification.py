"""
高级通知系统 — 照搬 Claude Code 设计理念
====================================
核心功能：
- 多渠道通知支持
- 通知分类和优先级
- 通知持久化
- 通知模板系统
- 通知历史管理
"""

import os
import json
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


# ============================================================================# 类型定义# ============================================================================

class NotificationType:
    """通知类型"""
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    SUCCESS = 'success'
    SYSTEM = 'system'
    USER = 'user'

class NotificationPriority:
    """通知优先级"""
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    URGENT = 'urgent'

class Notification:
    """通知"""
    def __init__(self, id: str, title: str, message: str, notification_type: str, priority: str,
                 timestamp: datetime.datetime = None, read: bool = False, metadata: Optional[Dict[str, Any]] = None):
        self.id = id
        self.title = title
        self.message = message
        self.type = notification_type
        self.priority = priority
        self.timestamp = timestamp or datetime.datetime.now()
        self.read = read
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'title': self.title,
            'message': self.message,
            'type': self.type,
            'priority': self.priority,
            'timestamp': self.timestamp.isoformat(),
            'read': self.read,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Notification':
        """从字典创建"""
        return cls(
            id=data['id'],
            title=data['title'],
            message=data['message'],
            notification_type=data['type'],
            priority=data['priority'],
            timestamp=datetime.datetime.fromisoformat(data['timestamp']),
            read=data['read'],
            metadata=data.get('metadata', {})
        )


# ============================================================================# 通知管理器# ============================================================================

class NotificationManager:
    """
    通知管理器
    功能：
    1. 管理通知的创建和发送
    2. 处理通知的持久化和加载
    3. 提供通知的查询和过滤
    4. 支持多种通知渠道
    """
    
    # 单例模式实例存储
    _instance = None
    _initialized = False
    
    def __new__(cls, config=None):
        """实现单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config=None):
        """初始化通知管理器"""
        # 防止重复初始化
        if self.__class__._initialized:
            return
        
        if config is None:
            raise ValueError("首次初始化NotificationManager时必须提供config参数")
            
        self.config = config
        self.notifications_dir = os.path.join(config.memory_dir, "notifications")
        self.notifications: List[Notification] = []
        self.channels = {
            'console': self._send_console,
            'file': self._send_file
        }
        
        # 确保通知目录存在
        os.makedirs(self.notifications_dir, exist_ok=True)
        
        # 加载通知历史
        self._load_notifications()
        
        # 标记为已初始化
        self.__class__._initialized = True
    
    def _load_notifications(self):
        """加载通知历史"""
        notifications_file = os.path.join(self.notifications_dir, "notifications.json")
        if os.path.exists(notifications_file):
            try:
                with open(notifications_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for notification_data in data:
                    notification = Notification.from_dict(notification_data)
                    self.notifications.append(notification)
                    
            except Exception as e:
                print(f"[Notification] Failed to load notifications: {e}")
    
    def _save_notifications(self):
        """保存通知历史"""
        notifications_file = os.path.join(self.notifications_dir, "notifications.json")
        try:
            data = [notification.to_dict() for notification in self.notifications]
            with open(notifications_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"[Notification] Failed to save notifications: {e}")
    
    def create_notification(self, title: str, message: str, notification_type: str = NotificationType.INFO,
                           priority: str = NotificationPriority.MEDIUM, metadata: Optional[Dict[str, Any]] = None) -> Notification:
        """创建通知"""
        import uuid
        notification_id = str(uuid.uuid4())
        
        notification = Notification(
            id=notification_id,
            title=title,
            message=message,
            notification_type=notification_type,
            priority=priority,
            metadata=metadata
        )
        
        # 添加到通知列表
        self.notifications.append(notification)
        
        # 保存通知
        self._save_notifications()
        
        # 发送通知
        self.send_notification(notification)
        
        return notification
    
    def send_notification(self, notification: Notification, channels: Optional[List[str]] = None):
        """发送通知"""
        channels = channels or list(self.channels.keys())
        
        for channel in channels:
            if channel in self.channels:
                try:
                    self.channels[channel](notification)
                except Exception as e:
                    print(f"[Notification] Failed to send notification to {channel}: {e}")
    
    def _send_console(self, notification: Notification):
        """发送到控制台"""
        color_map = {
            NotificationType.INFO: '\033[94m',      # 蓝色
            NotificationType.WARNING: '\033[93m',   # 黄色
            NotificationType.ERROR: '\033[91m',     # 红色
            NotificationType.SUCCESS: '\033[92m',   # 绿色
            NotificationType.SYSTEM: '\033[96m',    # 青色
            NotificationType.USER: '\033[95m'       # 紫色
        }
        
        color = color_map.get(notification.type, '\033[0m')
        reset = '\033[0m'
        
        timestamp = notification.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        print(f"{color}[{timestamp}] [{notification.type.upper()}] {notification.title}: {notification.message}{reset}")
    
    def _send_file(self, notification: Notification):
        """发送到文件"""
        log_file = os.path.join(self.notifications_dir, "notification.log")
        timestamp = notification.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] [{notification.type.upper()}] [{notification.priority}] {notification.title}: {notification.message}\n"
        
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            print(f"[Notification] Failed to write to log file: {e}")
    
    def get_notifications(self, limit: Optional[int] = None, unread_only: bool = False,
                         notification_type: Optional[str] = None, priority: Optional[str] = None) -> List[Notification]:
        """获取通知"""
        notifications = self.notifications.copy()
        
        # 过滤未读
        if unread_only:
            notifications = [n for n in notifications if not n.read]
        
        # 过滤类型
        if notification_type:
            notifications = [n for n in notifications if n.type == notification_type]
        
        # 过滤优先级
        if priority:
            notifications = [n for n in notifications if n.priority == priority]
        
        # 按时间排序（最新的在前）
        notifications.sort(key=lambda x: x.timestamp, reverse=True)
        
        # 限制数量
        if limit:
            notifications = notifications[:limit]
        
        return notifications
    
    def mark_as_read(self, notification_id: str) -> bool:
        """标记通知为已读"""
        for notification in self.notifications:
            if notification.id == notification_id:
                notification.read = True
                self._save_notifications()
                return True
        return False
    
    def mark_all_as_read(self) -> int:
        """标记所有通知为已读"""
        count = 0
        for notification in self.notifications:
            if not notification.read:
                notification.read = True
                count += 1
        
        if count > 0:
            self._save_notifications()
        
        return count
    
    def delete_notification(self, notification_id: str) -> bool:
        """删除通知"""
        for i, notification in enumerate(self.notifications):
            if notification.id == notification_id:
                del self.notifications[i]
                self._save_notifications()
                return True
        return False
    
    def delete_old_notifications(self, days: int = 7) -> int:
        """删除旧通知"""
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
        old_count = len([n for n in self.notifications if n.timestamp < cutoff_date])
        
        self.notifications = [n for n in self.notifications if n.timestamp >= cutoff_date]
        
        if old_count > 0:
            self._save_notifications()
        
        return old_count
    
    def get_unread_count(self) -> int:
        """获取未读通知数量"""
        return len([n for n in self.notifications if not n.read])
    
    def get_status(self) -> Dict[str, Any]:
        """获取通知系统状态"""
        total = len(self.notifications)
        unread = self.get_unread_count()
        by_type = {}
        by_priority = {}
        
        for notification in self.notifications:
            by_type[notification.type] = by_type.get(notification.type, 0) + 1
            by_priority[notification.priority] = by_priority.get(notification.priority, 0) + 1
        
        return {
            'total_notifications': total,
            'unread_notifications': unread,
            'notifications_by_type': by_type,
            'notifications_by_priority': by_priority,
            'channels': list(self.channels.keys())
        }


# ============================================================================# 便捷函数# ============================================================================

def create_notification_manager(config=None) -> NotificationManager:
    """创建通知管理器 - 返回单例实例"""
    return NotificationManager(config)

def send_notification(config, title: str, message: str, notification_type: str = NotificationType.INFO,
                      priority: str = NotificationPriority.MEDIUM, metadata: Optional[Dict[str, Any]] = None):
    """发送通知 - 使用单例实例"""
    manager = create_notification_manager(config)
    return manager.create_notification(title, message, notification_type, priority, metadata)


# 为了兼容性，创建别名
NotificationService = NotificationManager
