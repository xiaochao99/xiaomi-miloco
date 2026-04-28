# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Memory Service - Business logic layer for memory management.
记忆服务层 - 记忆管理的业务逻辑层
"""

import logging
import re
from typing import Optional, List, Dict, Any, Callable, Coroutine

from miloco_server.schema.memory_schema import (
    Memory,
    MemoryType,
    MemoryAction,
    MemoryExtractionResult,
    MemorySearchResult,
    MemoryContext,
    MemoryStats,
    ManualMemoryCommand,
)
from miloco_server.memory.memory_manager import MemoryManager, get_memory_manager, initialize_memory_manager
from miloco_server.memory.memory_extractor import MemoryExtractor, SmartMemoryFilter
from miloco_server.memory.memory_retriever import MemoryRetriever, get_memory_retriever

logger = logging.getLogger(__name__)


class MemoryService:
    """
    记忆服务

    提供完整的记忆管理业务逻辑：
    - 自动记忆提取和存储
    - 手动记忆管理
    - 记忆检索和上下文构建
    - 记忆统计
    """

    def __init__(
        self,
        manager: Optional[MemoryManager] = None,
        extractor: Optional[MemoryExtractor] = None,
        retriever: Optional[MemoryRetriever] = None,
    ):
        self._manager = manager
        self._extractor = extractor or MemoryExtractor()
        self._retriever = retriever

    @property
    def manager(self) -> MemoryManager:
        if self._manager is None:
            mgr = get_memory_manager()
            if mgr is None:
                raise RuntimeError("记忆管理器未初始化，请先调用 initialize_memory_manager")
            self._manager = mgr
        return self._manager

    @property
    def retriever(self) -> MemoryRetriever:
        if self._retriever is None:
            ret = get_memory_retriever()
            if ret is None:
                self._retriever = MemoryRetriever(self.manager)
            else:
                self._retriever = ret
        return self._retriever

    @property
    def extractor(self) -> MemoryExtractor:
        return self._extractor

    async def initialize(self, persist_directory: Optional[str] = None) -> bool:
        """初始化记忆服务"""
        try:
            mgr = await initialize_memory_manager(persist_directory)
            self._manager = mgr
            from miloco_server.memory.memory_retriever import initialize_memory_retriever
            self._retriever = initialize_memory_retriever(mgr)
            logger.info("记忆服务初始化完成")
            return True
        except Exception as e:
            logger.error(f"记忆服务初始化失败: {e}")
            return False

    async def process_conversation(
        self,
        messages: List[Dict[str, str]],
        session_id: Optional[str] = None,
    ) -> MemoryExtractionResult:
        """处理对话，自动提取并存储重要记忆"""
        extraction_result = self.extractor.extract_from_conversation(
            messages, session_id
        )

        stored_count = 0
        for memory in extraction_result.memories:
            stored = await self.manager.add_memory(
                content=memory.content,
                memory_type=memory.memory_type,
                metadata=memory.metadata,
                session_id=session_id,
                importance=memory.importance,
            )
            if stored:
                stored_count += 1

        logger.info(
            f"对话记忆处理完成: 提取 {len(extraction_result.memories)} 条，"
            f"存储 {stored_count} 条"
        )
        return extraction_result

    async def add_manual_memory(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.PERSONAL,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.7,
    ) -> Optional[Memory]:
        """手动添加记忆"""
        return await self.manager.add_memory(
            content=content,
            memory_type=memory_type,
            metadata=metadata,
            importance=importance,
        )

    async def search_memories(
        self,
        query: str,
        limit: int = 10,
        memory_type: Optional[MemoryType] = None,
        min_importance: float = 0.0,
    ) -> List[MemorySearchResult]:
        """搜索记忆"""
        return await self.manager.search_memories(
            query=query,
            limit=limit,
            memory_type=memory_type,
            min_importance=min_importance,
        )

    async def get_memory(self, memory_id: str) -> Optional[Memory]:
        """获取单条记忆"""
        return await self.manager.get_memory(memory_id)

    async def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        return await self.manager.delete_memory(memory_id)

    async def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance: Optional[float] = None,
    ) -> Optional[Memory]:
        """更新记忆"""
        return await self.manager.update_memory(
            memory_id=memory_id,
            content=content,
            metadata=metadata,
            importance=importance,
        )

    async def get_context_for_query(
        self,
        query: str,
        max_memories: int = 5,
        min_importance: float = 0.3,
    ) -> MemoryContext:
        """获取与查询相关的记忆上下文"""
        return await self.retriever.retrieve_for_context(
            query=query,
            max_memories=max_memories,
            min_score=min_importance,
        )

    async def get_stats(self) -> MemoryStats:
        """获取记忆统计信息"""
        return await self.manager.get_stats()

    async def get_all_memories(
        self,
        limit: int = 100,
        memory_type: Optional[MemoryType] = None,
    ) -> List[Memory]:
        """获取所有记忆"""
        results = await self.manager.search_memories(
            query="",
            limit=limit,
            memory_type=memory_type,
        )
        return [r.memory for r in results]

    async def handle_manual_command(
        self,
        command: ManualMemoryCommand,
    ) -> Dict[str, Any]:
        """处理手动记忆命令"""
        try:
            if command.action == MemoryAction.ADD:
                if not command.content:
                    return {"success": False, "error": "记忆内容不能为空"}
                memory = await self.add_manual_memory(
                    content=command.content,
                    memory_type=command.memory_type or MemoryType.PERSONAL,
                    metadata=command.metadata,
                    importance=command.importance,
                )
                if memory:
                    return {"success": True, "memory": memory.to_dict()}
                return {"success": False, "error": "添加记忆失败"}

            elif command.action == MemoryAction.SEARCH:
                if not command.query:
                    return {"success": False, "error": "搜索查询不能为空"}
                results = await self.search_memories(
                    query=command.query,
                    memory_type=command.memory_type,
                )
                return {
                    "success": True,
                    "results": [r.to_dict() for r in results],
                    "total": len(results),
                }

            elif command.action == MemoryAction.DELETE:
                if not command.memory_id:
                    return {"success": False, "error": "记忆ID不能为空"}
                success = await self.delete_memory(command.memory_id)
                return {"success": success}

            elif command.action == MemoryAction.UPDATE:
                if not command.memory_id:
                    return {"success": False, "error": "记忆ID不能为空"}
                memory = await self.update_memory(
                    memory_id=command.memory_id,
                    content=command.content,
                    memory_type=command.memory_type,
                    metadata=command.metadata,
                    importance=command.importance,
                )
                if memory:
                    return {"success": True, "memory": memory.to_dict()}
                return {"success": False, "error": "更新记忆失败"}

            elif command.action == MemoryAction.GET_STATS:
                stats = await self.get_stats()
                return {"success": True, "stats": stats.to_dict()}

            elif command.action == MemoryAction.GET_ALL:
                memories = await self.get_all_memories(
                    memory_type=command.memory_type,
                )
                return {
                    "success": True,
                    "memories": [m.to_dict() for m in memories],
                    "total": len(memories),
                }

            elif command.action == MemoryAction.GET_CONTEXT:
                if not command.query:
                    return {"success": False, "error": "查询不能为空"}
                context = await self.get_context_for_query(command.query)
                return {"success": True, "context": context.to_dict()}

            else:
                return {"success": False, "error": f"未知操作: {command.action}"}

        except Exception as e:
            logger.error(f"处理记忆命令失败: {e}")
            return {"success": False, "error": str(e)}


_memory_service: Optional[MemoryService] = None


def get_memory_service() -> Optional[MemoryService]:
    return _memory_service


def initialize_memory_service(
    manager: Optional[MemoryManager] = None,
    persist_directory: Optional[str] = None,
) -> MemoryService:
    global _memory_service
    if _memory_service is not None:
        return _memory_service
    _memory_service = MemoryService(manager=manager)
    return _memory_service


def set_memory_service(service: MemoryService):
    global _memory_service
    _memory_service = service
