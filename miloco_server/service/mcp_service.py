# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
MCP service module
"""

import logging
from typing import List

from miloco_server.dao.mcp_config_dao import MCPConfigDAO
from miloco_server.mcp.mcp_client_manager import MCPClientManager
from miloco_server.schema.mcp_schema import (
    MCPClientStatusList, MCPConfigModel, TransportType, MCPConfigResponse, LocalMcpClientId
)
from miloco_server.utils.mcp_util import MCPConfigConverter
from miloco_server.middleware.exceptions import (
    ConflictException,
    ValidationException,
    ResourceNotFoundException,
    BusinessException
)

logger = logging.getLogger(__name__)


class McpService:
    """MCP service class"""

    def __init__(self, mcp_config_dao: MCPConfigDAO, mcp_client_manager: MCPClientManager):
        self._mcp_config_dao = mcp_config_dao
        self._mcp_client_manager = mcp_client_manager

    async def create_mcp_config(self, config: MCPConfigModel) -> MCPConfigResponse:
        """
        Create MCP configuration

        Args:
            config: MCP configuration object

        Returns:
            MCPConfigResponse: Response object containing config ID and connection status
        """
        logger.info(
            "Creating MCP configuration: name=%s, access_type=%s", config.name, config.access_type.value
        )

        # Check if configuration name already exists
        exists_by_name = self._mcp_config_dao.exists_by_name(config.name)
        logger.info("Pre-creation check - Configuration name: %s, exists: %s", config.name, exists_by_name)

        if exists_by_name:
            logger.warning("MCP configuration name already exists: %s", config.name)
            raise ConflictException("MCP configuration name already exists")

        # Validate configuration parameters
        if config.access_type == TransportType.STDIO:
            if not config.command:
                raise ValidationException("Stdio type must provide command parameter")
        elif config.access_type in [
                TransportType.HTTP_SSE, TransportType.STREAMABLE_HTTP
        ]:
            if not config.url:
                raise ValidationException("HTTP type must provide url parameter")

        # Create configuration
        config_id = self._mcp_config_dao.create(config)

        if not config_id:
            logger.error("MCP configuration creation failed: name=%s", config.name)
            raise BusinessException("MCP configuration creation failed")

        config.id = config_id

        # Synchronously update MCPClientManager
        connection_success = False
        connection_error = None

        if not config.enable:
            return MCPConfigResponse(
                config_id=config_id,
                connection_success=connection_success,
                connection_error=connection_error
            )

        try:
            # Convert configuration format
            client_config = MCPConfigConverter.to_mcp_client_config(config)
            client_transport_type = config.access_type

            # Add to MCPClientManager
            success = await self._mcp_client_manager.add_client(
                client_transport_type, client_config)
            connection_success = success
            if not success:
                connection_error = "Connection failed, please check configuration parameters"
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Failed to sync MCPClientManager: %s", str(e))
            connection_error = f"Connection failed: {str(e)}"

        logger.info("MCP configuration created successfully: id=%s, name=%s", config_id, config.name)
        return MCPConfigResponse(
            config_id=config_id,
            connection_success=connection_success,
            connection_error=connection_error
        )

    async def get_all_mcp_configs(self) -> List[MCPConfigModel]:
        """
        Get all MCP configurations

        Returns:
            List[MCPConfigModel]: MCP configuration list
        """
        logger.info("Getting all MCP configurations")

        configs = self._mcp_config_dao.get_all()
        logger.info("Retrieved %d MCP configurations", len(configs))
        return configs

    async def update_mcp_config(self, config: MCPConfigModel) -> MCPConfigResponse:
        """
        Update MCP configuration

        Args:
            config: MCP configuration object, must contain id field

        Returns:
            MCPConfigResponse: Response object containing config ID and connection status
        """
        logger.info("Updating MCP configuration: id=%s, name=%s", config.id, config.name)

        # Check if configuration exists
        existing_config = self._mcp_config_dao.get_by_id(config.id)
        if not existing_config:
            logger.warning("MCP configuration does not exist: id=%s", config.id)
            raise ResourceNotFoundException("MCP configuration does not exist")

        # Check if name conflicts with other configurations
        if config.name != existing_config.name and self._mcp_config_dao.exists_by_name(
                config.name):
            logger.warning("MCP configuration name already exists: %s", config.name)
            raise ConflictException("MCP configuration name already exists")

        # Validate configuration parameters
        if config.access_type == TransportType.STDIO:
            if not config.command:
                raise ValidationException("Stdio type must provide command parameter")
        elif config.access_type in [
                TransportType.HTTP_SSE, TransportType.STREAMABLE_HTTP
        ]:
            if not config.url:
                raise ValidationException("HTTP type must provide url parameter")

        # Update configuration
        success = self._mcp_config_dao.update(config)

        if not success:
            logger.error("MCP configuration update failed: id=%s", config.id)
            raise BusinessException("MCP configuration update failed")

        # Synchronously update MCPClientManager
        connection_success = False
        connection_error = None

        try:
            if not config.enable:
                await self._mcp_client_manager.remove_client(config.id)
                return MCPConfigResponse(
                    config_id=config.id,
                    connection_success=connection_success,
                    connection_error=connection_error
                )

            # Convert configuration format
            client_config = MCPConfigConverter.to_mcp_client_config(config)
            client_transport_type = config.access_type

            success = await self._mcp_client_manager.update_client(
                client_transport_type, client_config)

            connection_success = success
            if not success:
                connection_error = "Connection failed, please check configuration parameters"
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Failed to sync MCPClientManager: %s", str(e))
            connection_error = f"Connection failed: {str(e)}"

        logger.info("MCP configuration updated successfully: id=%s", config.id)
        return MCPConfigResponse(
            config_id=config.id,
            connection_success=connection_success,
            connection_error=connection_error
        )

    async def delete_mcp_config(self, config_id: str):
        """
        Delete MCP configuration

        Args:
            config_id: Configuration ID
        """
        logger.info("Deleting MCP configuration: id=%s", config_id)

        # Check if configuration exists
        if not self._mcp_config_dao.exists(config_id):
            logger.warning("MCP configuration does not exist: id=%s", config_id)
            raise ResourceNotFoundException("MCP configuration does not exist")

        # Get configuration info for syncing deletion of client in MCPClientManager
        config = self._mcp_config_dao.get_by_id(config_id)
        config_name = config.name if config else "unknown"

        # Delete configuration
        success = self._mcp_config_dao.delete(config_id)

        if not success:
            logger.error("MCP configuration deletion failed: id=%s", config_id)
            raise BusinessException("MCP configuration deletion failed")

        # Verify deletion success - add debug logs
        exists_after_delete = self._mcp_config_dao.exists(config_id)
        exists_by_name_after_delete = self._mcp_config_dao.exists_by_name(config_name)
        logger.info("Post-deletion verification - ID exists: %s, name exists: %s, config name: %s",
                   exists_after_delete, exists_by_name_after_delete, config_name)

        # Synchronously delete client in MCPClientManager
        if config:
            try:
                await self._mcp_client_manager.remove_client(config_id)
                logger.info("MCP Client deleted successfully: %s", config_id)
            except Exception as e:  # pylint: disable=broad-except
                logger.error("Failed to sync delete MCPClientManager: %s", str(e))
                # Do not throw exception, as database operation was successful

        logger.info("MCP configuration deleted successfully: id=%s, name=%s", config_id, config_name)

    async def reconnect_mcp_client(self, config_id: str) -> MCPConfigResponse:
        """
        Reconnect MCP client

        Args:
            config_id: Configuration ID

        Returns:
            MCPConfigResponse: Response object containing reconnection result
        """
        logger.info("Reconnecting MCP client: id=%s", config_id)

        is_local_client = config_id in [LocalMcpClientId.LOCAL_DEFAULT, LocalMcpClientId.MIOT_MANUAL_SCENES,
                                      LocalMcpClientId.MIOT_DEVICES, LocalMcpClientId.HA_AUTOMATIONS]

        if is_local_client:
            logger.info("Reconnecting local MCP client: id=%s", config_id)
        else:
            config = self._mcp_config_dao.get_by_id(config_id)
            if not config:
                logger.warning("MCP configuration does not exist: id=%s", config_id)
                raise ResourceNotFoundException("MCP configuration does not exist")

        client = self._mcp_client_manager.get_client(config_id)
        if not client:
            logger.warning("client does not exist: id=%s", config_id)
            raise ResourceNotFoundException(f"{config_id} client does not exist")

        try:
            # Directly use ensure_connected to reconnect
            success = await client.ensure_connected()

            error_message = None if success else (
                "Local MCP client reconnection failed" if is_local_client
                else "Reconnection failed, please check configuration parameters"
            )

            return MCPConfigResponse(
                config_id=config_id,
                connection_success=success,
                connection_error=error_message
            )
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Failed to reconnect MCPClient: %s", str(e))
            error_message = (f"Local MCP client reconnection failed: {str(e)}" if is_local_client
                           else f"Reconnection failed: {str(e)}")
            return MCPConfigResponse(
                config_id=config_id,
                connection_success=False,
                connection_error=error_message
            )

    async def get_all_mcp_clients_status(self) -> MCPClientStatusList:
        """
        Get status of all MCP clients

        Returns:
            MCPClientStatusList: List containing status of all clients
        """
        logger.info("Getting all MCP client statuses")

        try:
            # Changed to async call for real-time ping detection
            clients_status = await self._mcp_client_manager.get_all_clients_status()

            # Build mapping of configuration and client status
            result = MCPClientStatusList(
                count=len(clients_status),
                clients=clients_status,
            )

            logger.info("Successfully retrieved MCP client statuses: %d clients", len(clients_status))
            return result

        except Exception as e:
            logger.error("Failed to get MCP client statuses: %s", str(e), exc_info=True)
            raise BusinessException(f"Failed to get MCP client statuses: {str(e)}") from e

