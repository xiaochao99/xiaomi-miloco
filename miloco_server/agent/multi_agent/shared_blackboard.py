# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Shared Blackboard Module

共享黑板 - Agent间无通信的数据共享机制

优势:
1. 消除Agent间直接通信开销
2. 所有Agent读取同一份数据，保证一致性
3. 支持异步写入，不阻塞其他Agent
4. 内置过期机制，自动清理陈旧数据
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable, Awaitable
from datetime import datetime
from enum import Enum, auto

logger = logging.getLogger(__name__)


class BlackboardNamespace(Enum):
    """黑板命名空间 - 用于隔离不同类型的数据"""
    SESSION = auto()      # 会话相关数据
    DEVICE = auto()       # 设备状态数据
    CONTEXT = auto()      # 上下文数据
    RESULT = auto()       # 执行结果数据
    AGENT = auto()        # Agent状态数据
    RULE = auto()         # 规则引擎数据


@dataclass
class BlackboardEntry:
    """黑板条目"""
    key: str
    value: Any
    source: str
    namespace: BlackboardNamespace = BlackboardNamespace.SESSION
    timestamp: datetime = field(default_factory=datetime.now)
    ttl_seconds: int = 300
    version: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        return (datetime.now() - self.timestamp).seconds > self.ttl_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "source": self.source,
            "namespace": self.namespace.name,
            "timestamp": self.timestamp.isoformat(),
            "ttl_seconds": self.ttl_seconds,
            "version": self.version,
            "metadata": self.metadata,
        }


class SharedBlackboard:
    """
    共享黑板 - AHAA架构的核心数据共享组件

    使用命名空间隔离不同类型的数据，支持TTL过期、订阅通知和并发安全访问。

    用法:
        blackboard = SharedBlackboard()

        # 写入数据
        await blackboard.write("session_123", {"state": "active"}, source="router")

        # 读取数据
        session_data = await blackboard.read("session_123")

        # 订阅变化
        blackboard.subscribe("session_123", on_session_change)

        # 按模式读取
        all_sessions = await blackboard.read_pattern("session_", namespace=BlackboardNamespace.SESSION)
    """

    def __init__(self, max_entries: int = 10000, cleanup_interval: int = 60):
        self._board: Dict[str, BlackboardEntry] = {}
        self._lock = asyncio.Lock()
        self._subscribers: Dict[str, List[Callable[..., Awaitable[None]]]] = {}
        self._pattern_subscribers: Dict[str, List[Callable[..., Awaitable[None]]]] = {}
        self._max_entries = max_entries
        self._cleanup_interval = cleanup_interval
        self._stats = {
            "writes": 0,
            "reads": 0,
            "hits": 0,
            "misses": 0,
            "evictions": 0,
        }
        logger.info(f"SharedBlackboard initialized: max_entries={max_entries}")

    async def write(
        self,
        key: str,
        value: Any,
        source: str,
        namespace: BlackboardNamespace = BlackboardNamespace.SESSION,
        ttl: int = 300,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        async with self._lock:
            existing = self._board.get(key)
            version = (existing.version + 1) if existing else 0

            self._board[key] = BlackboardEntry(
                key=key,
                value=value,
                source=source,
                namespace=namespace,
                ttl_seconds=ttl,
                version=version,
                metadata=metadata or {},
            )
            self._stats["writes"] += 1

            if len(self._board) > self._max_entries:
                await self._evict_oldest()

        for callback in self._subscribers.get(key, []):
            try:
                await callback(key, value, source)
            except Exception as e:
                logger.error(f"Subscriber callback error for key '{key}': {e}")

        for pattern, callbacks in self._pattern_subscribers.items():
            if pattern in key:
                for callback in callbacks:
                    try:
                        await callback(key, value, source)
                    except Exception as e:
                        logger.error(f"Pattern subscriber callback error: {e}")

        logger.debug(f"Blackboard write: {key} (version={version}, source={source})")
        return version

    async def read(self, key: str, default: Any = None) -> Any:
        self._stats["reads"] += 1
        entry = self._board.get(key)
        if entry and not entry.is_expired():
            self._stats["hits"] += 1
            return entry.value
        self._stats["misses"] += 1
        return default

    async def read_entry(self, key: str) -> Optional[BlackboardEntry]:
        entry = self._board.get(key)
        if entry and not entry.is_expired():
            return entry
        return None

    async def read_pattern(
        self,
        pattern: str,
        namespace: Optional[BlackboardNamespace] = None,
    ) -> Dict[str, Any]:
        result = {}
        for key, entry in self._board.items():
            if pattern in key and not entry.is_expired():
                if namespace is None or entry.namespace == namespace:
                    result[key] = entry.value
        return result

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._board:
                del self._board[key]
                logger.debug(f"Blackboard delete: {key}")
                return True
            return False

    async def clear_namespace(self, namespace: BlackboardNamespace) -> int:
        async with self._lock:
            keys_to_delete = [
                key for key, entry in self._board.items()
                if entry.namespace == namespace
            ]
            for key in keys_to_delete:
                del self._board[key]
            logger.debug(f"Cleared {len(keys_to_delete)} entries from namespace {namespace.name}")
            return len(keys_to_delete)

    def subscribe(self, key: str, callback: Callable[..., Awaitable[None]]) -> None:
        self._subscribers.setdefault(key, []).append(callback)
        logger.debug(f"Subscribed to key: {key}")

    def subscribe_pattern(self, pattern: str, callback: Callable[..., Awaitable[None]]) -> None:
        self._pattern_subscribers.setdefault(pattern, []).append(callback)
        logger.debug(f"Subscribed to pattern: {pattern}")

    def unsubscribe(self, key: str, callback: Optional[Callable] = None) -> None:
        if key in self._subscribers:
            if callback:
                self._subscribers[key] = [cb for cb in self._subscribers[key] if cb != callback]
            else:
                del self._subscribers[key]

    async def _evict_oldest(self) -> None:
        if not self._board:
            return
        oldest_key = min(self._board, key=lambda k: self._board[k].timestamp)
        del self._board[oldest_key]
        self._stats["evictions"] += 1
        logger.debug(f"Evicted oldest entry: {oldest_key}")

    async def cleanup_expired(self) -> int:
        async with self._lock:
            expired_keys = [
                key for key, entry in self._board.items()
                if entry.is_expired()
            ]
            for key in expired_keys:
                del self._board[key]
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired entries")
            return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        total_entries = len(self._board)
        hit_rate = (
            self._stats["hits"] / self._stats["reads"]
            if self._stats["reads"] > 0
            else 0.0
        )
        return {
            **self._stats,
            "total_entries": total_entries,
            "hit_rate": hit_rate,
            "subscriber_count": sum(len(v) for v in self._subscribers.values()),
        }

    def __len__(self) -> int:
        return len(self._board)
