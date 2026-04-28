# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Context Manager Module

Manages conversation context, state tracking, and context-aware responses.
Supports multi-turn conversations and context persistence.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from datetime import datetime, timedelta
from collections import deque
import copy

logger = logging.getLogger(__name__)


class ContextState(Enum):
    """Context states"""
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    EXECUTING = auto()
    RESPONDING = auto()
    WAITING_CONFIRMATION = auto()
    ERROR = auto()
    COMPLETED = auto()


@dataclass
class Message:
    """Conversation message"""
    role: str  # system, user, assistant, tool
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tool_calls: Optional[List[Dict]] = None
    tool_results: Optional[List[Dict]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "tool_calls": self.tool_calls,
            "tool_results": self.tool_results,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
            tool_calls=data.get("tool_calls"),
            tool_results=data.get("tool_results"),
        )


@dataclass
class ConversationContext:
    """Complete conversation context"""
    session_id: str
    messages: deque = field(default_factory=lambda: deque(maxlen=50))
    state: ContextState = ContextState.IDLE
    entities: Dict[str, Any] = field(default_factory=dict)
    intents: List[str] = field(default_factory=list)
    active_tools: Set[str] = field(default_factory=set)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    session_metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    turn_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "messages": [m.to_dict() for m in self.messages],
            "state": self.state.name,
            "entities": self.entities,
            "intents": self.intents,
            "active_tools": list(self.active_tools),
            "user_preferences": self.user_preferences,
            "session_metadata": self.session_metadata,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "turn_count": self.turn_count,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationContext":
        context = cls(
            session_id=data["session_id"],
            state=ContextState[data.get("state", "IDLE")],
            entities=data.get("entities", {}),
            intents=data.get("intents", []),
            active_tools=set(data.get("active_tools", [])),
            user_preferences=data.get("user_preferences", {}),
            session_metadata=data.get("session_metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_activity=datetime.fromisoformat(data["last_activity"]),
            turn_count=data.get("turn_count", 0),
        )
        context.messages = deque(
            [Message.from_dict(m) for m in data.get("messages", [])],
            maxlen=50
        )
        return context


class ContextManager:
    """
    Context Manager
    
    Manages conversation contexts with state tracking and persistence.
    Supports context summarization and entity extraction.
    """
    
    def __init__(self, max_contexts: int = 100, ttl_seconds: int = 3600):
        """
        Initialize context manager
        
        Args:
            max_contexts: Maximum number of concurrent contexts
            ttl_seconds: Context time-to-live in seconds
        """
        self._contexts: Dict[str, ConversationContext] = {}
        self._max_contexts = max_contexts
        self._ttl = timedelta(seconds=ttl_seconds)
        
        logger.info(f"ContextManager initialized: max_contexts={max_contexts}, ttl={ttl_seconds}s")
    
    def create_context(self, session_id: str, **metadata) -> ConversationContext:
        """
        Create new conversation context
        
        Args:
            session_id: Unique session identifier
            **metadata: Additional session metadata
            
        Returns:
            New conversation context
        """
        # Clean up expired contexts if at limit
        if len(self._contexts) >= self._max_contexts:
            self._cleanup_expired()
        
        context = ConversationContext(
            session_id=session_id,
            session_metadata=metadata,
        )
        self._contexts[session_id] = context
        
        logger.info(f"Created context for session: {session_id}")
        return context
    
    def get_context(self, session_id: str) -> Optional[ConversationContext]:
        """
        Get context by session ID
        
        Args:
            session_id: Session identifier
            
        Returns:
            Context or None if not found/expired
        """
        context = self._contexts.get(session_id)
        
        if context is None:
            return None
        
        # Check if expired
        if datetime.now() - context.last_activity > self._ttl:
            logger.debug(f"Context expired for session: {session_id}")
            del self._contexts[session_id]
            return None
        
        return context
    
    def get_or_create_context(self, session_id: str, **metadata) -> ConversationContext:
        """
        Get existing context or create new one
        
        Args:
            session_id: Session identifier
            **metadata: Metadata for new context
            
        Returns:
            Existing or new context
        """
        context = self.get_context(session_id)
        if context is None:
            context = self.create_context(session_id, **metadata)
        return context
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None,
        tool_calls: Optional[List[Dict]] = None,
        tool_results: Optional[List[Dict]] = None,
    ) -> None:
        """
        Add message to context
        
        Args:
            session_id: Session identifier
            role: Message role
            content: Message content
            metadata: Optional metadata
            tool_calls: Optional tool calls
            tool_results: Optional tool results
        """
        context = self.get_or_create_context(session_id)
        
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {},
            tool_calls=tool_calls,
            tool_results=tool_results,
        )
        
        context.messages.append(message)
        context.last_activity = datetime.now()
        
        if role == "user":
            context.turn_count += 1
        
        logger.debug(f"Added message to {session_id}: {role}")
    
    def update_state(self, session_id: str, state: ContextState) -> None:
        """
        Update context state
        
        Args:
            session_id: Session identifier
            state: New state
        """
        context = self.get_context(session_id)
        if context:
            old_state = context.state
            context.state = state
            context.last_activity = datetime.now()
            logger.debug(f"State change for {session_id}: {old_state.name} -> {state.name}")
    
    def update_entities(self, session_id: str, entities: Dict[str, Any]) -> None:
        """
        Update extracted entities
        
        Args:
            session_id: Session identifier
            entities: Entity dictionary
        """
        context = self.get_context(session_id)
        if context:
            context.entities.update(entities)
            context.last_activity = datetime.now()
    
    def add_intent(self, session_id: str, intent: str) -> None:
        """
        Add recognized intent
        
        Args:
            session_id: Session identifier
            intent: Recognized intent
        """
        context = self.get_context(session_id)
        if context:
            if intent not in context.intents:
                context.intents.append(intent)
            context.last_activity = datetime.now()
    
    def get_recent_messages(
        self,
        session_id: str,
        count: int = 10,
        include_system: bool = True,
    ) -> List[Message]:
        """
        Get recent messages from context
        
        Args:
            session_id: Session identifier
            count: Number of messages to retrieve
            include_system: Whether to include system messages
            
        Returns:
            List of messages
        """
        context = self.get_context(session_id)
        if not context:
            return []
        
        messages = list(context.messages)
        if not include_system:
            messages = [m for m in messages if m.role != "system"]
        
        return messages[-count:]
    
    def get_conversation_summary(self, session_id: str, max_length: int = 500) -> str:
        """
        Get conversation summary
        
        Args:
            session_id: Session identifier
            max_length: Maximum summary length
            
        Returns:
            Summary string
        """
        context = self.get_context(session_id)
        if not context:
            return ""
        
        # Simple summary: combine user intents and key entities
        parts = []
        
        if context.intents:
            parts.append(f"Intents: {', '.join(context.intents[-5:])}")
        
        if context.entities:
            entity_str = ', '.join(f"{k}={v}" for k, v in list(context.entities.items())[:5])
            parts.append(f"Entities: {entity_str}")
        
        # Add last few exchanges
        recent = [m for m in context.messages if m.role in ("user", "assistant")][-3:]
        if recent:
            exchange_str = ' | '.join(f"{m.role}: {m.content[:50]}..." for m in recent)
            parts.append(f"Recent: {exchange_str}")
        
        summary = ' | '.join(parts)
        return summary[:max_length]
    
    def is_context_active(self, session_id: str) -> bool:
        """
        Check if context is active
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if context exists and not expired
        """
        return self.get_context(session_id) is not None
    
    def clear_context(self, session_id: str) -> None:
        """
        Clear specific context
        
        Args:
            session_id: Session identifier
        """
        if session_id in self._contexts:
            del self._contexts[session_id]
            logger.info(f"Cleared context for session: {session_id}")
    
    def clear_all_contexts(self) -> None:
        """Clear all contexts"""
        count = len(self._contexts)
        self._contexts.clear()
        logger.info(f"Cleared all {count} contexts")
    
    def _cleanup_expired(self) -> None:
        """Remove expired contexts"""
        now = datetime.now()
        expired = [
            sid for sid, ctx in self._contexts.items()
            if now - ctx.last_activity > self._ttl
        ]
        
        for sid in expired:
            del self._contexts[sid]
        
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired contexts")
    
    def get_active_sessions(self) -> List[str]:
        """Get list of active session IDs"""
        self._cleanup_expired()
        return list(self._contexts.keys())
    
    def get_context_stats(self) -> Dict[str, Any]:
        """Get context manager statistics"""
        self._cleanup_expired()
        
        total_contexts = len(self._contexts)
        total_messages = sum(len(ctx.messages) for ctx in self._contexts.values())
        avg_turns = sum(ctx.turn_count for ctx in self._contexts.values()) / total_contexts if total_contexts > 0 else 0
        
        return {
            "total_contexts": total_contexts,
            "total_messages": total_messages,
            "average_turns": avg_turns,
            "max_contexts": self._max_contexts,
            "ttl_seconds": self._ttl.total_seconds(),
        }
    
    def export_context(self, session_id: str) -> Optional[str]:
        """
        Export context as JSON string
        
        Args:
            session_id: Session identifier
            
        Returns:
            JSON string or None
        """
        context = self.get_context(session_id)
        if context:
            return json.dumps(context.to_dict(), ensure_ascii=False, indent=2)
        return None
    
    def import_context(self, json_str: str) -> Optional[ConversationContext]:
        """
        Import context from JSON string
        
        Args:
            json_str: JSON string
            
        Returns:
            Imported context or None
        """
        try:
            data = json.loads(json_str)
            context = ConversationContext.from_dict(data)
            self._contexts[context.session_id] = context
            return context
        except Exception as e:
            logger.error(f"Failed to import context: {e}")
            return None
    
    def fork_context(self, source_session_id: str, new_session_id: str) -> Optional[ConversationContext]:
        """
        Fork existing context to new session
        
        Args:
            source_session_id: Source session ID
            new_session_id: New session ID
            
        Returns:
            New context or None
        """
        source = self.get_context(source_session_id)
        if not source:
            return None
        
        # Deep copy context
        new_context = copy.deepcopy(source)
        new_context.session_id = new_session_id
        new_context.created_at = datetime.now()
        new_context.last_activity = datetime.now()
        new_context.turn_count = 0
        
        self._contexts[new_session_id] = new_context
        logger.info(f"Forked context from {source_session_id} to {new_session_id}")
        
        return new_context


# Global context manager instance
context_manager = ContextManager()
