# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Detection controller for real-time object detection API endpoints.
Provides REST API and WebSocket endpoints for detection management.
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, Field

from miloco_server.detection.detection_service import get_detection_service, DetectionService
from miloco_server.detection.websocket_handler import ws_manager
from miloco_server.service.manager import get_manager

logger = logging.getLogger(__name__)

# Router
detection_router = APIRouter(prefix="/detection", tags=["detection"])


# Pydantic models
class DetectionConfigRequest(BaseModel):
    """Request model for updating detection configuration."""
    confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    process_fps: Optional[float] = Field(None, ge=1.0, le=30.0)
    min_detection_interval: Optional[float] = Field(None, ge=0.1, le=10.0)
    enable_tracking: Optional[bool] = None


class DetectionStartRequest(BaseModel):
    """Request model for starting detection."""
    camera_id: str
    config: Optional[DetectionConfigRequest] = None


class DetectionResponse(BaseModel):
    """Response model for detection operations."""
    success: bool
    message: str
    data: Optional[Dict] = None


class CameraDetectionStatus(BaseModel):
    """Status of detection for a camera."""
    camera_id: str
    active: bool
    stats: Optional[Dict] = None


# API Endpoints

@detection_router.post("/start", response_model=DetectionResponse)
async def start_detection(
    request: DetectionStartRequest,
    service: DetectionService = Depends(get_detection_service)
):
    """
    Start object detection for a camera.

    The camera must be already registered and streaming.
    """
    try:
        manager = get_manager()

        # Find camera handler through miot_proxy
        camera_handler = None
        camera_name = request.camera_id

        # Check in miot_proxy's camera managers
        miot_proxy = manager.miot_proxy
        if hasattr(miot_proxy, '_camera_img_managers') and request.camera_id in miot_proxy._camera_img_managers:
            camera_handler = miot_proxy._camera_img_managers[request.camera_id]
            if hasattr(camera_handler, 'camera_info'):
                camera_name = camera_handler.camera_info.name or request.camera_id

        if camera_handler is None:
            raise HTTPException(status_code=404, detail=f"Camera {request.camera_id} not found or not streaming")

        # Build config
        config = {}
        if request.config:
            if request.config.process_fps:
                config['process_fps'] = request.config.process_fps
            if request.config.min_detection_interval:
                config['min_detection_interval'] = request.config.min_detection_interval
            if request.config.enable_tracking is not None:
                config['enable_tracking'] = request.config.enable_tracking

        # Start detection
        success = await service.start_detection(
            camera_id=request.camera_id,
            camera_handler=camera_handler,
            camera_name=camera_name,
            config_override=config
        )

        if success:
            return DetectionResponse(
                success=True,
                message=f"Detection started for camera {request.camera_id}",
                data={"camera_id": request.camera_id, "camera_name": camera_name}
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to start detection")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting detection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@detection_router.post("/stop/{camera_id}", response_model=DetectionResponse)
async def stop_detection(
    camera_id: str,
    service: DetectionService = Depends(get_detection_service)
):
    """Stop object detection for a camera."""
    try:
        success = await service.stop_detection(camera_id)

        if success:
            return DetectionResponse(
                success=True,
                message=f"Detection stopped for camera {camera_id}",
                data={"camera_id": camera_id}
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to stop detection")

    except Exception as e:
        logger.error(f"Error stopping detection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@detection_router.get("/status", response_model=Dict)
async def get_detection_status(
    service: DetectionService = Depends(get_detection_service)
):
    """Get overall detection service status."""
    return {
        "active": service.is_running(),
        "detector_info": service.get_detector_info(),
        "active_cameras": service.get_active_cameras(),
        "stats": service.get_all_stats(),
    }


@detection_router.get("/cameras", response_model=List[CameraDetectionStatus])
async def get_camera_detection_status(
    service: DetectionService = Depends(get_detection_service)
):
    """Get detection status for all cameras."""
    manager = get_manager()
    cameras = []

    # Get all available cameras from miot_proxy
    all_cameras = set()
    miot_proxy = manager.miot_proxy

    if hasattr(miot_proxy, '_camera_img_managers'):
        all_cameras.update(miot_proxy._camera_img_managers.keys())

    active_cameras = set(service.get_active_cameras())

    for camera_id in all_cameras:
        cameras.append(CameraDetectionStatus(
            camera_id=camera_id,
            active=camera_id in active_cameras,
            stats=service.get_camera_stats(camera_id) if camera_id in active_cameras else None
        ))

    return cameras


@detection_router.get("/stats/{camera_id}", response_model=Dict)
async def get_camera_stats(
    camera_id: str,
    service: DetectionService = Depends(get_detection_service)
):
    """Get detection statistics for a specific camera."""
    stats = service.get_camera_stats(camera_id)

    if stats is None:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found or detection not active")

    return stats


@detection_router.post("/config/{camera_id}", response_model=DetectionResponse)
async def update_detection_config(
    camera_id: str,
    config: DetectionConfigRequest,
    service: DetectionService = Depends(get_detection_service)
):
    """Update detection configuration for a camera."""
    config_dict = config.dict(exclude_unset=True)

    success = service.update_config(camera_id, config_dict)

    if success:
        return DetectionResponse(
            success=True,
            message=f"Configuration updated for camera {camera_id}",
            data={"camera_id": camera_id, "config": config_dict}
        )
    else:
        raise HTTPException(status_code=500, detail="Failed to update configuration")


# WebSocket endpoints

@detection_router.websocket("/ws")
async def detection_websocket_global(websocket: WebSocket):
    """
    WebSocket endpoint for real-time detection events from all cameras.
    """
    await ws_manager.connect(websocket, camera_id=None)

    try:
        while True:
            # Receive and handle client messages
            message = await websocket.receive_json()
            await ws_manager.handle_client_message(websocket, message)

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await ws_manager.disconnect(websocket)


@detection_router.websocket("/ws/{camera_id}")
async def detection_websocket_camera(websocket: WebSocket, camera_id: str):
    """
    WebSocket endpoint for real-time detection events from a specific camera.
    """
    await ws_manager.connect(websocket, camera_id=camera_id)

    try:
        while True:
            message = await websocket.receive_json()
            await ws_manager.handle_client_message(websocket, message)

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, camera_id)
    except Exception as e:
        logger.error(f"WebSocket error for camera {camera_id}: {e}")
        await ws_manager.disconnect(websocket, camera_id)


# Snapshot endpoint

@detection_router.get("/snapshot/{camera_id}/{timestamp}")
async def get_detection_snapshot(
    camera_id: str,
    timestamp: float,
    service: DetectionService = Depends(get_detection_service)
):
    """
    Get a detection snapshot image.
    Note: This is a placeholder - snapshots should be stored and served via the image manager.
    """
    # For now, return a placeholder response
    # In production, you'd store snapshots and serve them
    raise HTTPException(status_code=501, detail="Snapshot storage not yet implemented")
