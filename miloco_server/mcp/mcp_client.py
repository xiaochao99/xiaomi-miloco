# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
MCP Client
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import json

from fastmcp import Client, FastMCP
from fastmcp.client.client import CallToolResult
from fastmcp.client.transports import StdioTransport
from mcp.types import Tool, Resource
from miloco_server.schema.mcp_schema import TransportType
import httpx

logger = logging.getLogger(__name__)


class BearerTokenAuth(httpx.Auth):
    """Bearer Token authentication for HTTP requests"""
    
    def __init__(self, token: str):
        # Normalize token to support multiple input formats:
        # 1. "Bearer sk-xxx" -> extract "sk-xxx"
        # 2. "Authorization=Bearer sk-xxx" -> extract "sk-xxx"
        # 3. "sk-xxx" -> use directly
        self.token = self._normalize_token(token)
    
    @staticmethod
    def _normalize_token(token: str) -> str:
        """Normalize token format by removing possible prefixes"""
        if not token:
            return token
        
        token = token.strip()
        
        # Handle "Authorization=Bearer xxx" format
        if token.startswith("Authorization="):
            token = token[len("Authorization="):].strip()
        
        # Handle "Bearer xxx" format
        if token.startswith("Bearer"):
            token = token[len("Bearer"):].strip()
        
        return token
    
    def auth_flow(self, request):
        """Add Bearer token to request headers"""
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request


class MCPClientConfig:
    """MCP Client configuration base class"""

    def __init__(
            self,
            client_id: str,
            server_name: str,
            timeout: float = 30.0,
            init_timeout: float = 30.0):
        self.id = client_id
        self.server_name = server_name
        self.timeout = timeout
        self.init_timeout = init_timeout


class LocalMCPConfig(MCPClientConfig):
    """Local MCP Config."""

    def __init__(self, mcp_server: FastMCP, **kwargs):
        super().__init__(**kwargs)
        self.mcp_server = mcp_server


class StdioConfig(MCPClientConfig):
    """Stdio configuration"""

    def __init__(self, command: str, args: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None,
                 cwd: Optional[str] = None, keep_alive: Optional[bool] = True, **kwargs):
        super().__init__(**kwargs)
        self.command = command
        self.args = args
        self.env = env
        self.cwd = cwd
        self.keep_alive = keep_alive


class HTTPConfig(MCPClientConfig):
    """HTTP configuration"""

    def __init__(self, server_url: str, request_header_token: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.server_url = server_url
        self.request_header_token = request_header_token


class MCPClientBase(ABC):
    """MCP Client abstract base class"""

    def __init__(self, config: MCPClientConfig):
        self.config = config
        self.client: Optional[Client] = None
        self._connected = False
        self._tools: Dict[str, Tool] = {}
        self._resources: Dict[str, Resource] = {}

    @abstractmethod
    def _create_transport(self):
        """Create transport object"""
        pass

    def _create_client(self) -> Client:
        """Create client object"""
        transport = self._create_transport()
        return Client(
            transport=transport,
            timeout=self.config.timeout,
            init_timeout=self.config.init_timeout)

    async def connect(self) -> bool:
        """Connect to MCP Server"""
        try:
            self.client = self._create_client()

            async with self.client:
                await self._load_tools()

                await self._load_resources()

                self._connected = True
                logger.info(
                    "Successfully connected to MCP Server [%s]: %s",
                    self.config.server_name,
                    self._get_connection_info())
                return True

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to connect to MCP Server [%s]: %s", self.config.server_name, e, exc_info=True)
            self._connected = False
            return False

    @abstractmethod
    def _get_connection_info(self) -> str:
        """Get connection information"""
        pass

    async def disconnect(self):
        """Disconnect from MCP Server"""
        if self.client and self._connected:
            try:
                await self.client.close()
                self._connected = False
                logger.info("Disconnected from MCP Server [%s]", self.config.server_name)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Error occurred while disconnecting from MCP Server [%s]: %s", self.config.server_name, e)

    async def _load_tools(self):
        """Load available tools"""
        if not self.client:
            return

        try:
            tools = await self.client.list_tools()
            self._tools = {tool.name: tool for tool in tools}
            logger.info("MCP Server [%s] loaded %d tools", self.config.server_name, len(self._tools))
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("MCP Server [%s] failed to load tools: %s", self.config.server_name, e, exc_info=True)

    async def _load_resources(self):
        """Load available resources"""
        if not self.client:
            return

        try:
            resources = await self.client.list_resources()
            self._resources = {resource.uri: resource for resource in resources}
            logger.info("MCP Server [%s] loaded %d resources", self.config.server_name, len(self._resources))
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("MCP Server [%s] failed to load resources: %s", self.config.server_name, e, exc_info=True)

    def get_tools_name(self) -> List[str]:
        """Get available tools list"""
        return list(self._tools.keys())

    def get_tools(self) -> List[Tool]:
        """Get tools object list"""
        return list(self._tools.values())

    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """Get tool object"""
        return self._tools.get(tool_name)

    def get_resources_name(self) -> List[str]:
        """Get available resources list"""
        return list(self._resources.keys())

    def get_resources(self) -> List[Resource]:
        """Get resources object list"""
        return list(self._resources.values())

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call tool"""
        logger.info("MCP Server [%s] call_tool - tool_name: %s, arguments type: %s, arguments: %s",
                    self.config.server_name, tool_name, type(arguments), arguments)

        if not self.client:
            raise RuntimeError(f"MCP Server [{self.config.server_name}] instance does not exist")

        if not await self.ensure_connected():
            raise RuntimeError(
                f"MCP Server [{self.config.server_name}] connection failed, cannot call tool '{tool_name}'")

        if tool_name not in self._tools:
            raise ValueError(f"Tool '{tool_name}' does not exist")

        async with self.client:
            result: CallToolResult = await self.client.call_tool(name=tool_name, arguments=arguments)
            logger.info("MCP Server [%s] call_tool - result: %s", self.config.server_name, result)
            return self._convert_call_tool_result(result)

    def _convert_call_tool_result(self, result: CallToolResult) -> Dict[str, Any]:
        """Convert CallToolResult to dictionary format"""
        if result is None:
            raise ValueError("CallToolResult is None")

        # Check if there is an error
        if result.is_error:
            raise ValueError("Tool execution failed")

        # Prioritize result from structured_content
        if result.structured_content:
            structured_data = result.structured_content
            return structured_data

        # Fallback to text in content
        if result.content:
            # Extract text content
            text_content = []
            for item in result.content:
                if hasattr(item, "text") and item.text:
                    text_content.append(item.text)

            if text_content:
                # Try to parse as JSON, if failed return original text
                try:
                    return json.loads("".join(text_content))
                except json.JSONDecodeError:
                    return {"content": "".join(text_content)}

        return {}

    async def read_resource(self, resource_uri: str) -> Dict[str, Any]:
        """Read resource"""
        if not self._connected or not self.client:
            raise RuntimeError(f"MCP Server [{self.config.server_name}] not connected")

        if resource_uri not in self._resources:
            raise ValueError(f"Resource '{resource_uri}' does not exist")

        try:
            async with self.client:
                return await self.client.read_resource(uri=resource_uri)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("MCP Server [%s] failed to read resource '%s': %s",
                         self.config.server_name, resource_uri, e, exc_info=True)
            raise

    def is_connected(self) -> bool:
        """Check if connected"""
        return self._connected

    def set_connected_false(self):
        """Set connection status"""
        self._connected = False
        self.client = None

    async def ensure_connected(self) -> bool:
        """Ensure client is connected, if not connected then try to connect"""
        if self._connected and self.client:
            # Try ping to verify if connection is actually valid
            try:
                logger.info("MCP Server [%s] verifying connection status: %s",
                            self.config.server_name, self._get_connection_info())
                async with self.client:
                    ping_result = await self.client.ping()
                    if ping_result:
                        logger.info("MCP Server [%s] connection verification successful", self.config.server_name)
                        return True
                    else:
                        logger.warning(
                            "MCP Server [%s] Ping failed, connection may be disconnected",
                            self.config.server_name)
                        self._connected = False
                        self.client = None
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning(
                    "MCP Server [%s] connection status abnormal, trying to reconnect... error: %s",
                    self.config.server_name,
                    e)
                self._connected = False
                self.client = None

        # Try to connect
        logger.info("Trying to reconnect to MCP Server [%s]: %s", self.config.server_name, self._get_connection_info())
        return await self.connect()

    def get_resource_info(self, resource_uri: str) -> Optional[Resource]:
        """Get resource information"""
        return self._resources.get(resource_uri)

    async def ping(self) -> bool:
        """Ping server"""
        if not self._connected or not self.client:
            return False

        try:
            async with self.client:
                return await self.client.ping()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.debug("MCP Server [%s] ping failed: %s", self.config.server_name, e)
            return False


class LocalMCPClient(MCPClientBase):
    """Local MCP Client implementation"""

    def __init__(self, config: LocalMCPConfig):
        super().__init__(config)
        self.config: LocalMCPConfig = config

    def _create_client(self) -> Client:
        """Create client object for local MCP server"""
        return Client(self.config.mcp_server)

    def _create_transport(self):
        """Create local transport object"""
        raise NotImplementedError("LocalMCPClient does not support local transport")

    def _get_connection_info(self) -> str:
        """Get connection information"""
        return "Local MCP(Xiaomi Home & Home Assistant)"


class StdioMCPClient(MCPClientBase):
    """Stdio MCP Client implementation"""

    def __init__(self, config: StdioConfig):
        super().__init__(config)
        self.config: StdioConfig = config

    def _create_transport(self):
        """Create Stdio transport object"""
        return StdioTransport(
            command=self.config.command,
            args=self.config.args or [],
            env=self.config.env,
            cwd=self.config.cwd,
            keep_alive=self.config.keep_alive
        )

    def _get_connection_info(self) -> str:
        """Get connection information"""
        args = " ".join(self.config.args or []) if self.config.args else ""
        return f"stdio ({self.config.command} {args})"


class SSEMCPClient(MCPClientBase):
    """SSE MCP Client implementation"""

    def __init__(self, config: HTTPConfig):
        super().__init__(config)
        self.config: HTTPConfig = config

    def _create_transport(self):
        """Create SSE transport object"""
        return self.config.server_url

    def _create_client(self) -> Client:
        """Create client object with authentication support"""
        transport = self._create_transport()
        # Get authentication token for HTTP transport
        auth = None
        if self.config.request_header_token:
            auth = BearerTokenAuth(self.config.request_header_token)
        return Client(
            transport=transport,
            timeout=self.config.timeout,
            init_timeout=self.config.init_timeout,
            auth=auth)

    def _get_connection_info(self) -> str:
        """Get connection information"""
        return f"sse ({self.config.server_url})"


class StreamableHTTPMCPClient(MCPClientBase):
    """Streamable HTTP MCP Client implementation"""

    def __init__(self, config: HTTPConfig):
        super().__init__(config)
        self.config: HTTPConfig = config

    def _create_transport(self):
        """Create Streamable HTTP transport object"""
        return self.config.server_url

    def _create_client(self) -> Client:
        """Create client object with authentication support"""
        transport = self._create_transport()
        # Get authentication token for HTTP transport
        auth = None
        if self.config.request_header_token:
            auth = BearerTokenAuth(self.config.request_header_token)
        return Client(
            transport=transport,
            timeout=self.config.timeout,
            init_timeout=self.config.init_timeout,
            auth=auth)

    def _get_connection_info(self) -> str:
        """Get connection information"""
        return f"streamable_http ({self.config.server_url})"


class MCPClientFactory:
    """MCP Client factory class"""

    @staticmethod
    def create_client(transport_type: TransportType, config: MCPClientConfig) -> MCPClientBase:
        """Create MCP Client instance"""
        if transport_type == TransportType.LOCAL:
            if not isinstance(config, LocalMCPConfig):
                raise ValueError("Local transport requires LocalMCPConfig configuration")
            return LocalMCPClient(config)
        if transport_type == TransportType.STDIO:
            if not isinstance(config, StdioConfig):
                raise ValueError("Stdio transport requires StdioConfig configuration")
            return StdioMCPClient(config)
        if transport_type == TransportType.HTTP_SSE:
            if not isinstance(config, HTTPConfig):
                raise ValueError("SSE transport requires HTTPConfig configuration")
            return SSEMCPClient(config)

        if transport_type == TransportType.STREAMABLE_HTTP:
            if not isinstance(config, HTTPConfig):
                raise ValueError("Streamable HTTP transport requires HTTPConfig configuration")
            return StreamableHTTPMCPClient(config)

        raise ValueError(f"Unsupported transport type: {transport_type}")
