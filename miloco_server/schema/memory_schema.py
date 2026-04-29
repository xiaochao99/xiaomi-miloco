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
    PREFERENCE = "preference"
    FACT = "fact"
    HABIT = "habit"
    DEVICE_SETTING = "device_setting"
    SCHEDULE = "schedule"
    RELATIONSHIP = "relationship"
    CONVERSATION = "conversation"
    USER_PREFERENCE = "user_preference"
    OBJECT_LOCATION = "object_location"
    PET_BEHAVIOR = "pet_behavior"
    PERSONAL = "personal"
    CUSTOM = "custom"


class MemoryAction(str, Enum):
    """记忆操作类型"""
    ADD = "add"
    UPDATE = "update"
    DELETE = "delete"
    QUERY = "query"
    NONE = "none"
    SEARCH = "search"
    GET = "get"
    GET_STATS = "get_stats"
    GET_ALL = "get_all"
    GET_CONTEXT = "get_context"


class Memory:
    """记忆数据模型"""

    def __init__(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.CUSTOM,
        metadata: Optional[Dict[str, Any]] = None,
        id: Optional[str] = None,
        user_id: str = "default",
        session_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        source: str = "auto",
        is_active: bool = True,
        confidence: float = 1.0,
    ):
        self.id = id
        self.content = content
        self.memory_type = memory_type
        self.metadata = metadata or {}
        self.user_id = user_id
        self.session_id = session_id
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()
        self.source = source
        self.is_active = is_active
        self.confidence = confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "metadata": self.metadata,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "source": self.source,
            "is_active": self.is_active,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Memory":
        return cls(
            id=data.get("id"),
            content=data.get("content", ""),
            memory_type=MemoryType(data.get("memory_type", "custom")),
            metadata=data.get("metadata", {}),
            user_id=data.get("user_id", "default"),
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
            source=data.get("source", "auto"),
            is_active=data.get("is_active", True),
            confidence=data.get("confidence", 1.0),
        )


class MemoryExtractionResult:
    """记忆提取结果"""

    def __init__(
        self,
        memories: Optional[List[Memory]] = None,
        extraction_time: Optional[datetime] = None,
        should_save: bool = False,
        action: MemoryAction = MemoryAction.NONE,
        reasoning: str = "",
        related_memory_ids: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.memories = memories or []
        self.extraction_time = extraction_time or datetime.now()
        self.should_save = should_save
        self.action = action
        self.reasoning = reasoning
        self.related_memory_ids = related_memory_ids or []
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "should_save": self.should_save,
            "action": self.action.value,
            "memories": [m.to_dict() for m in self.memories],
            "reasoning": self.reasoning,
            "related_memory_ids": self.related_memory_ids,
            "extraction_time": (
                self.extraction_time.isoformat()
                if self.extraction_time
                else None
            ),
            "metadata": self.metadata,
        }


class MemorySearchResult:
    """记忆搜索结果"""

    def __init__(
        self,
        memory: Memory,
        score: float = 0.0,
        distance: float = 0.0,
    ):
        self.memory = memory
        self.score = score
        self.distance = distance

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory": self.memory.to_dict(),
            "score": self.score,
            "distance": self.distance,
        }


class MemoryContext:
    """记忆上下文，用于注入到 LLM 对话中"""

    def __init__(
        self,
        memories: Optional[List[MemorySearchResult]] = None,
        query: str = "",
        relevant_memories: Optional[List[Memory]] = None,
        summary: str = "",
        total_count: int = 0,
        context_text: str = "",
    ):
        self.query = query
        self.memories = memories or []
        self.relevant_memories = relevant_memories or []
        self.summary = summary
        self.total_count = total_count
        self.context_text = context_text

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "memories": [m.to_dict() if isinstance(m, MemorySearchResult) else m for m in self.memories],
            "relevant_memories": [m.to_dict() for m in self.relevant_memories],
            "summary": self.summary,
            "total_count": self.total_count,
            "context_text": self.context_text,
        }

    def to_prompt_text(self) -> str:
        """将记忆上下文转换为用于Prompt的文本格式"""
        if not self.memories:
            return ""

        parts = ["[相关记忆上下文]"]
        for i, result in enumerate(self.memories, 1):
            if isinstance(result, MemorySearchResult):
                parts.append(f"{i}. [{result.memory.memory_type.value}] {result.memory.content}")
            else:
                parts.append(f"{i}. {result.content}")

        parts.append("[/相关记忆上下文]")
        return "\n".join(parts)


class MemoryStats:
    """记忆统计信息"""

    def __init__(
        self,
        total_count: int = 0,
        by_type: Optional[Dict[str, int]] = None,
        by_source: Optional[Dict[str, int]] = None,
        active_count: int = 0,
        avg_importance: float = 0.0,
    ):
        self.total_count = total_count
        self.by_type = by_type or {}
        self.by_source = by_source or {}
        self.active_count = active_count
        self.avg_importance = avg_importance

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_count": self.total_count,
            "by_type": self.by_type,
            "by_source": self.by_source,
            "active_count": self.active_count,
            "avg_importance": self.avg_importance,
        }


class ManualMemoryCommand:
    """手动记忆命令"""

    def __init__(
        self,
        action: MemoryAction = MemoryAction.NONE,
        content: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        memory_id: Optional[str] = None,
        query: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        target_description: str = "",
        confidence: float = 0.0,
    ):
        self.action = action
        self.content = content
        self.memory_type = memory_type
        self.memory_id = memory_id
        self.query = query
        self.metadata = metadata
        self.target_description = target_description
        self.confidence = confidence
