"""
团队协作功能 — 照搬 Claude Code 设计理念
====================================
核心功能：
- 团队成员管理
- 协作会话管理
- 任务分配和跟踪
- 共享资源管理
- 协作权限控制
- 活动日志和通知
"""

import os
import json
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


# ============================================================================# 类型定义# ============================================================================

class TeamRole:
    """团队角色"""
    OWNER = 'owner'
    ADMIN = 'admin'
    MEMBER = 'member'
    GUEST = 'guest'

class TeamMember:
    """团队成员"""
    def __init__(self, id: str, name: str, email: str, role: str, joined_at: datetime.datetime = None,
                 last_active: datetime.datetime = None, metadata: Optional[Dict[str, Any]] = None):
        self.id = id
        self.name = name
        self.email = email
        self.role = role
        self.joined_at = joined_at or datetime.datetime.now()
        self.last_active = last_active or datetime.datetime.now()
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'role': self.role,
            'joined_at': self.joined_at.isoformat(),
            'last_active': self.last_active.isoformat(),
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TeamMember':
        """从字典创建"""
        return cls(
            id=data['id'],
            name=data['name'],
            email=data['email'],
            role=data['role'],
            joined_at=datetime.datetime.fromisoformat(data['joined_at']),
            last_active=datetime.datetime.fromisoformat(data['last_active']),
            metadata=data.get('metadata', {})
        )

class CollaborationSession:
    """协作会话"""
    def __init__(self, id: str, name: str, description: str, created_by: str, created_at: datetime.datetime = None,
                 members: Optional[List[str]] = None, status: str = 'active', metadata: Optional[Dict[str, Any]] = None):
        self.id = id
        self.name = name
        self.description = description
        self.created_by = created_by
        self.created_at = created_at or datetime.datetime.now()
        self.members = members or []
        self.status = status
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat(),
            'members': self.members,
            'status': self.status,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CollaborationSession':
        """从字典创建"""
        return cls(
            id=data['id'],
            name=data['name'],
            description=data['description'],
            created_by=data['created_by'],
            created_at=datetime.datetime.fromisoformat(data['created_at']),
            members=data.get('members', []),
            status=data.get('status', 'active'),
            metadata=data.get('metadata', {})
        )

class TaskStatus:
    """任务状态"""
    TODO = 'todo'
    IN_PROGRESS = 'in_progress'
    DONE = 'done'
    BLOCKED = 'blocked'

class Task:
    """任务"""
    def __init__(self, id: str, title: str, description: str, assignee: str, session_id: str, status: str = TaskStatus.TODO,
                 priority: str = 'medium', due_date: Optional[datetime.datetime] = None, created_by: str = None,
                 created_at: datetime.datetime = None, completed_at: Optional[datetime.datetime] = None,
                 metadata: Optional[Dict[str, Any]] = None):
        self.id = id
        self.title = title
        self.description = description
        self.assignee = assignee
        self.session_id = session_id
        self.status = status
        self.priority = priority
        self.due_date = due_date
        self.created_by = created_by
        self.created_at = created_at or datetime.datetime.now()
        self.completed_at = completed_at
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'assignee': self.assignee,
            'session_id': self.session_id,
            'status': self.status,
            'priority': self.priority,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        """从字典创建"""
        return cls(
            id=data['id'],
            title=data['title'],
            description=data['description'],
            assignee=data['assignee'],
            session_id=data['session_id'],
            status=data.get('status', TaskStatus.TODO),
            priority=data.get('priority', 'medium'),
            due_date=datetime.datetime.fromisoformat(data['due_date']) if data.get('due_date') else None,
            created_by=data.get('created_by'),
            created_at=datetime.datetime.fromisoformat(data['created_at']),
            completed_at=datetime.datetime.fromisoformat(data['completed_at']) if data.get('completed_at') else None,
            metadata=data.get('metadata', {})
        )

class ActivityType:
    """活动类型"""
    MEMBER_JOINED = 'member_joined'
    MEMBER_LEFT = 'member_left'
    SESSION_CREATED = 'session_created'
    SESSION_UPDATED = 'session_updated'
    TASK_CREATED = 'task_created'
    TASK_UPDATED = 'task_updated'
    TASK_COMPLETED = 'task_completed'
    RESOURCE_SHARED = 'resource_shared'
    RESOURCE_UPDATED = 'resource_updated'

class ActivityLog:
    """活动日志"""
    def __init__(self, id: str, type: str, actor: str, message: str, session_id: Optional[str] = None,
                 resource_id: Optional[str] = None, timestamp: datetime.datetime = None,
                 metadata: Optional[Dict[str, Any]] = None):
        self.id = id
        self.type = type
        self.actor = actor
        self.message = message
        self.session_id = session_id
        self.resource_id = resource_id
        self.timestamp = timestamp or datetime.datetime.now()
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'type': self.type,
            'actor': self.actor,
            'message': self.message,
            'session_id': self.session_id,
            'resource_id': self.resource_id,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ActivityLog':
        """从字典创建"""
        return cls(
            id=data['id'],
            type=data['type'],
            actor=data['actor'],
            message=data['message'],
            session_id=data.get('session_id'),
            resource_id=data.get('resource_id'),
            timestamp=datetime.datetime.fromisoformat(data['timestamp']),
            metadata=data.get('metadata', {})
        )


# ============================================================================# 团队管理器# ============================================================================

class TeamManager:
    """
    团队管理器
    功能：
    1. 管理团队成员
    2. 管理协作会话
    3. 管理任务分配和跟踪
    4. 管理共享资源
    5. 记录活动日志
    """
    
    def __init__(self, config):
        """初始化团队管理器"""
        self.config = config
        self.team_dir = os.path.join(config.memory_dir, "team")
        self.members: Dict[str, TeamMember] = {}
        self.sessions: Dict[str, CollaborationSession] = {}
        self.tasks: Dict[str, Task] = {}
        self.activities: List[ActivityLog] = []
        
        # 确保团队目录存在
        os.makedirs(self.team_dir, exist_ok=True)
        
        # 加载团队数据
        self._load_data()
    
    def _load_data(self):
        """加载团队数据"""
        # 加载成员
        members_file = os.path.join(self.team_dir, "members.json")
        if os.path.exists(members_file):
            try:
                with open(members_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for member_data in data:
                    member = TeamMember.from_dict(member_data)
                    self.members[member.id] = member
            except Exception as e:
                print(f"[Team] Failed to load members: {e}")
        
        # 加载会话
        sessions_file = os.path.join(self.team_dir, "sessions.json")
        if os.path.exists(sessions_file):
            try:
                with open(sessions_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for session_data in data:
                    session = CollaborationSession.from_dict(session_data)
                    self.sessions[session.id] = session
            except Exception as e:
                print(f"[Team] Failed to load sessions: {e}")
        
        # 加载任务
        tasks_file = os.path.join(self.team_dir, "tasks.json")
        if os.path.exists(tasks_file):
            try:
                with open(tasks_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for task_data in data:
                    task = Task.from_dict(task_data)
                    self.tasks[task.id] = task
            except Exception as e:
                print(f"[Team] Failed to load tasks: {e}")
        
        # 加载活动日志
        activities_file = os.path.join(self.team_dir, "activities.json")
        if os.path.exists(activities_file):
            try:
                with open(activities_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for activity_data in data:
                    activity = ActivityLog.from_dict(activity_data)
                    self.activities.append(activity)
            except Exception as e:
                print(f"[Team] Failed to load activities: {e}")
    
    def _save_data(self):
        """保存团队数据"""
        # 保存成员
        members_file = os.path.join(self.team_dir, "members.json")
        try:
            data = [member.to_dict() for member in self.members.values()]
            with open(members_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Team] Failed to save members: {e}")
        
        # 保存会话
        sessions_file = os.path.join(self.team_dir, "sessions.json")
        try:
            data = [session.to_dict() for session in self.sessions.values()]
            with open(sessions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Team] Failed to save sessions: {e}")
        
        # 保存任务
        tasks_file = os.path.join(self.team_dir, "tasks.json")
        try:
            data = [task.to_dict() for task in self.tasks.values()]
            with open(tasks_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Team] Failed to save tasks: {e}")
        
        # 保存活动日志
        activities_file = os.path.join(self.team_dir, "activities.json")
        try:
            data = [activity.to_dict() for activity in self.activities]
            with open(activities_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Team] Failed to save activities: {e}")
    
    def add_member(self, name: str, email: str, role: str = TeamRole.MEMBER) -> TeamMember:
        """添加团队成员"""
        import uuid
        member_id = str(uuid.uuid4())
        
        member = TeamMember(
            id=member_id,
            name=name,
            email=email,
            role=role
        )
        
        self.members[member_id] = member
        self._save_data()
        
        # 记录活动
        self._add_activity(
            type=ActivityType.MEMBER_JOINED,
            actor="system",
            message=f"Member {name} joined the team as {role}"
        )
        
        return member
    
    def remove_member(self, member_id: str) -> bool:
        """移除团队成员"""
        if member_id in self.members:
            member = self.members[member_id]
            del self.members[member_id]
            self._save_data()
            
            # 记录活动
            self._add_activity(
                type=ActivityType.MEMBER_LEFT,
                actor="system",
                message=f"Member {member.name} left the team"
            )
            
            return True
        return False
    
    def update_member_role(self, member_id: str, role: str) -> bool:
        """更新成员角色"""
        if member_id in self.members:
            member = self.members[member_id]
            old_role = member.role
            member.role = role
            member.last_active = datetime.datetime.now()
            self._save_data()
            
            # 记录活动
            self._add_activity(
                type=ActivityType.MEMBER_JOINED,  # 复用相同类型
                actor="system",
                message=f"Member {member.name} role changed from {old_role} to {role}"
            )
            
            return True
        return False
    
    def create_session(self, name: str, description: str, created_by: str, members: Optional[List[str]] = None) -> CollaborationSession:
        """创建协作会话"""
        import uuid
        session_id = str(uuid.uuid4())
        
        session = CollaborationSession(
            id=session_id,
            name=name,
            description=description,
            created_by=created_by,
            members=members or []
        )
        
        self.sessions[session_id] = session
        self._save_data()
        
        # 记录活动
        self._add_activity(
            type=ActivityType.SESSION_CREATED,
            actor=created_by,
            message=f"Session '{name}' created",
            session_id=session_id
        )
        
        return session
    
    def add_member_to_session(self, session_id: str, member_id: str) -> bool:
        """添加成员到会话"""
        if session_id in self.sessions and member_id in self.members:
            session = self.sessions[session_id]
            if member_id not in session.members:
                session.members.append(member_id)
                self._save_data()
                
                # 记录活动
                member = self.members[member_id]
                self._add_activity(
                    type=ActivityType.SESSION_UPDATED,
                    actor="system",
                    message=f"Member {member.name} added to session '{session.name}'",
                    session_id=session_id
                )
                
            return True
        return False
    
    def create_task(self, title: str, description: str, assignee: str, session_id: str, priority: str = 'medium',
                    due_date: Optional[datetime.datetime] = None, created_by: str = None) -> Task:
        """创建任务"""
        import uuid
        task_id = str(uuid.uuid4())
        
        task = Task(
            id=task_id,
            title=title,
            description=description,
            assignee=assignee,
            session_id=session_id,
            priority=priority,
            due_date=due_date,
            created_by=created_by
        )
        
        self.tasks[task_id] = task
        self._save_data()
        
        # 记录活动
        self._add_activity(
            type=ActivityType.TASK_CREATED,
            actor=created_by or "system",
            message=f"Task '{title}' created and assigned to {assignee}",
            session_id=session_id,
            resource_id=task_id
        )
        
        return task
    
    def update_task_status(self, task_id: str, status: str) -> bool:
        """更新任务状态"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            old_status = task.status
            task.status = status
            
            if status == TaskStatus.DONE:
                task.completed_at = datetime.datetime.now()
            
            self._save_data()
            
            # 记录活动
            activity_type = ActivityType.TASK_COMPLETED if status == TaskStatus.DONE else ActivityType.TASK_UPDATED
            self._add_activity(
                type=activity_type,
                actor="system",
                message=f"Task '{task.title}' status changed from {old_status} to {status}",
                session_id=task.session_id,
                resource_id=task_id
            )
            
            return True
        return False
    
    def _add_activity(self, type: str, actor: str, message: str, session_id: Optional[str] = None,
                      resource_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        """添加活动日志"""
        import uuid
        activity_id = str(uuid.uuid4())
        
        activity = ActivityLog(
            id=activity_id,
            type=type,
            actor=actor,
            message=message,
            session_id=session_id,
            resource_id=resource_id,
            metadata=metadata
        )
        
        self.activities.append(activity)
        
        # 限制活动日志数量
        if len(self.activities) > 1000:
            self.activities = self.activities[-1000:]
        
        self._save_data()
    
    def get_members(self) -> List[TeamMember]:
        """获取所有成员"""
        return list(self.members.values())
    
    def get_sessions(self) -> List[CollaborationSession]:
        """获取所有会话"""
        return list(self.sessions.values())
    
    def get_tasks(self, session_id: Optional[str] = None, assignee: Optional[str] = None,
                  status: Optional[str] = None) -> List[Task]:
        """获取任务"""
        tasks = list(self.tasks.values())
        
        if session_id:
            tasks = [t for t in tasks if t.session_id == session_id]
        if assignee:
            tasks = [t for t in tasks if t.assignee == assignee]
        if status:
            tasks = [t for t in tasks if t.status == status]
        
        return tasks
    
    def get_activities(self, session_id: Optional[str] = None, limit: int = 50) -> List[ActivityLog]:
        """获取活动日志"""
        activities = self.activities.copy()
        
        if session_id:
            activities = [a for a in activities if a.session_id == session_id]
        
        # 按时间排序（最新的在前）
        activities.sort(key=lambda x: x.timestamp, reverse=True)
        
        # 限制数量
        if limit:
            activities = activities[:limit]
        
        return activities
    
    def get_status(self) -> Dict[str, Any]:
        """获取团队系统状态"""
        total_members = len(self.members)
        total_sessions = len(self.sessions)
        total_tasks = len(self.tasks)
        tasks_by_status = {}
        
        for task in self.tasks.values():
            tasks_by_status[task.status] = tasks_by_status.get(task.status, 0) + 1
        
        return {
            'total_members': total_members,
            'total_sessions': total_sessions,
            'total_tasks': total_tasks,
            'tasks_by_status': tasks_by_status,
            'recent_activities': len(self.activities)
        }


# ============================================================================# 便捷函数# ============================================================================

def create_team_manager(config) -> TeamManager:
    """创建团队管理器"""
    return TeamManager(config)


# 为了兼容性，创建别名
TeamCollaboration = TeamManager
