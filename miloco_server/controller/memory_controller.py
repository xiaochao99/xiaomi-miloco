# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Memory Controller - REST API for memory management.
记忆控制器 - 提供记忆管理的 REST API 接口
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from miloco_server.schema.memory_schema import MemoryType, MemoryAction, ManualMemoryCommand
from miloco_server.service.memory_service import MemoryService, get_memory_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["记忆管理"])


def get_service() -> MemoryService:
    service = get_memory_service()
    if service is None:
        raise RuntimeError("记忆服务未初始化，请等待应用启动完成")
    return service


class AddMemoryRequest(BaseModel):
    content: str
    memory_type: str = "personal"
    importance: float = 0.7
    metadata: Optional[dict] = None


class UpdateMemoryRequest(BaseModel):
    content: Optional[str] = None
    memory_type: Optional[str] = None
    importance: Optional[float] = None
    metadata: Optional[dict] = None


class SearchMemoryRequest(BaseModel):
    query: str
    limit: int = 10
    memory_type: Optional[str] = None
    min_importance: float = 0.0


@router.post("/add")
async def add_memory(request: AddMemoryRequest):
    """手动添加记忆"""
    try:
        service = get_service()
        mtype = MemoryType(request.memory_type)
        memory = await service.add_manual_memory(
            content=request.content,
            memory_type=mtype,
            metadata=request.metadata,
            importance=request.importance,
        )
        if memory:
            return {"success": True, "memory": memory.to_dict()}
        raise HTTPException(status_code=500, detail="添加记忆失败")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效的记忆类型: {e}")
    except Exception as e:
        logger.error(f"添加记忆失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
async def search_memories(request: SearchMemoryRequest):
    """搜索记忆"""
    try:
        service = get_service()
        mtype = MemoryType(request.memory_type) if request.memory_type else None
        results = await service.search_memories(
            query=request.query,
            limit=request.limit,
            memory_type=mtype,
            min_importance=request.min_importance,
        )
        return {
            "success": True,
            "results": [r.to_dict() for r in results],
            "total": len(results),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效的参数: {e}")
    except Exception as e:
        logger.error(f"搜索记忆失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_memories(
    limit: int = Query(100, ge=1, le=1000),
    memory_type: Optional[str] = Query(None),
):
    """获取所有记忆"""
    try:
        service = get_service()
        mtype = MemoryType(memory_type) if memory_type else None
        memories = await service.get_all_memories(limit=limit, memory_type=mtype)
        return {
            "success": True,
            "memories": [m.to_dict() for m in memories],
            "total": len(memories),
        }
    except Exception as e:
        logger.error(f"获取记忆列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_memory_stats():
    """获取记忆统计信息"""
    try:
        service = get_service()
        stats = await service.get_stats()
        return {"success": True, "stats": stats.to_dict()}
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{memory_id}")
async def get_memory(memory_id: str):
    """获取单条记忆"""
    try:
        service = get_service()
        memory = await service.get_memory(memory_id)
        if memory:
            return {"success": True, "memory": memory.to_dict()}
        raise HTTPException(status_code=404, detail="记忆不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取记忆失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{memory_id}")
async def update_memory(memory_id: str, request: UpdateMemoryRequest):
    """更新记忆"""
    try:
        service = get_service()
        mtype = MemoryType(request.memory_type) if request.memory_type else None
        memory = await service.update_memory(
            memory_id=memory_id,
            content=request.content,
            memory_type=mtype,
            metadata=request.metadata,
            importance=request.importance,
        )
        if memory:
            return {"success": True, "memory": memory.to_dict()}
        raise HTTPException(status_code=404, detail="记忆不存在或更新失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新记忆失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str):
    """删除记忆"""
    try:
        service = get_service()
        success = await service.delete_memory(memory_id)
        if success:
            return {"success": True, "message": "记忆已删除"}
        raise HTTPException(status_code=404, detail="记忆不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除记忆失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/context/{query}")
async def get_memory_context(
    query: str,
    max_memories: int = Query(5, ge=1, le=20),
):
    """获取与查询相关的记忆上下文"""
    try:
        service = get_service()
        context = await service.get_context_for_query(
            query=query,
            max_memories=max_memories,
        )
        return {"success": True, "context": context.to_dict()}
    except Exception as e:
        logger.error(f"获取记忆上下文失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
