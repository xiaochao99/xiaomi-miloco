# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Common data models
Define all common request and response data structures
"""

from typing import Any, Optional
from pydantic import BaseModel


class NormalResponse(BaseModel):
    """Standard API response model"""
    code: int
    message: str
    data: Optional[Any] = None




