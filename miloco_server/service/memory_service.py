# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according of the terms of the Xiaomi Miloco License Agreement.

"""
Memory Service - Business logic layer for memory management.
记忆服务层 - 记忆管理的业务逻辑层
"""

import logging
from typing import Optional, List, Dict, Any

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
from miloco_server.memory.memory_manager import MemoryManager, get_memory_manager
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
        self._extractor = extractor
        self._retriever = retriever
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def manager(self) -> MemoryManager:
        if self._manager is None:
            self._manager = get_memory_manager()
        return self._manager

    @property
    def retriever(self) -> MemoryRetriever:
        if self._retriever is None:
            self._retriever = get_memory_retriever()
        return self._retriever

    @property
    def extractor(self) -> MemoryExtractor:
        if self._extractor is None:
            self._extractor = MemoryExtractor(self._call_llm)
        return self._extractor

    async def _call_llm(self, messages: List[dict]) -> dict:
        """LLM调用函数，需要在初始化时提供"""
        raise NotImplementedError("需要提供 LLM 调用函数")

    async def initialize(self, persist_directory: Optional[str] = None) -> bool:
        """初始化记忆服务"""
        try:
            from miloco_server.memory.memory_manager import initialize_memory_manager
            success = await initialize_memory_manager()
            if not success:
                logger.warning("MemoryManager initialization failed")
                return False

            self._manager = get_memory_manager()
            self._initialized = True
            logger.info("记忆服务初始化完成")
            return True
        except Exception as e:
            logger.error(f"记忆服务初始化失败: {e}")
            return False

    async def process_conversation(
        self,
        user_message: str,
        assistant_response: Optional[str] = None,
        user_id: str = "default",
    ) -> MemoryExtractionResult:
        """
        处理对话，自动提取并存储重要记忆

        Args:
            user_message: 用户消息
            assistant_response: 助手响应
            user_id: 用户ID

        Returns:
            MemoryExtractionResult: 提取结果
        """
        try:
            if SmartMemoryFilter.should_skip(user_message):
                logger.debug("消息跳过记忆提取: %s", user_message[:50])
                return MemoryExtractionResult(
                    should_save=False,
                    action=MemoryAction.NONE,
                    memories=[],
                    reasoning="消息被智能过滤器跳过"
                )

            if SmartMemoryFilter.is_memory_management_command(user_message):
                logger.debug("检测到记忆管理命令: %s", user_message[:50])
                cmd_result = await self.handle_manual_command(user_message, user_id)
                if cmd_result.get("success"):
                    return MemoryExtractionResult(
                        should_save=False,
                        action=MemoryAction.NONE,
                        memories=[],
                        reasoning=f"手动命令已处理: {cmd_result.get('message', '')}"
                    )

            result = await self.extractor.extract_memories(
                user_message=user_message,
                assistant_response=assistant_response,
            )

            if result.should_save and result.memories:
                for memory in result.memories:
                    await self.manager.add_memory(
                        content=memory.content,
                        user_id=user_id,
                        memory_type=memory.memory_type,
                        metadata=memory.metadata,
                        source="auto",
                    )
                logger.info("自动提取并存储 %d 条记忆", len(result.memories))

            return result

        except Exception as e:
            logger.error("处理对话记忆失败: %s", e)
            return MemoryExtractionResult(
                should_save=False,
                action=MemoryAction.NONE,
                memories=[],
                reasoning=f"处理失败: {str(e)}"
            )

    async def add_memory(
        self,
        content: str,
        user_id: str = "default",
        memory_type: MemoryType = MemoryType.CUSTOM,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Memory]:
        """手动添加记忆"""
        try:
            memory = await self.manager.add_memory(
                content=content,
                user_id=user_id,
                memory_type=memory_type,
                metadata=metadata,
                source="manual",
            )
            if memory:
                logger.info("手动添加记忆: %s", content[:50])
            return memory
        except Exception as e:
            logger.error("添加记忆失败: %s", e)
            return None

    async def search_memories(
        self,
        query: str,
        user_id: str = "default",
        limit: int = 5,
        memory_types: Optional[List[MemoryType]] = None,
    ) -> List[MemorySearchResult]:
        """搜索记忆"""
        return await self.manager.search_memories(
            query=query,
            user_id=user_id,
            limit=limit,
            memory_types=memory_types,
        )

    async def get_memory(self, memory_id: str) -> Optional[Memory]:
        """获取单条记忆"""
        return await self.manager.get_memory(memory_id)

    async def delete_memory(self, memory_id: str, soft_delete: bool = True) -> bool:
        """删除记忆"""
        return await self.manager.delete_memory(memory_id, soft_delete=soft_delete)

    async def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        metadata: Optional[Dict[str, Any]] = None,
        is_active: Optional[bool] = None,
    ) -> bool:
        """更新记忆"""
        return await self.manager.update_memory(
            memory_id=memory_id,
            content=content,
            memory_type=memory_type,
            metadata=metadata,
            is_active=is_active,
        )

    async def get_context_for_query(
        self,
        query: str,
        user_id: str = "default",
        limit: int = 5,
    ) -> MemoryContext:
        """获取与查询相关的记忆上下文"""
        return await self.manager.get_memory_context(
            query=query,
            user_id=user_id,
            limit=limit,
        )

    async def get_full_context(
        self,
        query: str,
        user_id: str = "default",
    ) -> MemoryContext:
        """获取记忆上下文（用于注入到Prompt）"""
        return await self.retriever.build_full_context(
            query=query,
            user_id=user_id,
            max_memories=5,
            min_relevance=0.35,
        )

    async def get_stats(self, user_id: str = "default") -> MemoryStats:
        """获取记忆统计信息"""
        return await self.manager.get_stats(user_id=user_id)

    async def get_all_memories(
        self,
        user_id: str = "default",
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Memory]:
        """获取所有记忆"""
        return await self.manager.get_all_memories(
            user_id=user_id,
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
        )

    async def handle_manual_command(
        self,
        command: str,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """
        处理自然语言记忆管理指令

        Args:
            command: 用户的自然语言指令
            user_id: 用户ID

        Returns:
            处理结果字典
        """
        try:
            parsed = await self.extractor.parse_manual_command(command)

            if parsed.action == MemoryAction.ADD:
                if not parsed.content:
                    return {"success": False, "message": "记忆内容不能为空"}

                memory = await self.add_memory(
                    content=parsed.content,
                    user_id=user_id,
                    memory_type=parsed.memory_type or MemoryType.CUSTOM,
                )

                if memory:
                    return {
                        "success": True,
                        "message": "记忆添加成功",
                        "memory": memory.to_dict()
                    }
                return {"success": False, "message": "添加记忆失败"}

            elif parsed.action == MemoryAction.DELETE:
                if parsed.target_description:
                    results = await self.search_memories(
                        query=parsed.target_description,
                        user_id=user_id,
                        limit=5,
                    )
                    if results:
                        for result in results:
                            await self.delete_memory(result.memory.id)
                        return {
                            "success": True,
                            "message": f"已删除 {len(results)} 条相关记忆"
                        }
                return {"success": False, "message": "未找到要删除的记忆"}

            elif parsed.action == MemoryAction.UPDATE:
                if parsed.target_description:
                    results = await self.search_memories(
                        query=parsed.target_description,
                        user_id=user_id,
                        limit=1,
                    )
                    if results:
                        target = results[0].memory
                        success = await self.update_memory(
                            memory_id=target.id,
                            content=parsed.content or None,
                            memory_type=parsed.memory_type or None,
                        )
                        if success:
                            return {"success": True, "message": "记忆更新成功"}
                return {"success": False, "message": "未找到要更新的记忆"}

            elif parsed.action == MemoryAction.QUERY:
                if parsed.target_description:
                    results = await self.search_memories(
                        query=parsed.target_description,
                        user_id=user_id,
                        limit=10,
                    )
                    return {
                        "success": True,
                        "message": f"找到 {len(results)} 条相关记忆",
                        "memories": [r.memory.to_dict() for r in results]
                    }
                context = await self.get_full_context(
                    query=command,
                    user_id=user_id,
                )
                return {
                    "success": True,
                    "message": f"找到 {len(context.memories)} 条相关记忆",
                    "context": context.to_dict()
                }

            else:
                return {"success": False, "message": "无法理解指令"}

        except Exception as e:
            logger.error("处理记忆命令失败: %s", e)
            return {"success": False, "message": f"处理失败: {str(e)}"}


_memory_service: Optional[MemoryService] = None


def get_memory_service() -> Optional[MemoryService]:
    return _memory_service


def initialize_memory_service() -> MemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service


def set_memory_service(service: MemoryService):
    global _memory_service
    _memory_service = service
