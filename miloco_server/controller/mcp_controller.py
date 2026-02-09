# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
MCP configuration controller
Implements CRUD interfaces for MCP configuration
Uses unified exception handling framework
"""

from fastapi import APIRouter, Depends
from miloco_server.service.manager import get_manager
from miloco_server.schema.common_schema import NormalResponse
from miloco_server.schema.mcp_schema import MCPConfigModel
from miloco_server.middleware import verify_token
import logging
from typing import List

logger = logging.getLogger(name=__name__)

router = APIRouter(prefix="/mcp", tags=["MCP Configuration"])

manager = get_manager()


@router.post("", summary="Create MCP configuration", response_model=NormalResponse)
async def create_mcp_config(
    config: MCPConfigModel,
    current_user: str = Depends(verify_token)
):
    """
    Create MCP configuration
    - Requires login permissions
    - Configuration name must be unique
    - Validate required parameters based on access type
    """
    logger.info("Create MCP config API called - User: %s, Config name: %s", current_user, config.name)
    result = await manager.mcp_service.create_mcp_config(config)
    message = ("MCP configuration created successfully, connection normal"
               if result.connection_success
               else f"MCP configuration created successfully, but connection failed: {result.connection_error}")
    logger.info("MCP config created successfully - Config ID: %s", result.config_id)
    return NormalResponse(
        code=0,
        message=message,
        data=result
    )


@router.get("", summary="Get all MCP configurations", response_model=NormalResponse)
async def get_all_mcp_configs(
    current_user: str = Depends(verify_token)
):
    """
    Get all MCP configurations
    - Requires login
    """
    logger.info("Get all MCP configs API called - User: %s", current_user)
    configs: List[MCPConfigModel] = await manager.mcp_service.get_all_mcp_configs()
    logger.info("All MCP configs retrieved successfully - Count: %s", len(configs))
    return NormalResponse(
        code=0,
        message="MCP configuration list retrieved successfully",
        data={"configs": configs, "count": len(configs)}
    )


@router.put("/{config_id}", summary="Update MCP configuration", response_model=NormalResponse)
async def update_mcp_config(
    config_id: str,
    config: MCPConfigModel,
    current_user: str = Depends(verify_token)
):
    """
    Update MCP configuration
    - Requires login permissions
    - Configuration name must be unique
    - Validate required parameters based on access type
    """
    logger.info("Update MCP config API called - User: %s, Config ID: %s", current_user, config_id)
    config.id = config_id
    result = await manager.mcp_service.update_mcp_config(config)
    message = ("MCP configuration updated successfully, connection normal"
               if result.connection_success
               else f"MCP configuration updated successfully, but connection failed: {result.connection_error}")
    logger.info("MCP config updated successfully - Config ID: %s", config_id)
    return NormalResponse(
        code=0,
        message=message,
        data=result
    )


@router.delete("/{config_id}", summary="Delete MCP configuration", response_model=NormalResponse)
async def delete_mcp_config(
    config_id: str,
    current_user: str = Depends(verify_token)
):
    """
    Delete MCP configuration
    - Requires login permissions
    """
    logger.info("Delete MCP config API called - User: %s, Config ID: %s", current_user, config_id)
    await manager.mcp_service.delete_mcp_config(config_id)
    logger.info("MCP config deleted successfully - Config ID: %s", config_id)
    return NormalResponse(
        code=0,
        message="MCP configuration deleted successfully",
        data=None
    )


@router.post("/reconnect/{config_id}", summary="Reconnect MCP client", response_model=NormalResponse)
async def reconnect_mcp_client(
    config_id: str,
    current_user: str = Depends(verify_token)
):
    """
    Reconnect MCP client
    - Requires login
    """
    logger.info("Reconnect MCP client API called - User: %s, Config ID: %s", current_user, config_id)
    result = await manager.mcp_service.reconnect_mcp_client(config_id)
    message = ("MCP client reconnected successfully"
               if result.connection_success
               else f"MCP client reconnection failed: {result.connection_error}")
    logger.info("MCP client reconnect completed - Config ID: %s", config_id)
    return NormalResponse(
        code=0,
        message=message,
        data=result
    )


@router.get("/clients/status", summary="Get all MCP client status", response_model=NormalResponse)
async def get_all_mcp_clients_status(
    current_user: str = Depends(verify_token)
):
    """
    Get all MCP client status
    - Requires login
    """
    logger.info("Get all MCP clients status API called - User: %s", current_user)
    status = await manager.mcp_service.get_all_mcp_clients_status()
    logger.info("All MCP clients status retrieved successfully")
    return NormalResponse(
        code=0,
        message="MCP client status retrieved successfully",
        data=status
    )
