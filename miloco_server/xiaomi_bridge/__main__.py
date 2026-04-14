# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Xiaomi Bridge main entry point.

Reference: open-xiaoai-bridge/core/__main__.py
"""

import argparse
import asyncio
import logging
import os
import signal

from miloco_server.xiaomi_bridge.utils.config import ConfigManager
from miloco_server.xiaomi_bridge.utils.logger import logger


def init_logging(level: str = "INFO"):
    """Initialize logging."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
        ],
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Xiaomi Bridge")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to configuration file",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    parser.add_argument(
        "--no-miloco",
        action="store_true",
        help="Disable Miloco integration",
    )
    args = parser.parse_args()

    # Initialize logging
    init_logging(args.log_level)

    # Initialize config
    config = ConfigManager.instance()
    if args.config:
        config.load_config_from_file(args.config)

    # Ensure model directories exist
    model_dirs = ["models/asr", "models/kws", "models/vad"]
    for model_dir in model_dirs:
        os.makedirs(model_dir, exist_ok=True)

    logger.info("🚀 Starting Xiaomi Bridge...")

    try:
        # Initialize main app
        from miloco_server.xiaomi_bridge.main_app import MainApp
        app = MainApp.instance(enable_miloco=not args.no_miloco)
        app.run()

        # Start HTTP server
        start_http_server()

        # Wait indefinitely
        signal.pause()

    except KeyboardInterrupt:
        logger.info("👋 Received shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        # Cleanup
        if "app" in locals():
            app.shutdown()


async def _start_fastapi():
    """Start FastAPI server."""
    from fastapi import FastAPI
    from miloco_server.xiaomi_bridge.routes import api_router, websocket_router

    app = FastAPI(title="Xiaomi Bridge API", version="1.0")
    app.include_router(api_router)
    app.include_router(websocket_router)

    import uvicorn
    config = ConfigManager.instance()
    host = config.get_app_config("server.host", "0.0.0.0")
    port = config.get_app_config("server.port", 8000)

    logger.info(f"🌐 Starting HTTP server on {host}:{port}")
    await uvicorn.Server(
        uvicorn.Config(app, host=host, port=port)
    ).serve()


def start_http_server():
    """Start HTTP server in separate thread."""
    import threading
    thread = threading.Thread(
        target=lambda: asyncio.run(_start_fastapi()),
        daemon=True,
    )
    thread.start()


if __name__ == "__main__":
    main()