# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
MCP utility functions
Handle MCP-related utility operations and conversions
"""

from miloco_server.schema.mcp_schema import MCPConfigModel, TransportType
from miloco_server.mcp.mcp_client import StdioConfig, HTTPConfig


class MCPConfigConverter:
    """MCP configuration converter"""
    @staticmethod
    def to_mcp_client_config(config: MCPConfigModel):
        """Convert frontend configuration to MCP Client configuration"""
        if config.access_type == TransportType.STDIO:
            return StdioConfig(
                client_id=config.id,
                command=config.command,
                args=config.args,
                env=config.env_vars,
                cwd=config.working_directory,
                server_name=config.name,
                timeout=config.timeout,
                init_timeout=config.timeout
            )
        elif config.access_type in [TransportType.HTTP_SSE, TransportType.STREAMABLE_HTTP]:
            return HTTPConfig(
                client_id=config.id,
                server_url=config.url,
                server_name=config.name,
                timeout=config.timeout,
                init_timeout=config.timeout,
                request_header_token=config.request_header_token
            )
        else:
            raise ValueError(f"Unsupported transport type: {config.access_type}")
