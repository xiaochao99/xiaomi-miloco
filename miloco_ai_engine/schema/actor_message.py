# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Actor message module for defining actor message data structures."""
from dataclasses import dataclass
from typing import Any, Optional, Union
from thespian.actors import ActorAddress, ActorSystem
from enum import Enum
from miloco_ai_engine.schema.models_schema import ChatCompletionResponse

actor_system = ActorSystem()


class TaskAction(Enum):
    """Task action enumeration"""
    START = "start"
    CANCEL = "cancel"
    GET_INFO = "get_info"


class TaskSchedulerAction(Enum):
    """Task scheduler action enumeration"""
    START = "start"
    STOP = "stop"
    CLEANUP = "cleanup"
    SUBMIT_TASK = "submit_task"


class ModelAction(Enum):
    """Model action"""
    LOAD = "load"  # Load model
    UNLOAD = "unload"  # Unload model
    CHAT = "chat"  # Chat completion
    STREAM_CHAT = "stream_chat"  # Streaming chat
    GET_STATUS = "get_status"  # Get status
    CLEANUP = "cleanup"  # Cleanup
    CHAT_RESPONSE = "chat_response"  # Chat response

Action = Union[TaskAction, TaskSchedulerAction, ModelAction]

@dataclass
class ResultMessage:
    """Model manager result message"""
    result: bool
    error: Optional[str] = None
    data: Optional[Any] = None


@dataclass
class CallbackMessage:
    """Callback message"""
    callback_actor: ActorAddress
    callback_action: Action
    request_id: Optional[str] = None


@dataclass
class RequestMessage:
    """Request message"""
    action: Action
    data: Optional[Any] = None
    call_back_message: Optional[CallbackMessage] = None


@dataclass
class ModelActorResponse:
    """Model actor response message"""
    request_id: str
    response: ChatCompletionResponse

@dataclass
class TaskActorResponse:
    """Task scheduler response message"""
    task_id: str
    success: bool
