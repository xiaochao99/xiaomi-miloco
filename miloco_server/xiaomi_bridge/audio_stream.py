# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
WebSocket音频流处理器
接收小米音箱的音频流并处理
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional, Dict, Set, Any
from dataclasses import dataclass, field
import json
import uuid
import time as _time
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# 设备信息存储路径
DEVICE_STORAGE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "xiaomi_bridge_devices.json"
)


@dataclass
class AudioStreamConfig:
    """音频流配置"""
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 320  # 20ms at 16kHz


@dataclass
class ConnectedDevice:
    """连接的设备信息"""
    client_id: str
    websocket: WebSocket
    connected_at: float  # 连接时间戳
    device_name: str = "Unknown"  # 设备名称
    ip_address: str = "Unknown"   # 设备IP地址
    # open-xiaoai client-rust protocol state
    protocol: str = "open-xiaoai-client-rust"
    last_rx_at: float = field(default_factory=time.time)
    first_rx_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    # Outgoing command channel (text frames)
    command_queue: "asyncio.Queue[str]" = field(default_factory=asyncio.Queue, repr=False)
    sender_task: Optional[asyncio.Task] = field(default=None, repr=False)
    max_queued_commands: int = 50
    _drop_counter: int = 0
    # Pending command tracking (debug/capability detection)
    pending_commands: Dict[str, float] = field(default_factory=dict, repr=False)  # id -> sent_at
    last_command_result_at: float = 0.0
    playback_started: bool = False
    recording_started: bool = False
    # Play stream channel (server -> device): single queue + single sender loop
    play_queue: "asyncio.Queue[tuple[int, bytes]]" = field(default_factory=asyncio.Queue, repr=False)
    play_sender_task: Optional[asyncio.Task] = field(default=None, repr=False)
    play_session_id: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典用于API返回"""
        return {
            "client_id": self.client_id,
            "device_name": self.device_name,
            "ip_address": self.ip_address,
            "connected_at": self.connected_at,
            "connected_duration": int(time.time() - self.connected_at)
        }


class AudioStreamManager:
    """
    WebSocket音频流管理器
    接收来自小米音箱的音频流
    """
    
    _instance: Optional[AudioStreamManager] = None
    
    def __init__(self):
        self._devices: Dict[str, ConnectedDevice] = {}  # 改为存储设备对象
        self._audio_handler = None
        self._running = False
        self._config = AudioStreamConfig()
        # Command channel tuning (open-xiaoai client-rust RPC)
        self._command_ready_timeout_s = float(os.getenv("MILOCO_XIAOAI_COMMAND_READY_TIMEOUT_S", "0.2"))
        self._command_result_timeout_s = float(os.getenv("MILOCO_XIAOAI_COMMAND_RESULT_TIMEOUT_S", "5.0"))
        # 设备信息缓存（持久化存储）
        self._device_info_cache: Dict[str, Dict[str, Any]] = {}
        self._load_device_info()
        # Playback pacing (single-channel) tuning
        self._play_sample_rate = int(os.getenv("MILOCO_XIAOAI_PLAY_SAMPLE_RATE", "24000"))
        self._play_bytes_per_sample = int(os.getenv("MILOCO_XIAOAI_PLAY_BYTES_PER_SAMPLE", "2"))
        self._play_max_ahead_ms = int(os.getenv("MILOCO_XIAOAI_PLAY_MAX_AHEAD_MS", "1500"))
        self._play_pacing_enabled = os.getenv("MILOCO_XIAOAI_PLAY_PACING", "1").strip().lower() in ("1", "true", "yes", "on")
        self._play_direct_send = os.getenv("MILOCO_XIAOAI_PLAY_DIRECT_SEND", "0").strip().lower() in ("1", "true", "yes", "on")
    
    def _load_device_info(self):
        """从本地存储加载设备信息"""
        try:
            if os.path.exists(DEVICE_STORAGE_PATH):
                with open(DEVICE_STORAGE_PATH, "r", encoding="utf-8") as f:
                    self._device_info_cache = json.load(f)
                logger.info(f"[AudioStream] Loaded {len(self._device_info_cache)} device records from storage")
            else:
                # 确保目录存在
                os.makedirs(os.path.dirname(DEVICE_STORAGE_PATH), exist_ok=True)
        except Exception as e:
            logger.error(f"[AudioStream] Failed to load device info: {e}")
            self._device_info_cache = {}
    
    async def save_device_info(self, client_id: str, info: Dict[str, Any]):
        """保存设备信息到本地存储"""
        try:
            if client_id not in self._device_info_cache:
                self._device_info_cache[client_id] = {}
            self._device_info_cache[client_id].update(info)
            
            with open(DEVICE_STORAGE_PATH, "w", encoding="utf-8") as f:
                json.dump(self._device_info_cache, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"[AudioStream] Saved device info for {client_id}")
        except Exception as e:
            logger.error(f"[AudioStream] Failed to save device info: {e}")
    
    def get_cached_device_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """获取缓存的设备信息"""
        return self._device_info_cache.get(client_id)
    
    def get_stable_device_id(self, ip_address: str, device_name: str) -> str:
        """
        根据IP地址和设备名称生成稳定的设备ID
        确保设备重启后ID保持稳定
        """
        # 先尝试查找已有记录
        for stored_id, info in self._device_info_cache.items():
            stored_ip = info.get("ip_address")
            stored_name = info.get("device_name")
            if stored_ip == ip_address or (stored_name and stored_name == device_name):
                return stored_id
        
        # 如果没有记录，使用IP地址生成稳定ID
        if ip_address and ip_address != "Unknown":
            # 使用IP地址的哈希作为设备ID
            import hashlib
            hash_value = hashlib.md5(ip_address.encode()).hexdigest()
            return hash_value
        
        # 回退到UUID
        return str(uuid.uuid4())
    
    @classmethod
    def instance(cls) -> AudioStreamManager:
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def set_audio_handler(self, handler):
        """设置音频处理回调"""
        self._audio_handler = handler
    
    async def start(self):
        """启动音频流管理器"""
        self._running = True
        logger.info("Audio stream manager started")
    
    async def stop(self):
        """停止音频流管理器"""
        self._running = False
        
        # 关闭所有连接
        for client_id, device in list(self._devices.items()):
            try:
                await device.websocket.close()
            except Exception:
                pass
        
        self._devices.clear()
        logger.info("Audio stream manager stopped")
    
    async def handle_connection(self, websocket: WebSocket, client_id: str = "default"):
        """处理WebSocket连接"""
        # Get URL path to identify which endpoint was connected to
        url_path = "Unknown"
        try:
            if hasattr(websocket, 'url'):
                url_path = websocket.url.path
        except Exception:
            pass
        
        logger.info(f"[AudioStream] handle_connection called from path={url_path}, client_id={client_id}")
        await websocket.accept()
        
        # 获取客户端IP地址
        ip_address = "Unknown"
        try:
            if hasattr(websocket.client, 'host'):
                ip_address = websocket.client.host
            elif hasattr(websocket, 'client') and websocket.client:
                ip_address = str(websocket.client)[0] if isinstance(websocket.client, tuple) else str(websocket.client)
        except Exception:
            pass
        
        # 获取设备名称（从查询参数）
        device_name = websocket.query_params.get("device_name", "Unknown")
        
        # 使用稳定的设备ID（基于IP地址和设备名称）
        stable_client_id = self.get_stable_device_id(ip_address, device_name)
        
        # 如果客户端没有提供client_id或者提供的是临时ID，使用稳定ID
        if client_id == "default" or client_id.startswith("default-") or len(client_id) == 36:
            # 可能是新连接或临时UUID
            client_id = stable_client_id
        else:
            # 使用客户端提供的ID，但仍检查是否有缓存信息
            cached_info = self.get_cached_device_info(client_id)
            if cached_info:
                # 更新缓存中的IP地址
                await self.save_device_info(client_id, {"ip_address": ip_address})
        
        # 检查是否有缓存的设备名称
        cached_info = self.get_cached_device_info(client_id)
        if cached_info and cached_info.get("device_name"):
            device_name = cached_info["device_name"]
        
        if client_id in self._devices:
            # 关闭旧连接
            try:
                await self._devices[client_id].websocket.close()
            except Exception:
                pass
        
        # 创建设备对象
        device = ConnectedDevice(
            client_id=client_id,
            websocket=websocket,
            connected_at=time.time(),
            device_name=device_name,
            ip_address=ip_address
        )
        self._devices[client_id] = device
        
        # 保存/更新设备信息到缓存
        await self.save_device_info(client_id, {
            "device_name": device_name,
            "ip_address": ip_address
        })
        
        logger.info(f"[AudioStream] Client connected: client_id={client_id}, device_name={device_name}, ip_address={ip_address}")
        
        try:
            # Start a per-device command sender loop (text frames).
            device.sender_task = asyncio.create_task(self._command_sender_loop(device))
            # Start a per-device play sender loop (binary frames).
            device.play_sender_task = asyncio.create_task(self._play_sender_loop(device))
            # Match open-xiaoai-bridge startup behavior: initialize recording pipeline.
            await self._ensure_recording_started(device)

            while self._running:
                try:
                    msg = await websocket.receive()

                    # Starlette/FastAPI websocket.receive() returns dict:
                    # {"type": "websocket.receive", "text": "..."} or {"type": "...", "bytes": b"..."}
                    if msg is None:
                        continue

                    if msg.get("type") == "websocket.disconnect":
                        break

                    if msg.get("text") is not None:
                        device.last_rx_at = time.time()
                        device.first_rx_event.set()
                        await self._handle_text_message(msg.get("text"), device)
                        continue

                    if msg.get("bytes") is not None:
                        device.last_rx_at = time.time()
                        device.first_rx_event.set()
                        await self._handle_binary_message(msg.get("bytes"), device)
                        continue
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error("Error receiving audio: %s", e)
                    break
        finally:
            # Stop sender loop
            if device.sender_task:
                device.sender_task.cancel()
                try:
                    await device.sender_task
                except Exception:
                    pass
            if device.play_sender_task:
                device.play_sender_task.cancel()
                try:
                    await device.play_sender_task
                except Exception:
                    pass
            if client_id in self._devices:
                del self._devices[client_id]
            logger.info("Audio stream client disconnected: %s", client_id)

    async def _command_sender_loop(self, device: ConnectedDevice):
        """
        Per-device outgoing command loop.

        Design goal (open-xiaoai-bridge 风格): 连接建立后可以随时 enqueue 命令，
        等设备开始有任何 rx（或 hello）后再发送，避免“未 ready 即下发导致丢消息”。
        """
        while True:
            cmd = await device.command_queue.get()
            try:
                cmd_id = None
                try:
                    parsed = json.loads(cmd)
                    if isinstance(parsed, dict):
                        # open-xiaoai RPC uses externally tagged enum:
                        # {"Request":{"id":"...","command":"run_shell","payload":"..."}}
                        req = parsed.get("Request")
                        if isinstance(req, dict):
                            cmd_id = req.get("id")
                except Exception:
                    cmd_id = None

                # Wait until we have seen any rx from client (connection fully established).
                try:
                    await asyncio.wait_for(device.first_rx_event.wait(), timeout=self._command_ready_timeout_s)
                except asyncio.TimeoutError:
                    pass

                await device.websocket.send_text(cmd)
                logger.info(f"[Command Send] Sent to {device.client_id}: {cmd[:200]}")

                if cmd_id:
                    device.pending_commands[cmd_id] = time.time()
                    asyncio.create_task(self._watch_command_result(device, cmd_id))
            except Exception as e:
                logger.error(f"[Command Send] Failed to send to {device.client_id}: {e}", exc_info=True)
                raise
            finally:
                device.command_queue.task_done()

    async def _watch_command_result(self, device: ConnectedDevice, cmd_id: str):
        """等待命令回执（若设备端不实现回执，则输出明确诊断日志）。"""
        try:
            await asyncio.sleep(self._command_result_timeout_s)
            sent_at = device.pending_commands.get(cmd_id)
            if not sent_at:
                return
            logger.warning(
                "[Command Result] No result/ack from client %s for command id=%s within %.1fs. "
                "This device may not implement command channel (text frames).",
                device.client_id,
                cmd_id,
                self._command_result_timeout_s,
            )
        except Exception:
            return

    async def _handle_binary_message(self, payload: bytes, device: ConnectedDevice):
        """
        open-xiaoai client-rust binary frame is JSON of Stream:
        {"id": "...", "tag": "record"|"play", "bytes":[..], "data": ...}
        """
        if not payload:
            return
        try:
            stream = json.loads(payload.decode("utf-8"))
        except Exception:
            # Not a stream frame; ignore to avoid breaking audio pipeline
            logger.debug("[Protocol] Ignored non-JSON binary frame from %s (len=%d)", device.client_id, len(payload))
            return

        if not isinstance(stream, dict):
            return

        tag = stream.get("tag")
        raw = stream.get("bytes")
        if not isinstance(tag, str) or not isinstance(raw, list):
            logger.debug("[Protocol] Ignored malformed Stream from %s (tag=%s)", device.client_id, tag)
            return

        try:
            audio_bytes = bytes(raw)
        except Exception:
            logger.debug("[Protocol] Ignored Stream with non-bytes list from %s", device.client_id)
            return

        if tag == "record":
            await self._process_audio(audio_bytes)
            return

        # Other tags: "play" is server->client direction; ignore if received.
        logger.debug("[Protocol] Received stream tag=%s from %s (len=%d)", tag, device.client_id, len(audio_bytes))

    async def _handle_text_message(self, text: str, device: ConnectedDevice):
        """处理来自客户端的文本消息（open-xiaoai RPC: Request/Response/Event）。"""
        if not text:
            return
        logger.info(f"[Protocol] Received text from {device.client_id}: {text[:400]}")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Some clients might send plain text logs; ignore.
            logger.debug("[Protocol] Ignored non-JSON text message")
            return

        if not isinstance(data, dict):
            return

        # Externally tagged enum: {"Response":{...}} / {"Event":{...}} / {"Request":{...}}
        if "Response" in data and isinstance(data.get("Response"), dict):
            resp = data["Response"]
            resp_id = resp.get("id")
            if isinstance(resp_id, str) and resp_id in device.pending_commands:
                device.pending_commands.pop(resp_id, None)
                device.last_command_result_at = time.time()
                logger.info(
                    "[RPC Response] id=%s code=%s msg=%s",
                    resp_id,
                    resp.get("code"),
                    resp.get("msg"),
                )
            return

        if "Event" in data and isinstance(data.get("Event"), dict):
            ev = data["Event"]
            logger.debug("[RPC Event] event=%s id=%s", ev.get("event"), ev.get("id"))
            return

        if "Request" in data and isinstance(data.get("Request"), dict):
            # Client calling server command (not used in our bridge for now)
            req = data["Request"]
            logger.info("[RPC Request] from=%s command=%s id=%s", device.client_id, req.get("command"), req.get("id"))
            return

        logger.debug("[Protocol] Unhandled RPC frame keys=%s", list(data.keys())[:10])
    
    async def _process_audio(self, audio_data: bytes):
        """处理接收到的音频数据"""
        if self._audio_handler:
            try:
                await self._audio_handler(audio_data)
            except Exception as e:
                logger.error("Audio handler error: %s", e)
    
    async def send_audio(self, client_id: str, audio_data: bytes):
        """向客户端发送音频数据（open-xiaoai Stream tag=play）。

        为了降低 underrun（设备端断粮），默认走“单通道队列 + sender loop”：
        - 调用方只负责 enqueue
        - sender loop 负责按节奏发送
        """
        if client_id in self._devices:
            try:
                device = self._devices[client_id]
                # Ensure play sender loop is alive (it may crash on websocket/network errors).
                if device.play_sender_task is None or device.play_sender_task.done():
                    try:
                        if device.play_sender_task:
                            _ = device.play_sender_task.exception()
                    except Exception:
                        pass
                    logger.warning(
                        "[Play Sender] play_sender_task not running for %s, restarting...",
                        device.client_id,
                    )
                    device.play_sender_task = asyncio.create_task(self._play_sender_loop(device))
                # Ensure device playback pipeline is ready before first play stream.
                if self._play_direct_send:
                    await self._ensure_playback_started(device)
                    await self._send_play_frame(device, audio_data)
                    return

                # Enqueue to single-channel sender loop
                await device.play_queue.put((device.play_session_id, audio_data))
            except Exception as e:
                logger.error("Error sending audio to %s: %s", client_id, e)

    async def _send_play_frame(self, device: ConnectedDevice, audio_data: bytes):
        stream = {
            "id": str(uuid.uuid4()),
            "tag": "play",
            "bytes": list(audio_data),
            "data": None,
        }
        await device.websocket.send_bytes(
            json.dumps(stream, ensure_ascii=False).encode("utf-8")
        )

    async def _play_sender_loop(self, device: ConnectedDevice):
        """
        Single-channel play sender loop.

        - Only one coroutine sends binary play frames per device.
        - Optional pacing keeps device buffer ahead bounded (MAX_AHEAD).
        - Drops stale packets automatically when play_session_id changes.
        """
        bytes_per_sec = max(1, self._play_sample_rate * self._play_bytes_per_sample)
        sent_bytes = 0
        playback_start = None  # monotonic seconds when first packet sent

        while True:
            session_id, payload = await device.play_queue.get()
            try:
                # Drop stale packets from previous session.
                if session_id != device.play_session_id:
                    logger.debug(
                        "[Play Sender] Drop stale audio for %s: queued_session=%s current_session=%s",
                        device.client_id,
                        session_id,
                        device.play_session_id,
                    )
                    continue

                # Ensure playback is ready (start_play) right before first send.
                await self._ensure_playback_started(device)

                if playback_start is None or sent_bytes == 0:
                    playback_start = _time.monotonic()

                await self._send_play_frame(device, payload)
                sent_bytes += len(payload)

                if self._play_pacing_enabled and playback_start is not None:
                    # Throttle if device is too far ahead of real-time playback.
                    sent_duration_ms = sent_bytes * 1000 / bytes_per_sec
                    elapsed_ms = (_time.monotonic() - playback_start) * 1000
                    ahead_ms = max(0.0, sent_duration_ms - elapsed_ms)
                    if ahead_ms > self._play_max_ahead_ms:
                        wait_ms = int(ahead_ms - self._play_max_ahead_ms)
                        while wait_ms > 0 and session_id == device.play_session_id:
                            step = min(wait_ms, 50)
                            await asyncio.sleep(step / 1000.0)
                            wait_ms -= step
            except Exception as exc:
                logger.error(
                    "[Play Sender] Fatal error for %s: %s",
                    device.client_id,
                    exc,
                    exc_info=True,
                )
                # Reraise so the task is marked done; send_audio() will restart it.
                raise
            finally:
                device.play_queue.task_done()

    async def _ensure_playback_started(self, device: ConnectedDevice):
        """Send start_play command once per connection before first play stream."""
        if device.playback_started:
            return
        sample_rate = int(os.getenv("MILOCO_XIAOAI_PLAY_SAMPLE_RATE", "24000"))
        channels = int(os.getenv("MILOCO_XIAOAI_PLAY_CHANNELS", "1"))
        bits_per_sample = int(os.getenv("MILOCO_XIAOAI_PLAY_BITS_PER_SAMPLE", "16"))
        # Use a larger playback ring buffer to reduce aplay underrun on jittery streams.
        period_size = int(os.getenv("MILOCO_XIAOAI_PLAY_PERIOD_SIZE", "1200"))
        buffer_size = int(os.getenv("MILOCO_XIAOAI_PLAY_BUFFER_SIZE", "4800"))
        payload = {
            "bits_per_sample": bits_per_sample,
            "buffer_size": buffer_size,
            "channels": channels,
            "pcm": "noop",
            "period_size": period_size,
            "sample_rate": sample_rate,
        }
        await self._send_rpc_direct(device, "start_play", payload)
        device.playback_started = True

    async def restart_playback(self, client_ids: Optional[list[str]] = None, force_reinit: bool = True):
        """
        Ensure remote playback pipeline is ready.

        Default behavior aligns with open-xiaoai-bridge:
        - Do NOT stop playback every time
        - Only ensure start_play has been issued for this connection

        Optional force stop via env:
        - MILOCO_XIAOAI_FORCE_STOP_BEFORE_PLAY=1 -> stop_play -> start_play
        """
        targets = client_ids if client_ids else list(self._devices.keys())
        force_stop_before_play = os.getenv("MILOCO_XIAOAI_FORCE_STOP_BEFORE_PLAY", "0").strip().lower() in ("1", "true", "yes", "on")
        for client_id in targets:
            device = self._devices.get(client_id)
            if not device:
                continue
            if force_reinit:
                # open-xiaoai-bridge style: each TTS session re-ensures start_play.
                device.playback_started = False
                # Bump session id to drop queued audio from previous sessions.
                device.play_session_id += 1
                # Reset pacing counters by draining queue lazily (sender loop will drop stale).
            if force_stop_before_play:
                try:
                    await self._send_rpc_direct(device, "stop_play", None)
                except Exception:
                    # Best effort stop; continue to re-init playback.
                    logger.debug("[AudioStream] stop_play failed for %s", client_id, exc_info=True)
                device.playback_started = False
            await self._ensure_playback_started(device)

    async def _ensure_recording_started(self, device: ConnectedDevice):
        """Send start_recording command once per connection."""
        if device.recording_started:
            return
        payload = {
            "bits_per_sample": 16,
            "buffer_size": 1440,
            "channels": 1,
            "pcm": "noop",
            "period_size": 360,
            "sample_rate": 16000,
        }
        await self._send_rpc_direct(device, "start_recording", payload)
        device.recording_started = True

    async def _send_rpc_direct(self, device: ConnectedDevice, command: str, payload: Dict[str, Any] | None = None):
        """Send one RPC request directly to websocket, preserving startup ordering."""
        req_id = str(uuid.uuid4())
        message = {
            "Request": {
                "id": req_id,
                "command": command,
                "payload": payload,
            }
        }
        try:
            # Wait until client has produced any rx frame (or timeout) before sending startup command.
            try:
                await asyncio.wait_for(device.first_rx_event.wait(), timeout=self._command_ready_timeout_s)
            except asyncio.TimeoutError:
                pass
            await device.websocket.send_text(json.dumps(message, ensure_ascii=False))
            device.pending_commands[req_id] = time.time()
            asyncio.create_task(self._watch_command_result(device, req_id))
            logger.info("[RPC Direct] Sent %s to %s", command, device.client_id)
        except Exception as e:
            logger.warning("[RPC Direct] Failed to send %s to %s: %s", command, device.client_id, e)
            raise
    
    async def broadcast_audio(self, audio_data: bytes):
        """向所有客户端广播音频"""
        for client_id in list(self._devices.keys()):
            await self.send_audio(client_id, audio_data)
    
    async def send_audio_to_clients(self, audio_data: bytes, client_ids: list[str] = None):
        """
        向指定客户端发送音频数据
        
        Args:
            audio_data: 音频数据
            client_ids: 客户端ID列表，为空则发送给所有客户端
        """
        if client_ids:
            for client_id in client_ids:
                await self.send_audio(client_id, audio_data)
        else:
            await self.broadcast_audio(audio_data)

    async def run_shell(self, script: str, client_ids: list[str] | None = None):
        """通过 open-xiaoai client-rust RPC 调用音箱执行 shell。"""
        if not script:
            return

        target_clients = client_ids if client_ids else list(self._devices.keys())
        if not target_clients:
            logger.warning("No connected clients to run_shell")
            return

        logger.info("Sending run_shell to %d client(s): %s...", len(target_clients), script[:120])
        for client_id in target_clients:
            request = {
                "Request": {
                    "id": str(uuid.uuid4()),
                    "command": "run_shell",
                    "payload": script,
                }
            }
            await self._send_rpc_text_to_client(client_id, json.dumps(request, ensure_ascii=False))

    async def _send_rpc_text_to_client(self, client_id: str, message_text: str):
        """向单个客户端发送 RPC 文本帧（入队，sender loop 负责发送）。"""
        if client_id not in self._devices:
            logger.warning("[RPC Send] Client %s not found", client_id)
            return
        device = self._devices[client_id]
        if device.command_queue.qsize() >= device.max_queued_commands:
            try:
                _ = device.command_queue.get_nowait()
                device.command_queue.task_done()
            except Exception:
                pass
            device._drop_counter += 1
            logger.warning("[RPC Send] Queue full, dropped oldest for %s (dropped=%d)", client_id, device._drop_counter)
        await device.command_queue.put(message_text)
        logger.info("[RPC Send] Enqueued for %s (queue=%d)", client_id, device.command_queue.qsize())
    
    def get_device_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """获取指定设备的信息"""
        device = self._devices.get(client_id)
        if device:
            return device.to_dict()
        return None
    
    def get_all_devices(self) -> list[Dict[str, Any]]:
        """获取所有连接设备的列表"""
        return [device.to_dict() for device in self._devices.values()]
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def connected_clients(self) -> Set[str]:
        return set(self._devices.keys())
    
    @property
    def device_count(self) -> int:
        """获取连接设备数量"""
        return len(self._devices)


# 全局单例
_manager: Optional[AudioStreamManager] = None


def get_audio_stream_manager() -> AudioStreamManager:
    """获取全局音频流管理器"""
    global _manager
    if _manager is None:
        _manager = AudioStreamManager.instance()
    return _manager