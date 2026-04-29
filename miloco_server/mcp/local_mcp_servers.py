# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Local MCP server implementation
Uses Tool.from_function() to automatically generate parameter definitions, more concise and elegant
"""

import asyncio
import logging
from datetime import datetime
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


def get_current_time(
    timezone: Annotated[Optional[str], "时区，如 'Asia/Shanghai'、'UTC'，默认使用系统时区"] = None
) -> dict[str, Any]:
    """
    获取当前时间的工具函数。
    Tool function to get current time.
    """
    try:
        from zoneinfo import ZoneInfo
        
        if timezone:
            try:
                tz = ZoneInfo(timezone)
                now = datetime.now(tz)
            except ValueError:
                return {"success": False, "error": f"Unknown timezone: {timezone}"}
        else:
            now = datetime.now()

        result = {
            "success": True,
            "datetime": now.isoformat(),
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "hour": now.hour,
            "minute": now.minute,
            "second": now.second,
            "weekday": now.isoweekday(),
            "weekday_name": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.isoweekday() - 1],
            "timezone": timezone or "system",
            "formatted": now.strftime("%Y年%m月%d日 %H:%M:%S"),
            "formatted_en": now.strftime("%Y-%m-%d %H:%M:%S")
        }
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


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
            description=(
                "摄像头画面理解工具。当用户询问家中摄像头画面内容时使用此工具。"
                "此工具会返回对画面的完整描述，你可以直接将返回内容作为最终答案输出。"
                "每个问题只需调用一次此工具，收到结果后不要再重复调用，"
                "请直接基于返回内容整理后输出 <final_answer>。"
                "Tool for understanding camera images. Returns a complete description of the scene."
                "Use the returned content directly as your final answer. "
                "Only call this tool ONCE per query - do NOT call it again after receiving the result."
            ))
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

        current_time_tool = Tool.from_function(
            fn=get_current_time,
            name="get_current_time",
            description=(
                '获取当前时间的工具。适用于用户问"现在几点了"、"当前时间"、"今天几号"等请求。'
                "可以选择指定时区，如 Asia/Shanghai（上海）、UTC 等。"
                "Tool for getting current time. Use this when user asks about current time or date."
                "Optional timezone parameter, e.g., Asia/Shanghai, UTC."
            ),
        )
        self.mcp.add_tool(tool=current_time_tool)

        env_context_tool = Tool.from_function(
            fn=self.get_environment_context,
            name="get_environment_context",
            description=(
                '【最高优先级】获取当前家庭环境上下文数据，包括：室内温度、室外温度、湿度、光照强度、'
                '是否有人在家、是否有人在场、天气状况、室外温度、风速、空气质量、当前时段。'
                '当用户询问与环境相关的问题（如"家里多少度"、"外面冷不冷"、"家里有人吗"、'
                '"今天天气怎么样"、"空气质量如何"等）时，优先使用此工具获取实时环境数据。'
                "此工具返回的数据可直接用于回答用户关于家庭环境的问题，"
                "也可用于判断是否需要自动控制设备（如温度过高开空调、没人在家关灯等）。"
                "【Highest Priority】Get current home environment context including: indoor/outdoor temperature, "
                "humidity, light level, presence detection, weather, wind speed, air quality, time period. "
                "Use this tool FIRST when users ask about home environment or when deciding whether "
                "to auto-control devices based on environmental conditions."
            ),
        )
        self.mcp.add_tool(tool=env_context_tool)

        await self._register_cached_ha_tools()

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
        if location is not None and location.lower() in ("none", "null", ""):
            location = None
        if notify is not None and notify.lower() in ("none", "null", ""):
            notify = None
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
        if location is not None and location.lower() in ("none", "null", ""):
            location = None
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
        if location is not None and location.lower() in ("none", "null", ""):
            location = None
        chat_data: ChatCachedData | None = self._manager.chat_companion.get_chat_data(request_id)
        if chat_data is None:
            return {"success": False, "message": "request_id not found"}

        choose_camera_ids = chat_data.camera_ids or []
        camera_img_seqs = chat_data.camera_images

        if not camera_img_seqs:
            camera_dids = choose_camera_ids
            if not camera_dids:
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

    async def _register_cached_ha_tools(self):
        """Register cached Home Assistant state query tools"""
        logger.info("Cached HA tools registration skipped (disabled)")
        return

    async def get_environment_context(self) -> dict[str, Any]:
        """获取当前家庭环境上下文数据"""
        try:
            from miloco_server.service.context_provider import ContextProvider
            provider = ContextProvider.get_instance()
            if not provider:
                return {
                    "success": False,
                    "error": "环境上下文服务未初始化",
                }
            ctx = provider.get_context()
            return {
                "success": True,
                "indoor_temperature": ctx.temperature,
                "outdoor_temperature": ctx.weather_temperature,
                "humidity": ctx.humidity,
                "light_level": ctx.light_level,
                "is_home": ctx.is_home,
                "is_anyone_present": ctx.is_anyone_present,
                "weather": ctx.weather,
                "wind_speed": ctx.wind_speed,
                "air_quality": ctx.air_quality,
                "time_period": ctx.time_period,
            }
        except Exception as e:
            logger.error("get_environment_context failed: %s", e)
            return {"success": False, "error": str(e)}

    # Cached tool methods removed to prevent unnecessary calls
    # All cached_get_* methods have been disabled


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
