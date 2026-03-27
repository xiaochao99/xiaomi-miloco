# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Detection service for managing multiple camera streams and real-time detection.
Integrates with the Miloco server architecture.
"""

import asyncio
import json
import logging
import time
from typing import Callable, Dict, List, Optional, Set, Any
from dataclasses import asdict

from miloco_server.detection.detector import ObjectDetector, DetectionConfig
from miloco_server.detection.face_detector import FaceDetector, FaceDetectionConfig
from miloco_server.detection.multitask_detector import MultiTaskDetector
from miloco_server.detection.stream_processor import (
    StreamConfig,
    StreamDetectionEvent,
    StreamProcessor,
)
from miloco_server.utils.carmera_vision_handler import BaseCameraVisionHandler
from miloco_server.config.normal_config import DETECTION_CONFIG

logger = logging.getLogger(__name__)


class DetectionService:
    """
    Service for managing real-time object detection across multiple cameras.
    Provides WebSocket integration for real-time event streaming.
    """

    def __init__(self):
        self._object_detector: Optional[ObjectDetector] = None
        self._face_detector: Optional[FaceDetector] = None
        self._processors: Dict[str, StreamProcessor] = {}
        self._camera_handlers: Dict[str, BaseCameraVisionHandler] = {}
        # Per-camera flag: whether face recognition is enabled for the running detector.
        # We only switch it from False -> True to avoid breaking other rules that share a camera.
        self._camera_face_enabled: Dict[str, bool] = {}
        self._ws_callbacks: List[Callable[[Dict], None]] = []
        self._event_callbacks: List[Callable[[StreamDetectionEvent], None]] = []
        self._running = False
        self._lock = asyncio.Lock()

        # Configuration
        self._default_detection_config = DetectionConfig(
            confidence_threshold=float(DETECTION_CONFIG.get("confidence_threshold", 0.5)),
            iou_threshold=float(DETECTION_CONFIG.get("iou_threshold", 0.45)),
            device=str(DETECTION_CONFIG.get("device", "auto")),
            half_precision=bool(DETECTION_CONFIG.get("half_precision", True)),
        )
        self._default_stream_config = {
            "process_fps": float(DETECTION_CONFIG.get("process_fps", 5.0)),
            "min_detection_interval": float(DETECTION_CONFIG.get("min_detection_interval", 0.5)),
            "enable_tracking": bool(DETECTION_CONFIG.get("enable_tracking", True)),
        }

        # Statistics
        self._stats = {
            'total_detections': 0,
            'active_streams': 0,
            'start_time': 0.0,
        }

    async def initialize(self) -> bool:
        """Initialize the detection service."""
        try:
            # Initialize object detector
            self._object_detector = ObjectDetector(self._default_detection_config)
            success = await self._object_detector.initialize()

            if not success:
                logger.error("Failed to initialize object detector")
                return False

            # Initialize face detector (optional; keep server working if it fails)
            self._face_detector = FaceDetector(
                FaceDetectionConfig(min_face_score=0.1, max_faces=10)
            )
            await self._face_detector.initialize()

            self._running = True
            self._stats['start_time'] = time.time()
            logger.info("Detection service initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Detection service initialization failed: {e}")
            return False

    async def destroy(self):
        """Cleanup and stop all detection."""
        self._running = False

        # Stop all processors
        async with self._lock:
            for processor in self._processors.values():
                await processor.stop()
            self._processors.clear()
            self._camera_handlers.clear()

        if self._object_detector:
            await self._object_detector.destroy()
            self._object_detector = None
        if self._face_detector:
            await self._face_detector.destroy()
            self._face_detector = None

        self._ws_callbacks.clear()
        self._event_callbacks.clear()
        self._camera_face_enabled.clear()

        logger.info("Detection service destroyed")

    async def start_detection(
        self,
        camera_id: str,
        camera_handler: BaseCameraVisionHandler,
        camera_name: str = "",
        config_override: Optional[Dict] = None
    ) -> bool:
        """
        Start detection on a camera stream.

        Args:
            camera_id: Unique camera identifier
            camera_handler: Camera vision handler for frame access
            camera_name: Human-readable camera name
            config_override: Optional configuration overrides

        Returns:
            True if started successfully
        """
        async with self._lock:
            if camera_id in self._processors:
                logger.debug(f"Detection already running for camera {camera_id}")

                # Apply basic config updates even if already running.
                if config_override and 'confidence_threshold' in config_override and self._object_detector:
                    self._object_detector.config.confidence_threshold = config_override['confidence_threshold']
                    logger.info(
                        f"Updated detector confidence_threshold to {config_override['confidence_threshold']}"
                    )

                if config_override and 'process_fps' in config_override:
                    processor = self._processors.get(camera_id)
                    if processor:
                        processor.update_config({'process_fps': config_override['process_fps']})

                requested_enable_face = False
                if config_override:
                    requested_enable_face = bool(
                        config_override.get(
                            "enable_face_recognition",
                            config_override.get("enable_face", False),
                        )
                    )

                current_enable_face = bool(self._camera_face_enabled.get(camera_id, False))

                # Only enable face when requested; never disable (prevents breaking other rules).
                if requested_enable_face and not current_enable_face:
                    # Restart processor with face enabled
                    processor = self._processors.get(camera_id)
                    if processor:
                        await camera_handler.unregister_jpeg_stream(channel=0)
                        await processor.stop()
                        self._processors.pop(camera_id, None)
                        self._camera_handlers.pop(camera_id, None)

                    # Continue to the normal start path below (do not return)
                else:
                    return True

            if not self._object_detector or not self._object_detector.is_initialized():
                logger.error("Detector not initialized")
                return False

            try:
                # Create stream config
                config = self._default_stream_config.copy()
                if config_override:
                    config.update(config_override)

                # Update detector config if confidence_threshold provided
                if config_override and 'confidence_threshold' in config_override:
                    self._object_detector.config.confidence_threshold = config_override['confidence_threshold']
                    logger.info(f"Updated detector confidence_threshold to {config_override['confidence_threshold']}")

                enable_face_recognition = False
                if config_override:
                    enable_face_recognition = bool(
                        config_override.get(
                            "enable_face_recognition",
                            config_override.get("enable_face", False),
                        )
                    )

                stream_config = StreamConfig(
                    camera_id=camera_id,
                    camera_name=camera_name or camera_id,
                    process_fps=config.get('process_fps', 5.0),
                    min_detection_interval=config.get('min_detection_interval', 0.5),
                    enable_tracking=config.get('enable_tracking', True),
                )

                # Create processor
                detector = MultiTaskDetector(
                    object_detector=self._object_detector,
                    face_detector=self._face_detector,
                    enable_face_recognition=enable_face_recognition,
                    face_accept_threshold=float(
                        config_override.get("face_accept_threshold", 0.35)
                    ) if config_override else 0.35,
                )
                processor = StreamProcessor(
                    config=stream_config,
                    detector=detector,
                    event_callback=self._on_detection_event
                )

                await processor.start()

                # Register JPEG frame callback with camera handler
                callback = self._create_jpeg_callback(camera_id, processor)
                await camera_handler.register_jpeg_stream(callback, channel=0)

                self._processors[camera_id] = processor
                self._camera_handlers[camera_id] = camera_handler
                self._camera_face_enabled[camera_id] = bool(enable_face_recognition)
                self._stats['active_streams'] = len(self._processors)

                logger.info(f"[Detection] Successfully started detection for camera {camera_id}")
                return True

            except Exception as e:
                logger.error(f"Failed to start detection for camera {camera_id}: {e}")
                return False

    async def stop_detection(self, camera_id: str) -> bool:
        """Stop detection for a specific camera."""
        async with self._lock:
            if camera_id not in self._processors:
                return True

            try:
                processor = self._processors[camera_id]
                camera_handler = self._camera_handlers[camera_id]

                # Unregister from camera handler
                await camera_handler.unregister_jpeg_stream(channel=0)

                # Stop processor
                await processor.stop()

                # Remove from tracking
                del self._processors[camera_id]
                del self._camera_handlers[camera_id]
                self._camera_face_enabled.pop(camera_id, None)
                self._stats['active_streams'] = len(self._processors)

                logger.info(f"Stopped detection for camera {camera_id}")
                return True

            except Exception as e:
                logger.error(f"Error stopping detection for camera {camera_id}: {e}")
                return False

    def _create_jpeg_callback(
        self,
        camera_id: str,
        processor: StreamProcessor
    ) -> Callable:
        """Create JPEG frame callback for camera handler.

        JPEG callback signature: (did: str, data: bytes, ts: int, channel: int)
        """
        frame_count = 0
        last_log_time = 0
        first_frame = True

        async def on_jpeg_frame(did: str, data: bytes, ts: int, channel: int):
            nonlocal frame_count, last_log_time, first_frame
            frame_count += 1

            # Log first frame received
            if first_frame:
                logger.info(f"[Detection] Camera {camera_id}: FIRST JPEG frame received, size={len(data) if data else 0} bytes")
                first_frame = False

            # Log every 30 seconds
            current_time = time.time()
            if current_time - last_log_time > 30:
                stats = processor.get_stats()
                logger.info(f"[Detection] Camera {camera_id}: received {frame_count} JPEG frames in last 30s, stats={stats}")
                frame_count = 0
                last_log_time = current_time

            # JPEG data is already decoded, just process it
            if data and len(data) > 1000:
                processor.add_frame(data, timestamp=ts / 1000.0)
            else:
                logger.warning(f"[Detection] Camera {camera_id}: skipping invalid JPEG frame, data_len={len(data) if data else 0}")

        return on_jpeg_frame

    def _on_detection_event(self, event: StreamDetectionEvent):
        """Handle detection event from stream processor."""
        try:
            self._stats['total_detections'] += len(event.detections)

            # Convert to WebSocket message format
            ws_message = self._event_to_ws_message(event)

            # Notify WebSocket callbacks
            for callback in self._ws_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(ws_message))
                    else:
                        callback(ws_message)
                except Exception as e:
                    logger.error(f"WebSocket callback error: {e}")

            # Notify event callbacks
            for callback in self._event_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(event))
                    else:
                        callback(event)
                except Exception as e:
                    logger.error(f"Event callback error: {e}")

        except Exception as e:
            logger.error(f"Error handling detection event: {e}")

    def _event_to_ws_message(self, event: StreamDetectionEvent) -> Dict:
        """Convert detection event to WebSocket message format."""
        return {
            'type': 'detection',
            'camera_id': event.camera_id,
            'timestamp': event.timestamp,
            'frame_id': event.frame_id,
            'event_type': event.event_type,
            'detections': [
                {
                    'class_id': d.class_id,
                    'class_name': d.class_name,
                    'confidence': round(d.confidence, 3),
                    'bbox': [round(x, 4) for x in d.bbox],
                    **({'extra': d.extra} if getattr(d, 'extra', None) else {}),
                }
                for d in event.detections
            ],
            'tracked_objects': [
                {
                    'track_id': t.track_id,
                    'class_name': t.class_name,
                    'hit_count': t.hit_count,
                    'duration': round(t.last_seen - t.first_seen, 2),
                    'avg_confidence': round(sum(t.confidence_history) / len(t.confidence_history), 3)
                        if t.confidence_history else 0,
                }
                for t in event.tracked_objects
            ],
            'snapshot_url': f"/api/detection/snapshot/{event.camera_id}/{event.timestamp}"
                if event.snapshot else None,
        }

    def register_ws_callback(self, callback: Callable[[Dict], None]):
        """Register a WebSocket callback for real-time events."""
        if callback not in self._ws_callbacks:
            self._ws_callbacks.append(callback)

    def unregister_ws_callback(self, callback: Callable[[Dict], None]):
        """Unregister a WebSocket callback."""
        if callback in self._ws_callbacks:
            self._ws_callbacks.remove(callback)

    def register_event_callback(self, callback: Callable[[StreamDetectionEvent], None]):
        """Register a detection event callback."""
        if callback not in self._event_callbacks:
            self._event_callbacks.append(callback)

    def unregister_event_callback(self, callback: Callable[[StreamDetectionEvent], None]):
        """Unregister a detection event callback."""
        if callback in self._event_callbacks:
            self._event_callbacks.remove(callback)

    def get_active_cameras(self) -> List[str]:
        """Get list of cameras with active detection."""
        return list(self._processors.keys())

    def get_camera_stats(self, camera_id: str) -> Optional[Dict]:
        """Get statistics for a specific camera."""
        if camera_id not in self._processors:
            return None
        return self._processors[camera_id].get_stats()

    def get_all_stats(self) -> Dict:
        """Get overall service statistics."""
        stats = self._stats.copy()
        stats['runtime_seconds'] = time.time() - stats['start_time']
        stats['camera_stats'] = {
            cid: proc.get_stats()
            for cid, proc in self._processors.items()
        }
        return stats

    def update_config(
        self,
        camera_id: str,
        config: Dict
    ) -> bool:
        """Update configuration for a camera stream.

        Args:
            camera_id: Camera identifier
            config: Configuration dict with optional keys:
                - confidence_threshold: Detection confidence threshold
                - process_fps: Target processing FPS

        Returns:
            True if updated successfully
        """
        try:
            # Update detector confidence threshold if provided
            if 'confidence_threshold' in config and self._object_detector:
                self._object_detector.config.confidence_threshold = config['confidence_threshold']
                logger.info(f"[Detection] Updated confidence_threshold to {config['confidence_threshold']}")

            # Update stream processor config if camera is active
            if camera_id in self._processors:
                processor = self._processors[camera_id]
                processor_config = {}

                if 'process_fps' in config:
                    processor_config['process_fps'] = config['process_fps']

                if processor_config:
                    processor.update_config(processor_config)

                logger.info(f"[Detection] Configuration updated for camera {camera_id}: {config}")
            else:
                logger.debug(f"[Detection] Camera {camera_id} not active, config will apply on next start")

            return True
        except Exception as e:
            logger.error(f"[Detection] Error updating config for camera {camera_id}: {e}")
            return False

    def is_running(self) -> bool:
        """Check if service is running."""
        return self._running

    def get_detector_info(self) -> Dict:
        """Get information about the detector."""
        if not self._object_detector:
            return {}

        return {
            'initialized': self._object_detector.is_initialized(),
            'device': self._object_detector._device if hasattr(self._object_detector, '_device') else 'unknown',
            'input_size': self._object_detector.config.input_size if self._object_detector.config else None,
            'confidence_threshold': self._object_detector.config.confidence_threshold if self._object_detector.config else 0.5,
        }


# Singleton instance
detection_service = DetectionService()


async def get_detection_service() -> DetectionService:
    """Get the detection service singleton."""
    return detection_service
