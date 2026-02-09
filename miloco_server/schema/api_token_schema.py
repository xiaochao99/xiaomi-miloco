# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
API Token schema definitions
长期 API Token 数据模型定义
"""

from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class ApiTokenCreateRequest(BaseModel):
    """创建 API Token 请求"""
    name: str = Field(..., min_length=1, max_length=50, description="Token 名称")
    description: Optional[str] = Field(None, max_length=200, description="Token 描述")
    expires_days: Optional[int] = Field(365, ge=1, le=3650, description="过期天数(默认1年)")


class ApiTokenInfo(BaseModel):
    """API Token 信息"""
    id: str = Field(..., description="Token ID")
    name: str = Field(..., description="Token 名称")
    description: Optional[str] = Field(None, description="Token 描述")
    created_at: str = Field(..., description="创建时间")
    expires_at: str = Field(..., description="过期时间")
    last_used_at: Optional[str] = Field(None, description="最后使用时间")
    is_active: bool = Field(True, description="是否有效")
    token_preview: str = Field(..., description="Token 预览(仅显示前几位)")


class ApiTokenCreateResponse(BaseModel):
    """创建 API Token 响应"""
    id: str = Field(..., description="Token ID")
    name: str = Field(..., description="Token 名称")
    token: str = Field(..., description="完整的 API Token(仅创建时返回一次)")
    expires_at: str = Field(..., description="过期时间")


class ApiTokenListResponse(BaseModel):
    """API Token 列表响应"""
    tokens: List[ApiTokenInfo] = Field(default_factory=list, description="Token 列表")


class ApiTokenDeleteRequest(BaseModel):
    """删除 API Token 请求"""
    token_id: str = Field(..., description="要删除的 Token ID")
