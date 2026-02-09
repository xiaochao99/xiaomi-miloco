# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Mico content processing utility
"""
from typing import Union, List, Dict, Any
import base64
import os
from miloco_ai_engine.schema.models_schema import ChatCompletionResponse, ChatCompletionChoice, ChatMessage, Role, FinishReason, ToolCall, FunctionCall, ContentType
from miloco_ai_engine.middleware.exceptions import CoreResponeException
import json
import uuid

import logging
logger = logging.getLogger(__name__)

# TODO: only support qwen, should use model config
QWEN_TOOL_CALL_START = "<tool_call>"
QWEN_TOOL_CALL_END = "</tool_call>"
QWEN_FUNCTION_NAME_TABLE = "name"
QWEN_FUNCTION_ARGUMENTS_TABLE = "arguments"

class MicoContentUtil:
    """Mico content processing utility class"""

    def __init__(self,
                 tool_call_start: str = QWEN_TOOL_CALL_START,
                 tool_call_end: str = QWEN_TOOL_CALL_END,
                 function_name_table: str = QWEN_FUNCTION_NAME_TABLE,
                 function_arguments_table: str = QWEN_FUNCTION_ARGUMENTS_TABLE):
        self.tool_call_start = tool_call_start
        self.tool_call_end = tool_call_end
        self.function_name_table = function_name_table
        self.function_arguments_table = function_arguments_table

    def process_tool_calls(
        self, tool_wait: bool, tool_call: bool, accumulated_content: str
    ) -> tuple[bool, bool, str, Union[None, str, ChatCompletionResponse]]:
        """
        Process tool call content

        Returns:
        tool_wait, tool_call, accumulated_content, tmp_tool_response
        """
        if not tool_call:
            if accumulated_content and self.tool_call_start.startswith(
                    accumulated_content):
                tool_wait = True
            else:
                tool_wait = False

            if self.tool_call_start in accumulated_content:
                tool_call = True
                if tool_wait:
                    logger.info("Tool call start detected, waiting for complete generation...")
                tool_wait = False

            if tool_wait:
                # Wait for tool call to start
                return tool_wait, tool_call, accumulated_content, None

        if tool_call:
            if self.tool_call_end in accumulated_content:
                logger.info("Tool call end detected, starting generation...")
                tmp_tool_respone = ChatCompletionResponse(
                    object="chat.completion.chunk",
                    choices=[
                        ChatCompletionChoice(index=0,
                                             message=ChatMessage(
                                                 role=Role.ASSISTANT,
                                                 content=accumulated_content))
                    ])

                tool_respone = self._process_tool_call_response(tmp_tool_respone)
                tool_call = False
                accumulated_content = ""
                # Tool call complete
                return tool_wait, tool_call, accumulated_content, tool_respone

            # Wait for tool call to complete
            return tool_wait, tool_call, accumulated_content, None

        # Tool call not started and not waiting or incorrect table
        return tool_wait, tool_call, "", accumulated_content

    def process_multimodal_message(
            self,
            content: Union[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        Process multimodal message content
        """
        if isinstance(content, str):
            return [{"type": "text", "text": content}]

        if not isinstance(content, list):
            logger.error("Failed to parse multimodal content")
            raise CoreResponeException("Invalid content information type")

        processed_content = []
        for item in content:
            if not isinstance(item, dict) or "type" not in item:
                logger.warning("Failed to parse multimodal content")
                continue

            if item["type"] is ContentType.TEXT:
                text_item = {"type": "text", "text": item["text"]}
                processed_content.append(text_item)

            elif item["type"] is ContentType.IMAGE_URL:
                # Process image URL
                if "image_url" not in item or not isinstance(item["image_url"], dict):
                    logger.warning("Failed to parse multimodal content")
                    continue

                url: str = item["image_url"].get("url", "")
                if url.startswith("data:image/"):  # base64
                    image_item = {"type": "image", "image": url}
                    processed_content.append(image_item)
                elif url.startswith("http"):  # http resource
                    logger.warning("HTTP image URLs not supported yet, please use base64 format")
                else:  # static resource
                    try:
                        with open(url, "rb") as f:
                            image_data = f.read()
                            base64_data = base64.b64encode(image_data).decode("utf-8")
                            mime_type = self._get_mime_type(url)
                            processed_content.append({
                                "type":"image",
                                "image":f"data:{mime_type};base64,{base64_data}"
                            })
                    except Exception as e: # pylint: disable=broad-exception-caught
                        logger.error("Failed to process image file: %s", e)

            else:  # Other formats
                item_type = item["type"].value
                value = item.get(item_type, "")

                if isinstance(value, list):
                    value = [str(v) for v in value]
                else:
                    value = str(value)

                type_item = {"type": item_type, item_type: value}
                processed_content.append(type_item)

        return processed_content

    def mutilmodal_message_to_bytes(
        self,
        content: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[bytes]]:
        """
        Convert base64-encoded multimodal messages to byte streams
        """
        if not isinstance(content, list):
            raise CoreResponeException("Invalid content information type")

        base64_table = ";base64,"

        bytes_list = []
        for item in content:
            if not isinstance(item, dict) or "type" not in item:
                logger.warning("Invalid content information type")
                continue

            if item["type"] == "image":
                if "image" not in item or not isinstance(item["image"], str):
                    logger.warning("Invalid content information type")
                    continue
                tables = item["image"].split(base64_table)
                base64_image = tables[1]
                bytes_list.append(base64.b64decode(base64_image))
                item["image"] = tables[0] + base64_table

            elif item["type"] == "video":
                if "video" not in item or not isinstance(item["video"], list):
                    logger.warning("Invalid content information type")
                    continue
                for i, video_item in enumerate(item["video"]):
                    tables = video_item.split(base64_table)
                    base64_image = tables[1]
                    bytes_list.append(base64.b64decode(base64_image))
                    item["video"][i] = tables[0] + base64_table

        return content, bytes_list

    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type based on file extension"""
        ext = os.path.splitext(file_path)[1].lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".webp": "image/webp"
        }
        return mime_types.get(ext, "image/jpeg")

    def _process_tool_call_response(
            self, response: ChatCompletionResponse) -> ChatCompletionResponse:
        """
        Process tool call response
        """
        # Check if message content contains tool call format
        message = response.choices[0].message
        content = message.content
        if not (isinstance(content, str) and self.tool_call_start in content):
            return response

        # Parse tool call format
        tool_calls = self._parse_tool_use_format(content)

        if tool_calls:
            message.tool_calls = tool_calls
            message.content = message.content.split(self.tool_call_start)[0]
            logger.info("Tool parsing complete...%s", tool_calls)
            response.choices[0].finish_reason = FinishReason.TOOL_CALL

        return response

    def _parse_tool_use_format(self, content: str) -> List[ToolCall]:
        """
        Parse tool call in the following format:
        <tool_call>\n{"name": <function-name>, "arguments": <args-json-object>}\n</tool_call>
        """
        tool_calls = []
        func = None
        if content.count(self.tool_call_start) > 0 and content.count(
                self.tool_call_end) > 0:
            func = content.split(self.tool_call_start)[1].split(
                self.tool_call_end)[0]

        try:
            if not func:
                raise CoreResponeException("Failed to parse function from model's <tool_call> response")

            parsed_args = json.loads(func)
            if self.function_name_table in parsed_args and self.function_arguments_table in parsed_args:
                arguments = parsed_args[self.function_arguments_table]
                if isinstance(arguments, str):
                    arguments = arguments.strip()
                else:
                    arguments = json.dumps(arguments, ensure_ascii=False)

                tool_calls.append(
                    ToolCall(id=str(uuid.uuid4()),
                             type="function",
                             function=FunctionCall(name=str(
                                 parsed_args[self.function_name_table]),
                                                   arguments=arguments)))
            return tool_calls

        except json.JSONDecodeError:
            logger.error("Failed to parse tool call")
            return tool_calls
