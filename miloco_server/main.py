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
    habit_router,
    ha_router,
    mcp_router,
    memory_router,
    miot_router,
    model_router,
    openai_compat_router,
    recording_router,
    trigger_router,
    web_router,
    xiaomi_bridge_router,
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
app.include_router(xiaomi_bridge_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(habit_router, prefix="/api")
app.include_router(recording_router, prefix="/api")


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

    # Initialize recording service
    await _init_recording_service()

    # Initialize memory service
    await _init_memory_service()

    # Initialize Xiaomi bridge
    await _init_xiaomi_bridge()

    # Auto-initialize MIoT after startup (if logged in)
    await _init_miot_after_startup()

    # Initialize habit learning system
    await _init_habit_learning()

    logger.info("=" * 50)


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


async def _init_memory_service():
    """Initialize the memory management service."""
    try:
        from miloco_server.service.memory_service import MemoryService, set_memory_service

        service = MemoryService()
        success = await service.initialize()
        if success:
            set_memory_service(service)
            logger.info("Memory service initialized successfully")
        else:
            logger.warning("Memory service initialization failed - memory features will be unavailable")

    except Exception as e:
        logger.error(f"Memory service initialization error: {e}")


async def _init_recording_service():
    """Initialize the recording service (RecordEngine)."""
    try:
        from miloco_server.record_engine import init_record_engine

        engine = await init_record_engine()

        # Register detection event callback for person-mode recording
        try:
            from miloco_server.detection.detection_service import get_detection_service
            from miloco_server.detection.stream_processor import StreamDetectionEvent

            detection_service = await get_detection_service()

            async def on_detection_event_for_recording(event: StreamDetectionEvent):
                """Forward person detection events to recording engine."""
                has_person = False
                if event.detections:
                    has_person = any(
                        d.class_name.lower() in ("person", "people")
                        for d in event.detections
                    )
                if has_person:
                    await engine.on_person_detected(event.camera_id)
                else:
                    await engine.on_person_lost(event.camera_id)

            detection_service.register_event_callback(on_detection_event_for_recording)
            logger.info("RecordEngine registered with detection service for person-mode triggers")
        except Exception as e:
            logger.warning("Could not register RecordEngine with detection service: %s", e)

        logger.info("RecordEngine initialized successfully")

    except Exception as e:
        logger.error(f"RecordEngine initialization error: {e}")


async def _init_xiaomi_bridge():
    """Initialize Xiaomi speaker bridge."""
    try:
        from miloco_server.xiaomi_bridge.config import BridgeConfig
        from miloco_server.xiaomi_bridge.manager import init_bridge

        config = BridgeConfig.from_database()
        if not config.enabled:
            logger.info("Xiaomi bridge disabled, skipping initialization")
            return

        await init_bridge(config)
        logger.info("Xiaomi bridge initialized successfully")

    except Exception as e:
        logger.error(f"Xiaomi bridge initialization error: {e}")


async def _init_miot_after_startup():
    """Auto-initialize MIoT devices and MCP clients after startup."""
    try:
        manager = get_manager()
        miot_proxy = manager.miot_proxy

        # Check if already logged in
        if not miot_proxy._oauth_info:
            logger.info("MIoT not logged in, skipping auto-initialization")
            return

        logger.info("Auto-initializing MIoT after startup...")

        # 1. Refresh token if needed
        try:
            await miot_proxy._check_and_refresh_token()
            logger.info("MIoT token check completed")
        except Exception as e:
            logger.warning("MIoT token refresh failed: %s", e)

        # 2. Refresh device info (including cameras)
        try:
            await miot_proxy.refresh_miot_info()
            logger.info("MIoT devices refreshed successfully")
        except Exception as e:
            logger.warning("MIoT devices refresh failed: %s", e)

        # 2.5. Register camera handlers with RecordEngine
        # This must be after MIoT refresh (cameras exist) and after RecordEngine init
        try:
            from miloco_server.record_engine import get_record_engine
            engine = get_record_engine()
            for camera_id, handler in miot_proxy._camera_img_managers.items():
                await engine.register_camera_handler(camera_id, handler)
            logger.info("Registered %d camera handlers with RecordEngine", len(miot_proxy._camera_img_managers))
        except Exception as e:
            logger.warning("Could not register cameras with RecordEngine: %s", e)

        # 3. Initialize MCP clients (MIoT scenarios etc)
        try:
            mcp_service = manager.mcp_service
            if hasattr(mcp_service, 'init_miot_mcp_clients'):
                await mcp_service.init_miot_mcp_clients()
                logger.info("MCP MIoT clients initialized")
        except Exception as e:
            logger.warning("MCP MIoT clients initialization failed: %s", e)

        # 4. Initialize enabled detection rules (must be after MIoT device refresh)
        try:
            logger.info("Initializing detection rules after MIoT startup...")
            await manager.trigger_rule_service.initialize_detection_on_startup()
        except Exception as e:
            logger.error(f"Failed to initialize detection on startup: {e}")

        logger.info("Auto-initialization completed")

    except Exception as e:
        logger.error("Auto-initialization failed: %s", e)


async def _init_habit_learning():
    """Initialize habit learning and decision engine."""
    try:
        from miloco_server.config.normal_config import HABIT_LEARNING_CONFIG, save_habit_config_enabled
        if not HABIT_LEARNING_CONFIG:
            logger.info("Habit learning config not found, skipping")
            return
        if not HABIT_LEARNING_CONFIG.get("enabled", False):
            has_sub = any(HABIT_LEARNING_CONFIG.get(k) for k in ("context_entities", "collector", "learner", "decision_engine"))
            if has_sub:
                logger.info("Habit learning 'enabled' field missing but sub-configs exist, auto-enabling")
                save_habit_config_enabled()
            else:
                logger.info("Habit learning disabled, skipping")
                return

        from miloco_server.utils.database import get_db_connector
        from miloco_server.dao.habit_dao import HabitDAO
        from miloco_server.service.habit_collector import HabitCollector
        from miloco_server.service.behavior_learner import BehaviorLearner
        from miloco_server.service.risk_assessor import RiskAssessor
        from miloco_server.service.decision_engine import DecisionEngine
        from miloco_server.service.model_trainer import ModelTrainer
        from miloco_server.service.context_provider import ContextProvider

        db = get_db_connector()
        habit_dao = HabitDAO(db)
        habit_dao.initialize()

        from miloco_server.service.manager import get_manager
        manager = get_manager()

        ctx_entities = HABIT_LEARNING_CONFIG.get("context_entities", {})
        ctx_provider = ContextProvider(ha_listener=manager.ha_listener, context_entities=ctx_entities)

        collector_config = HABIT_LEARNING_CONFIG.get("collector", {})
        collector = HabitCollector(
            habit_dao=habit_dao,
            flush_interval=collector_config.get("flush_interval", 5),
            context_provider=ctx_provider,
        )
        await collector.start()

        learner_config = HABIT_LEARNING_CONFIG.get("learner", {})
        learner = BehaviorLearner(
            habit_dao=habit_dao,
            min_occurrences=learner_config.get("min_occurrences", 3),
            time_bucket_minutes=learner_config.get("time_bucket_minutes", 30),
        )
        learner.set_context_provider(ctx_provider)

        # Start model trainer (periodic re-learning and data cleanup)
        trainer = ModelTrainer(behavior_learner=learner, habit_dao=habit_dao)
        learn_interval = learner_config.get("learn_interval", 3600)
        retention_config = HABIT_LEARNING_CONFIG.get("data_retention", {})
        events_retention = retention_config.get("events_days", 90)
        patterns_retention = retention_config.get("patterns_days", 180)
        cleanup_interval = retention_config.get("cleanup_interval", 86400)
        await trainer.start(
            learn_interval=learn_interval,
            events_retention_days=events_retention,
            patterns_retention_days=patterns_retention,
            cleanup_interval=cleanup_interval,
        )

        # Always create DecisionEngine (start loop only if enabled)
        de_config = HABIT_LEARNING_CONFIG.get("decision_engine", {})
        assessor = RiskAssessor()
        engine = DecisionEngine(
            behavior_learner=learner,
            risk_assessor=assessor,
            ha_proxy=manager.ha_proxy,
            cycle_interval=de_config.get("cycle_interval", 60),
            confidence_threshold=de_config.get("confidence_threshold", 0.65),
            risk_level_limit=de_config.get("risk_level_limit", "HIGH"),
            context_provider=ctx_provider,
        )

        try:
            from miloco_server.xiaomi_bridge.manager import get_bridge_manager
            engine.bridge_manager = get_bridge_manager()
        except Exception:
            pass

        if hasattr(manager, 'wakeup_scheduler'):
            engine.wakeup_scheduler = manager.wakeup_scheduler

        if de_config.get("enabled", False):
            await engine.start()
            logger.info("Decision engine started")
        else:
            logger.info("Decision engine created (not started, waiting for enable)")

        logger.info("Habit learning system initialized")

    except Exception as e:
        logger.error("Habit learning initialization error: %s", e)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup operations when application shuts down"""
    logger.info("Application is shutting down...")

    # Shutdown habit learning
    try:
        from miloco_server.service.habit_collector import HabitCollector
        from miloco_server.service.decision_engine import DecisionEngine
        from miloco_server.service.model_trainer import ModelTrainer

        collector = HabitCollector.get_instance()
        if collector:
            await collector.stop()

        engine = DecisionEngine.get_instance()
        if engine:
            await engine.stop()

        logger.info("Habit learning shutdown completed")
    except Exception as e:
        logger.error(f"Habit learning shutdown error: {e}")

    # Shutdown Xiaomi bridge
    try:
        from miloco_server.xiaomi_bridge.manager import get_bridge_manager
        bridge_manager = get_bridge_manager()
        await bridge_manager.stop()
        logger.info("Xiaomi bridge shutdown completed")
    except Exception as e:
        logger.error(f"Xiaomi bridge shutdown error: {e}")

    # Shutdown memory service
    try:
        from miloco_server.memory.memory_manager import get_memory_manager
        memory_manager = get_memory_manager()
        if memory_manager:
            await memory_manager.shutdown()
            logger.info("Memory service shutdown completed")
    except Exception as e:
        logger.error(f"Memory service shutdown error: {e}")

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

    # Shutdown recording service
    try:
        from miloco_server.record_engine import get_record_engine
        engine = get_record_engine()
        await engine.shutdown()
        logger.info("RecordEngine shutdown completed")
    except Exception as e:
        logger.error(f"RecordEngine shutdown error: {e}")

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