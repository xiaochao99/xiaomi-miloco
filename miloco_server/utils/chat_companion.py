# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Chat companion utility for managing chat data and history.
Provides functionality to store, retrieve and manage chat session data.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from cachetools import TTLCache

from miloco_server.dao.chat_history_dao import ChatHistoryDAO
from miloco_server.schema.chat_history_schema import ChatHistoryStorage
from miloco_server.schema.miot_schema import CameraImgSeq
from thespian.actors import ActorAddress

logger = logging.getLogger(__name__)


@dataclass
class ChatCachedData:
    """Chat cached data structure"""
    out_actor_address: Optional[ActorAddress] = None
    camera_ids: Optional[list[str]] = None
    mcp_ids: Optional[list[str]] = None
    other_mcp_tools_meta: Optional[list] = None
    camera_images: Optional[list[CameraImgSeq]] = None


class ChatCompanion:
    """Chat companion for managing chat data and history"""

    def __init__(self, chat_history_dao: ChatHistoryDAO):
        self._chat_data_map: TTLCache[str, ChatCachedData] = TTLCache(maxsize=100, ttl=1800)
        self._chat_history_dao = chat_history_dao

    def store_chat_history(self, chat_history: ChatHistoryStorage) -> bool:
        """
        Store chat history
        """
        if self._chat_history_dao.exists(chat_history.session_id):
            return self._chat_history_dao.update(chat_history)
        else:
            return self._chat_history_dao.create(chat_history)

    def get_chat_history(self,
                         session_id: str) -> Optional[ChatHistoryStorage]:
        """
        Get chat history
        """
        return self._chat_history_dao.get_by_id(session_id)


    def get_chat_data(self, request_id: str) -> Optional[ChatCachedData]:
        """
        Get chat data
        """
        return self._chat_data_map.get(request_id)

    def set_chat_data(self, request_id: str, chat_data: ChatCachedData):
        """
        Set chat data
        """
        current_chat_data = self._chat_data_map.get(request_id)
        if current_chat_data is None:
            self._chat_data_map[request_id] = chat_data
        else:
            for field_name, field_value in chat_data.__dict__.items():
                if field_value is not None:
                    setattr(current_chat_data, field_name, field_value)

    def clear_chat_data(self, request_id: str):
        """
        Clear chat data
        """
        self._chat_data_map.pop(request_id, None)
