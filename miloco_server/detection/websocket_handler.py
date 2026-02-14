# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
WebSocket handler for real-time detection events.
Provides live streaming of detection results to clients.
"""

import asyncio
import json
import logging
from typing import Dict, List, Set
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect

from miloco_server.detection.detection_service import get_detection_service

logger = logging.getLogger(__name__)


class DetectionWebSocketManager:
    """Manages WebSocket connections for real-time detection streaming."""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.global_connections: Set[WebSocket] = set()
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._broadcast_task: asyncio.Task = None
        self._running = False

    async def start(self):
        """Start the WebSocket manager."""
        if self._running:
            return

        self._running = True
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())

        # Register with detection service
        service = await get_detection_service()
        service.register_ws_callback(self._on_detection_event)

        logger.info("Detection WebSocket manager started")

    async def stop(self):
        """Stop the WebSocket manager."""
        self._running = False

        # Unregister from detection service
        try:
            service = await get_detection_service()
            service.unregister_ws_callback(self._on_detection_event)
        except Exception as e:
            logger.warning(f"Error unregistering from detection service: {e}")

        # Cancel broadcast task
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass

        # Close all connections
        for connections in self.active_connections.values():
            for ws in connections:
                try:
                    await ws.close()
                except Exception:
                    pass

        for ws in self.global_connections:
            try:
                await ws.close()
            except Exception:
                pass

        self.active_connections.clear()
        self.global_connections.clear()

        logger.info("Detection WebSocket manager stopped")

    async def connect(self, websocket: WebSocket, camera_id: str = None):
        """
        Accept a new WebSocket connection.

        Args:
            websocket: The WebSocket connection
            camera_id: Optional camera ID to filter events (None = all cameras)
        """
        await websocket.accept()

        if camera_id:
            if camera_id not in self.active_connections:
                self.active_connections[camera_id] = set()
            self.active_connections[camera_id].add(websocket)
            logger.debug(f"WebSocket connected for camera {camera_id}")
        else:
            self.global_connections.add(websocket)
            logger.debug("Global WebSocket connected")

        # Send initial status
        await self._send_status(websocket)

    async def disconnect(self, websocket: WebSocket, camera_id: str = None):
        """Disconnect a WebSocket."""
        try:
            if camera_id and camera_id in self.active_connections:
                self.active_connections[camera_id].discard(websocket)
                if not self.active_connections[camera_id]:
                    del self.active_connections[camera_id]
            else:
                self.global_connections.discard(websocket)

            await websocket.close()
        except Exception:
            pass

    def _on_detection_event(self, message: Dict):
        """Handle detection event from service."""
        try:
            self._message_queue.put_nowait(message)
        except asyncio.QueueFull:
            logger.warning("WebSocket message queue full, dropping message")

    async def _broadcast_loop(self):
        """Main broadcast loop."""
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=1.0
                )
                await self._broadcast(message)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Broadcast loop error: {e}")
                await asyncio.sleep(0.1)

    async def _broadcast(self, message: Dict):
        """Broadcast message to relevant clients."""
        camera_id = message.get('camera_id')

        # Prepare message
        ws_message = {
            **message,
            'server_time': datetime.now().isoformat(),
        }

        # Send to camera-specific subscribers
        if camera_id and camera_id in self.active_connections:
            disconnected = []
            for ws in self.active_connections[camera_id]:
                try:
                    await ws.send_json(ws_message)
                except Exception:
                    disconnected.append(ws)

            # Remove disconnected clients
            for ws in disconnected:
                self.active_connections[camera_id].discard(ws)

        # Send to global subscribers
        disconnected = []
        for ws in self.global_connections:
            try:
                await ws.send_json(ws_message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            self.global_connections.discard(ws)

    async def _send_status(self, websocket: WebSocket):
        """Send current status to a new connection."""
        try:
            service = await get_detection_service()

            status = {
                'type': 'status',
                'active_cameras': service.get_active_cameras(),
                'detector_info': service.get_detector_info(),
                'server_time': datetime.now().isoformat(),
            }

            await websocket.send_json(status)
        except Exception as e:
            logger.error(f"Failed to send status: {e}")

    async def handle_client_message(self, websocket: WebSocket, message: Dict):
        """Handle incoming client message."""
        msg_type = message.get('type')

        if msg_type == 'ping':
            await websocket.send_json({'type': 'pong', 'time': datetime.now().isoformat()})

        elif msg_type == 'get_status':
            await self._send_status(websocket)

        elif msg_type == 'subscribe_camera':
            camera_id = message.get('camera_id')
            if camera_id:
                # Move connection to camera-specific set
                self.global_connections.discard(websocket)
                if camera_id not in self.active_connections:
                    self.active_connections[camera_id] = set()
                self.active_connections[camera_id].add(websocket)
                await websocket.send_json({
                    'type': 'subscribed',
                    'camera_id': camera_id,
                })

        elif msg_type == 'unsubscribe_camera':
            camera_id = message.get('camera_id')
            if camera_id and camera_id in self.active_connections:
                self.active_connections[camera_id].discard(websocket)
            self.global_connections.add(websocket)
            await websocket.send_json({'type': 'unsubscribed'})


# Singleton instance
ws_manager = DetectionWebSocketManager()
