# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Chat history data access object
Handles CRUD operations for chat_history table, provides conversation history storage functionality
"""

import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from miloco_server.utils.database import get_db_connector
from miloco_server.schema.chat_history_schema import ChatHistoryStorage, ChatHistoryMessages, ChatHistorySession, ChatHistorySimpleInfo
from miloco_server.schema.chat_schema import Event, Instruction


logger = logging.getLogger(__name__)


class ChatHistoryDAO:
    """Chat history data access object"""

    def __init__(self):
        self.db_connector = get_db_connector()

    def _serialize_session(self,
                           chat_history_session: ChatHistorySession) -> str:
        """Serialize session content"""

        chat_history_session.zip_toast_stream()
        return json.dumps(chat_history_session.model_dump(mode="json"))

    def _deserialize_session(self, session: str) -> ChatHistorySession:
        """Deserialize session content"""
        session_data = json.loads(session)
        if isinstance(session_data, dict) and "data" in session_data:
            parsed_data = []
            for item in session_data["data"]:
                if isinstance(item, dict) and "header" in item:
                    header = item["header"]
                    if isinstance(header, dict) and "type" in header:
                        if header["type"] == "event":
                            parsed_data.append(Event.model_validate(item))
                        elif header["type"] == "instruction":
                            parsed_data.append(Instruction.model_validate(item))
                        else:
                            parsed_data.append(Event.model_validate(item))
                    else:
                        parsed_data.append(Event.model_validate(item))
                else:
                    parsed_data.append(item)
            session_data["data"] = parsed_data
        return ChatHistorySession.model_validate(session_data)

    def _dict_to_chat_history_info(self,
                                   data: Dict[str, Any]) -> ChatHistoryStorage:
        """Convert database data to ChatHistoryStorage object"""
        # Deserialize message/session
        messages = data["messages"] if data.get(
            "messages") else ChatHistoryMessages().to_json()
        session = self._deserialize_session(
            data["session"]) if data.get("session") else None

        return ChatHistoryStorage(session_id=data["session_id"],
                                  title=data["title"],
                                  timestamp=data["timestamp"],
                                  messages=messages,
                                  session=session)

    def _dict_to_chat_history_simple_info(
            self, data: Dict[str, Any]) -> ChatHistorySimpleInfo:
        """Convert database data to ChatHistorySimpleInfo object"""
        return ChatHistorySimpleInfo(session_id=data["session_id"],
                                     title=data["title"],
                                     timestamp=data["timestamp"])

    def create(self,
               chat_history_storage: ChatHistoryStorage) -> Optional[str]:
        """
        Create new chat history record

        Args:
            chat_history_storage: Chat history storage object

        Returns:
            Optional[str]: New UUID if successful, None if failed
        """
        try:
            session_id = chat_history_storage.session_id

            current_time = datetime.now().isoformat()

            sql = """
                INSERT INTO chat_history (session_id, title, messages, session, timestamp, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """

            params = (session_id, chat_history_storage.title,
                      chat_history_storage.messages,
                      self._serialize_session(chat_history_storage.session),
                      chat_history_storage.timestamp, current_time,
                      current_time)

            with self.db_connector.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                conn.commit()

                logger.info(
                    "Chat history created successfully: session_id=%s, title=%s",
                    session_id, chat_history_storage.title
                )
                return True

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error(
                "Error creating chat history: title=%s, error=%s",
                chat_history_storage.title, e, exc_info=True)
            return False

    def get_by_id(self, session_id: str) -> Optional[ChatHistoryStorage]:
        """
        Get chat history record by ID

        Args:
            session_id: Chat record ID

        Returns:
            Optional[ChatHistoryStorage]: Chat history record info, None if not exists
        """
        try:
            sql = "SELECT * FROM chat_history WHERE session_id = ?"
            params = (session_id, )

            results = self.db_connector.execute_query(sql, params)

            if results:
                logger.debug("Chat history found: session_id=%s", session_id)
                return self._dict_to_chat_history_info(results[0])
            else:
                logger.debug(
                    "Chat history not found: session_id=%s", session_id)
                return None

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error(
                "Error getting chat history by session_id: session_id=%s, error=%s",
                session_id, e
            )
            return None

    def get_simple_by_keyword(self,
                              keyword: str) -> List[ChatHistorySimpleInfo]:
        """
        Search chat history records by title

        Args:
            keyword: Conversation title (supports fuzzy search)

        Returns:
            List[ChatHistorySimpleInfo]: List of matching chat history simple info
        """
        try:
            # Select only required fields to improve query efficiency
            sql = """
                SELECT session_id, title, timestamp
                FROM chat_history
                WHERE title LIKE ?
                ORDER BY created_at DESC
            """
            params = (f"%{keyword}%", )

            results = self.db_connector.execute_query(sql, params)

            # Convert to ChatHistorySimpleInfo objects
            chat_histories = [
                self._dict_to_chat_history_simple_info(row) for row in results
            ]
            logger.debug(
                "Found %d chat history records with title containing '%s'",
                len(chat_histories), keyword
            )
            return chat_histories

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error(
                "Error searching chat history by title: title=%s, error=%s",
                keyword, e
            )
            return []

    def get_all_simple(self, ) -> List[ChatHistorySimpleInfo]:
        """
        Get all chat history records (simplified version)
        """
        try:
            sql = """
                SELECT session_id, title, timestamp
                FROM chat_history
                ORDER BY created_at DESC
            """

            results = self.db_connector.execute_query(sql)

            chat_histories = [
                self._dict_to_chat_history_simple_info(row) for row in results
            ]

            logger.debug("Found %d chat history records", len(chat_histories))
            return chat_histories

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error getting all chat history simple: error=%s", e)
            return []

    def update(self, chat_history_storage: ChatHistoryStorage) -> bool:
        """
        Update chat history record

        Args:
            chat_history_storage: Chat history storage object

        Returns:
            bool: True if update successful, False otherwise
        """
        try:
            sql = """
                UPDATE chat_history
                SET title = ?, messages = ?, session = ?, timestamp = ?, updated_at = ?
                WHERE session_id = ?
            """
            params = (chat_history_storage.title,
                      chat_history_storage.messages,
                      self._serialize_session(chat_history_storage.session),
                      chat_history_storage.timestamp,
                      datetime.now().isoformat(),
                      chat_history_storage.session_id)

            affected_rows = self.db_connector.execute_update(sql, params)

            if affected_rows > 0:
                logger.info(
                    "Chat history updated successfully: session_id=%s",
                    chat_history_storage.session_id
                )
                return True
            else:
                logger.warning(
                    "Failed to update chat history, might not exist: session_id=%s",
                    chat_history_storage.session_id
                )
                return False

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error(
                "Error updating chat history: session_id=%s, error=%s",
                chat_history_storage.session_id, e
            )
            return False

    def delete(self, session_id: str) -> bool:
        """
        Delete chat history record

        Args:
            session_id: Chat record ID

        Returns:
            bool: True if deletion successful, False otherwise
        """
        try:
            sql = "DELETE FROM chat_history WHERE session_id = ?"
            params = (session_id, )

            affected_rows = self.db_connector.execute_update(sql, params)

            if affected_rows > 0:
                logger.info(
                    "Chat history deleted successfully: session_id=%s",
                    session_id
                )
                return True
            else:
                logger.warning(
                    "Failed to delete chat history, might not exist: session_id=%s",
                    session_id
                )
                return False

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error(
                "Error deleting chat history: session_id=%s, error=%s",
                session_id, e
            )
            return False

    def exists(self, session_id: str) -> bool:
        """
        Check if chat history record exists

        Args:
            session_id: Chat record ID

        Returns:
            bool: True if exists, False otherwise
        """
        try:
            sql = "SELECT COUNT(*) as count FROM chat_history WHERE session_id = ?"
            params = (session_id, )

            results = self.db_connector.execute_query(sql, params)

            if results and results[0]["count"] > 0:
                return True
            return False

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error(
                "Error checking chat history existence: session_id=%s, error=%s",
                session_id, e
            )
            return False

    def count_all(self) -> int:
        """
        Get total count of chat history records

        Returns:
            int: Total record count
        """
        try:
            sql = "SELECT COUNT(*) as count FROM chat_history"
            results = self.db_connector.execute_query(sql)

            if results:
                return results[0]["count"]
            return 0

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error getting chat history count: error=%s", e)
            return 0

    def delete_by_ids(self, session_ids: List[str]) -> bool:
        """
        Delete chat history records by IDs
        """
        try:
            sql = "DELETE FROM chat_history WHERE session_id = ?"
            params = [(session_id,) for session_id in session_ids]
            affected_rows = self.db_connector.execute_many(sql, params)
            if affected_rows > 0:
                logger.info(
                    "Chat history deleted successfully: session_ids=%s",
                    session_ids
                )
                return True
            else:
                logger.warning(
                    "Failed to delete chat history, might not exist: session_ids=%s",
                    session_ids
                )
                return False
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error(
                "Error deleting chat history: session_ids=%s, error=%s",
                session_ids, e
            )
            return False

    def get_records_before_days(self, days: int) -> List[ChatHistorySimpleInfo]:
        """
        Get history records before specified days

        Args:
            days: Number of days, get records before days days

        Returns:
            List[ChatHistorySimpleInfo]: List of chat history simple info before specified days
        """
        try:
            # Calculate cutoff time
            cutoff_timestamp = int((datetime.now().timestamp() - days * 24 * 3600) * 1000)

            sql = """
                SELECT session_id, title, timestamp
                FROM chat_history
                WHERE timestamp < ?
                ORDER BY timestamp DESC
            """
            params = (cutoff_timestamp, )

            results = self.db_connector.execute_query(sql, params)

            # Convert to ChatHistorySimpleInfo objects
            chat_histories = [
                self._dict_to_chat_history_simple_info(row) for row in results
            ]

            logger.debug(
                "Found %d chat history records older than %d days",
                len(chat_histories), days
            )
            return chat_histories

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error(
                "Error getting chat history records before %d days: error=%s",
                days, e
            )
            return []
