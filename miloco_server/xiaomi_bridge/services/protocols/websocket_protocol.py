# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
WebSocket protocol implementation for Xiaomi Bridge.

Reference: open-xiaoai-bridge/core/services/protocols/websocket_protocol.py
"""

import asyncio
import json
import uuid
from typing import Dict, Any, Optional, Callable

from miloco_server.xiaomi_bridge.services.protocols.typing import MessageType, StreamInfo
from miloco_server.xiaomi_bridge.utils.logger import logger


class WebSocketProtocol:
    """WebSocket protocol handler."""

    def __init__(self, websocket):
        """Initialize protocol handler."""
        self._websocket = websocket
        self._pending: Dict[str, asyncio.Future] = {}
        self._stream_info = StreamInfo()
        self._on_message_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self._on_audio_callback: Optional[Callable[[bytes], None]] = None

    async def send_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Send a request and wait for response.
        
        Args:
            method: Request method name
            params: Request parameters
        
        Returns:
            Response data
        """
        req_id = str(uuid.uuid4())
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self._pending[req_id] = fut

        request_payload = {
            "type": MessageType.REQUEST.value,
            "id": req_id,
            "method": method,
            "params": params or {},
        }

        logger.debug(f"[WS] Sending request: {method}, req_id={req_id}")
        await self._websocket.send(json.dumps(request_payload))

        try:
            result = await asyncio.wait_for(fut, timeout=30)
            return result
        except asyncio.TimeoutError:
            logger.error(f"[WS] Request timeout: {method}, req_id={req_id}")
            raise
        finally:
            self._pending.pop(req_id, None)

    async def send_event(self, event_name: str, payload: Dict[str, Any] = None):
        """
        Send an event message.
        
        Args:
            event_name: Event name
            payload: Event payload
        """
        event_payload = {
            "type": MessageType.EVENT.value,
            "event": event_name,
            "payload": payload or {},
        }
        await self._websocket.send(json.dumps(event_payload))
        logger.debug(f"[WS] Sent event: {event_name}")

    async def send_audio(self, audio_data: bytes):
        """
        Send audio data.
        
        Args:
            audio_data: PCM audio bytes
        """
        # Send as binary frame
        await self._websocket.send_bytes(audio_data)
        logger.debug(f"[WS] Sent audio: {len(audio_data)} bytes")

    async def receive_messages(self):
        """Receive and process messages from WebSocket."""
        try:
            async for message in self._websocket:
                if isinstance(message, bytes):
                    # Binary frame - audio data
                    if self._on_audio_callback:
                        self._on_audio_callback(message)
                    continue

                if not isinstance(message, str):
                    continue

                try:
                    data = json.loads(message)
                    msg_type = data.get("type")

                    if msg_type == MessageType.RESPONSE.value:
                        await self._handle_response(data)
                    elif msg_type == MessageType.EVENT.value:
                        await self._handle_event(data)
                    elif msg_type == MessageType.REQUEST.value:
                        await self._handle_request(data)
                    else:
                        logger.debug(f"[WS] Unknown message type: {msg_type}")

                except json.JSONDecodeError:
                    logger.warning(f"[WS] Failed to decode message: {message[:200]}")

        except asyncio.CancelledError:
            logger.debug("[WS] Receiver task cancelled")
            raise
        except Exception as e:
            logger.error(f"[WS] Receive error: {e}")
            raise

    async def _handle_response(self, data: Dict[str, Any]):
        """Handle response message."""
        req_id = data.get("id")
        if req_id:
            future = self._pending.get(req_id)
            if future and not future.done():
                future.set_result(data)
            elif future and future.done():
                # Second response for same request - clean up
                self._pending.pop(req_id, None)

    async def _handle_event(self, data: Dict[str, Any]):
        """Handle event message."""
        event_name = data.get("event", "")
        payload = data.get("payload", {})
        
        logger.debug(f"[WS] Received event: {event_name}")
        
        if self._on_message_callback:
            try:
                self._on_message_callback(data)
            except Exception as e:
                logger.error(f"[WS] Message callback error: {e}")

    async def _handle_request(self, data: Dict[str, Any]):
        """Handle request message from client."""
        req_id = data.get("id")
        method = data.get("method")
        params = data.get("params", {})

        logger.debug(f"[WS] Received request: {method}, req_id={req_id}")

        # Handle common requests
        response = {"type": MessageType.RESPONSE.value, "id": req_id}
        
        try:
            if method == "get_stream_info":
                response["ok"] = True
                response["payload"] = self._stream_info.to_dict()
            elif method == "set_stream_info":
                self._stream_info = StreamInfo.from_dict(params)
                response["ok"] = True
                response["payload"] = {"message": "Stream info updated"}
            else:
                response["ok"] = False
                response["error"] = {"message": f"Unknown method: {method}"}
        except Exception as e:
            response["ok"] = False
            response["error"] = {"message": str(e)}

        await self._websocket.send(json.dumps(response))

    def set_message_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Set callback for message handling."""
        self._on_message_callback = callback

    def set_audio_callback(self, callback: Callable[[bytes], None]):
        """Set callback for audio data."""
        self._on_audio_callback = callback

    def get_stream_info(self) -> StreamInfo:
        """Get current stream information."""
        return self._stream_info

    def set_stream_info(self, stream_info: StreamInfo):
        """Set stream information."""
        self._stream_info = stream_info