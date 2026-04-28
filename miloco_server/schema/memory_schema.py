# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Memory Schema - Data models for memory management.
记忆数据模型 - 定义记忆管理相关的数据结构
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class MemoryType(str, Enum):
    """记忆类型枚举"""
    CONVERSATION = "conversation"
    USER_PREFERENCE = "user_preference"
    OBJECT_LOCATION = "object_location"
    PET_BEHAVIOR = "pet_behavior"
    SCHEDULE = "schedule"
    PERSONAL = "personal"
    CUSTOM = "custom"


class MemoryAction(str, Enum):
    """记忆操作类型"""
    ADD = "add"
    SEARCH = "search"
    UPDATE = "update"
    DELETE = "delete"
    GET = "get"
    GET_STATS = "get_stats"
    GET_ALL = "get_all"
    GET_CONTEXT = "get_context"


class Memory:
    """记忆数据模型"""

    def __init__(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.CONVERSATION,
        metadata: Optional[Dict[str, Any]] = None,
        id: Optional[str] = None,
        session_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        importance: float = 0.5,
    ):
        self.id = id
        self.content = content
        self.memory_type = memory_type
        self.metadata = metadata or {}
        self.session_id = session_id
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()
        self.importance = importance

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "metadata": self.metadata,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "importance": self.importance,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Memory":
        return cls(
            id=data.get("id"),
            content=data.get("content", ""),
            memory_type=MemoryType(data.get("memory_type", "conversation")),
            metadata=data.get("metadata", {}),
            session_id=data.get("session_id"),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else None
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if data.get("updated_at")
                else None
            ),
            importance=data.get("importance", 0.5),
        )


class MemoryExtractionResult:
    """记忆提取结果"""

    def __init__(
        self,
        memories: List[Memory],
        extraction_time: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.memories = memories
        self.extraction_time = extraction_time or datetime.now()
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memories": [m.to_dict() for m in self.memories],
            "extraction_time": (
                self.extraction_time.isoformat()
                if self.extraction_time
                else None
            ),
            "metadata": self.metadata,
        }


class MemorySearchResult:
    """记忆搜索结果"""

    def __init__(self, memory: Memory, score: float = 0.0):
        self.memory = memory
        self.score = score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory": self.memory.to_dict(),
            "score": self.score,
        }


class MemoryContext:
    """记忆上下文，用于注入到 LLM 对话中"""

    def __init__(
        self,
        query: str = "",
        relevant_memories: Optional[List[Memory]] = None,
        summary: str = "",
        total_count: int = 0,
    ):
        self.query = query
        self.relevant_memories = relevant_memories or []
        self.summary = summary
        self.total_count = total_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "relevant_memories": [m.to_dict() for m in self.relevant_memories],
            "summary": self.summary,
            "total_count": self.total_count,
        }


class MemoryStats:
    """记忆统计信息"""

    def __init__(
        self,
        total_count: int = 0,
        type_counts: Optional[Dict[str, int]] = None,
        avg_importance: float = 0.0,
    ):
        self.total_count = total_count
        self.type_counts = type_counts or {}
        self.avg_importance = avg_importance

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_count": self.total_count,
            "type_counts": self.type_counts,
            "avg_importance": self.avg_importance,
        }


class ManualMemoryCommand:
    """手动记忆命令"""

    def __init__(
        self,
        action: MemoryAction = MemoryAction.ADD,
        content: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        memory_id: Optional[str] = None,
        query: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
    ):
        self.action = action
        self.content = content
        self.memory_type = memory_type
        self.memory_id = memory_id
        self.query = query
        self.metadata = metadata
        self.importance = importance
