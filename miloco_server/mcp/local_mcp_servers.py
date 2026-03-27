# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Local MCP server implementation
Uses Tool.from_function() to automatically generate parameter definitions, more concise and elegant
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Annotated

import numpy as np
from fastmcp import FastMCP
from fastmcp.tools import Tool
from miloco_server import actor_system
from miloco_server.detection.face_detector import FaceDetectionConfig, FaceDetector
from miloco_server.face_recognition.face_library_service import FaceLibraryService
from miloco_server.schema.mcp_schema import LocalMcpClientId
from miloco_server.utils.chat_companion import ChatCachedData
from miloco_server.utils.llm_utils.device_chooser import DeviceChooser
from miloco_server.tools.rule_create_tool import RuleCreateMessage, RuleCreateTool
from miloco_server.tools.vision_chat_tool import VisionChatTool, VisionUnderstandStart
from thespian.actors import ActorExitRequest

logger = logging.getLogger(__name__)


class LocalMCPBase:
    """Base class for local MCP servers"""

    def __init__(self, name: str, instructions: str = None):
        from miloco_server.service.manager import get_manager # pylint: disable=import-outside-toplevel
        self.name = name
        self.instructions = instructions or f"Local tool server: {name}"
        self.mcp: FastMCP = None
        self._initialized = False
        self._manager = get_manager()

    async def init_async(self):
        """Asynchronously initialize MCP server"""
        if self._initialized:
            return

        self.mcp = FastMCP(
            name=self.name,
            instructions=self.instructions,
            on_duplicate="error",
            mask_error_details=True,
        )

        # Register tools
        await self._register_tools()
        self._initialized = True
        logger.info("Local MCP server %s initialization completed", self.name)

    async def _register_tools(self):
        """Register tools to MCP server"""
        raise NotImplementedError("Subclass must implement _register_tools method")

    @property
    def mcp_instance(self) -> FastMCP:
        """Get MCP instance"""
        if not self._initialized:
            raise RuntimeError("MCP server not initialized, please call init_async() first")
        return self.mcp


class LocalDefaultMcp(LocalMCPBase):
    """Local default MCP server - includes rule creation and vision understanding tools"""

    def __init__(self):
        super().__init__(
            name="本地默认工具 (Local Default Tools)",
            instructions="Provides core tools for rule creation, vision understanding, etc."
        )

    async def _register_tools(self):
        """Register all default tools"""
        rule_tool = Tool.from_function(
            fn=self.create_rule,
            name="create_rule",
            description="""
用于创建规则的工具 / Tool for creating rules, used when users want to create a rule through this tool.
典型的解决问题为"当XXX时，执行YYY" / Typical problem solving is "when XXX, execute YYY". Examples:
1. "当XXX时，执行YYY和ZZZZ" / "When XXX, execute YYY and ZZZZ".
2. "当客厅的有人移动时，执行开灯场景" / "When someone moves in the living room, execute the turn on light scene".
3. "当卧室有人摔倒时，执行通知场景" / "When someone falls in the bedroom, execute the notification scene".
4. "当有人坐在沙发上时，执行开灯和打开电视机场景" / "When someone sits on the sofa, execute the turn on light and turn on TV scene".
注意：用户可能拒绝保存规则，此时无需再次尝试保存规则。 / Note: The user may refuse to save the rule, in this case, do not try to save the rule again.
"""
        )
        self.mcp.add_tool(tool=rule_tool)

        vision_tool = Tool.from_function(
            fn=self.vision_understand,
            name="vision_understand",
            description="Tool for understanding images, used when users want to understand the home cameras displayed.")
        self.mcp.add_tool(tool=vision_tool)

        who_am_i_tool = Tool.from_function(
            fn=self.who_am_i,
            name="who_am_i",
            description=(
                "用于识别人脸身份的工具。适用于用户问“我是谁/看看我是谁/你认识我吗”等请求。"
                "工具会从摄像头截图中检测人脸，并与人脸库做1:N比对。"
            ),
        )
        self.mcp.add_tool(tool=who_am_i_tool)

    async def create_rule(
        self,
        request_id: Annotated[str, "request_id"],
        name: Annotated[str, "Description of the rule to be created, concise and natural, format: xx rule, 4-6 chars"],
        condition: Annotated[str, "Condition, such as 'when XXX'"],
        actions: Annotated[list[str], "Actions, such as 'execute YYY and ZZZ', action descriptions should be concise and natural, real user descriptions (no excessive thinking), if it is 'execute YYY and ZZZ', then pass [YYY,ZZZ]"],  # pylint: disable=line-too-long
        location: Annotated[Optional[str], "Location, such as 'living room', empty if no specific location is described"] = None,  # pylint: disable=line-too-long
        notify: Annotated[Optional[str], "Notification content, such as 'someone fell', can be empty"] = None
    ) -> dict[str, Any]:
        """Create rule"""
        chat_data: ChatCachedData | None = self._manager.chat_companion.get_chat_data(request_id)
        if chat_data is None:
            return "error: request_id not found"

        if chat_data.out_actor_address is None:
            return "error: transver_actor_address not found"

        rule_create_tool = actor_system.createActor(
            lambda: RuleCreateTool(
                request_id=request_id,
                out_actor_address=chat_data.out_actor_address,
                camera_ids=chat_data.camera_ids,
                mcp_ids=chat_data.mcp_ids,
            ))

        logger.info("RuleTool: create rule: %s, %s, %s, %s, %s", name, condition, actions, location, notify)
        future: asyncio.Future = actor_system.ask(
            rule_create_tool, RuleCreateMessage(
                name, condition, actions, location, notify), timeout=5)
        timeout = 600
        try:
            response = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as exc:
            logger.error("RuleTool: create rule timeout after %d seconds, error: %s", timeout, str(exc), exc_info=True)
            return {"error": f"RuleTool: create rule timeout after {timeout} seconds, error: {str(exc)}"}


        actor_system.tell(rule_create_tool, ActorExitRequest())
        logger.info("RuleTool: create rule response: %s", response)
        return response

    async def vision_understand(
        self,
        request_id: Annotated[str, "Request ID"],
        query: Annotated[str, "Query content, such as 'what is my cat doing'"],
        location: Annotated[Optional[str], "Location, such as 'living room', empty if no specific location is described"] = None  # pylint: disable=line-too-long
    ) -> dict[str, Any]:
        """Understand image"""
        chat_data: ChatCachedData | None = self._manager.chat_companion.get_chat_data(request_id)
        if chat_data is None:
            return "error: request_id not found"

        if chat_data.out_actor_address is None:
            return "error: transver_actor_address not found"

        camera_ids = chat_data.camera_ids

        vision_chat_tool = actor_system.createActor(lambda: VisionChatTool(
            request_id=request_id,
            query=query,
            out_actor_address=chat_data.out_actor_address,
            location_info=location,
            user_choosed_camera_dids=camera_ids,
            camera_images=chat_data.camera_images,
        ))

        future: asyncio.Future = actor_system.ask(vision_chat_tool,
                                                  VisionUnderstandStart(),
                                                  timeout=5)
        timeout = 600
        try:
            response = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as exc:
            logger.error("VisionUnderstandTool: vision understand timeout after %d seconds, error: %s", timeout, str(exc), exc_info=True)
            return {"error": f"VisionUnderstandTool: vision understand timeout after {timeout} seconds, error: {str(exc)}"}

        actor_system.tell(vision_chat_tool, ActorExitRequest())
        logger.info("VisionUnderstandTool: vision understand response: %s", response)
        return response

    async def who_am_i(
        self,
        request_id: Annotated[str, "Request ID"],
        location: Annotated[Optional[str], "可选，房间位置，比如 living room / 客厅"] = None,
        accept_threshold: Annotated[float, "人脸匹配阈值，默认0.35，越高越严格"] = 0.35,
    ) -> dict[str, Any]:
        """Detect face from camera snapshot and identify user from face library."""
        chat_data: ChatCachedData | None = self._manager.chat_companion.get_chat_data(request_id)
        if chat_data is None:
            return {"success": False, "message": "request_id not found"}

        choose_camera_ids = chat_data.camera_ids or []
        camera_img_seqs = chat_data.camera_images

        if not camera_img_seqs:
            device_chooser = DeviceChooser(
                request_id=request_id,
                location=location,
                choose_camera_device_ids=choose_camera_ids,
            )
            camera_list, all_cameras, _, _ = await device_chooser.run()
            if len(camera_list) == 0:
                camera_list = all_cameras

            camera_dids = [camera.did for camera in camera_list]
            if not camera_dids:
                return {
                    "success": False,
                    "recognized": False,
                    "reason_code": "no_available_camera",
                    "message": (
                        "当前没有可用摄像头，无法进行“我是谁”识别。"
                        "请先在设备页确认已接入并在线至少一个摄像头。"
                    ),
                }

            camera_img_seqs = await self._manager.miot_service.get_miot_cameras_img(camera_dids, 1)

        total_count = len(camera_img_seqs or [])
        online_count = len([seq for seq in (camera_img_seqs or []) if seq.camera_info.online])
        camera_img_seqs = [
            seq for seq in (camera_img_seqs or [])
            if seq.camera_info.online and len(seq.img_list) > 0
        ]
        if len(camera_img_seqs) == 0:
            if total_count == 0:
                return {
                    "success": False,
                    "recognized": False,
                    "reason_code": "no_camera_snapshot",
                    "message": (
                        "当前无法获取摄像头截图，暂时不能识别你是谁。"
                        "请检查摄像头网络连接后重试。"
                    ),
                }
            if online_count == 0:
                return {
                    "success": False,
                    "recognized": False,
                    "reason_code": "camera_offline",
                    "message": (
                        "检测到摄像头均不在线，无法进行人脸识别。"
                        "请先让摄像头上线后再试。"
                    ),
                }
            return {
                "success": False,
                "recognized": False,
                "reason_code": "empty_camera_frames",
                "message": (
                    "摄像头在线但未获取到有效画面，无法进行人脸识别。"
                    "请稍后重试或调整摄像头。"
                ),
            }

        from miloco_server.detection.detection_service import get_detection_service  # pylint: disable=import-outside-toplevel
        detection_service = await get_detection_service()
        face_detector = getattr(detection_service, "_face_detector", None)
        if not face_detector or not face_detector.is_initialized():
            return {
                "success": False,
                "recognized": False,
                "reason_code": "face_service_unavailable",
                "message": (
                    "人脸识别服务不可用：未连接到 ai_engine 的 /face/analyze。"
                    "请先启动 ai_engine（确保 /face/health/face/analyze 可用）。"
                ),
            }

        face_library = FaceLibraryService()

        for seq in camera_img_seqs:
            camera_name = seq.camera_info.name or seq.camera_info.did
            for img in seq.img_list:
                faces = face_detector.analyze(img.data, with_embedding=True)
                if not faces:
                    continue

                best = max(faces, key=lambda f: f.det_score)
                if best.embedding is None or best.embedding.size == 0:
                    continue

                matches = face_library.search(
                    query_embedding=np.asarray(best.embedding, dtype=np.float32),
                    top_k=1,
                    accept_threshold=accept_threshold,
                )
                if matches:
                    m = matches[0]
                    return {
                        "success": True,
                        "recognized": True,
                        "name": m.name,
                        "score": round(float(m.score), 4),
                        "camera_name": camera_name,
                        "message": f"识别到你可能是 {m.name}",
                    }
                return {
                    "success": True,
                    "recognized": False,
                    "camera_name": camera_name,
                    "message": "看到了人脸，但我不认识你",
                }

        return {
            "success": True,
            "recognized": False,
            "message": "当前截图中没有检测到清晰人脸",
        }


class LocalMCPServerFactory:
    """Local MCP server factory"""

    @staticmethod
    async def create_all_servers() -> Dict[str, LocalMCPBase]:
        """Create all local MCP servers"""
        servers = {}

        try:
            default_server = LocalDefaultMcp()
            await default_server.init_async()
            servers[LocalMcpClientId.LOCAL_DEFAULT] = default_server

            logger.info("Successfully created %d local MCP servers", len(servers))

        except Exception as e:
            logger.error("Failed to create local MCP servers: %s", e)
            raise

        return servers
