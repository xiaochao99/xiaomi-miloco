# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Third-party model data access object
Handles CRUD operations for model_vendor table
"""

import logging
import uuid
from typing import Optional, List, Dict, Any
from miloco_server.utils.database import get_db_connector
from miloco_server.schema.model_schema import ThirdPartyModelInfo

logger = logging.getLogger(__name__)


class ThirdPartyModelDAO:
    """Third-party model data access object"""

    def __init__(self):
        self.db_connector = get_db_connector()


    def _dict_to_model(self, data: Dict[str, Any]) -> ThirdPartyModelInfo:
        """Convert database data to ThirdPartyModelInfo object"""
        return ThirdPartyModelInfo(
            id=data["id"],
            base_url=data["base_url"],
            api_key=data["api_key"],
            model_name=data["model_name"]
        )

    def create(self, model: ThirdPartyModelInfo) -> Optional[str]:
        """
        Create new third-party model

        Args:
            model: Third-party model object

        Returns:
            Optional[str]: New UUID if successful, None if failed
        """
        try:
            model_id = str(uuid.uuid4())

            sql = """
                INSERT INTO model_vendor (id, base_url, api_key, model_name)
                VALUES (?, ?, ?, ?)
            """
            params = (model_id, model.base_url, model.api_key, model.model_name)

            affected_rows = self.db_connector.execute_update(sql, params)

            if affected_rows > 0:
                logger.info("Third party model created successfully: id=%s", model_id)
                return model_id
            else:
                logger.error("Failed to create third party model")
                return None

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error creating third party model: error=%s", e)
            return None

    def get_by_id(self, model_id: str) -> Optional[ThirdPartyModelInfo]:
        """
        Get third-party model by ID

        Args:
            model_id: Model ID (UUID)

        Returns:
            Optional[ThirdPartyModelInfo]: Third-party model object, None if not exists
        """
        try:
            sql = "SELECT * FROM model_vendor WHERE id = ?"
            params = (model_id,)

            results = self.db_connector.execute_query(sql, params)

            if results:
                logger.debug("Third party model found: id=%s", model_id)
                return self._dict_to_model(results[0])
            else:
                logger.debug("Third party model not found: id=%s", model_id)
                return None

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error querying third party model: id=%s, error=%s", model_id, e)
            return None


    def get_all(self) -> List[ThirdPartyModelInfo]:
        """
        Get all third-party models

        Returns:
            List[ThirdPartyModelInfo]: List of third-party models
        """
        try:
            sql = "SELECT * FROM model_vendor ORDER BY model_name"

            results = self.db_connector.execute_query(sql)

            models = [self._dict_to_model(row) for row in results]
            logger.debug("Retrieved %s third party models", len(models))
            return models

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error retrieving third party models: error=%s", e)
            return []

    def update(self, model: ThirdPartyModelInfo) -> bool:
        """
        Update third-party model

        Args:
            model: Third-party model object

        Returns:
            bool: True if update successful, False otherwise
        """
        try:
            sql = """
                UPDATE model_vendor
                SET base_url = ?, api_key = ?, model_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            params = (model.base_url, model.api_key, model.model_name, model.id)

            affected_rows = self.db_connector.execute_update(sql, params)

            if affected_rows > 0:
                logger.info("Third party model updated successfully: id=%s", model.id)
                return True
            else:
                logger.warning("Failed to update third party model, might not exist: id=%s", model.id)
                return False

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error updating third party model: id=%s, error=%s", model.id, e)
            return False

    def delete(self, model_id: str) -> bool:
        """
        Delete third-party model

        Args:
            model_id: Model ID (UUID)

        Returns:
            bool: True if deletion successful, False otherwise
        """
        try:
            sql = "DELETE FROM model_vendor WHERE id = ?"
            params = (model_id,)

            affected_rows = self.db_connector.execute_update(sql, params)

            if affected_rows > 0:
                logger.info("Third party model deleted successfully: id=%s", model_id)
                return True
            else:
                logger.warning("Failed to delete third party model, might not exist: id=%s", model_id)
                return False

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error deleting third party model: id=%s, error=%s", model_id, e)
            return False

    def exists(self, model_id: str) -> bool:
        """
        Check if third-party model exists

        Args:
            model_id: Model ID (UUID)

        Returns:
            bool: True if exists, False otherwise
        """
        try:
            sql = "SELECT COUNT(*) as count FROM model_vendor WHERE id = ?"
            params = (model_id,)

            results = self.db_connector.execute_query(sql, params)

            if results and results[0]["count"] > 0:
                return True
            return False

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error checking third party model existence: id=%s, error=%s", model_id, e)
            return False



    def count(self) -> int:
        """
        Get count of third-party models

        Returns:
            int: Number of third-party models
        """
        try:
            sql = "SELECT COUNT(*) as count FROM model_vendor"
            results = self.db_connector.execute_query(sql)

            if results:
                return results[0]["count"]
            return 0

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error getting third party model count: error=%s", e)
            return 0
