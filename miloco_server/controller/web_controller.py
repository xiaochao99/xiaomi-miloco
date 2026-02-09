# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Web controller
Handles web page rendering and static content
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from miloco_server.service.manager import get_manager
from miloco_server.config.normal_config import STATIC_DIR

router = APIRouter()

manager = get_manager()

# Set template directory using configuration path
templates = Jinja2Templates(directory=str(STATIC_DIR))

@router.get("/", response_class=HTMLResponse)
async def welcome_page(request: Request):
    """Welcome page - no authentication required"""
    return templates.TemplateResponse(request, "index.html")

