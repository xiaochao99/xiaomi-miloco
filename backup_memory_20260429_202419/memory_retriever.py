# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Memory Retriever - Advanced retrieval strategies for memory.
记忆检索器 - 高级记忆检索策略
"""

import logging
from typing import List, Optional, Dict, Any

from miloco_server.schema.memory_schema import (
    Memory,
    MemoryType,
    MemorySearchResult,
    MemoryContext,
)
from miloco_server.memory.memory_manager import MemoryManager, get_memory_manager

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONTEXT_MEMORIES = 5
DEFAULT_MIN_RELEVANCE_SCORE = 0.3


class MemoryRetriever:
    """高级记忆检索器，支持多策略检索"""

    def __init__(self, manager: Optional[MemoryManager] = None):
        self._manager = manager

    @property
    def manager(self) -> MemoryManager:
        if self._manager is None:
            mgr = get_memory_manager()
            if mgr is None:
                raise RuntimeError("记忆管理器未初始化")
            self._manager = mgr
        return self._manager

    async def retrieve_for_context(
        self,
        query: str,
        max_memories: int = DEFAULT_MAX_CONTEXT_MEMORIES,
        min_score: float = DEFAULT_MIN_RELEVANCE_SCORE,
        memory_types: Optional[List[MemoryType]] = None,
    ) -> MemoryContext:
        """为 LLM 对话检索相关记忆"""
        all_results: List[MemorySearchResult] = []

        semantic_results = await self.manager.search_memories(
            query=query,
            limit=max_memories * 2,
            min_importance=0.3,
        )
        all_results.extend(semantic_results)

        if memory_types:
            for mtype in memory_types:
                type_results = await self.manager.search_memories(
                    query=query,
                    limit=max_memories,
                    memory_type=mtype,
                    min_importance=0.3,
                )
                all_results.extend(type_results)

        deduplicated = self._deduplicate_results(all_results)
        scored = self._score_results(deduplicated, query)
        filtered = [r for r in scored if r.score >= min_score]
        filtered.sort(key=lambda x: x.score, reverse=True)
        top_results = filtered[:max_memories]

        memories = [r.memory for r in top_results]
        summary = self._build_context_summary(memories)

        return MemoryContext(
            query=query,
            relevant_memories=memories,
            summary=summary,
            total_count=len(memories),
        )

    async def retrieve_recent(
        self,
        limit: int = 10,
        memory_type: Optional[MemoryType] = None,
    ) -> List[Memory]:
        """获取最近的记忆"""
        results = await self.manager.search_memories(
            query="",
            limit=limit,
            memory_type=memory_type,
        )
        return [r.memory for r in results]

    async def retrieve_important(
        self,
        limit: int = 10,
        min_importance: float = 0.7,
    ) -> List[Memory]:
        """获取重要记忆"""
        results = await self.manager.search_memories(
            query="",
            limit=limit,
            min_importance=min_importance,
        )
        return [r.memory for r in results]

    async def retrieve_by_type(
        self,
        memory_type: MemoryType,
        limit: int = 50,
    ) -> List[Memory]:
        """按类型获取记忆"""
        results = await self.manager.search_memories(
            query="",
            limit=limit,
            memory_type=memory_type,
        )
        return [r.memory for r in results]

    def _deduplicate_results(
        self,
        results: List[MemorySearchResult],
    ) -> List[MemorySearchResult]:
        seen_ids = set()
        deduplicated = []
        for r in results:
            if r.memory.id not in seen_ids:
                seen_ids.add(r.memory.id)
                deduplicated.append(r)
        return deduplicated

    def _score_results(
        self,
        results: List[MemorySearchResult],
        query: str,
    ) -> List[MemorySearchResult]:
        for r in results:
            importance_bonus = r.memory.importance * 0.2
            r.score = min(1.0, r.score + importance_bonus)
        return results

    def _build_context_summary(self, memories: List[Memory]) -> str:
        if not memories:
            return "暂无相关记忆"

        parts = []
        for mem in memories:
            parts.append(f"- {mem.content}")

        return "相关记忆:\n" + "\n".join(parts)


_memory_retriever: Optional[MemoryRetriever] = None


def get_memory_retriever() -> Optional[MemoryRetriever]:
    return _memory_retriever


def initialize_memory_retriever(
    manager: Optional[MemoryManager] = None,
) -> MemoryRetriever:
    global _memory_retriever
    _memory_retriever = MemoryRetriever(manager)
    return _memory_retriever
