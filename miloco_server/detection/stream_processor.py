# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Stream processor for real-time video stream analysis.
Processes frames from cameras and runs object detection.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple
from collections import deque

import numpy as np

from miloco_server.detection.detector import (
    DetectionConfig,
    DetectionResult,
    FrameDetectionResult,
    ObjectDetector,
)

logger = logging.getLogger(__name__)


@dataclass
class StreamConfig:
    """Configuration for stream processing."""
    camera_id: str
    camera_name: str = ""
    process_fps: float = 5.0  # Target processing FPS (lower = less CPU)
    min_detection_interval: float = 0.5  # Minimum seconds between detections
    enable_tracking: bool = True  # Enable object tracking
    detection_zones: List[Dict] = field(default_factory=list)  # ROI zones
    confidence_thresholds: Dict[str, float] = field(default_factory=dict)


@dataclass
class TrackedObject:
    """Tracked object across frames."""
    track_id: int
    class_name: str
    last_bbox: Tuple[float, float, float, float]
    last_seen: float
    first_seen: float
    hit_count: int = 0
    confidence_history: List[float] = field(default_factory=list)


@dataclass
class StreamDetectionEvent:
    """Detection event for a stream."""
    camera_id: str
    timestamp: float
    frame_id: int
    detections: List[DetectionResult]
    tracked_objects: List[TrackedObject]
    event_type: str = "detection"  # detection, enter, leave
    snapshot: Optional[bytes] = None  # JPEG snapshot


class ObjectTracker:
    """Simple IoU-based object tracker."""

    def __init__(self, iou_threshold: float = 0.3, max_age: float = 2.0):
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self.tracks: Dict[int, TrackedObject] = {}
        self.next_id = 0

    def update(self, detections: List[DetectionResult], timestamp: float) -> List[TrackedObject]:
        """Update tracks with new detections."""
        # Remove old tracks
        self._remove_old_tracks(timestamp)

        if not detections:
            return list(self.tracks.values())

        # Match detections to existing tracks
        matched_tracks = set()
        matched_dets = set()

        for det in detections:
            best_iou = 0
            best_track_id = None

            for track_id, track in self.tracks.items():
                if track_id in matched_tracks:
                    continue
                if track.class_name != det.class_name:
                    continue

                iou = self._calculate_iou(track.last_bbox, det.bbox)
                if iou > best_iou and iou >= self.iou_threshold:
                    best_iou = iou
                    best_track_id = track_id

            if best_track_id is not None:
                # Update existing track
                track = self.tracks[best_track_id]
                track.last_bbox = det.bbox
                track.last_seen = timestamp
                track.hit_count += 1
                track.confidence_history.append(det.confidence)
                if len(track.confidence_history) > 10:
                    track.confidence_history.pop(0)
                matched_tracks.add(best_track_id)
                matched_dets.add(id(det))
            else:
                # Create new track
                self.next_id += 1
                new_track = TrackedObject(
                    track_id=self.next_id,
                    class_name=det.class_name,
                    last_bbox=det.bbox,
                    last_seen=timestamp,
                    first_seen=timestamp,
                    hit_count=1,
                    confidence_history=[det.confidence]
                )
                self.tracks[self.next_id] = new_track

        return list(self.tracks.values())

    def _remove_old_tracks(self, current_time: float):
        """Remove tracks that haven't been seen recently."""
        to_remove = [
            track_id for track_id, track in self.tracks.items()
            if current_time - track.last_seen > self.max_age
        ]
        for track_id in to_remove:
            del self.tracks[track_id]

    def _calculate_iou(self, box1: Tuple[float, ...], box2: Tuple[float, ...]) -> float:
        """Calculate IoU between two bounding boxes."""
        x1_1, y1_1, x2_1, y2_1 = box1
        x1_2, y1_2, x2_2, y2_2 = box2

        # Calculate intersection
        xi1 = max(x1_1, x1_2)
        yi1 = max(y1_1, y1_2)
        xi2 = min(x2_1, x2_2)
        yi2 = min(y2_1, y2_2)

        if xi2 <= xi1 or yi2 <= yi1:
            return 0.0

        intersection = (xi2 - xi1) * (yi2 - yi1)

        # Calculate union
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection

        if union <= 0:
            return 0.0

        return intersection / union

    def reset(self):
        """Reset all tracks."""
        self.tracks.clear()
        self.next_id = 0


class StreamProcessor:
    """
    Processes video streams and runs object detection.
    Optimized for real-time performance with configurable FPS.
    """

    def __init__(
        self,
        config: StreamConfig,
        detector: ObjectDetector,
        event_callback: Optional[Callable[[StreamDetectionEvent], None]] = None
    ):
        self.config = config
        self.detector = detector
        self.event_callback = event_callback

        self._running = False
        self._frame_queue: asyncio.Queue = asyncio.Queue(maxsize=10)
        self._task: Optional[asyncio.Task] = None
        self._last_detection_time = 0.0
        self._frame_count = 0
        self._loop: Optional[asyncio.AbstractEventLoop] = None  # Store event loop for thread safety

        self._tracker = ObjectTracker() if config.enable_tracking else None
        self._recent_frames = deque(maxlen=30)  # Keep recent frames for snapshots

        # Statistics
        self._stats = {
            'frames_processed': 0,
            'frames_received': 0,
            'detections_made': 0,
            'avg_inference_time': 0.0,
            'start_time': 0.0,
        }

    async def start(self):
        """Start the stream processor."""
        if self._running:
            return

        self._running = True
        self._loop = asyncio.get_running_loop()  # Store event loop for thread-safe operations
        self._stats['start_time'] = time.time()
        self._task = asyncio.create_task(self._process_loop())
        logger.info(f"[StreamProcessor] Started for camera {self.config.camera_id}, loop={id(self._loop)}")

    async def stop(self):
        """Stop the stream processor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # Clear queue
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        if self._tracker:
            self._tracker.reset()

        logger.info(f"Stream processor stopped for camera {self.config.camera_id}")

    def is_running(self) -> bool:
        """Check if processor is running."""
        return self._running

    def add_frame(self, frame_data: bytes, timestamp: Optional[float] = None):
        """
        Add a frame to be processed.
        NOTE: This method is thread-safe and can be called from any thread.

        Args:
            frame_data: JPEG encoded frame bytes
            timestamp: Frame timestamp (defaults to current time)
        """
        import threading
        current_thread = threading.current_thread().name

        if not self._running:
            logger.debug(f"[StreamProcessor] Cannot add frame, not running for camera {self.config.camera_id}")
            return

        # Log first frame at INFO level, subsequent frames at DEBUG
        if self._stats['frames_received'] == 0:
            logger.info(f"[StreamProcessor] First frame received for camera {self.config.camera_id}, size={len(frame_data)}")
        else:
            logger.debug(f"[StreamProcessor] Frame received for camera {self.config.camera_id}, size={len(frame_data)}")

        # Use thread-safe queue operation via run_coroutine_threadsafe
        try:
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._enqueue_frame_coro(frame_data, timestamp or time.time()),
                    self._loop
                )
            else:
                logger.warning(f"[StreamProcessor] Event loop not available for camera {self.config.camera_id}, dropping frame")
        except Exception as e:
            logger.error(f"[StreamProcessor] Error scheduling frame enqueue: {e}")

    async def _enqueue_frame_coro(self, frame_data: bytes, timestamp: float):
        """Coroutine to enqueue frame - runs in event loop thread."""
        try:
            # Drop oldest frame if queue is full
            if self._frame_queue.full():
                try:
                    self._frame_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass

            self._frame_queue.put_nowait((frame_data, timestamp))
            self._stats['frames_received'] += 1
        except asyncio.QueueFull:
            pass
        except Exception as e:
            logger.error(f"[StreamProcessor] Error enqueueing frame: {e}")

    async def _process_loop(self):
        """Main processing loop."""
        frame_interval = 1.0 / self.config.process_fps
        last_process_time = 0.0
        last_frame_received_time = time.time()

        logger.info(f"[StreamProcessor] Process loop started for camera {self.config.camera_id}, fps={self.config.process_fps}")

        while self._running:
            try:
                # Wait for next frame with timeout
                frame_data, timestamp = await asyncio.wait_for(
                    self._frame_queue.get(),
                    timeout=1.0
                )

                last_frame_received_time = time.time()
                current_time = time.time()

                # Rate limiting - skip frames if processing too fast
                if current_time - last_process_time < frame_interval:
                    continue

                # Check minimum detection interval
                if current_time - self._last_detection_time < self.config.min_detection_interval:
                    continue

                last_process_time = current_time
                await self._process_frame(frame_data, timestamp)

            except asyncio.TimeoutError:
                # Only warn if actually no frames received for 30s
                no_frame_duration = time.time() - last_frame_received_time
                if no_frame_duration > 30:
                    logger.warning(f"[StreamProcessor] No frames received for {no_frame_duration:.0f}s for camera {self.config.camera_id}")
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in process loop: {e}")
                await asyncio.sleep(0.1)

    async def _process_frame(self, frame_data: bytes, timestamp: float):
        """Process a single frame."""
        try:
            # Store frame for potential snapshot
            self._recent_frames.append((frame_data, timestamp))

            # Run detection
            logger.debug(f"Processing frame {self._stats['frames_processed'] + 1}, frame_size={len(frame_data)} bytes")
            result = self.detector.detect(frame_data)
            if result.detections:
                logger.info(f"Frame {self._stats['frames_processed'] + 1}: detected {len(result.detections)} objects, inference_time={result.inference_time_ms:.1f}ms")
            else:
                logger.debug(f"Frame {self._stats['frames_processed'] + 1}: no detections, inference_time={result.inference_time_ms:.1f}ms")

            self._stats['frames_processed'] += 1
            self._last_detection_time = time.time()

            if result.detections:
                self._stats['detections_made'] += len(result.detections)

                # Update tracking
                tracked_objects = []
                if self._tracker:
                    tracked_objects = self._tracker.update(result.detections, timestamp)

                # Create snapshot with bounding boxes
                snapshot = await self._create_snapshot(frame_data, result.detections)

                # Create and emit event
                event = StreamDetectionEvent(
                    camera_id=self.config.camera_id,
                    timestamp=timestamp,
                    frame_id=result.frame_id,
                    detections=result.detections,
                    tracked_objects=tracked_objects,
                    snapshot=snapshot
                )

                if self.event_callback:
                    try:
                        if asyncio.iscoroutinefunction(self.event_callback):
                            await self.event_callback(event)
                        else:
                            self.event_callback(event)
                    except Exception as e:
                        logger.error(f"Event callback error: {e}")

            # Update average inference time
            if result.inference_time_ms > 0:
                n = self._stats['frames_processed']
                self._stats['avg_inference_time'] = (
                    (self._stats['avg_inference_time'] * (n - 1) + result.inference_time_ms) / n
                )

        except Exception as e:
            logger.error(f"Frame processing error: {e}")

    async def _create_snapshot(
        self,
        frame_data: bytes,
        detections: List[DetectionResult]
    ) -> Optional[bytes]:
        """Create a snapshot image with bounding boxes."""
        try:
            import cv2

            # Decode frame
            frame = cv2.imdecode(np.frombuffer(frame_data, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                return None

            h, w = frame.shape[:2]

            # Colors for different classes
            colors = {
                'person': (0, 255, 0),  # Green
                'cat': (255, 0, 0),     # Blue
                'dog': (0, 0, 255),     # Red
                'face': (0, 255, 255),   # Yellow/Cyan
            }

            # Draw bounding boxes
            for det in detections:
                color = colors.get(det.class_name, (255, 255, 255))

                # Get pixel coordinates
                if det.bbox_px:
                    x1, y1, x2, y2 = det.bbox_px
                else:
                    x1, y1, x2, y2 = (
                        int(det.bbox[0] * w),
                        int(det.bbox[1] * h),
                        int(det.bbox[2] * w),
                        int(det.bbox[3] * h)
                    )

                # Draw rectangle
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                # Draw label
                label = f"{det.class_name}: {det.confidence:.2f}"
                label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
                cv2.rectangle(
                    frame,
                    (x1, y1 - label_size[1] - 4),
                    (x1 + label_size[0], y1),
                    color,
                    -1
                )
                cv2.putText(
                    frame, label,
                    (x1, y1 - 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (255, 255, 255), 2
                )

            # Encode to JPEG
            _, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return encoded.tobytes()

        except Exception as e:
            logger.warning(f"Failed to create snapshot: {e}")
            return None

    def get_stats(self) -> Dict:
        """Get processing statistics."""
        stats = self._stats.copy()
        if stats['start_time'] > 0:
            stats['runtime_seconds'] = time.time() - stats['start_time']
            if stats['runtime_seconds'] > 0:
                stats['fps'] = stats['frames_processed'] / stats['runtime_seconds']
        return stats

    def reset_stats(self):
        """Reset statistics."""
        self._stats = {
            'frames_processed': 0,
            'frames_received': 0,
            'detections_made': 0,
            'avg_inference_time': 0.0,
            'start_time': time.time(),
        }

    def update_config(self, config: Dict) -> bool:
        """
        Update stream processor configuration dynamically.

        Args:
            config: Configuration dict with optional keys:
                - process_fps: Target processing FPS
                - min_detection_interval: Minimum seconds between detections
                - confidence_threshold: Detection confidence threshold (passed to detector)

        Returns:
            True if updated successfully
        """
        try:
            if 'process_fps' in config:
                self.config.process_fps = config['process_fps']
                logger.info(f"[StreamProcessor] Camera {self.config.camera_id}: updated process_fps to {config['process_fps']}")

            if 'min_detection_interval' in config:
                self.config.min_detection_interval = config['min_detection_interval']
                logger.info(f"[StreamProcessor] Camera {self.config.camera_id}: updated min_detection_interval to {config['min_detection_interval']}")

            return True
        except Exception as e:
            logger.error(f"[StreamProcessor] Error updating config for camera {self.config.camera_id}: {e}")
            return False
