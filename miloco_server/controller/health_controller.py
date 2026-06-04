# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Health check controller
Provides health check endpoints for container orchestration and monitoring
"""

import time
from datetime import datetime
from fastapi import APIRouter
from ..config.normal_config import APP_CONFIG, SERVER_CONFIG

router = APIRouter(tags=["Health"])

# Track server start time
_server_start_time = time.time()


@router.get("/health")
async def health_check():
    """
    Health check endpoint for container orchestration (Docker, Kubernetes, etc.)
    
    Returns:
        dict: Health status with service information
    """
    uptime_seconds = int(time.time() - _server_start_time)
    
    return {
        "status": "healthy",
        "service": APP_CONFIG.get("service_name", "miloco-server"),
        "version": APP_CONFIG.get("version", "unknown"),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "uptime_seconds": uptime_seconds,
        "port": SERVER_CONFIG.get("port", 8000)
    }


@router.get("/health/ready")
async def readiness_check():
    """
    Readiness check endpoint
    Indicates whether the service is ready to accept requests
    
    Returns:
        dict: Readiness status
    """
    return {
        "status": "ready",
        "service": APP_CONFIG.get("service_name", "miloco-server"),
        "version": APP_CONFIG.get("version", "unknown")
    }


@router.get("/health/live")
async def liveness_check():
    """
    Liveness check endpoint
    Indicates whether the service is alive (basic health check)
    
    Returns:
        dict: Liveness status
    """
    return {
        "status": "alive"
    }
