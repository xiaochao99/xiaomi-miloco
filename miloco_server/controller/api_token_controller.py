# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
API Token Controller
长期 API Token 管理接口
"""

import logging
from fastapi import APIRouter, Depends

from miloco_server.schema.common_schema import NormalResponse
from miloco_server.schema.api_token_schema import (
    ApiTokenCreateRequest, ApiTokenDeleteRequest, ApiTokenListResponse
)
from miloco_server.service.manager import get_manager
from miloco_server.middleware import verify_token

router = APIRouter(prefix="/tokens", tags=["API Token Management"])
logger = logging.getLogger(__name__)

manager = get_manager()


@router.post("/create", summary="创建 API Token", response_model=NormalResponse)
async def create_api_token(
    request: ApiTokenCreateRequest,
    current_user: str = Depends(verify_token)
):
    """
    创建新的长期 API Token
    
    - Token 仅创建时返回一次，请妥善保存
    - 默认有效期 365 天
    """
    try:
        result = manager.api_token_service.create_token(current_user, request)
        return NormalResponse(
            code=0,
            message="API Token created successfully",
            data=result.model_dump()
        )
    except Exception as e:
        logger.error("Failed to create API token: %s", e)
        return NormalResponse(
            code=500,
            message=f"Failed to create API token: {str(e)}",
            data=None
        )


@router.get("/list", summary="列出所有 API Token", response_model=NormalResponse)
async def list_api_tokens(
    current_user: str = Depends(verify_token)
):
    """
    获取当前用户的所有 API Token 列表
    
    返回的列表中不包含完整的 Token 值
    """
    try:
        tokens = manager.api_token_service.list_tokens(current_user)
        return NormalResponse(
            code=0,
            message="API Tokens retrieved successfully",
            data={"tokens": [token.model_dump() for token in tokens]}
        )
    except Exception as e:
        logger.error("Failed to list API tokens: %s", e)
        return NormalResponse(
            code=500,
            message=f"Failed to list API tokens: {str(e)}",
            data=None
        )


@router.post("/delete", summary="删除 API Token", response_model=NormalResponse)
async def delete_api_token(
    request: ApiTokenDeleteRequest,
    current_user: str = Depends(verify_token)
):
    """
    删除指定的 API Token
    
    删除后该 Token 将立即失效
    """
    try:
        success = manager.api_token_service.delete_token(current_user, request.token_id)
        if success:
            return NormalResponse(
                code=0,
                message="API Token deleted successfully",
                data=None
            )
        else:
            return NormalResponse(
                code=404,
                message="Token not found",
                data=None
            )
    except Exception as e:
        logger.error("Failed to delete API token: %s", e)
        return NormalResponse(
            code=500,
            message=f"Failed to delete API token: {str(e)}",
            data=None
        )
