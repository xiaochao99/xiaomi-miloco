# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Unit test for miot.mdns.py.
"""
import asyncio
import logging
import pytest

from miot.mdns import MdnsService

# pylint: disable=import-outside-toplevel, unused-argument, missing-function-docstring
_LOGGER = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.dependency()
async def test_mdns_async() -> None:
    mdns = MdnsService()
    await mdns.init_async()

    while True:
        await asyncio.sleep(1)

    await mdns.deinit_async()
