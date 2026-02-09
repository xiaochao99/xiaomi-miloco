# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Tool executor module for executing and managing MCP tools."""

import json
import logging
from typing import Any, Optional

from miloco_server.schema.mcp_schema import CallToolResult
from miloco_server.mcp.mcp_client_manager import MCPClientManager
from openai.types.chat import ChatCompletionMessageToolCall, ChatCompletionToolParam
from openai.types.shared.function_definition import FunctionDefinition

logger = logging.getLogger(__name__)

TOOL_NAME_CONNECT_CHARS = "___"

class ToolExecutor:
    """Executor for managing and executing MCP tools."""
    def __init__(self, mcp_client_manager: MCPClientManager):
        self.mcp_client_manager = mcp_client_manager

    def _create_function_definition(self, name: str, description: str,
                                    parameters: dict[str, Any]) -> FunctionDefinition:
        """
        Common method to create FunctionDefinition

        Args:
            name: Function name
            description: Function description
            parameters: Function parameters

        Returns:
            FunctionDefinition: Function definition object
        """
        return FunctionDefinition(
            name=name,
            description=description,
            parameters=parameters
        )

    def _create_chat_completion_tool(self, function_def: FunctionDefinition) -> ChatCompletionToolParam:
        """
        Common method to create ChatCompletionToolParam

        Args:
            function_def: Function definition object

        Returns:
            ChatCompletionToolParam: Chat completion tool parameter
        """
        return ChatCompletionToolParam(
            type="function",
            function=function_def
        )

    def _convert_tool_to_chat_completion_format(
            self, name: str, description: str, parameters: dict[str, Any]) -> ChatCompletionToolParam:
        """
        Common method to convert tool to ChatCompletionToolParam format

        Args:
            name: Tool name
            description: Tool description
            parameters: Tool parameters

        Returns:
            ChatCompletionToolParam: Chat completion tool parameter
        """
        try:
            function_def = self._create_function_definition(name, description, parameters)
            return self._create_chat_completion_tool(function_def)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to convert tool %s: %s", name, e)
            raise

    def get_mcp_chat_completion_tools(
            self,
            mcp_client_ids: Optional[list[str]] = None,
            exclude_tool_names: Optional[list[str]] = None,
            ) -> list[ChatCompletionToolParam]:

        """
        Convert MCP tools to ChatCompletionToolParam format

        Args:
            mcp_client_ids: Client ID list, used when mcp_client_ids is not None
            exclude_tool_names: Tool name list to exclude
        Returns:
            list[ChatCompletionToolParam]: OpenAI compatible tool list
        """
        converted_tools: list[ChatCompletionToolParam] = []

        try:
            if mcp_client_ids:
                tool_infos = self.mcp_client_manager.get_tools_by_ids(mcp_client_ids)
            else:
                logger.warning("No MCP client ID specified, returning empty tool list")
                return []

            # Convert to ChatCompletionToolParam format
            for tool_info in tool_infos:
                try:
                    if exclude_tool_names and tool_info.tool_name in exclude_tool_names:
                        logger.debug("Excluding tool %s.%s", tool_info.client_id, tool_info.tool_name)
                        continue
                    client_id = tool_info.client_id
                    tool_name = tool_info.tool_name
                    tool_name_with_prefix = f"{client_id}{TOOL_NAME_CONNECT_CHARS}{tool_name}"
                    tool_param = self._convert_tool_to_chat_completion_format(
                        name=tool_name_with_prefix,
                        description=tool_info.description,
                        parameters=tool_info.parameters
                    )
                    converted_tools.append(tool_param)
                    logger.debug(
                        "Successfully converted tool: %s.%s -> %s",
                        tool_info.client_id,
                        tool_info.tool_name,
                        tool_name_with_prefix)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.error("Failed to convert tool %s.%s: %s", tool_info.client_id, tool_info.tool_name, e)
                    continue

            logger.info("Successfully converted %d tools to ChatCompletionToolParam format", len(converted_tools))

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error occurred while getting tools: %s", e)

        return converted_tools

    def parse_tool_call(self, tool_call: ChatCompletionMessageToolCall) -> tuple[str, str, dict[str, Any]]:
        logger.info("ToolExecutor parse_tool_call: %s", tool_call)

        tool_name = tool_call.function.name
        parameters_str = tool_call.function.arguments

        # Parse parameter string to dictionary - handle multiple escape situations
        try:
            logger.info(
                "ToolExecutor parse_tool_call parameters_str: %s type: %s",
                parameters_str,
                type(parameters_str))
            if parameters_str:
                parameters = parameters_str
                # Loop parse until get dictionary type or cannot continue parsing
                parse_count = 0
                while isinstance(parameters, str) and parse_count < 5:  # Parse at most 5 times to prevent infinite loop
                    try:
                        parameters = json.loads(parameters)
                        parse_count += 1
                        logger.info(
                            "ToolExecutor parse_tool_call parameters after parse %d: %s type: %s",
                            parse_count,
                            parameters,
                            type(parameters))
                    except json.JSONDecodeError as e:
                        logger.error("Parse attempt %d failed: %s, parameters: %s", parse_count + 1, e, parameters)
                        break

                # If final result is still string, cannot parse as JSON, return empty dictionary
                if isinstance(parameters, str):
                    logger.warning(
                        "Parameters cannot be parsed as dictionary, final result is still string: %s",
                        parameters)
                    parameters = {}
            else:
                parameters = {}
            logger.info("ToolExecutor parse_tool_call final parameters: %s type: %s", parameters, type(parameters))
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to parse tool call: %s, error: %s", tool_call, e)
            parameters = {}

        if TOOL_NAME_CONNECT_CHARS in tool_name:
            client_id, tool_name = tool_name.split(TOOL_NAME_CONNECT_CHARS, 1)
        else:
            client_id = "unknown"

        return client_id, tool_name, parameters

    def get_server_name(self, client_id: str) -> str:
        client = self.mcp_client_manager.get_client(client_id)
        return client.config.server_name if client else "Unknow Server"

    async def execute_tool_by_params(self, client_id: str, tool_name: str,
                                     parameters: dict[str, Any]) -> CallToolResult:
        tool_result = await self.mcp_client_manager.call_tool(
            client_id=client_id, tool_name=tool_name, arguments=parameters)
        return tool_result

    async def execute_tool(self, tool_call: ChatCompletionMessageToolCall) -> CallToolResult:
        client_id, tool_name, parameters = self.parse_tool_call(tool_call)
        return await self.execute_tool_by_params(client_id, tool_name, parameters)
