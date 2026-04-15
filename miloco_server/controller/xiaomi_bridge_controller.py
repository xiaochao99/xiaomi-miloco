# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Xiaomi Bridge Controller
API endpoints for Xiaomi speaker bridge functionality.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, File, UploadFile, Request, Depends, HTTPException, status
from pydantic import BaseModel

from miloco_server.middleware import verify_token, verify_websocket_token
from miloco_server.xiaomi_bridge.audio_stream import get_audio_stream_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/xiaomi-bridge", tags=["Xiaomi Bridge"])


def _is_xiaomi_bridge_api_auth_enabled() -> bool:
    """Whether Xiaomi Bridge API auth is enabled (default: enabled)."""
    raw = os.getenv("MILOCO_XIAOMI_BRIDGE_API_AUTH", "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _get_xiaomi_bridge_public_endpoints() -> set[str]:
    """
    Configurable anonymous whitelist.
    Example: MILOCO_XIAOMI_BRIDGE_PUBLIC_ENDPOINTS="health,status,ws/play_stream"
    """
    raw = os.getenv("MILOCO_XIAOMI_BRIDGE_PUBLIC_ENDPOINTS", "health,status")
    endpoints = {
        item.strip().strip("/").lower()
        for item in raw.split(",")
        if item.strip()
    }
    return endpoints


def _to_endpoint_key(path: str) -> str:
    """Convert full path to router-local key, e.g. '/api/xiaomi-bridge/health' -> 'health'."""
    if not path:
        return ""
    normalized = path.strip().lower()
    for prefix in ("/api/xiaomi-bridge/", "/xiaomi-bridge/"):
        if normalized.startswith(prefix):
            return normalized[len(prefix):].strip("/")
    return normalized.strip("/")


async def _verify_xiaomi_bridge_http_access(request: Request) -> str:
    """HTTP access gate for Xiaomi Bridge endpoints."""
    if not _is_xiaomi_bridge_api_auth_enabled():
        return "anonymous"
    endpoint_key = _to_endpoint_key(request.url.path)
    if endpoint_key in _get_xiaomi_bridge_public_endpoints():
        return "anonymous"
    return verify_token(request)


def _verify_xiaomi_bridge_websocket_access(websocket: WebSocket) -> str:
    """WebSocket access gate for Xiaomi Bridge endpoints."""
    if not _is_xiaomi_bridge_api_auth_enabled():
        return "anonymous"
    endpoint_key = _to_endpoint_key(websocket.url.path)
    if endpoint_key in _get_xiaomi_bridge_public_endpoints():
        return "anonymous"
    return verify_websocket_token(websocket)


class TextRequest(BaseModel):
    """Text input request model."""
    text: str


class ConnectedDevice(BaseModel):
    """连接设备信息模型."""
    client_id: str
    device_name: str
    ip_address: str
    connected_at: float
    connected_duration: int


@router.get("/devices")
async def get_connected_devices(_current_user: str = Depends(_verify_xiaomi_bridge_http_access)):
    """Get list of connected Xiaomi speakers."""
    manager = get_audio_stream_manager()
    devices = manager.get_all_devices()
    device_count = len(devices)
    logger.info(f"[XiaoAI Bridge] Connected devices count: {device_count}")
    logger.info(f"[XiaoAI Bridge] Connected device IDs: {[d['client_id'] for d in devices]}")
    return {"code": 0, "data": devices, "message": "success"}


@router.get("/devices/{client_id}")
async def get_device_info(client_id: str, _current_user: str = Depends(_verify_xiaomi_bridge_http_access)):
    """Get detailed information about a specific device."""
    manager = get_audio_stream_manager()
    device = manager.get_device_info(client_id)
    if not device:
        return {"code": -1, "data": None, "message": "Device not found"}
    return {"code": 0, "data": device, "message": "success"}


class DeviceUpdateRequest(BaseModel):
    """设备更新请求模型."""
    device_name: Optional[str] = None


@router.put("/devices/{client_id}")
async def update_device_info(
    client_id: str,
    request: DeviceUpdateRequest,
    _current_user: str = Depends(_verify_xiaomi_bridge_http_access),
):
    """Update device information (e.g., custom device name)."""
    manager = get_audio_stream_manager()
    
    if request.device_name is not None:
        # Update device name in memory
        device = manager._devices.get(client_id)
        if not device:
            return {"code": -1, "data": None, "message": "Device not found"}
        
        old_name = device.device_name
        device.device_name = request.device_name.strip()
        
        # Persist to storage
        await manager.save_device_info(client_id, {"device_name": device.device_name})
        
        logger.info(f"[XiaoAI Bridge] Updated device name: {client_id} - {old_name} -> {device.device_name}")
    
    return {"code": 0, "data": manager.get_device_info(client_id), "message": "success"}


@router.post("/play/text")
async def play_text(request: TextRequest, _current_user: str = Depends(_verify_xiaomi_bridge_http_access)):
    """
    Play text on connected Xiaomi speakers.
    Compatible with open-xiaoai-bridge API.
    
    This endpoint always uses Xiaomi native TTS via WebSocket,
    following the open-xiaoai-bridge protocol.
    
    Args:
        text: The text to speak
    """
    if not request.text:
        return {"code": -1, "data": None, "message": "Text is required"}
    
    try:
        manager = get_audio_stream_manager()
        from miloco_server.xiaomi_bridge.shell_utils import build_mibrain_tts_script

        payload = build_mibrain_tts_script(request.text)
        logger.info("[XiaoAI Bridge] Sending native TTS command via open-xiaoai RPC: %s", payload)
        await manager.run_shell(payload)
        
        return {"code": 0, "message": "ok"}
            
    except Exception as e:
        logger.error(f"Play text failed: {e}")
        return {"code": -1, "message": str(e)}


@router.get("/health")
async def health_check(_current_user: str = Depends(_verify_xiaomi_bridge_http_access)):
    """健康检查 - 兼容 open-xiaoai-bridge API"""
    return {"code": 0, "message": "ok"}


@router.get("/status")
async def get_status(_current_user: str = Depends(_verify_xiaomi_bridge_http_access)):
    """获取播放状态 - 兼容 open-xiaoai-bridge API"""
    manager = get_audio_stream_manager()
    devices = manager.get_all_devices()
    return {
        "code": 0,
        "data": {
            "connected_devices": len(devices),
            "devices": devices
        }
    }


@router.post("/interrupt")
async def interrupt_playback(_current_user: str = Depends(_verify_xiaomi_bridge_http_access)):
    """打断当前播放 - 兼容 open-xiaoai-bridge API"""
    try:
        manager = get_audio_stream_manager()
        from miloco_server.xiaomi_bridge.shell_utils import build_interrupt_script
        await manager.run_shell(build_interrupt_script())
        logger.info("Sent interrupt command via run_shell")
        return {"code": 0, "message": "ok"}
    except Exception as e:
        logger.error(f"Interrupt failed: {e}")
        return {"code": -1, "message": str(e)}


@router.post("/wakeup")
async def wakeup_speaker(_current_user: str = Depends(_verify_xiaomi_bridge_http_access)):
    """唤醒小爱音箱 - 兼容 open-xiaoai-bridge API"""
    try:
        manager = get_audio_stream_manager()
        from miloco_server.xiaomi_bridge.shell_utils import build_wakeup_script
        await manager.run_shell(build_wakeup_script(awake=True, silent=True))
        logger.info("Sent wakeup command via run_shell")
        return {"code": 0, "message": "ok"}
    except Exception as e:
        logger.error(f"Wakeup failed: {e}")
        return {"code": -1, "message": str(e)}


class PlayUrlRequest(BaseModel):
    """播放音频链接请求模型"""
    url: str

@router.post("/play/url")
async def play_url(request: PlayUrlRequest, _current_user: str = Depends(_verify_xiaomi_bridge_http_access)):
    """播放音频链接 - 兼容 open-xiaoai-bridge API"""
    if not request.url:
        return {"code": -1, "message": "URL is required"}
    
    try:
        manager = get_audio_stream_manager()
        from miloco_server.xiaomi_bridge.shell_utils import build_play_url_script
        await manager.run_shell(build_play_url_script(request.url))
        logger.info("Sent play URL command via run_shell: %s...", request.url[:50])
        return {"code": 0, "message": "ok"}
    except Exception as e:
        logger.error(f"Play URL failed: {e}")
        return {"code": -1, "message": str(e)}


@router.post("/play/file")
async def play_file(file: UploadFile = File(...), _current_user: str = Depends(_verify_xiaomi_bridge_http_access)):
    """上传并播放音频文件 - 兼容 open-xiaoai-bridge API"""
    if not file:
        return {"code": -1, "message": "File is required"}
    
    try:
        # 读取文件内容
        audio_data = await file.read()
        
        # 发送音频数据
        manager = get_audio_stream_manager()
        await manager.send_audio_to_clients(audio_data)
        
        logger.info(f"Played uploaded file: {file.filename}")
        return {"code": 0, "message": "ok"}
    except Exception as e:
        logger.error(f"Play file failed: {e}")
        return {"code": -1, "message": str(e)}


class TTSRequest(BaseModel):
    """统一 TTS 请求模型（按 MILOCO_TTS_ENGINE 自动路由）"""
    text: str
    speaker_id: Optional[str] = None
    client_ids: Optional[List[str]] = None


@router.post("/tts")
async def tts(request: TTSRequest, _current_user: str = Depends(_verify_xiaomi_bridge_http_access)):
    """
    统一 TTS 合成并播放接口（唯一入口）。

    按环境变量 `MILOCO_TTS_ENGINE` 自动选择引擎：
    - `doubao`
    - `mimo`
    - `xiaoai`
    """
    if not request.text:
        return {"code": -1, "message": "Text is required"}

    try:
        from miloco_server.xiaomi_bridge.tts import TTSService

        tts = TTSService.instance()
        if not tts.is_initialized:
            ok = await tts.initialize()
            if not ok:
                return {"code": -1, "message": "TTS service not configured"}

        engine = tts.engine
        logger.info(f"[TTS] Using engine: {engine}")

        ok = await tts.speak(request.text, request.speaker_id, client_ids=request.client_ids)
        if not ok:
            return {"code": -1, "message": f"{engine} TTS speak failed"}

        return {"code": 0, "message": "ok", "engine": engine}
    except Exception as e:
        logger.error("TTS failed: %s", e, exc_info=True)
        return {"code": -1, "message": str(e)}


@router.post("/tts/stream")
async def tts_stream(request: TTSRequest, _current_user: str = Depends(_verify_xiaomi_bridge_http_access)):
    """
    统一 TTS 流式合成并播放接口。

    按环境变量 `MILOCO_TTS_ENGINE` 自动选择引擎。
    对于不支持流式的场景，将按引擎内部策略自动回退。
    """
    if not request.text:
        return {"code": -1, "message": "Text is required"}

    try:
        from miloco_server.xiaomi_bridge.tts import TTSService

        tts = TTSService.instance()
        if not tts.is_initialized:
            ok = await tts.initialize()
            if not ok:
                return {"code": -1, "message": "TTS service not configured"}

        engine = tts.engine
        logger.info(f"[TTS Stream] Using engine: {engine}")

        ok = await tts.speak_stream(request.text, request.speaker_id, request.client_ids)
        if not ok:
            return {"code": -1, "message": f"{engine} stream TTS failed"}

        return {"code": 0, "message": "ok", "engine": engine}
    except Exception as e:
        logger.error("Stream TTS failed: %s", e, exc_info=True)
        return {"code": -1, "message": str(e)}

@router.get("/tts/doubao_voices")
async def get_doubao_voices(_current_user: str = Depends(_verify_xiaomi_bridge_http_access)):
    """获取豆包可用音色列表（仅在 `MILOCO_TTS_ENGINE=doubao` 时生效）"""
    voices = [
        {"id": "zh_female_vv_uranus_bigtts", "name": "薇薇"},
        {"id": "zh_female_cancan_mars_bigtts", "name": "灿灿"},
        {"id": "zh_female_shuangkuaisisi_moon_bigtts", "name": "思思"},
        {"id": "zh_male_raphael_bigtts", "name": "拉斐尔"},
        {"id": "zh_male_lengkugege_emo_v2_mars_bigtts", "name": "冷酷哥哥"},
        {"id": "zh_female_qingqing_stellar_bigtts", "name": "青青"},
        {"id": "zh_male_yangyang_nebula_bigtts", "name": "洋洋"},
        {"id": "zh_female_xiaoxiao_bigtts", "name": "晓晓"},
    ]
    return {"code": 0, "data": voices}


@router.websocket("/ws/play_stream")
async def ws_play_stream(websocket: WebSocket):
    """
    流式推送音频到小爱（客户端发送二进制音频 chunk，服务端立即转发到已连接音箱）。

    可选：首条 text 消息可携带 JSON {"client_ids":[...]} 指定目标设备；否则广播。
    """
    try:
        _verify_xiaomi_bridge_websocket_access(websocket)
    except HTTPException as e:
        await websocket.close(code=1008, reason=e.detail or "Unauthorized")
        return
    except Exception:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await websocket.accept()
    manager = get_audio_stream_manager()
    client_ids: Optional[List[str]] = None

    try:
        first = True
        while True:
            msg = await websocket.receive()
            if msg is None:
                continue
            if msg.get("type") == "websocket.disconnect":
                break

            text = msg.get("text")
            data = msg.get("bytes")

            if first and text:
                first = False
                try:
                    import json
                    payload: Any = json.loads(text)
                    if isinstance(payload, dict) and isinstance(payload.get("client_ids"), list):
                        client_ids = [str(x) for x in payload["client_ids"]]
                        await websocket.send_text(json.dumps({"ok": True, "client_ids": client_ids}, ensure_ascii=False))
                        continue
                except Exception:
                    # ignore malformed setup frame
                    pass

            first = False
            if data:
                await manager.send_audio_to_clients(data, client_ids)
                continue

            if text:
                # keepalive / ignore
                continue

    except WebSocketDisconnect:
        return
    except Exception as e:
        logger.error("ws_play_stream error: %s", e, exc_info=True)
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass


@router.websocket("/ws/audio")
async def audio_stream_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for audio streaming from Xiaomi speaker.
    Receives raw audio data for VAD/ASR processing.
    """
    # 该入口容易被误用（HTTP API 端口），并且会导致设备连错端口、握手/投递行为不一致。
    # 正确的小爱音箱连接入口是 BridgeManager 单独启动的 WS 服务（默认 4399）的根路径 "/".
    try:
        # 即使是 deprecated 入口也要鉴权，避免被匿名探测和滥用。
        _verify_xiaomi_bridge_websocket_access(websocket)

        ip_address = "Unknown"
        try:
            if hasattr(websocket.client, "host"):
                ip_address = websocket.client.host
        except Exception:
            pass

        logger.error(
            "[XiaoAI Bridge] Deprecated WS endpoint hit: /api/xiaomi-bridge/ws/audio from ip=%s. "
            "Please connect the speaker to ws://<server>:4399/ (standalone WS server).",
            ip_address,
        )
        await websocket.accept()
        await websocket.close(code=1008, reason="Deprecated endpoint. Use ws://<server>:4399/")
    except Exception:
        try:
            await websocket.close(code=1008, reason="Deprecated endpoint")
        except Exception:
            pass