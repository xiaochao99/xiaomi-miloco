# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
MILOCO Server main application entry point.
Provides FastAPI application setup, middleware configuration, and server startup.
"""

import logging
import threading
import time
import webbrowser

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from miloco_server.config import APP_CONFIG, IMAGE_DIR, SERVER_CONFIG, STATIC_DIR
from miloco_server.controller import (
    api_token_router,
    auth_router,
    chat_router,
    detection_router,
    face_recognition_router,
    ha_router,
    mcp_router,
    miot_router,
    model_router,
    openai_compat_router,
    trigger_router,
    web_router,
)
from miloco_server.middleware.auth_middleware import AuthStaticFiles
from miloco_server.middleware.exception_handler import handle_exception
from miloco_server.service.manager import get_manager
from miloco_server.utils.database import init_database
from miloco_server.utils.normal_util import get_uvicorn_log_config, update_localhost_cert

logger = logging.getLogger(__name__)

app = FastAPI(
    title=APP_CONFIG["title"],
    description=APP_CONFIG["description"],
    version=APP_CONFIG["version"]
)


@app.middleware("http")
async def catch_all_exceptions_middleware(request: Request, call_next):
    """Global exception handling middleware"""
    try:
        return await call_next(request)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return handle_exception(request, exc)


app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")
app.mount("/static/camera/images", AuthStaticFiles(directory=str(IMAGE_DIR)), name="images")
app.include_router(web_router)
app.include_router(auth_router, prefix="/api")
app.include_router(miot_router, prefix="/api")
app.include_router(ha_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(trigger_router, prefix="/api")
app.include_router(model_router, prefix="/api")
app.include_router(mcp_router, prefix="/api")
app.include_router(api_token_router, prefix="/api")
app.include_router(detection_router, prefix="/api")
app.include_router(face_recognition_router, prefix="/api")
app.include_router(openai_compat_router)


@app.get("/{full_path:path}")
async def spa_handler(full_path: str):
    """SPA route handler - catch all unmatched GET requests"""
    if full_path.startswith("api/"):
        return Response(status_code=404, content="404 Not Found")

    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    else:
        return Response(status_code=404, content="404 Not Found")


@app.on_event("startup")
async def startup_event():
    """Application initialization operations on startup"""
    logger.info("Initializing application...")

    try:
        init_database()
        logger.info("Database initialization completed")
    except Exception as e:
        logger.error("Database initialization failed: %s", e)
        raise

    logger.info("Application initialization completed")

    try:
        await get_manager().initialize(callback=open_browser_async)
        logger.info("Manager initialization completed")
    except Exception as e:
        logger.error("Manager initialization failed: %s", e)
        raise

    # Initialize detection service
    await _init_detection_service()

    # 启动后自动初始化 MIoT（如果已登录）
    await _init_miot_after_startup()


async def _init_detection_service():
    """Initialize the real-time detection service."""
    try:
        from miloco_server.detection.detection_service import get_detection_service
        from miloco_server.detection.websocket_handler import ws_manager

        service = await get_detection_service()
        success = await service.initialize()

        if success:
            await ws_manager.start()
            logger.info("Detection service initialized successfully")
        else:
            logger.warning("Detection service initialization failed - detection features will be unavailable")

    except Exception as e:
        logger.error(f"Detection service initialization error: {e}")


async def _init_miot_after_startup():
    """启动后自动初始化 MIoT 设备和 MCP 客户端"""
    try:
        manager = get_manager()
        miot_proxy = manager.miot_proxy

        # 检查是否已登录
        if not miot_proxy._oauth_info:
            logger.info("MIoT not logged in, skipping auto-initialization")
            return

        logger.info("Auto-initializing MIoT after startup...")

        # 1. 刷新 token（如果需要）
        try:
            await miot_proxy._check_and_refresh_token()
            logger.info("MIoT token check completed")
        except Exception as e:
            logger.warning("MIoT token refresh failed: %s", e)

        # 2. 刷新设备信息（包括摄像头）
        try:
            await miot_proxy.refresh_miot_info()
            logger.info("MIoT devices refreshed successfully")
        except Exception as e:
            logger.warning("MIoT devices refresh failed: %s", e)

        # 3. 初始化 MCP 客户端（MIoT 场景等）
        try:
            mcp_service = manager.mcp_service
            if hasattr(mcp_service, 'init_miot_mcp_clients'):
                await mcp_service.init_miot_mcp_clients()
                logger.info("MCP MIoT clients initialized")
        except Exception as e:
            logger.warning("MCP MIoT clients initialization failed: %s", e)

        # 4. 初始化已启用的目标检测规则（必须在 MIoT 设备刷新后）
        try:
            logger.info("Initializing detection rules after MIoT startup...")
            await manager.trigger_rule_service.initialize_detection_on_startup()
        except Exception as e:
            logger.error(f"Failed to initialize detection on startup: {e}")

        logger.info("Auto-initialization completed")

    except Exception as e:
        logger.error("Auto-initialization failed: %s", e)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup operations when application shuts down"""
    logger.info("Application is shutting down...")

    # Shutdown detection service
    try:
        from miloco_server.detection.detection_service import get_detection_service
        from miloco_server.detection.websocket_handler import ws_manager

        await ws_manager.stop()

        service = await get_detection_service()
        await service.destroy()
        logger.info("Detection service shutdown completed")
    except Exception as e:
        logger.error(f"Detection service shutdown error: {e}")

    logger.info("Application has been shut down")


def _open_browser():
    """Delayed browser opening"""
    time.sleep(2)
    port = SERVER_CONFIG["port"]
    url = f"https://127.0.0.1:{port}"
    webbrowser.open(url)


def open_browser_async():
    """Open browser asynchronously"""
    browser_thread = threading.Thread(target=_open_browser)
    browser_thread.daemon = True
    browser_thread.start()


def start_server():
    """Start server and automatically open browser"""
    logger.debug("Debug log test - if you see this message, debug logging is enabled")
    logger.info("Starting Miloco server...")

    log_config = get_uvicorn_log_config()
    update_localhost_cert(cert_path=SERVER_CONFIG["ssl_certfile"], key_path=SERVER_CONFIG["ssl_keyfile"])

    uvicorn.run(
        app,
        host=SERVER_CONFIG["host"],
        port=SERVER_CONFIG["port"],
        log_level=SERVER_CONFIG["log_level"],
        log_config=log_config,
        ssl_certfile=SERVER_CONFIG["ssl_certfile"],
        ssl_keyfile=SERVER_CONFIG["ssl_keyfile"]
    )
