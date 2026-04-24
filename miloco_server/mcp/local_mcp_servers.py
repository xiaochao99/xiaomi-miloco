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
                "获取当前时间的工具。适用于用户问“现在几点了”、“当前时间”、“今天几号”等请求。"
                "可以选择指定时区，如 Asia/Shanghai（上海）、UTC 等。"
                "Tool for getting current time. Use this when user asks about current time or date."
                "Optional timezone parameter, e.g., Asia/Shanghai, UTC."
            ),
        )
        self.mcp.add_tool(tool=current_time_tool)

        # Register cached HA state query tools
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
        # Check if device cache manager is available
        if not self._manager.device_cache_manager or not self._manager.device_cache_manager.is_started:
            logger.warning("Device cache manager not available, skipping cached HA tools registration")
            return

        try:
            # 1. Fast device state query
            cached_get_state_tool = Tool.from_function(
                fn=self.cached_get_device_state,
                name="cached_get_device_state",
                description="""
【高速缓存版】获取 Home Assistant 设备的当前状态。响应速度极快（通常<10ms）。

Args:
    entity_id: 设备实体ID，如 "sensor.living_room_temperature", "light.bedroom_main"

Returns:
    设备状态信息，包含 state, attributes, last_updated, data_source 等

Examples:
    - 查询客厅温度: entity_id="sensor.living_room_temperature"
    - 查询卧室主灯: entity_id="light.bedroom_main"
    - 查询空调状态: entity_id="climate.living_room"

Note:
    - 数据来自本地内存缓存，响应速度极快（<10ms）
    - 数据通过 WebSocket 实时同步，保证新鲜度
    - 如果缓存数据过期，会自动触发后台更新

何时使用：
    - 需要快速响应的场景（如语音交互）
    - 频繁查询同一设备
    - 批量查询多个设备

对比普通查询：
    - 普通 REST API 查询: 150-300ms
    - 此缓存查询: <10ms（快 15-30 倍）
                """
            )
            self.mcp.add_tool(tool=cached_get_state_tool)

            # 2. Room environment query
            cached_get_room_env_tool = Tool.from_function(
                fn=self.cached_get_room_environment,
                name="cached_get_room_environment",
                description="""
【高速缓存版】获取指定房间的环境综合数据。

Args:
    room: 房间名称，如 "living_room", "bedroom", "kitchen", "客厅", "卧室"

Returns:
    房间内所有环境传感器的数据，包括：
    - 温度 (temperature)
    - 湿度 (humidity)
    - PM2.5 (pm25)
    - CO2 (co2)
    - 光照 (illuminance)
    - 空调/温控器状态

Examples:
    - 查询客厅环境: room="living_room" 或 room="客厅"
    - 查询卧室环境: room="bedroom" 或 room="卧室"
    - 查询厨房环境: room="kitchen" 或 room="厨房"

Note:
    一次性返回房间内所有环境相关设备的状态，适合询问"客厅环境怎么样"这类问题。
    响应速度极快（<10ms），因为数据来自本地缓存。
                """
            )
            self.mcp.add_tool(tool=cached_get_room_env_tool)

            # 3. Search devices
            cached_search_tool = Tool.from_function(
                fn=self.cached_search_devices,
                name="cached_search_devices",
                description="""
【高速缓存版】根据关键词搜索 Home Assistant 设备。

Args:
    keyword: 搜索关键词，可以匹配实体ID或友好名称

Returns:
    匹配的设备列表，包含 entity_id, state, friendly_name

Examples:
    - 搜索温度相关设备: keyword="temperature"
    - 搜索客厅设备: keyword="living_room"
    - 搜索卧室设备: keyword="bedroom"
    - 搜索灯光: keyword="light"

Note:
    当不确定设备确切ID时，先用此工具搜索。
    搜索在本地缓存中进行，响应速度极快。
                """
            )
            self.mcp.add_tool(tool=cached_search_tool)

            # 4. Batch query
            cached_batch_tool = Tool.from_function(
                fn=self.cached_get_multiple_states,
                name="cached_get_multiple_states",
                description="""
【高速缓存版】批量获取多个设备的状态。

Args:
    entity_ids: 设备实体ID列表，如 ["sensor.temp_1", "light.main"]

Returns:
    所有设备的状态信息

Note:
    适合需要同时查询多个设备的场景，比多次单查更高效。
    所有查询都在本地缓存中完成，响应速度极快。
                """
            )
            self.mcp.add_tool(tool=cached_batch_tool)

            # 5. Get cache stats
            cache_stats_tool = Tool.from_function(
                fn=self.get_cache_stats,
                name="get_ha_cache_stats",
                description="""
获取 Home Assistant 设备状态缓存的统计信息。

Returns:
    缓存统计信息，包括：
    - total_cached: 缓存的设备数量
    - cache_hits: 缓存命中次数
    - cache_misses: 缓存未命中次数
    - hit_rate: 缓存命中率
    - avg_response_time_ms: 平均响应时间（毫秒）
    - hot_entities: 热点设备列表

Note:
    用于监控缓存性能和调试。
                """
            )
            self.mcp.add_tool(tool=cache_stats_tool)

            logger.info("Successfully registered %d cached HA state query tools", 5)

        except Exception as e:
            logger.error("Failed to register cached HA tools: %s", e)

    async def cached_get_device_state(
        self,
        entity_id: Annotated[str, "设备实体ID，如 sensor.living_room_temperature"]
    ) -> dict[str, Any]:
        """Get device state from HaStateListener cache (fast, <10ms)"""
        try:
            cache_manager = self._manager.device_cache_manager
            if not cache_manager or not cache_manager.is_started:
                return {"error": "Device cache not available", "entity_id": entity_id}

            # Direct sync call to HaStateListener cache (extremely fast)
            state = cache_manager.get_state(entity_id)
            if state is None:
                return {"error": "Entity not found in cache", "entity_id": entity_id}

            return {
                "entity_id": entity_id,
                "state": state.get("state"),
                "attributes": state.get("attributes", {}),
                "last_updated": state.get("last_updated"),
                "last_changed": state.get("last_changed"),
                "data_source": "cache",
                "context": state.get("context")
            }
        except Exception as e:
            logger.error("Error in cached_get_device_state: %s", e)
            return {"error": str(e), "entity_id": entity_id}

    async def cached_get_room_environment(
        self,
        room: Annotated[str, "房间名称，如 living_room, bedroom"]
    ) -> dict[str, Any]:
        """Get room environment from cache (fast)"""
        try:
            cache_manager = self._manager.device_cache_manager
            if not cache_manager or not cache_manager.is_started:
                return {"error": "Device cache not available", "room": room}

            # Get all states and filter by room
            all_states = cache_manager.get_all_states()
            room_lower = room.lower().replace(" ", "_")

            results = {}
            for entity_id, state in all_states.items():
                # Match by room name in entity_id
                if room_lower in entity_id.lower():
                    friendly_name = state.get("attributes", {}).get("friendly_name", entity_id)
                    results[entity_id] = {
                        "state": state.get("state"),
                        "friendly_name": friendly_name,
                        "unit": state.get("attributes", {}).get("unit_of_measurement", ""),
                        "last_updated": state.get("last_updated")
                    }

            return {
                "room": room,
                "devices": results,
                "device_count": len(results),
                "data_source": "cache"
            }
        except Exception as e:
            logger.error("Error in cached_get_room_environment: %s", e)
            return {"error": str(e), "room": room}

    async def cached_search_devices(
        self,
        keyword: Annotated[str, "搜索关键词"]
    ) -> list[dict[str, Any]]:
        """Search devices from cache (fast)"""
        try:
            cache_manager = self._manager.device_cache_manager
            if not cache_manager or not cache_manager.is_started:
                return []

            all_states = cache_manager.get_all_states()
            keyword_lower = keyword.lower()
            matches = []

            for entity_id, state in all_states.items():
                friendly_name = state.get("attributes", {}).get("friendly_name", "")
                if keyword_lower in entity_id.lower() or keyword_lower in friendly_name.lower():
                    matches.append({
                        "entity_id": entity_id,
                        "state": state.get("state"),
                        "friendly_name": friendly_name,
                        "domain": entity_id.split(".")[0] if "." in entity_id else "unknown"
                    })

            return matches
        except Exception as e:
            logger.error("Error in cached_search_devices: %s", e)
            return []

    async def cached_get_multiple_states(
        self,
        entity_ids: Annotated[list[str], "设备实体ID列表"]
    ) -> dict[str, Any]:
        """Get multiple device states from cache (fast)"""
        try:
            cache_manager = self._manager.device_cache_manager
            if not cache_manager or not cache_manager.is_started:
                return {"error": "Device cache not available", "entity_ids": entity_ids}

            results = {}
            for eid in entity_ids:
                state = cache_manager.get_state(eid)
                if state:
                    results[eid] = {
                        "state": state.get("state"),
                        "attributes": state.get("attributes", {}),
                        "last_updated": state.get("last_updated"),
                        "data_source": "cache"
                    }
                else:
                    results[eid] = {"error": "Not found in cache"}

            return {
                "results": results,
                "total": len(entity_ids),
                "successful": sum(1 for r in results.values() if "error" not in r)
            }
        except Exception as e:
            logger.error("Error in cached_get_multiple_states: %s", e)
            return {"error": str(e), "entity_ids": entity_ids}

    async def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics"""
        try:
            cache_manager = self._manager.device_cache_manager
            if not cache_manager:
                return {"status": "not_initialized"}

            return cache_manager.get_stats()
        except Exception as e:
            logger.error("Error in get_cache_stats: %s", e)
            return {"error": str(e)}


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
