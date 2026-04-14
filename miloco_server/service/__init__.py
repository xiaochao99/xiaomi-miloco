# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
service package
"""
from cachetools import TTLCache
from typing import Any


# Cache of dynamic executor actor addresses/handles.
# NOTE: Keep this module import-light to avoid pulling heavy dependencies at import time.
trigger_rule_dynamic_executor_cache: TTLCache[str, Any] = TTLCache(maxsize=100, ttl=600)
