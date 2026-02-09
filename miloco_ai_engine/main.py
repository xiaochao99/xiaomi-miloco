# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
LLaMA-MICO AI Engine for MICO Server
Provides FastAPI application for AI model management and chat completions.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from miloco_ai_engine.config.config import APP_CONFIG, LOGGING_CONFIG, SERVER_CONFIG
from miloco_ai_engine.middleware.exception_handler import handle_exception
from miloco_ai_engine.middleware.exceptions import ModelManagerException
from miloco_ai_engine.model_manager.model_manager import ModelManager
from miloco_ai_engine.schema.models_schema import (
    ChatCompletionRequest,
    ModelDescription,
    ModelDescriptionListRespone,
    ModelListResponse,
    StreamErrorChunk,
    StreamErrorChunkMessage,
    VramUsage,
)
from miloco_ai_engine.utils.utils import get_uvicorn_log_config

logger = logging.getLogger(__name__)

model_manager: Optional[ModelManager] = None


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI): # pylint: disable=unused-argument
    """Application lifecycle management"""
    global model_manager
    ############ Startup ############
    logger.info("Starting LLaMA-MICO AI Engine HTTP Server...")
    try:
        # Initialize model manager
        model_manager = ModelManager()
        await model_manager.start()
        logger.info("Model manager started successfully")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Server startup failed: %s", e)
        raise e

    logger.info("Server startup complete, ready to serve requests")
    yield
    ############ Shutdown ############
    logger.info("Shutting down server...")
    if model_manager:
        await model_manager.stop()
    logger.info("Server shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=APP_CONFIG["title"],
    description=APP_CONFIG["description"],
    version=APP_CONFIG["version"],
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def check_model_manager_middleware(request: Request, call_next):
    """Check if model manager is started"""
    # Paths that don't require model manager check
    excluded_paths = {"/", "/docs"}

    if request.url.path not in excluded_paths:
        if not model_manager:
            logger.error("Model manager not started")
            raise ModelManagerException("Model manager not started")

    response = await call_next(request)
    return response


@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    return handle_exception(request, exc)


@app.get("/")
async def root():
    """Root endpoint, returns server information"""
    return {
        "message": "LLaMA-MICO  AI Engine Server",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/v1/models", response_model=ModelListResponse)
async def list_models():
    """Get available model list"""
    models = []
    for model_name in model_manager.model_list():
        models.append(model_manager.model_info(model_name))

    return ModelListResponse(data=models)


@app.get("/models", response_model=ModelDescriptionListRespone)
async def list_model_descriptions():
    """Get detailed model information list"""
    models = []
    for model_name in model_manager.model_list():
        models.append(model_manager.model_desc(model_name))

    return ModelDescriptionListRespone(data=models)


@app.get("/models/{model_id}", response_model=ModelDescription)
async def get_model(model_id: str):
    """Get specific model information"""
    return model_manager.model_desc(model_id)


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """Chat completion endpoint"""
    model_name = request.model
    if request.stream:
        # Streaming response
        async def generate_stream():
            try:
                response_iterator = await model_manager.chat_completions_stream(model_name, request)
                async for chunk in response_iterator:
                    yield f"data: {chunk.model_dump_json()}\n\n"
            except Exception as e:  # pylint: disable=broad-exception-caught
                error_chunk = StreamErrorChunk(error=StreamErrorChunkMessage(message=str(e)))
                logger.error("Streaming chat completion error: %s", e)
                yield f"data: {error_chunk.model_dump_json()}\n\n"
            finally:
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream"
            }
        )

    # Non-streaming response
    response = await model_manager.chat_completions(model_name, request)
    return response


@app.post("/models/load")
async def load_model(model_name: str):
    """Manually load model"""
    # Load model according to global strategy
    await model_manager.auto_load_model(model_name)


@app.post("/models/unload")
async def unload_model(model_name: str):
    """Manually unload model"""
    await model_manager.auto_unload_model(model_name)


@app.get("/cuda_info", response_model=VramUsage)
async def get_cuda_info():
    """Get CUDA information"""
    return model_manager.get_vram_usage()


def start_server():
    """Start the server"""
    logger.debug("Debug log test - if you see this message, debug logging is enabled")
    log_config = get_uvicorn_log_config()

    uvicorn.run("miloco_ai_engine.main:app",
                host=SERVER_CONFIG["host"],
                port=SERVER_CONFIG["port"],
                log_level=LOGGING_CONFIG["log_level"].lower(),
                log_config=log_config,
                access_log=True)


if __name__ == "__main__":
    start_server()
