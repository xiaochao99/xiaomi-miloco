# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
API Token Service
长期 API Token 管理服务
"""

import uuid
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from miloco_server.dao.kv_dao import KVDao, AuthConfigKeys
from miloco_server.schema.api_token_schema import (
    ApiTokenCreateRequest, ApiTokenInfo, ApiTokenCreateResponse
)
from miloco_server.middleware import AuthorizationException

logger = logging.getLogger(__name__)

API_TOKEN_PREFIX = "apt_"  # API Token 前缀
API_TOKEN_STORAGE_KEY = "api_tokens"


class ApiTokenService:
    """
    API Token 管理服务
    
    功能:
    - 创建长期 API Token
    - 列出用户的所有 Token
    - 删除 Token
    - 验证 Token 有效性
    """
    
    def __init__(self, kv_dao: KVDao):
        self._kv_dao = kv_dao
    
    def _get_storage_key(self, username: str) -> str:
        """获取存储 key"""
        return f"{API_TOKEN_STORAGE_KEY}:{username}"
    
    def _hash_token(self, token: str) -> str:
        """对 Token 进行哈希存储(仅存储哈希值)"""
        return hashlib.sha256(token.encode()).hexdigest()
    
    def _generate_token(self) -> str:
        """生成新的 API Token"""
        # 生成 32 字节随机字符串
        random_part = secrets.token_urlsafe(32)
        return f"{API_TOKEN_PREFIX}{random_part}"
    
    def _mask_token(self, token: str) -> str:
        """遮罩 Token，只显示前 8 位"""
        if len(token) <= 12:
            return "***"
        return f"{token[:8]}...{token[-4:]}"
    
    def create_token(
        self, 
        username: str, 
        request: ApiTokenCreateRequest
    ) -> ApiTokenCreateResponse:
        """
        创建新的 API Token
        
        Args:
            username: 用户名
            request: 创建请求
            
        Returns:
            ApiTokenCreateResponse: 包含完整的 Token(仅返回一次)
        """
        token_id = str(uuid.uuid4())
        full_token = self._generate_token()
        token_hash = self._hash_token(full_token)
        
        now = datetime.utcnow()
        expires_at = now + timedelta(days=request.expires_days)
        
        token_info = {
            "id": token_id,
            "name": request.name,
            "description": request.description,
            "token_hash": token_hash,
            "token_preview": self._mask_token(full_token),
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "last_used_at": None,
            "is_active": True,
        }
        
        # 保存到存储
        storage_key = self._get_storage_key(username)
        existing_tokens = self._get_all_tokens_raw(username)
        existing_tokens[token_id] = token_info
        
        self._kv_dao.set(storage_key, str(existing_tokens))
        
        logger.info("API Token created: %s for user %s", token_id, username)
        
        return ApiTokenCreateResponse(
            id=token_id,
            name=request.name,
            token=full_token,  # 仅创建时返回完整 Token
            expires_at=expires_at.isoformat()
        )
    
    def list_tokens(self, username: str) -> List[ApiTokenInfo]:
        """
        列出用户的所有 Token
        
        Args:
            username: 用户名
            
        Returns:
            List[ApiTokenInfo]: Token 列表
        """
        tokens_raw = self._get_all_tokens_raw(username)
        now = datetime.utcnow()
        
        result = []
        for token_id, token_data in tokens_raw.items():
            # 检查是否过期
            expires_at = datetime.fromisoformat(token_data["expires_at"])
            is_expired = now > expires_at
            
            # 如果过期，更新状态
            if is_expired and token_data.get("is_active", True):
                token_data["is_active"] = False
                self._update_token(username, token_id, token_data)
            
            result.append(ApiTokenInfo(
                id=token_id,
                name=token_data["name"],
                description=token_data.get("description"),
                created_at=token_data["created_at"],
                expires_at=token_data["expires_at"],
                last_used_at=token_data.get("last_used_at"),
                is_active=token_data.get("is_active", True) and not is_expired,
                token_preview=token_data.get("token_preview", "***")
            ))
        
        # 按创建时间倒序排列
        result.sort(key=lambda x: x.created_at, reverse=True)
        return result
    
    def delete_token(self, username: str, token_id: str) -> bool:
        """
        删除 Token
        
        Args:
            username: 用户名
            token_id: Token ID
            
        Returns:
            bool: 是否删除成功
        """
        tokens_raw = self._get_all_tokens_raw(username)
        
        if token_id not in tokens_raw:
            logger.warning("Token not found: %s for user %s", token_id, username)
            return False
        
        del tokens_raw[token_id]
        
        storage_key = self._get_storage_key(username)
        self._kv_dao.set(storage_key, str(tokens_raw))
        
        logger.info("API Token deleted: %s for user %s", token_id, username)
        return True
    
    def verify_token(self, token: str) -> Optional[str]:
        """
        验证 API Token 并返回用户名
        
        Args:
            token: 完整的 API Token
            
        Returns:
            Optional[str]: 用户名，验证失败返回 None
        """
        if not token.startswith(API_TOKEN_PREFIX):
            return None
        
        token_hash = self._hash_token(token)
        now = datetime.utcnow()
        
        # 遍历所有用户的 Token(这里简化处理，实际可以优化)
        # 获取所有可能的存储 key
        all_keys = self._kv_dao.get_all_keys()
        
        for key in all_keys:
            if not key.startswith(API_TOKEN_STORAGE_KEY + ":"):
                continue
            
            username = key.split(":", 1)[1]
            tokens_raw = self._get_all_tokens_raw(username)
            
            for token_id, token_data in tokens_raw.items():
                if token_data.get("token_hash") == token_hash:
                    # 检查是否有效
                    if not token_data.get("is_active", True):
                        return None
                    
                    # 检查是否过期
                    expires_at = datetime.fromisoformat(token_data["expires_at"])
                    if now > expires_at:
                        token_data["is_active"] = False
                        self._update_token(username, token_id, token_data)
                        return None
                    
                    # 更新最后使用时间
                    token_data["last_used_at"] = now.isoformat()
                    self._update_token(username, token_id, token_data)
                    
                    logger.debug("API Token verified for user: %s", username)
                    return username
        
        return None
    
    def _get_all_tokens_raw(self, username: str) -> dict:
        """获取所有 Token 原始数据"""
        storage_key = self._get_storage_key(username)
        tokens_str = self._kv_dao.get(storage_key)
        
        if not tokens_str:
            return {}
        
        try:
            import ast
            return ast.literal_eval(tokens_str)
        except (SyntaxError, ValueError):
            logger.error("Failed to parse tokens for user: %s", username)
            return {}
    
    def _update_token(self, username: str, token_id: str, token_data: dict):
        """更新单个 Token 数据"""
        tokens_raw = self._get_all_tokens_raw(username)
        tokens_raw[token_id] = token_data
        
        storage_key = self._get_storage_key(username)
        self._kv_dao.set(storage_key, str(tokens_raw))
