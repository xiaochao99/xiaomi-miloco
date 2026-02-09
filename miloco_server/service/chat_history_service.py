# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Chat history service module
"""

import logging
from typing import List

from miloco_server.dao.chat_history_dao import ChatHistoryDAO
from miloco_server.utils.chat_companion import ChatCompanion
from miloco_server.schema.chat_history_schema import (
    ChatHistoryResponse,
    ChatHistorySimpleInfo,
)
from miloco_server.middleware.exceptions import (
    ResourceNotFoundException,
    BusinessException
)

logger = logging.getLogger(__name__)


class ChatHistoryService:
    """Chat service class"""

    def __init__(self, chat_history_dao: ChatHistoryDAO, chat_companion: ChatCompanion):
        self._chat_history_dao = chat_history_dao
        self._chat_companion = chat_companion

    def get_chat_history(self, session_id: str) -> ChatHistoryResponse:
        """
        Get chat history details

        Args:
            session_id: Chat history ID

        Returns:
            ChatHistoryResponse: Chat history details

        Raises:
            ResourceNotFoundException: When chat history does not exist
            BusinessException: When retrieval fails
        """
        try:
            chat_history_storage = self._chat_history_dao.get_by_id(session_id)
            chat_history_response = ChatHistoryResponse(
                session_id=chat_history_storage.session_id,
                title=chat_history_storage.title,
                timestamp=chat_history_storage.timestamp,
                session=chat_history_storage.session)
            if not chat_history_response:
                raise ResourceNotFoundException("Chat history does not exist")

            return chat_history_response

        except ResourceNotFoundException:
            raise
        except Exception as e:
            logger.error(
                "Error getting chat history: session_id=%s, error=%s",
                session_id, e
            )
            raise BusinessException(f"Failed to get chat history: {str(e)}") from e

    def get_all_chat_history_simple(self) -> List[ChatHistorySimpleInfo]:
        """
        Get chat history list (simplified version)

        Returns:
            List[ChatHistorySimpleInfo]: Simplified chat history list
        """
        try:
            chat_history_simple_list = self._chat_history_dao.get_all_simple()

            logger.debug(
                "Retrieved %d chat history records", len(chat_history_simple_list)
            )
            return chat_history_simple_list

        except Exception as e:
            logger.error("Error getting all chat histories: error=%s", e)
            raise BusinessException(f"Failed to get chat history list: {str(e)}") from e

    def delete_chat_history(self, session_id: str) -> bool:
        """
        Delete chat history record

        Args:
            session_id: Chat history ID

        Returns:
            bool: Returns True if deletion successful

        Raises:
            ResourceNotFoundException: When chat history does not exist
            BusinessException: When deletion fails
        """
        try:
            if not self._chat_history_dao.exists(session_id):
                raise ResourceNotFoundException("Chat history does not exist")

            success = self._chat_history_dao.delete(session_id)

            if not success:
                raise BusinessException("Failed to delete chat history")

            logger.info(
                "Chat history deleted successfully: session_id=%s", session_id)
            return True

        except ResourceNotFoundException:
            raise
        except Exception as e:
            logger.error(
                "Error deleting chat history: session_id=%s, error=%s",
                session_id, e
            )
            raise BusinessException(f"Failed to delete chat history: {str(e)}") from e

    def search_chat_histories(self,
                              keyword: str) -> List[ChatHistorySimpleInfo]:
        """
        Search chat history records

        Args:
            keyword: Search keyword
            limit: Limit number of records to return
            offset: Offset for pagination

        Returns:
            List[ChatHistorySimpleInfo]: Matching simplified chat history list
        """
        try:
            chat_history_simple_list = self._chat_history_dao.get_simple_by_keyword(
                keyword)

            logger.debug(
                "Found %d chat history records matching keyword '%s'",
                len(chat_history_simple_list), keyword
            )
            return chat_history_simple_list

        except Exception as e:
            logger.error(
                "Error searching chat histories: keyword=%s, error=%s",
                keyword, e
            )
            raise BusinessException(f"Failed to search chat history: {str(e)}") from e

    def get_chat_history_count(self) -> int:
        """
        Get total number of chat history records

        Returns:
            int: Total number of records
        """
        try:
            count = self._chat_history_dao.count_all()
            return count
        except Exception as e:
            logger.error("Error getting chat history count: error=%s", e)
            raise BusinessException(f"Failed to get chat history count: {str(e)}") from e

    def delete_old_chat_histories(self, days: int) -> int:
        """
        Delete old records before specified number of days

        Args:
            days: Number of days, delete records older than days

        Returns:
            int: Number of deleted records
        """
        try:
            deleted_count = self._chat_history_dao.delete_old_records(days)
            logger.info(
                "Deleted %d old chat history records older than %d days",
                deleted_count, days
            )
            return deleted_count
        except Exception as e:
            logger.error(
                "Error deleting old chat histories: days=%d, error=%s", days, e)
            raise BusinessException(f"Failed to delete old chat history: {str(e)}") from e
