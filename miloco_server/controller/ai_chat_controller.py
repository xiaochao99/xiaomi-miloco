# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
AI Chat REST API Controller
提供HTTP API接口，复用Web UI的AI对话系统核心逻辑
支持流式SSE输出，与Web UI消息格式保持一致
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Optional, List, AsyncGenerator
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from thespian.actors import Actor, ActorAddress, ActorExitRequest

from miloco_server import actor_system
from miloco_server.agent.nlp_request_agent import NlpRequestAgent
from miloco_server.schema.chat_schema import (
    Event, Header, Nlp, Template, Dialog, Instruction, InstructionPayload
)
from miloco_server.schema.chat_history_schema import (
    ChatHistoryStorage, ChatHistoryMessages, ChatHistorySession
)
from miloco_server.middleware import verify_token
from miloco_server.service.manager import get_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Chat API"])


def parse_ai_response(response_text: str) -> dict:
    """
    解析AI响应文本，提取思考过程和最终答案
    
    解析规则:
    - <reflect>...</reflect> 标签内容为思考过程
    - <final_answer>...</final_answer> 标签内容为最终答案
    
    返回:
        {
            "thinking": "思考过程（多个reflect标签内容合并）",
            "final_answer": "最终答案",
            "has_structured_format": True/False  # 是否为结构化格式
        }
    """
    import re
    
    if not response_text:
        return {
            "thinking": None,
            "final_answer": None,
            "has_structured_format": False
        }
    
    result = {
        "thinking": None,
        "final_answer": None,
        "has_structured_format": False
    }
    
    # 提取 reflect 标签内容
    # 支持多行匹配，非贪婪模式
    reflect_pattern = r'<reflect>(.*?)</reflect>'
    reflect_matches = re.findall(reflect_pattern, response_text, re.DOTALL | re.IGNORECASE)
    
    if reflect_matches:
        # 多个 reflect 标签内容用换行分隔
        result["thinking"] = "\n\n".join(
            match.strip() for match in reflect_matches if match.strip()
        )
        result["has_structured_format"] = True
    
    # 提取 final_answer 标签内容
    final_answer_pattern = r'<final_answer>(.*?)</final_answer>'
    final_answer_match = re.search(final_answer_pattern, response_text, re.DOTALL | re.IGNORECASE)
    
    if final_answer_match:
        result["final_answer"] = final_answer_match.group(1).strip()
        result["has_structured_format"] = True
    
    return result


class AIChatRequest(BaseModel):
    """AI对话请求 - 与Web UI输入框参数保持一致
    
    默认行为:
    - camera_ids为null时，自动选择所有在线摄像头
    - mcp_list为null时，使用所有可用的MCP服务
    """
    message: str = Field(..., description="用户输入的文字命令")
    camera_ids: Optional[List[str]] = Field(default=None, description="摄像头设备ID列表（可选，默认自动选择所有在线摄像头）")
    mcp_list: Optional[List[str]] = Field(default=None, description="MCP服务ID列表（可选，默认使用所有可用MCP服务）")
    session_id: Optional[str] = Field(default=None, description="对话会话ID（可选，用于多轮对话）")


class AIChatResponse(BaseModel):
    """AI对话响应（同步模式）
    
    响应内容会被自动解析，分离思考过程和最终答案：
    - thinking: 提取自 <reflect>...</reflect> 标签的思考过程
    - final_answer: 提取自 <final_answer>...</final_answer> 标签的最终答案
    """
    request_id: str = Field(..., description="请求ID")
    session_id: str = Field(..., description="会话ID")
    response: str = Field(..., description="原始完整响应内容")
    thinking: Optional[str] = Field(default=None, description="AI思考过程（从<reflect>标签提取）")
    final_answer: Optional[str] = Field(default=None, description="AI最终答案（从<final_answer>标签提取）")
    executed_actions: Optional[List[str]] = Field(default=None, description="执行的动作列表")
    processing_time: float = Field(..., description="处理耗时（秒）")


# 全局消息队列管理器，用于API流式输出
class APIMessageCollector:
    """
    API消息收集器 - 作为Actor系统的消息接收端
    收集ChatAgent发送的消息并通过队列提供给API层
    """
    _collectors = {}
    
    @classmethod
    def create_collector(cls, request_id: str) -> asyncio.Queue:
        """为请求创建消息队列"""
        queue = asyncio.Queue()
        cls._collectors[request_id] = queue
        return queue
    
    @classmethod
    def get_collector(cls, request_id: str) -> Optional[asyncio.Queue]:
        """获取请求的消息队列"""
        return cls._collectors.get(request_id)
    
    @classmethod
    def remove_collector(cls, request_id: str):
        """移除请求的消息队列"""
        cls._collectors.pop(request_id, None)
    
    @classmethod
    async def send_message(cls, request_id: str, message: dict):
        """发送消息到指定请求的队列"""
        queue = cls._collectors.get(request_id)
        if queue:
            await queue.put(message)


class APIOutActor(Actor):
    """
    API输出Actor - 接收ChatAgent发送的Instruction消息
    将消息转发给API消息收集器
    """
    
    def __init__(self, request_id: str, session_id: str = None):
        super().__init__()
        self.request_id = request_id
        self.session_id = session_id
        self.message_count = 0
    
    def receiveMessage(self, msg, sender):
        """接收来自ChatAgent的消息"""
        try:
            if isinstance(msg, (Template.ToastStream, Dialog.Finish, Dialog.Exception,
                               Template.CallTool, Template.CallToolResult)):
                self.message_count += 1
                
                # 提取消息类型信息
                namespace, name = self._get_message_type(msg)
                
                # 构建header
                header = {
                    "type": "instruction",
                    "namespace": namespace,
                    "name": name,
                    "timestamp": int(time.time() * 1000),
                    "request_id": self.request_id,
                    "session_id": self.session_id
                }
                
                # 提取payload
                payload = self._extract_payload(msg)
                
                message_dict = {
                    "header": header,
                    "payload": json.dumps(payload, ensure_ascii=False)
                }
                
                logger.debug("[%s] APIOutActor转发消息 #%d: %s.%s", 
                           self.request_id, self.message_count, namespace, name)
                
                # 异步发送消息到收集器
                asyncio.create_task(
                    APIMessageCollector.send_message(self.request_id, message_dict)
                )
                
                # 如果是Finish消息，再发送一个结束标记
                if isinstance(msg, Dialog.Finish):
                    logger.info("[%s] APIOutActor收到Finish消息，发送结束标记", self.request_id)
                    asyncio.create_task(
                        APIMessageCollector.send_message(self.request_id, {"__finish__": True})
                    )
                
            elif isinstance(msg, ActorExitRequest):
                logger.info("[%s] APIOutActor received exit request", self.request_id)
                
        except Exception as e:
            logger.error("[%s] APIOutActor error: %s", self.request_id, e, exc_info=True)
    
    def _get_message_type(self, msg) -> tuple:
        """获取消息类型（namespace, name）"""
        if isinstance(msg, Template.ToastStream):
            return ("Template", "ToastStream")
        elif isinstance(msg, Dialog.Finish):
            return ("Dialog", "Finish")
        elif isinstance(msg, Dialog.Exception):
            return ("Dialog", "Exception")
        elif isinstance(msg, Template.CallTool):
            return ("Template", "CallTool")
        elif isinstance(msg, Template.CallToolResult):
            return ("Template", "CallToolResult")
        else:
            return ("Unknown", "Unknown")
    
    def _extract_payload(self, msg) -> dict:
        """提取消息payload"""
        try:
            if isinstance(msg, Template.ToastStream):
                return {"stream": msg.stream}
            elif isinstance(msg, Dialog.Finish):
                return {"success": msg.success}
            elif isinstance(msg, Dialog.Exception):
                return {"message": msg.message}
            elif isinstance(msg, Template.CallTool):
                return {
                    "id": msg.id,
                    "service_name": msg.service_name,
                    "tool_name": msg.tool_name,
                    "tool_params": msg.tool_params
                }
            elif isinstance(msg, Template.CallToolResult):
                return {
                    "id": msg.id,
                    "success": msg.success,
                    "tool_response": msg.tool_response,
                    "error_message": msg.error_message
                }
        except Exception as e:
            logger.warning("[%s] 提取payload失败: %s", self.request_id, e)
        
        return {}


class APIChatAdapter:
    """
    API聊天适配器 - 复用ChatAgent/NlpRequestAgent的核心逻辑
    将Actor系统的消息输出转换为API可消费的流式数据
    """
    
    def __init__(self, request_id: str, session_id: Optional[str] = None):
        self.request_id = request_id
        self.session_id = session_id or str(uuid.uuid4())
        self.message_queue: asyncio.Queue = APIMessageCollector.create_collector(request_id)
        self._chat_agent = None
        self._out_actor = None
        self._manager = get_manager()
        self._chat_companion = self._manager.chat_companion
        
        # 初始化聊天历史
        chat_history_storage = self._chat_companion.get_chat_history(self.session_id)
        if chat_history_storage is not None:
            self._chat_history_storage = chat_history_storage
        else:
            self._chat_history_storage = ChatHistoryStorage(
                session_id=self.session_id,
                title="",
                timestamp=int(time.time() * 1000),
                session=ChatHistorySession(),
                messages=None,
            )
        self._chat_history_messages = ChatHistoryMessages.from_json(
            self._chat_history_storage.messages
        )
        self._need_storage_history = False
        self._full_response = ""
        self._success = True
        
        logger.info("[%s] APIChatAdapter 初始化完成, session_id: %s", 
                   request_id, self.session_id)
    
    async def _get_auto_selected_cameras(self) -> List[str]:
        """自动选择在线摄像头"""
        try:
            # 获取所有摄像头设备
            all_cameras = await self._manager.miot_proxy.get_cameras()
            if not all_cameras:
                logger.info("[%s] 未找到摄像头设备", self.request_id)
                return []

            # 选择所有在线的摄像头（检查 online 或 camera_status）
            online_cameras = []
            for did, camera_info in all_cameras.items():
                is_online = getattr(camera_info, 'online', False)
                camera_status = getattr(camera_info, 'camera_status', None)
                status_online = camera_status in ['1', 1, 'CONNECTED', 'ONLINE']

                if is_online or status_online:
                    online_cameras.append(did)
                    logger.debug("[%s] 选择在线摄像头: %s (online=%s, status=%s)",
                                self.request_id, did, is_online, camera_status)

            if online_cameras:
                logger.info("[%s] 自动选择 %d 个在线摄像头", self.request_id, len(online_cameras))
            else:
                all_dids = list(all_cameras.keys())
                logger.warning("[%s] 没有在线的摄像头，找到的设备: %s", self.request_id, all_dids)

            return online_cameras

        except Exception as e:
            logger.error("[%s] 获取摄像头列表失败: %s", self.request_id, e)
            return []
    
    async def _get_all_mcp_services(self) -> List[str]:
        """获取所有MCP服务ID"""
        try:
            # 从MCP服务管理器获取所有服务
            mcp_service = self._manager.mcp_service
            client_ids = []

            # 方法1: 直接获取 clients 字典的 keys
            if hasattr(mcp_service, 'clients') and isinstance(mcp_service.clients, dict):
                client_ids = list(mcp_service.clients.keys())

            # 方法2: 从 tool_executor 获取
            if not client_ids and hasattr(self._manager, 'tool_executor'):
                tool_executor = self._manager.tool_executor
                if hasattr(tool_executor, 'mcp_client_manager') and tool_executor.mcp_client_manager:
                    mcp_manager = tool_executor.mcp_client_manager
                    if hasattr(mcp_manager, 'clients') and isinstance(mcp_manager.clients, dict):
                        client_ids = list(mcp_manager.clients.keys())

            # 如果没有找到，至少包含 local_default
            if not client_ids:
                client_ids = ['local_default']

            logger.info("[%s] 获取到 %d 个MCP服务: %s", self.request_id, len(client_ids), client_ids)
            return client_ids

        except Exception as e:
            logger.error("[%s] 获取MCP服务列表失败: %s", self.request_id, e)
            # 出错时返回默认服务
            return ['local_default']
    
    async def process_query(self, query: str, camera_ids: Optional[List[str]] = None,
                          mcp_list: Optional[List[str]] = None) -> AsyncGenerator[dict, None]:
        """
        处理用户查询 - 复用NlpRequestAgent的核心逻辑
        
        流程:
        1. 创建APIOutActor作为消息接收端
        2. 创建NlpRequestAgent处理请求
        3. 收集Actor输出的Instruction消息
        4. 流式返回给客户端
        
        参数:
        - camera_ids: 摄像头ID列表，为None时自动选择所有在线摄像头
        - mcp_list: MCP服务ID列表，为None时使用所有可用MCP服务
        """
        start_time = time.time()
        
        try:
            # 更新聊天历史标题
            if self._chat_history_storage.title == "":
                self._chat_history_storage.title = query[:50]
            
            # === 处理默认参数 ===
            # 1. 摄像头自动选择（为None时选择所有在线摄像头）
            if camera_ids is None:
                camera_ids = await self._get_auto_selected_cameras()
                logger.info("[%s] 摄像头自动选择结果: %s", self.request_id, camera_ids)
            
            # 2. MCP全选（为None时使用所有MCP服务）
            if mcp_list is None:
                mcp_list = await self._get_all_mcp_services()
                logger.info("[%s] MCP服务全选结果: %s", self.request_id, mcp_list)
            
            # 1. 创建APIOutActor来接收消息
            logger.info("[%s] 创建APIOutActor", self.request_id)
            self._out_actor = actor_system.createActor(
                lambda: APIOutActor(self.request_id, self.session_id)
            )
            
            # 2. 创建NlpRequestAgent
            logger.info("[%s] 创建NlpRequestAgent", self.request_id)
            self._chat_agent = actor_system.createActor(
                lambda: NlpRequestAgent(
                    self.request_id, 
                    self._out_actor,  # 消息发送到APIOutActor
                    self._chat_history_messages
                )
            )
            
            # 3. 构建Event（与Web UI发送的格式一致）
            nlp_request = Nlp.Request(
                query=query,
                camera_ids=camera_ids or [],
                mcp_list=mcp_list or []
            )
            event = Event.build_event(nlp_request, self.request_id, self.session_id)
            
            # 存储Event到历史
            self._chat_history_storage.session.add_event(event)
            
            # 4. 发送Event到NlpRequestAgent
            logger.info("[%s] 发送Event到NlpRequestAgent: %s", self.request_id, query)
            actor_system.tell(self._chat_agent, event)
            
            # 5. 从队列中读取消息并流式输出
            finished = False
            timeout_count = 0
            max_timeout = 600  # 最大等待600次0.5秒 = 300秒
            finish_message_received = False
            
            while not finished and timeout_count < max_timeout:
                try:
                    # 等待消息，设置超时
                    message = await asyncio.wait_for(
                        self.message_queue.get(),
                        timeout=0.5
                    )

                    # 重置超时计数器 - 收到任何消息都表示Agent还在运行
                    timeout_count = 0

                    # 检查是否为结束标记
                    if isinstance(message, dict) and message.get("__finish__"):
                        logger.info("[%s] 收到结束标记", self.request_id)
                        finish_message_received = True
                        finished = True
                        continue

                    # 处理消息
                    await self._process_message(message)

                    # 流式输出消息
                    yield {
                        "type": "message",
                        "data": message
                    }

                    # 检查是否完成（Dialog.Finish消息）
                    if self._is_finish_message(message):
                        finish_message_received = True
                        # 收到Finish消息后再等待一个短暂时间确保所有消息都收到
                        try:
                            while True:
                                extra_msg = await asyncio.wait_for(
                                    self.message_queue.get(),
                                    timeout=0.3
                                )
                                if isinstance(extra_msg, dict) and extra_msg.get("__finish__"):
                                    break
                                await self._process_message(extra_msg)
                                yield {
                                    "type": "message",
                                    "data": extra_msg
                                }
                        except asyncio.TimeoutError:
                            pass
                        finished = True

                except asyncio.TimeoutError:
                    timeout_count += 1
                    # 如果已经收到Finish消息，允许再等待一段时间接收剩余消息
                    if finish_message_received and timeout_count < 10:
                        continue
                    # 只有在从未收到任何消息的情况下才超时（Agent可能未启动）
                    if timeout_count > 120 and not self._full_response and not finish_message_received:
                        logger.warning("[%s] 处理超时 - 60秒内未收到任何响应", self.request_id)
                        finished = True
                        self._success = False
            
            # 6. 发送完成事件
            processing_time = time.time() - start_time
            
            yield {
                "type": "complete",
                "data": {
                    "request_id": self.request_id,
                    "session_id": self.session_id,
                    "response": self._full_response,
                    "processing_time": processing_time,
                    "success": self._success
                }
            }
            
            # 7. 保存聊天历史
            if self._need_storage_history:
                self._chat_history_storage.messages = self._chat_history_messages.to_json()
                self._chat_companion.store_chat_history(self._chat_history_storage)
            
            logger.info("[%s] 查询处理完成，耗时: %.2f秒", self.request_id, processing_time)
            
        except Exception as e:
            logger.error("[%s] 处理查询失败: %s", self.request_id, e, exc_info=True)
            yield {
                "type": "error",
                "data": {
                    "error": str(e),
                    "request_id": self.request_id
                }
            }
        finally:
            await self._cleanup()
    
    async def _process_message(self, message: dict):
        """处理消息，提取关键信息"""
        try:
            header = message.get("header", {})
            payload_str = message.get("payload", "{}")
            payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
            
            # 累积响应文本（ToastStream消息）
            if (header.get("namespace") == "Template" and 
                header.get("name") == "ToastStream"):
                stream_text = payload.get("stream", "")
                self._full_response += stream_text
                
            # 检查是否为Finish消息
            elif (header.get("namespace") == "Dialog" and 
                  header.get("name") == "Finish"):
                self._success = payload.get("success", True)
                if header.get("session_id"):
                    self.session_id = header.get("session_id")
                self._need_storage_history = True
                    
            # 提取session_id
            if not self.session_id:
                self.session_id = header.get("session_id")
                
            # 存储到聊天历史
            instruction = Instruction(
                header=Header(
                    type=header.get("type", "instruction"),
                    namespace=header.get("namespace", ""),
                    name=header.get("name", ""),
                    timestamp=header.get("timestamp", int(time.time() * 1000)),
                    request_id=header.get("request_id", self.request_id),
                    session_id=header.get("session_id", self.session_id)
                ),
                payload=payload_str
            )
            self._chat_history_storage.session.add_instruction(instruction)
                
        except Exception as e:
            logger.warning("[%s] 解析消息失败: %s", self.request_id, e)
    
    def _is_finish_message(self, message: dict) -> bool:
        """检查是否为Finish消息"""
        try:
            header = message.get("header", {})
            return (header.get("namespace") == "Dialog" and 
                    header.get("name") == "Finish")
        except Exception:
            return False
    
    async def _cleanup(self):
        """清理资源"""
        try:
            # 清理Actor
            if self._chat_agent:
                try:
                    actor_system.tell(self._chat_agent, ActorExitRequest())
                except Exception as e:
                    logger.warning("[%s] 关闭ChatAgent失败: %s", self.request_id, e)
            
            if self._out_actor:
                try:
                    actor_system.tell(self._out_actor, ActorExitRequest())
                except Exception as e:
                    logger.warning("[%s] 关闭APIOutActor失败: %s", self.request_id, e)
            
            # 清理收集器
            APIMessageCollector.remove_collector(self.request_id)
            
            # 清理chat_companion数据
            self._chat_companion.clear_chat_data(self.request_id)
            
        except Exception as e:
            logger.warning("[%s] 清理资源失败: %s", self.request_id, e)


@router.post("/chat", response_model=AIChatResponse, summary="AI对话接口（同步）")
async def ai_chat(
    request: AIChatRequest,
    current_user: str = Depends(verify_token)
):
    """
    AI对话REST接口（同步返回）
    
    功能:
    - 发送文字命令到AI对话系统，复用Web UI的处理逻辑（NlpRequestAgent）
    - 支持摄像头视觉分析（可选，默认自动选择所有在线摄像头）
    - 支持MCP服务调用（可选，默认使用所有可用MCP服务）
    - 返回完整AI处理结果
    
    示例请求（最简）:
    ```json
    {
        "message": "你好，请介绍一下你的功能"
    }
    ```
    
    示例请求（指定参数）:
    ```json
    {
        "message": "查看摄像头，告诉我看到了什么",
        "camera_ids": ["camera_001"],
        "mcp_list": ["mcp_service_1"]
    }
    ```
    
    示例响应（结构化内容）:
    ```json
    {
        "request_id": "req_xxx",
        "session_id": "session_xxx",
        "response": "<reflect>思考过程...</reflect><final_answer>最终答案...</final_answer>",
        "thinking": "思考过程...",
        "final_answer": "最终答案...",
        "executed_actions": ["ai_chat_processing"],
        "processing_time": 2.35
    }
    ```
    
    示例响应（非结构化内容）:
    ```json
    {
        "request_id": "req_xxx",
        "session_id": "session_xxx",
        "response": "简单的文本回复",
        "thinking": null,
        "final_answer": null,
        "executed_actions": ["ai_chat_processing"],
        "processing_time": 1.23
    }
    ```
    """
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    
    try:
        logger.info("[%s] AI chat request from user %s: %s", 
                   request_id, current_user, request.message)
        
        # 创建API适配器
        adapter = APIChatAdapter(
            request_id=request_id,
            session_id=request.session_id
        )
        
        # 收集完整响应
        full_response = ""
        session_id = adapter.session_id
        success = True
        
        async for event in adapter.process_query(
            query=request.message,
            camera_ids=request.camera_ids,
            mcp_list=request.mcp_list
        ):
            if event["type"] == "message":
                # 解析消息内容
                try:
                    header = event["data"].get("header", {})
                    payload_str = event["data"].get("payload", "{}")
                    payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
                    
                    if (header.get("namespace") == "Template" and 
                        header.get("name") == "ToastStream"):
                        full_response += payload.get("stream", "")
                    elif (header.get("namespace") == "Dialog" and 
                          header.get("name") == "Finish"):
                        success = payload.get("success", True)
                        session_id = header.get("session_id", session_id)
                except Exception:
                    pass
            elif event["type"] == "complete":
                session_id = event["data"].get("session_id", session_id)
            elif event["type"] == "error":
                raise HTTPException(status_code=500, 
                                  detail=event["data"].get("error", "处理失败"))
        
        processing_time = time.time() - start_time
        
        # 解析响应，提取思考过程和最终答案
        parsed_response = parse_ai_response(full_response)
        
        logger.info("[%s] AI chat completed in %.2f seconds, has_structured_format: %s", 
                   request_id, processing_time, parsed_response["has_structured_format"])
        
        return AIChatResponse(
            request_id=request_id,
            session_id=session_id,
            response=full_response,
            thinking=parsed_response["thinking"],
            final_answer=parsed_response["final_answer"],
            executed_actions=["ai_chat_processing"],
            processing_time=processing_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[%s] AI chat error: %s", request_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@router.post("/chat/stream", summary="AI对话接口（流式）")
async def ai_chat_stream(
    request: AIChatRequest,
    current_user: str = Depends(verify_token)
):
    """
    AI对话REST接口（流式输出）
    
    复用Web UI的对话系统核心逻辑（NlpRequestAgent），使用SSE实现流式输出
    
    功能:
    - 发送文字命令到AI对话系统
    - 支持摄像头视觉分析（可选，默认自动选择所有在线摄像头）
    - 支持MCP服务调用（可选，默认使用所有可用MCP服务）
    - 通过SSE流式返回AI处理结果，消息格式与Web UI完全一致
    
    示例请求（最简）:
    ```json
    {
        "message": "请介绍一下你的功能"
    }
    ```
    
    示例请求（指定参数）:
    ```json
    {
        "message": "请介绍一下你的功能",
        "camera_ids": ["camera_001"],
        "mcp_list": ["mcp_service_1"],
        "session_id": null
    }
    ```
    
    流式响应格式（SSE）:
    ```
    event: metadata
    data: {"request_id": "req_xxx", "session_id": "session_xxx", "timestamp": 1234567890}
    
    event: message
    data: {"header": {"type": "instruction", "namespace": "Template", "name": "ToastStream", ...}, "payload": "{\"stream\": \"...\"}"}
    
    event: message
    data: {"header": {...}, "payload": {...}}
    
    event: complete
    data: {
        "request_id": "req_xxx",
        "session_id": "session_xxx",
        "response": "<reflect>...</reflect><final_answer>...</final_answer>",
        "thinking": "思考过程内容",
        "final_answer": "最终答案内容",
        "processing_time": 1.23,
        "success": true
    }
    
    event: error
    data: {"error": "处理失败: 错误信息"}
    ```
    
    消息格式说明:
    - `metadata`: 请求元数据
    - `message`: 与Web UI完全一致的消息格式
      - `Template.ToastStream`: 流式文本内容
      - `Template.CallTool`: 工具调用开始
      - `Template.CallToolResult`: 工具调用结果
      - `Dialog.Exception`: 异常信息
      - `Dialog.Finish`: 对话完成
    - `complete`: 处理完成事件
    - `error`: 错误事件
    """
    return StreamingResponse(
        _stream_ai_chat_response(request, current_user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


async def _stream_ai_chat_response(
    request: AIChatRequest,
    current_user: str
) -> AsyncGenerator[str, None]:
    """生成AI对话的流式响应（SSE格式）"""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    
    try:
        logger.info("[%s] AI chat stream request from user %s: %s", 
                   request_id, current_user, request.message)
        
        # 发送元数据事件
        yield _format_sse_event("metadata", {
            "request_id": request_id,
            "timestamp": int(time.time())
        })
        
        # 创建API适配器
        adapter = APIChatAdapter(
            request_id=request_id,
            session_id=request.session_id
        )
        
        # 发送session_id（在metadata之后）
        yield _format_sse_event("metadata", {
            "request_id": request_id,
            "session_id": adapter.session_id,
            "timestamp": int(time.time())
        })
        
        # 处理查询并流式输出
        full_response = ""
        session_id = adapter.session_id
        
        async for event in adapter.process_query(
            query=request.message,
            camera_ids=request.camera_ids,
            mcp_list=request.mcp_list
        ):
            if event["type"] == "message":
                # 转发消息事件 - 与Web UI格式完全一致
                yield _format_sse_event("message", event["data"])
                
                # 累积响应文本
                try:
                    header = event["data"].get("header", {})
                    payload_str = event["data"].get("payload", "{}")
                    payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
                    
                    if (header.get("namespace") == "Template" and 
                        header.get("name") == "ToastStream"):
                        full_response += payload.get("stream", "")
                    elif (header.get("namespace") == "Dialog" and 
                          header.get("name") == "Finish"):
                        session_id = header.get("session_id", session_id)
                except Exception:
                    pass
                    
            elif event["type"] == "complete":
                # 发送完成事件
                processing_time = time.time() - start_time
                session_id = event["data"].get("session_id", session_id)
                
                # 解析响应，提取思考过程和最终答案
                parsed_response = parse_ai_response(full_response)
                
                complete_data = {
                    "request_id": request_id,
                    "session_id": session_id,
                    "response": full_response,
                    "processing_time": processing_time,
                    "success": event["data"].get("success", True)
                }
                
                # 添加解析后的字段（如果有结构化内容）
                if parsed_response["thinking"]:
                    complete_data["thinking"] = parsed_response["thinking"]
                if parsed_response["final_answer"]:
                    complete_data["final_answer"] = parsed_response["final_answer"]
                
                yield _format_sse_event("complete", complete_data)
                
                logger.info("[%s] AI chat stream completed in %.2f seconds, has_structured_format: %s", 
                           request_id, processing_time, parsed_response["has_structured_format"])
                           
            elif event["type"] == "error":
                # 发送错误事件
                yield _format_sse_event("error", {
                    "error": event["data"].get("error", "处理失败"),
                    "request_id": request_id
                })
        
    except Exception as e:
        logger.error("[%s] AI chat stream error: %s", request_id, e, exc_info=True)
        yield _format_sse_event("error", {
            "error": f"处理失败: {str(e)}",
            "request_id": request_id
        })


def _format_sse_event(event_type: str, data: dict) -> str:
    """格式化SSE事件"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ==================== Home Assistant ConversationEntity 兼容格式 ====================

class HAConversationChunk(BaseModel):
    """Home Assistant ConversationEntity 流式响应块
    
    用于 Home Assistant 插件的 async_process 方法，支持逐步产生内容
    """
    role: str = Field(default="assistant", description="消息角色 (assistant)")
    content: str = Field(..., description="当前块的内容")
    session_id: Optional[str] = Field(default=None, description="会话ID")


class HAConversationComplete(BaseModel):
    """Home Assistant ConversationEntity 完成响应"""
    done: bool = Field(default=True, description="是否完成")
    response: str = Field(..., description="完整响应内容")
    thinking: Optional[str] = Field(default=None, description="思考过程")
    final_answer: Optional[str] = Field(default=None, description="最终答案")
    session_id: str = Field(..., description="会话ID")
    request_id: str = Field(..., description="请求ID")
    processing_time: float = Field(..., description="处理耗时（秒）")
    success: bool = Field(default=True, description="是否成功")


class HAConversationError(BaseModel):
    """Home Assistant ConversationEntity 错误响应"""
    error: str = Field(..., description="错误信息")
    done: bool = Field(default=True, description="是否完成")


@router.post("/chat/stream/v2", summary="AI对话接口（HA ConversationEntity 流式格式）")
async def ai_chat_stream_ha_conversation(
    request: AIChatRequest,
    current_user: str = Depends(verify_token)
):
    """
    AI对话REST接口（Home Assistant ConversationEntity 流式格式）
    
    **专为 Home Assistant ConversationEntity 插件设计**，返回 NDJSON 格式流式响应，
    便于在 `async_process` 方法中使用异步生成器逐步消费内容。
    
    功能:
    - 发送文字命令到AI对话系统
    - 支持摄像头视觉分析（可选，默认自动选择所有在线摄像头）
    - 支持MCP服务调用（可选，默认使用所有可用MCP服务）
    - 通过 NDJSON 流式返回AI处理结果，适合 Home Assistant 插件集成
    
    示例请求:
    ```json
    {
        "message": "请介绍一下你的功能",
        "camera_ids": ["camera_001"],
        "mcp_list": ["mcp_service_1"],
        "session_id": null
    }
    ```
    
    流式响应格式（NDJSON - 每行一个JSON对象）:
    ```
    {"role": "assistant", "content": "你好", "session_id": "session_xxx"}
    {"role": "assistant", "content": "！", "session_id": "session_xxx"}
    {"role": "assistant", "content": "我是", "session_id": "session_xxx"}
    {"role": "assistant", "content": "AI助手", "session_id": "session_xxx"}
    {"done": true, "response": "你好！我是AI助手", "thinking": null, "final_answer": "你好！我是AI助手", "session_id": "session_xxx", "request_id": "req_xxx", "processing_time": 1.23, "success": true}
    ```
    
    格式说明:
    - 每行是一个独立的 JSON 对象，以换行符 `\n` 分隔
    - 普通内容块：`{"role": "assistant", "content": "...", "session_id": "..."}`
    - 完成标记：`{"done": true, "response": "...", ...}`
    - 错误响应：`{"error": "...", "done": true}`
    
    Home Assistant 插件使用示例:
    ```python
    async def async_process(self, user_input: ConversationInput) -> ConversationResult:
        # 发送请求到流式接口
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://miloco-server:8080/ai/chat/stream/v2",
                json={"message": user_input.text},
                headers={"Authorization": "Bearer xxx"}
            ) as response:
                full_response = ""
                async for line in response.content:
                    if not line:
                        continue
                    data = json.loads(line.decode().strip())
                    
                    if data.get("done"):
                        # 处理完成
                        return ConversationResult(
                            response=data.get("response", full_response),
                            conversation_id=data.get("session_id")
                        )
                    elif "error" in data:
                        # 处理错误
                        raise Exception(data["error"])
                    else:
                        # 逐步接收内容
                        full_response += data.get("content", "")
                        # 可以在这里 yield 或发送给前端
    ```
    
    适用场景:
    - Home Assistant 自定义 ConversationEntity 插件开发
    - 需要异步生成器逐步消费流式内容的场景
    - 简单、轻量级的流式响应格式
    """
    return StreamingResponse(
        _stream_ai_chat_ha_conversation(request, current_user),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


async def _stream_ai_chat_ha_conversation(
    request: AIChatRequest,
    current_user: str
) -> AsyncGenerator[str, None]:
    """生成AI对话的流式响应（Home Assistant ConversationEntity NDJSON格式）"""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    
    try:
        logger.info("[%s] HA Conversation stream request from user %s: %s", 
                   request_id, current_user, request.message)
        
        # 创建API适配器
        adapter = APIChatAdapter(
            request_id=request_id,
            session_id=request.session_id
        )
        
        # 处理查询并流式输出
        full_response = ""
        session_id = adapter.session_id
        
        async for event in adapter.process_query(
            query=request.message,
            camera_ids=request.camera_ids,
            mcp_list=request.mcp_list
        ):
            if event["type"] == "message":
                # 解析消息内容
                try:
                    header = event["data"].get("header", {})
                    payload_str = event["data"].get("payload", "{}")
                    payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
                    
                    if (header.get("namespace") == "Template" and 
                        header.get("name") == "ToastStream"):
                        # 流式文本内容 - 使用 NDJSON 格式输出
                        chunk = payload.get("stream", "")
                        if chunk:
                            full_response += chunk
                            chunk_data = HAConversationChunk(
                                role="assistant",
                                content=chunk,
                                session_id=header.get("session_id", session_id)
                            )
                            yield json.dumps(chunk_data.model_dump(), ensure_ascii=False) + "\n"
                            
                    elif (header.get("namespace") == "Dialog" and 
                          header.get("name") == "Finish"):
                        session_id = header.get("session_id", session_id)
                        
                except Exception as e:
                    logger.warning("[%s] 解析消息失败: %s", request_id, e)
                    
            elif event["type"] == "complete":
                # 发送完成事件
                processing_time = time.time() - start_time
                session_id = event["data"].get("session_id", session_id)
                success = event["data"].get("success", True)
                
                # 解析响应，提取思考过程和最终答案
                parsed_response = parse_ai_response(full_response)
                
                complete_data = HAConversationComplete(
                    done=True,
                    response=full_response,
                    thinking=parsed_response.get("thinking"),
                    final_answer=parsed_response.get("final_answer"),
                    session_id=session_id,
                    request_id=request_id,
                    processing_time=processing_time,
                    success=success
                )
                
                yield json.dumps(complete_data.model_dump(), ensure_ascii=False) + "\n"
                
                logger.info("[%s] HA Conversation stream completed in %.2f seconds", 
                           request_id, processing_time)
                           
            elif event["type"] == "error":
                # 发送错误事件
                error_data = HAConversationError(
                    error=event["data"].get("error", "处理失败"),
                    done=True
                )
                yield json.dumps(error_data.model_dump(), ensure_ascii=False) + "\n"
        
    except Exception as e:
        logger.error("[%s] HA Conversation stream error: %s", request_id, e, exc_info=True)
        error_data = HAConversationError(
            error=f"处理失败: {str(e)}",
            done=True
        )
        yield json.dumps(error_data.model_dump(), ensure_ascii=False) + "\n"
