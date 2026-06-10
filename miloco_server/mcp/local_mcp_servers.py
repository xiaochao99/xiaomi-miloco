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
                "⚠️ 注意：仅在用户明确要求查看摄像头画面时使用。"
                "用户告知个人信息（如车牌号、地址、电话号码等）时不应调用此工具。"
                "Tool for understanding camera images. Returns a complete description of the scene."
                "Use the returned content directly as your final answer. "
                "Only call this tool ONCE per query - do NOT call it again after receiving the result. "
                "⚠️ Only use when the user explicitly asks about camera footage. "
                "Do NOT call this tool when the user is sharing personal information."
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

        env_context_tool = Tool.from_function(
            fn=self.get_environment_context,
            name="get_environment_context",
            description=(
                '获取当前家庭环境上下文数据（实时刷新），包括：室内温度、室外温度、湿度、光照强度、'
                '是否有人在家、是否有人在场、天气状况、风速、空气质量、当前时段、水浸检测状态、限行状态。'
                '注意：系统提示中已嵌入环境数据快照，仅在以下情况才需要调用此工具：'
                '1) 用户明确要求获取最新/实时数据；'
                '2) 距离上次数据已有较长时间需要刷新；'
                '3) 需要基于最新环境数据控制设备。'
                '每个对话轮次最多调用1次，不要重复调用。'
                "Get current home environment context (real-time refresh). "
                "Note: Environment data is already embedded in the system prompt. "
                "Only call this tool when you need to REFRESH the data (e.g., user explicitly asks for latest). "
                "Do NOT call this tool more than once per turn."
            ),
        )
        self.mcp.add_tool(tool=env_context_tool)

        # Register music control tools
        await self._register_music_tools()

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

    async def _register_music_tools(self):
        """Register music control tools"""
        try:
            from miloco_server.service.music_service import get_music_service
            music_service = get_music_service()
            if not music_service:
                logger.warning("Music service not available, skipping music tools registration")
                return

            # Music control tool
            music_control_tool = Tool.from_function(
                fn=self.music_control,
                name="music_control",
                description=(
                    "音乐播放控制工具。支持播放、暂停、停止、上一首、下一首、音量调节、静音、循环模式、随机播放等操作。"
                    "Music playback control tool. Supports play, pause, stop, next, previous, volume, mute, repeat mode, shuffle, etc."
                ),
            )
            self.mcp.add_tool(tool=music_control_tool)

            # Search music tool
            search_music_tool = Tool.from_function(
                fn=self.search_music,
                name="search_music",
                description=(
                    "搜索音乐工具。根据关键词搜索歌曲，支持按歌名、歌手、专辑搜索。"
                    "Search music tool. Search songs by keyword, supports search by title, artist, album."
                ),
            )
            self.mcp.add_tool(tool=search_music_tool)

            # Get playback status tool
            get_playback_status_tool = Tool.from_function(
                fn=self.get_playback_status,
                name="get_playback_status",
                description=(
                    "获取当前音乐播放状态，包括当前歌曲、播放状态、进度、音量等信息。"
                    "Get current music playback status, including current song, playback state, progress, volume, etc."
                ),
            )
            self.mcp.add_tool(tool=get_playback_status_tool)

            # Discover DLNA devices tool
            discover_dlna_tool = Tool.from_function(
                fn=self.discover_dlna_devices,
                name="discover_dlna_devices",
                description=(
                    "发现局域网内的DLNA音箱设备。用于查找可投屏的智能音箱。"
                    "Discover DLNA speaker devices in the local network. Used to find castable smart speakers."
                ),
            )
            self.mcp.add_tool(tool=discover_dlna_tool)

            # Cast to DLNA device tool
            cast_to_dlna_tool = Tool.from_function(
                fn=self.cast_to_dlna,
                name="cast_to_dlna",
                description=(
                    "将音乐投屏到DLNA音箱设备播放。需要先使用discover_dlna_devices发现设备。"
                    "Cast music to DLNA speaker device for playback. Use discover_dlna_devices first to find devices."
                ),
            )
            self.mcp.add_tool(tool=cast_to_dlna_tool)

            # Search and play online music tool
            search_online_tool = Tool.from_function(
                fn=self.search_and_play_online_music,
                name="search_and_play_online_music",
                description=(
                    "搜索在线音乐并添加到播放列表。支持网易云、QQ音乐、咪咕音乐等音源。"
                    "可以用自然语言描述想听的歌，如'播放周杰伦的晴天'、'我想听薛之谦的歌'。"
                    "Search online music and add to playlist. Supports NetEase, QQ Music, Migu, etc. "
                    "Use natural language like 'play Jay Chou's Sunny Day'."
                ),
            )
            self.mcp.add_tool(tool=search_online_tool)

            # Smart play tool - search by name and play
            smart_play_tool = Tool.from_function(
                fn=self.smart_play_music,
                name="smart_play_music",
                description=(
                    "智能播放音乐。根据歌名或歌手名搜索并直接播放第一首结果。"
                    "例如：'播放晴天'、'放一首周杰伦的歌'、'来点轻音乐'。"
                    "Smart play music. Search by song/artist name and play the first result. "
                    "E.g.: 'play Sunny Day', 'play a song by Jay Chou'."
                ),
            )
            self.mcp.add_tool(tool=smart_play_tool)

            # Scan local music tool
            scan_local_tool = Tool.from_function(
                fn=self.scan_local_music,
                name="scan_local_music",
                description=(
                    "扫描本地目录的音乐文件。指定目录路径，自动扫描并添加到播放列表。"
                    "例如：'扫描D盘Music目录的音乐'、'扫描/home/user/music'。"
                    "Scan local directory for music files. Specify directory path to scan and add to playlist."
                ),
            )
            self.mcp.add_tool(tool=scan_local_tool)

            # List DLNA devices tool
            list_dlna_tool = Tool.from_function(
                fn=self.list_dlna_devices,
                name="list_dlna_devices",
                description=(
                    "列出已发现的DLNA音箱设备。用于查看当前可用的投屏设备。"
                    "List discovered DLNA speaker devices. Used to see available cast devices."
                ),
            )
            self.mcp.add_tool(tool=list_dlna_tool)

            logger.info("Music control tools registered successfully")
        except Exception as e:
            logger.warning("Failed to register music tools: %s", e)

    async def music_control(
        self,
        action: Annotated[str, "播放控制动作: play(播放), pause(暂停), stop(停止), next(下一首), previous(上一首), set_volume(设置音量), toggle_mute(切换静音), set_repeat(设置循环模式), toggle_shuffle(切换随机播放), play_song(播放指定歌曲), play_playlist(播放指定播放列表)"],
        song_id: Annotated[Optional[str], "歌曲ID，当action为play_song时使用"] = None,
        playlist_id: Annotated[Optional[str], "播放列表ID，当action为play_playlist时使用"] = None,
        volume: Annotated[Optional[float], "音量值(0.0-1.0)，当action为set_volume时使用"] = None,
        position: Annotated[Optional[float], "播放位置(秒)，当action为seek时使用"] = None,
        repeat_mode: Annotated[Optional[str], "循环模式: off(关闭), one(单曲循环), all(列表循环)，当action为set_repeat时使用"] = None,
    ) -> dict[str, Any]:
        """控制音乐播放 - 通过命令队列发送到前端播放器执行"""
        try:
            from miloco_server.service.music_service import get_music_service
            music_service = get_music_service()
            if not music_service:
                return {"success": False, "error": "Music service not available"}

            # Validate action
            valid_actions = ["play", "pause", "stop", "next", "previous", "set_volume",
                             "toggle_mute", "set_repeat", "toggle_shuffle", "play_song",
                             "play_playlist", "seek", "toggle"]
            if action not in valid_actions:
                return {"success": False, "error": f"Unknown action: {action}. Valid: {', '.join(valid_actions)}"}

            # Build params
            params = {}
            if song_id:
                params["song_id"] = song_id
            if playlist_id:
                params["playlist_id"] = playlist_id
            if volume is not None:
                params["volume"] = volume
            if position is not None:
                params["position"] = position
            if repeat_mode:
                params["mode"] = repeat_mode

            # Push command to queue for frontend to pick up
            cmd_id = music_service.push_command(action, params)

            return {
                "success": True,
                "command_id": cmd_id,
                "action": action,
                "params": params,
                "message": f"命令 '{action}' 已发送到播放器",
            }
        except Exception as e:
            logger.error("music_control failed: %s", e)
            return {"success": False, "error": str(e)}

    async def search_music(
        self,
        keyword: Annotated[str, "搜索关键词，支持歌名、歌手、专辑"],
    ) -> dict[str, Any]:
        """搜索音乐"""
        try:
            from miloco_server.service.music_service import get_music_service
            from miloco_server.schema.music_schema import MusicSearchRequest

            music_service = get_music_service()
            if not music_service:
                return {"success": False, "error": "Music service not available"}

            request = MusicSearchRequest(keyword=keyword)
            result = music_service.search_songs(request)

            return {
                "success": True,
                "songs": [song.dict() for song in result.songs],
                "total": result.total,
            }
        except Exception as e:
            logger.error("search_music failed: %s", e)
            return {"success": False, "error": str(e)}

    async def get_playback_status(self) -> dict[str, Any]:
        """获取当前播放状态"""
        try:
            from miloco_server.service.music_service import get_music_service

            music_service = get_music_service()
            if not music_service:
                return {"success": False, "error": "Music service not available"}

            status = music_service.get_playback_status()

            return {
                "success": True,
                "state": status.state.value,
                "current_song": status.current_song.dict() if status.current_song else None,
                "position": status.position,
                "duration": status.current_song.duration if status.current_song else 0,
                "volume": status.volume,
                "is_muted": status.is_muted,
                "repeat_mode": status.repeat_mode.value,
                "is_shuffle": status.is_shuffle,
                "current_index": status.current_index,
                "playlist_name": status.playlist.name if status.playlist else None,
                "total_songs": len(status.playlist.songs) if status.playlist else 0,
            }
        except Exception as e:
            logger.error("get_playback_status failed: %s", e)
            return {"success": False, "error": str(e)}

    async def discover_dlna_devices(
        self,
        timeout: Annotated[int, "搜索超时时间(秒)，默认5秒"] = 5,
    ) -> dict[str, Any]:
        """发现DLNA设备"""
        try:
            from miloco_server.service.music_service import get_music_service

            music_service = get_music_service()
            if not music_service:
                return {"success": False, "error": "Music service not available"}

            devices = await music_service.discover_dlna_devices(timeout)

            return {
                "success": True,
                "devices": [device.dict() for device in devices],
                "total": len(devices),
            }
        except Exception as e:
            logger.error("discover_dlna_devices failed: %s", e)
            return {"success": False, "error": str(e)}

    async def cast_to_dlna(
        self,
        device_id: Annotated[str, "DLNA设备ID"],
        song_id: Annotated[Optional[str], "歌曲ID，不指定则播放当前歌曲"] = None,
    ) -> dict[str, Any]:
        """投屏到DLNA设备"""
        try:
            from miloco_server.service.music_service import get_music_service
            from miloco_server.schema.music_schema import DLNACastRequest

            music_service = get_music_service()
            if not music_service:
                return {"success": False, "error": "Music service not available"}

            request = DLNACastRequest(device_id=device_id, song_id=song_id)
            success = await music_service.cast_to_dlna(request)

            return {
                "success": success,
                "message": "投屏成功" if success else "投屏失败",
            }
        except Exception as e:
            logger.error("cast_to_dlna failed: %s", e)
            return {"success": False, "error": str(e)}

    async def search_and_play_online_music(
        self,
        keyword: Annotated[str, "搜索关键词，可以是歌名、歌手名或组合，如'周杰伦 晴天'、'薛之谦 演员'"],
        source: Annotated[str, "音源: netease(网易云), qq(QQ音乐), migu(咪咕音乐)"] = "netease",
    ) -> dict[str, Any]:
        """搜索在线音乐并通过命令队列添加到前端播放列表"""
        try:
            from miloco_server.service.music_service import get_music_service
            music_service = get_music_service()
            if not music_service:
                return {"success": False, "error": "Music service not available"}

            online_songs = await music_service.search_online_music(keyword, count=10, source=source)
            if not online_songs:
                return {"success": False, "error": f"未找到与 '{keyword}' 相关的歌曲", "songs": []}

            # 转为前端格式
            songs_for_frontend = []
            for s in online_songs:
                songs_for_frontend.append({
                    "id": f"online_{s['id']}",
                    "title": s["title"],
                    "artist": s["artist"],
                    "album": s["album"],
                    "picId": s.get("pic_id", ""),
                    "lyricId": s.get("lyric_id", ""),
                    "source": s.get("source", source),
                    "audio_url": None,
                    "cover_url": None,
                    "lyrics": None,
                })

            # 通过命令队列发送到前端
            music_service.push_command("add_songs", {"songs": songs_for_frontend})

            return {
                "success": True,
                "songs": songs_for_frontend,
                "total": len(songs_for_frontend),
                "message": f"找到 {len(songs_for_frontend)} 首歌曲，已添加到播放列表",
            }
        except Exception as e:
            logger.error("search_and_play_online_music failed: %s", e)
            return {"success": False, "error": str(e)}

    async def smart_play_music(
        self,
        query: Annotated[str, "播放请求，如'播放晴天'、'放一首周杰伦的歌'、'我想听稻香'"],
    ) -> dict[str, Any]:
        """智能播放音乐 - 优先本地，找不到再联网搜索"""
        try:
            from miloco_server.service.music_service import get_music_service
            from miloco_server.schema.music_schema import MusicSearchRequest
            music_service = get_music_service()
            if not music_service:
                return {"success": False, "error": "Music service not available"}

            # 提取关键词
            prefixes = ["播放", "放一首", "我想听", "来一首", "来点", "听一首", "听一下",
                        "play ", "Play ", "I want to listen to ", "listen to "]
            keyword = query.strip()
            for prefix in prefixes:
                if keyword.startswith(prefix):
                    keyword = keyword[len(prefix):].strip()
                    break
            if not keyword:
                keyword = query.strip()

            # ── Step 1: 搜索本地音乐 ──
            local_result = music_service.search_songs(MusicSearchRequest(keyword=keyword))
            if local_result.songs:
                local_song = local_result.songs[0]
                music_service.push_command("play_song", {"song_id": local_song.id})
                return {
                    "success": True,
                    "source": "local",
                    "message": f"正在播放本地歌曲: {local_song.title} - {local_song.artist}",
                    "song": {"id": local_song.id, "title": local_song.title, "artist": local_song.artist, "album": local_song.album},
                }

            # ── Step 2: 本地没有，联网搜索 ──
            online_songs = await music_service.search_online_music(keyword, count=5)
            if not online_songs:
                return {"success": False, "error": f"未找到与 '{keyword}' 相关的歌曲（本地和在线均无结果）"}

            songs_for_frontend = []
            for s in online_songs:
                songs_for_frontend.append({
                    "id": f"online_{s['id']}",
                    "title": s["title"],
                    "artist": s["artist"],
                    "album": s["album"],
                    "picId": s.get("pic_id", ""),
                    "lyricId": s.get("lyric_id", ""),
                    "source": s.get("source", "netease"),
                    "audio_url": None,
                    "cover_url": None,
                    "lyrics": None,
                })

            music_service.push_command("add_songs", {"songs": songs_for_frontend})
            music_service.push_command("play_song", {"song_id": songs_for_frontend[0]["id"]})

            first = songs_for_frontend[0]
            return {
                "success": True,
                "source": "online",
                "message": f"正在播放: {first['title']} - {first['artist']}（在线，共 {len(songs_for_frontend)} 首）",
                "song": first,
                "total_found": len(songs_for_frontend),
            }
        except Exception as e:
            logger.error("smart_play_music failed: %s", e)
            return {"success": False, "error": str(e)}

    async def scan_local_music(
        self,
        path: Annotated[str, "本地音乐目录路径，如 D:\\Music 或 /home/user/music"],
        recursive: Annotated[bool, "是否递归扫描子目录"] = True,
    ) -> dict[str, Any]:
        """扫描本地目录的音乐文件"""
        try:
            from miloco_server.service.music_service import get_music_service
            from miloco_server.schema.music_schema import LocalMusicScanRequest
            music_service = get_music_service()
            if not music_service:
                return {"success": False, "error": "Music service not available"}

            request = LocalMusicScanRequest(path=path, recursive=recursive)
            result = await music_service.scan_local_music(request)

            return {
                "success": True,
                "total": result.total,
                "new_count": result.new_count,
                "message": f"扫描完成，发现 {result.total} 首歌曲，新增 {result.new_count} 首",
            }
        except Exception as e:
            logger.error("scan_local_music failed: %s", e)
            return {"success": False, "error": str(e)}

    async def list_dlna_devices(self) -> dict[str, Any]:
        """列出已发现的DLNA设备"""
        try:
            from miloco_server.service.music_service import get_music_service
            music_service = get_music_service()
            if not music_service:
                return {"success": False, "error": "Music service not available"}

            devices = music_service.get_dlna_devices()
            return {
                "success": True,
                "devices": [d.dict() for d in devices],
                "total": len(devices),
                "message": f"发现 {len(devices)} 个DLNA设备" if devices else "未发现DLNA设备，请先使用 discover_dlna_devices 搜索",
            }
        except Exception as e:
            logger.error("list_dlna_devices failed: %s", e)
            return {"success": False, "error": str(e)}

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
                "water_leak_detected": ctx.water_leak_detected,
                "traffic_restricted": ctx.traffic_restricted,
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
