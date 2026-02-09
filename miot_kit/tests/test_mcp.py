# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Unit test for miot.mcp.py.
"""
import asyncio
import logging
from typing import Dict
import pytest

from miot.ha_api import HAHttpClient
from miot.i18n import MIoTI18n
from miot.mcp import (
    HomeAssistantAutomationMcp,
    HomeAssistantAutomationMcpInterface,
    MIoTDeviceMcpInterface,
    MIoTDeviceMcp,
    MIoTManualSceneMcpInterface,
    MIoTManualSceneMcp
)
from miot.client import MIoTClient
from miot.spec import MIoTSpecParser
from miot.storage import MIoTStorage


# pylint: disable=import-outside-toplevel, unused-argument, missing-function-docstring
_LOGGER = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.dependency()
async def test_miot_scene_mcp_async(
    test_lang: str,
    test_cache_path: str,
    test_cloud_server: str,
    test_oauth2_redirect_uri: str,
    test_domain_cloud_cache: str,
    test_name_oauth2_info: str,
    test_name_uuid: str
):
    i18n: MIoTI18n = MIoTI18n(lang=test_lang, loop=asyncio.get_running_loop())

    miot_storage = MIoTStorage(test_cache_path)
    uuid = await miot_storage.load_async(domain=test_domain_cloud_cache, name=test_name_uuid, type_=str)
    assert isinstance(uuid, str)
    oauth_info = await miot_storage.load_async(domain=test_domain_cloud_cache, name=test_name_oauth2_info, type_=dict)
    assert isinstance(oauth_info, Dict) and "access_token" in oauth_info

    miot_client: MIoTClient = MIoTClient(
        uuid=uuid,
        redirect_uri=test_oauth2_redirect_uri,
        oauth_info=oauth_info,
        cloud_server=test_cloud_server,
    )
    await miot_client.init_async()

    miot_mcp = MIoTManualSceneMcp(
        interface=MIoTManualSceneMcpInterface(
            translate_async=i18n.translate_async,
            get_manual_scenes_async=miot_client.get_manual_scenes_async,
            trigger_manual_scene_async=miot_client.run_manual_scene_async,
            send_app_notify_async=miot_client.send_app_notify_async
        )
    )
    await miot_mcp.init_async()
    await miot_mcp.run_http_async(host="0.0.0.0", port=8080)
    _LOGGER.info("start miot scene mcp server success")

    while True:
        await asyncio.sleep(1)

    await miot_client.deinit_async()


@pytest.mark.asyncio
@pytest.mark.dependency()
async def test_miot_device_mcp_async(
    test_lang: str,
    test_cache_path: str,
    test_cloud_server: str,
    test_oauth2_redirect_uri: str,
    test_domain_cloud_cache: str,
    test_name_oauth2_info: str,
    test_name_uuid: str
):
    i18n: MIoTI18n = MIoTI18n(lang=test_lang, loop=asyncio.get_running_loop())

    miot_storage = MIoTStorage(test_cache_path)
    uuid = await miot_storage.load_async(domain=test_domain_cloud_cache, name=test_name_uuid, type_=str)
    assert isinstance(uuid, str)
    oauth_info = await miot_storage.load_async(domain=test_domain_cloud_cache, name=test_name_oauth2_info, type_=dict)
    assert isinstance(oauth_info, Dict) and "access_token" in oauth_info

    miot_client: MIoTClient = MIoTClient(
        uuid=uuid,
        redirect_uri=test_oauth2_redirect_uri,
        oauth_info=oauth_info,  # type: ignore
        cloud_server=test_cloud_server,
    )
    await miot_client.init_async()

    spec_parser: MIoTSpecParser = MIoTSpecParser(storage=miot_storage, lang=test_lang)
    await spec_parser.init_async()

    miot_mcp = MIoTDeviceMcp(
        interface=MIoTDeviceMcpInterface(
            translate_async=i18n.translate_async,
            get_devices_async=miot_client.get_devices_async,
            get_homes_async=miot_client.get_homes_async,
            get_prop_async=miot_client.http_client.get_prop_async,
            set_prop_async=miot_client.http_client.set_prop_async,
            action_async=miot_client.http_client.action_async
        ),
        spec_parser=spec_parser
    )
    await miot_mcp.init_async()
    await miot_mcp.run_http_async(host="0.0.0.0", port=8081)
    _LOGGER.info("start miot device mcp server success")

    while True:
        await asyncio.sleep(1)

    await miot_client.deinit_async()


@pytest.mark.asyncio
@pytest.mark.dependency()
async def test_ha_scene_mcp_async(
    test_lang: str,
    test_cache_path: str,
    test_domain_ha_cache: str,
    test_name_ha_oauth_info: str,
    test_ha_url: str,
    test_ha_token: str
):
    """Test Home Assistant Scene MCP."""
    i18n: MIoTI18n = MIoTI18n(lang=test_lang, loop=asyncio.get_running_loop())

    # use OAuth2 token
    # miot_storage = MIoTStorage(test_cache_path)
    # oauth_info = await miot_storage.load_async(
    #     domain=test_domain_ha_cache, name=test_name_ha_oauth_info, type_=dict)
    # assert isinstance(oauth_info, Dict)
    # oauth_info = BaseOAuthInfo(**oauth_info)

    ha_http = HAHttpClient(
        base_url=test_ha_url,
        access_token=test_ha_token,
        loop=asyncio.get_running_loop()
    )

    ha_scene_mcp = HomeAssistantAutomationMcp(
        interface=HomeAssistantAutomationMcpInterface(
            translate_async=i18n.translate_async,
            get_automations_async=ha_http.get_automations_async,
            trigger_automation_async=ha_http.trigger_automation_async
        )
    )
    await ha_scene_mcp.init_async()
    await ha_scene_mcp.run_http_async(host="0.0.0.0", port=8082)
    _LOGGER.info("start home assistant scene mcp server success")

    while True:
        await asyncio.sleep(1)

    await ha_http.deinit_async()
