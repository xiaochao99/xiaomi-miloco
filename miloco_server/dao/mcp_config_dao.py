# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
MCP configuration data access object
Handles CRUD operations for mcp_config table
"""

import logging
import uuid
import json
from typing import Optional, List, Dict, Any
from miloco_server.utils.database import get_db_connector
from miloco_server.schema.mcp_schema import MCPConfigModel, TransportType

logger = logging.getLogger(__name__)


class MCPConfigDAO:
    """MCP configuration data access object"""

    def __init__(self):
        self.db_connector = get_db_connector()

    def _model_to_dict(self, config: MCPConfigModel) -> Dict[str, Any]:
        """Convert MCPConfigModel object to database storage format"""
        return {
            "id": getattr(config, "id", None),
            "access_type": config.access_type.value,
            "name": config.name,
            "description": config.description,
            "provider": config.provider,
            "provider_website": config.provider_website,
            "timeout": config.timeout,
            "enable": config.enable,
            "url": config.url,
            "request_header_token": config.request_header_token,
            "command": config.command,
            "args": json.dumps(config.args) if config.args else None,
            "env_vars": json.dumps(config.env_vars) if config.env_vars else None,
            "working_directory": config.working_directory
        }

    def _dict_to_model(self, data: Dict[str, Any]) -> MCPConfigModel:
        """Convert database data to MCPConfigModel object"""
        args = json.loads(data["args"]) if data["args"] else None
        env_vars = json.loads(data["env_vars"]) if data["env_vars"] else None

        return MCPConfigModel(
            id=data["id"],
            access_type=TransportType(data["access_type"]),
            name=data["name"],
            description=data["description"],
            provider=data["provider"],
            provider_website=data["provider_website"],
            timeout=data["timeout"],
            enable=bool(data["enable"]),
            url=data["url"],
            request_header_token=data["request_header_token"],
            command=data["command"],
            args=args,
            env_vars=env_vars,
            working_directory=data["working_directory"]
        )

    def create(self, config: MCPConfigModel) -> Optional[str]:
        """
        Create new MCP configuration

        Args:
            config: MCP configuration object

        Returns:
            Optional[str]: New UUID if successful, None if failed
        """
        try:
            config_id = str(uuid.uuid4())

            sql = """
                INSERT INTO mcp_config (
                    id, access_type, name, description, provider, provider_website,
                    timeout, enable, url, request_header_token, command, args, env_vars, working_directory
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            config_dict = self._model_to_dict(config)
            config_dict["id"] = config_id

            params = (
                config_id,
                config_dict["access_type"],
                config_dict["name"],
                config_dict["description"],
                config_dict["provider"],
                config_dict["provider_website"],
                config_dict["timeout"],
                config_dict["enable"],
                config_dict["url"],
                config_dict["request_header_token"],
                config_dict["command"],
                config_dict["args"],
                config_dict["env_vars"],
                config_dict["working_directory"]
            )

            affected_rows = self.db_connector.execute_update(sql, params)

            if affected_rows > 0:
                logger.info("MCP config created successfully: id=%s", config_id)
                return config_id
            else:
                logger.error("Failed to create MCP config")
                return None

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error creating MCP config: error=%s", e)
            return None

    def get_by_id(self, config_id: str) -> Optional[MCPConfigModel]:
        """
        Get MCP configuration by ID

        Args:
            config_id: Configuration ID (UUID)

        Returns:
            Optional[MCPConfigModel]: MCP configuration object, None if not exists
        """
        try:
            sql = "SELECT * FROM mcp_config WHERE id = ?"
            params = (config_id,)

            results = self.db_connector.execute_query(sql, params)

            if results:
                logger.debug("MCP config found: id=%s", config_id)
                return self._dict_to_model(results[0])
            else:
                logger.debug("MCP config not found: id=%s", config_id)
                return None

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error querying MCP config: id=%s, error=%s", config_id, e)
            return None


    def get_all(self) -> List[MCPConfigModel]:
        """
        Get all MCP configurations

        Returns:
            List[MCPConfigModel]: List of MCP configurations
        """
        try:
            sql = "SELECT * FROM mcp_config ORDER BY created_at DESC"

            results = self.db_connector.execute_query(sql)

            configs = []
            for row in results:
                configs.append(self._dict_to_model(row))

            logger.debug("Retrieved %s MCP configs", len(configs))
            return configs

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error querying all MCP configs: error=%s", e)
            return []

    def get_by_access_type(self, access_type: TransportType) -> List[MCPConfigModel]:
        """
        Get MCP configurations by access type

        Args:
            access_type: Access type

        Returns:
            List[MCPConfigModel]: List of MCP configurations
        """
        try:
            sql = "SELECT * FROM mcp_config WHERE access_type = ? ORDER BY created_at DESC"
            params = (access_type.value,)

            results = self.db_connector.execute_query(sql, params)

            configs = []
            for row in results:
                configs.append(self._dict_to_model(row))

            logger.debug("Retrieved %s MCP configs for access_type=%s", len(configs), access_type.value)
            return configs

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error querying MCP configs by access_type: access_type=%s, error=%s", access_type.value, e)
            return []

    def get_by_provider(self, provider: str) -> List[MCPConfigModel]:
        """
        Get MCP configurations by provider

        Args:
            provider: Provider name

        Returns:
            List[MCPConfigModel]: List of MCP configurations
        """
        try:
            sql = "SELECT * FROM mcp_config WHERE provider = ? ORDER BY created_at DESC"
            params = (provider,)

            results = self.db_connector.execute_query(sql, params)

            configs = []
            for row in results:
                configs.append(self._dict_to_model(row))

            logger.debug("Retrieved %s MCP configs for provider=%s", len(configs), provider)
            return configs

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error querying MCP configs by provider: provider=%s, error=%s", provider, e)
            return []

    def get_by_enable_status(self, enable: bool) -> List[MCPConfigModel]:
        """
        Get MCP configurations by enable status

        Args:
            enable: Enable status

        Returns:
            List[MCPConfigModel]: List of MCP configurations
        """
        try:
            sql = "SELECT * FROM mcp_config WHERE enable = ? ORDER BY created_at DESC"
            params = (1 if enable else 0,)

            results = self.db_connector.execute_query(sql, params)

            configs = []
            for row in results:
                configs.append(self._dict_to_model(row))

            logger.debug("Retrieved %s MCP configs for enable=%s", len(configs), enable)
            return configs

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error querying MCP configs by enable status: enable=%s, error=%s", enable, e)
            return []

    def get_enabled_configs(self) -> List[MCPConfigModel]:
        """
        Get all enabled MCP configurations

        Returns:
            List[MCPConfigModel]: List of enabled MCP configurations
        """
        return self.get_by_enable_status(True)

    def get_disabled_configs(self) -> List[MCPConfigModel]:
        """
        Get all disabled MCP configurations

        Returns:
            List[MCPConfigModel]: List of disabled MCP configurations
        """
        return self.get_by_enable_status(False)

    def update(self, config: MCPConfigModel) -> bool:
        """
        Update MCP configuration

        Args:
            config: MCP configuration object, must contain id field

        Returns:
            bool: True if update successful, False otherwise
        """
        try:
            if not hasattr(config, "id") or not config.id:
                logger.error("Cannot update MCP config without id")
                return False

            sql = """
                UPDATE mcp_config SET
                    access_type = ?, name = ?, description = ?, provider = ?, provider_website = ?,
                    timeout = ?, enable = ?, url = ?, request_header_token = ?, command = ?, args = ?,
                    env_vars = ?, working_directory = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """

            config_dict = self._model_to_dict(config)

            params = (
                config_dict["access_type"],
                config_dict["name"],
                config_dict["description"],
                config_dict["provider"],
                config_dict["provider_website"],
                config_dict["timeout"],
                config_dict["enable"],
                config_dict["url"],
                config_dict["request_header_token"],
                config_dict["command"],
                config_dict["args"],
                config_dict["env_vars"],
                config_dict["working_directory"],
                config.id
            )

            affected_rows = self.db_connector.execute_update(sql, params)

            if affected_rows > 0:
                logger.info("MCP config updated successfully: id=%s", config.id)
                return True
            else:
                logger.warning("MCP config not found for update: id=%s", config.id)
                return False

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error updating MCP config: id=%s, error=%s", config.id, e)
            return False

    def delete(self, config_id: str) -> bool:
        """
        Delete MCP configuration

        Args:
            config_id: Configuration ID (UUID)

        Returns:
            bool: True if deletion successful, False otherwise
        """
        try:
            sql = "DELETE FROM mcp_config WHERE id = ?"
            params = (config_id,)

            affected_rows = self.db_connector.execute_update(sql, params)

            if affected_rows > 0:
                logger.info("MCP config deleted successfully: id=%s", config_id)
                return True
            else:
                logger.warning("MCP config not found for deletion: id=%s", config_id)
                return False

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error deleting MCP config: id=%s, error=%s", config_id, e)
            return False


    def exists(self, config_id: str) -> bool:
        """
        Check if MCP configuration exists

        Args:
            config_id: Configuration ID (UUID)

        Returns:
            bool: True if exists, False otherwise
        """
        try:
            sql = "SELECT COUNT(*) as count FROM mcp_config WHERE id = ?"
            params = (config_id,)

            results = self.db_connector.execute_query(sql, params)

            if results and results[0]["count"] > 0:
                logger.debug("MCP config exists: id=%s", config_id)
                return True
            else:
                logger.debug("MCP config does not exist: id=%s", config_id)
                return False

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error checking MCP config existence: id=%s, error=%s", config_id, e)
            return False

    def exists_by_name(self, name: str) -> bool:
        """
        Check if MCP configuration exists by name

        Args:
            name: Configuration name

        Returns:
            bool: True if exists, False otherwise
        """
        try:
            sql = "SELECT COUNT(*) as count FROM mcp_config WHERE name = ?"
            params = (name,)

            results = self.db_connector.execute_query(sql, params)

            if results and results[0]["count"] > 0:
                logger.debug("MCP config exists by name: name=%s", name)
                return True
            else:
                logger.debug("MCP config does not exist by name: name=%s", name)
                return False

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error checking MCP config existence by name: name=%s, error=%s", name, e)
            return False

    def count(self) -> int:
        """
        Get total count of MCP configurations

        Returns:
            int: Total configuration count
        """
        try:
            sql = "SELECT COUNT(*) as count FROM mcp_config"

            results = self.db_connector.execute_query(sql)

            if results:
                count = results[0]["count"]
                logger.debug("MCP config count: %s", count)
                return count
            else:
                return 0

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error counting MCP configs: error=%s", e)
            return 0
