# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Unit test for miot_network.py.
"""
import logging
import asyncio
import pytest

from miot.network import MIoTNetwork, InterfaceStatus, NetworkInfo

_LOGGER = logging.getLogger(__name__)

# pylint: disable=import-outside-toplevel, unused-argument


@pytest.mark.asyncio
async def test_network_monitor_loop_async():
    """Test network monitor loop."""
    miot_net = MIoTNetwork()

    async def on_network_status_changed(status: bool):
        _LOGGER.info("on_network_status_changed, %s", status)
    await miot_net.register_status_changed_async(key="test", handler=on_network_status_changed)

    async def on_network_info_changed(
            status: InterfaceStatus, info: NetworkInfo):
        _LOGGER.info("on_network_info_changed, %s, %s", status, info)
    await miot_net.register_info_changed_async(key="test", handler=on_network_info_changed)

    await miot_net.init_async()
    _LOGGER.info("delay 3000ms")
    await asyncio.sleep(3)
    _LOGGER.info("net status: %s", miot_net.network_status)
    _LOGGER.info("net info: %s", miot_net.network_info)
    await miot_net.deinit_async()
