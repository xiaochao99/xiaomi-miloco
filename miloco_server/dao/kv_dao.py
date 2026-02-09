# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Key-value data access object
Handles CRUD operations for kv table, provides generic key-value storage functionality
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from miloco_server.utils.database import get_db_connector

logger = logging.getLogger(__name__)


class KVDao:
    """Key-value data access object"""

    def __init__(self):
        self.db_connector = get_db_connector()
        self.cache = self.get_all_as_dict()
        logger.info("KVDao init, current: %s", self.cache)


    def set(self, key: str, value: str) -> bool:
        """
        Set configuration item (create if not exists, update if exists)

        Args:
            key: Configuration key
            value: Configuration value

        Returns:
            bool: True if operation successful, False otherwise
        """
        try:
            self.cache[key] = value

            current_time = datetime.now().isoformat()
            sql = """
                INSERT INTO kv (key, value, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
            """
            params = (key, value, current_time, current_time)
            affected_rows = self.db_connector.execute_update(sql, params)
            if affected_rows > 0:
                logger.info("KV set successfully: key=%s, value=%s", key, value)
                return True
            else:
                logger.warning("Failed to set kv: key=%s, value=%s", key, value)
                return False
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error setting kv: key=%s, value=%s, error=%s", key, value, e)
            return False

    def _get_by_key(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get configuration item by key

        Args:
            key: Configuration key

        Returns:
            Optional[Dict[str, Any]]: Configuration item info, None if not exists
        """
        try:
            sql = "SELECT * FROM kv WHERE key = ?"
            params = (key,)
            results = self.db_connector.execute_query(sql, params)
            if results:
                logger.debug("KV found: key=%s", key)
                return results[0]
            else:
                logger.debug("KV not found: key=%s", key)
                return None
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error querying kv: key=%s, error=%s", key, e)
            return None

    def get(self, key: str, default_value: Optional[str] = None) -> Optional[str]:
        """
        Get configuration value by key

        Args:
            key: Configuration key
            default_value: Default value if configuration doesn't exist

        Returns:
            Optional[str]: Configuration value
        """
        if key in self.cache:
            return self.cache[key]
        kv = self._get_by_key(key)
        if kv:
            return kv.get("value")
        return default_value

    def get_all(self) -> Dict[str, str]:
        """
        Get all configuration items

        Returns:
            Dict[str, str]: Dictionary with key as key, value as value
        """
        return self.cache

    def _get_all(self) -> List[Dict[str, Any]]:
        """
        Get all configuration items

        Returns:
            List[Dict[str, Any]]: List of all configuration items
        """
        try:
            sql = "SELECT * FROM kv ORDER BY key"
            results = self.db_connector.execute_query(sql)
            logger.debug("Retrieved %d kv items", len(results))
            return results
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error retrieving all kv: error=%s", e)
            return []

    def get_all_as_dict(self) -> Dict[str, str]:
        """
        Get all configuration items and convert to key-value dictionary format

        Returns:
            Dict[str, str]: Dictionary with key as key, value as value
        """
        try:
            all_kvs = self._get_all()
            kv_dict = {}

            for kv in all_kvs:
                key = kv.get("key")
                value = kv.get("value")
                if key is not None and value is not None:
                    kv_dict[key] = value
            logger.info("Retrieved %d kv as dict", len(kv_dict))
            return kv_dict
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error converting kv to dict: error=%s", e)
            return {}

    def delete(self, key: str) -> bool:
        """
        Delete configuration item

        Args:
            key: Configuration key

        Returns:
            bool: True if deletion successful, False otherwise
        """
        try:
            self.cache.pop(key, None)
            sql = "DELETE FROM kv WHERE key = ?"
            params = (key,)
            affected_rows = self.db_connector.execute_update(sql, params)

            if affected_rows > 0:
                logger.info("KV deleted successfully: key=%s", key)
                return True
            else:
                logger.warning("Failed to delete kv, might not exist: key=%s", key)
                return False

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error deleting kv: key=%s, error=%s", key, e)
            return False

    def exists(self, key: str) -> bool:
        """
        Check if configuration item exists

        Args:
            key: Configuration key

        Returns:
            bool: True if exists, False otherwise
        """
        try:
            if key in self.cache:
                return True
            sql = "SELECT COUNT(*) as count FROM kv WHERE key = ?"
            params = (key,)
            results = self.db_connector.execute_query(sql, params)

            if results and results[0]["count"] > 0:
                return True
            return False

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error checking kv existence: key=%s, error=%s", key, e)
            return False

    def get_all_keys(self) -> List[str]:
        """
        获取所有配置项的 key 列表

        Returns:
            List[str]: key 列表
        """
        try:
            sql = "SELECT key FROM kv ORDER BY key"
            results = self.db_connector.execute_query(sql)
            keys = [row["key"] for row in results]
            logger.debug("Retrieved %d keys", len(keys))
            return keys
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error retrieving all keys: error=%s", e)
            return []


class AuthConfigKeys:
    ADMIN_PASSWORD_KEY = "ADMIN_PASSWORD_KEY"
    MIOT_TOKEN_INFO_KEY = "MIOT_TOKEN_INFO_KEY"
    MIOT_HA_BASE_URL_KEY = "MIOT_HA_BASE_URL_KEY"
    MIOT_HA_TOKEN_KEY = "MIOT_HA_TOKEN_KEY"
    USER_LANGUAGE_KEY = "USER_LANGUAGE_KEY"


class SystemConfigKeys:
    DEVICE_UUID_KEY = "DEVICE_UUID_KEY"
    CURRENT_MODEL_ID_KEY = "CURRENT_MODEL_ID_KEY"

class DeviceInfoKeys:
    CAMERA_INFO_KEY = "CAMERA_INFO_KEY"
    DEVICE_INFO_KEY = "DEVICE_INFO_KEY"
    SCENE_INFO_KEY = "SCENE_INFO_KEY"
    USER_INFO_KEY = "USER_INFO_KEY"
    HA_AUTOMATIONS_KEY = "HA_AUTOMATIONS_KEY"
