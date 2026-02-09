# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Test MCP Client.
"""
import asyncio
import logging
from typing import Dict
from fastmcp import Client
import pytest

from miot.ha_api import HAHttpClient
from miot.i18n import MIoTI18n
from miot.mcp import (
    HomeAssistantAutomationMcp,
    HomeAssistantAutomationMcpInterface,
    MIoTDeviceMcp, MIoTDeviceMcpInterface,
    MIoTManualSceneMcp,
    MIoTManualSceneMcpInterface
)
from miot.client import MIoTClient
from miot.spec import MIoTSpecParser
from miot.storage import MIoTStorage


# pylint: disable=import-outside-toplevel, unused-argument, missing-function-docstring
_LOGGER = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.dependency()
async def test_miot_mcp_async(
    test_cache_path: str,
    test_cloud_server: str,
    test_oauth2_redirect_uri: str,
    test_domain_cloud_cache: str,
    test_lang: str,
    test_name_oauth2_info: str,
    test_name_uuid: str
):
    miot_storage = MIoTStorage(test_cache_path)
    uuid = await miot_storage.load_async(domain=test_domain_cloud_cache, name=test_name_uuid, type_=str)
    assert isinstance(uuid, str)
    oauth_info = await miot_storage.load_async(domain=test_domain_cloud_cache, name=test_name_oauth2_info, type_=dict)
    assert isinstance(oauth_info, Dict) and "access_token" in oauth_info

    miot_client: MIoTClient = MIoTClient(
        uuid=uuid,
        redirect_uri=test_oauth2_redirect_uri,
        lang=test_lang,
        oauth_info=oauth_info,
        cloud_server=test_cloud_server,
    )
    await miot_client.init_async()

    spec_parser: MIoTSpecParser = MIoTSpecParser(storage=miot_storage, lang=test_lang, loop=asyncio.get_running_loop())
    i18n: MIoTI18n = MIoTI18n(lang=test_lang, loop=asyncio.get_running_loop())

    # MIoT manual scene MCP
    miot_scene_mcp = MIoTManualSceneMcp(
        interface=MIoTManualSceneMcpInterface(
            translate_async=i18n.translate_async,
            get_manual_scenes_async=miot_client.get_manual_scenes_async,
            trigger_manual_scene_async=miot_client.run_manual_scene_async,
            send_app_notify_async=miot_client.send_app_notify_async,
        )
    )
    await miot_scene_mcp.init_async()
    mcp_client = Client(miot_scene_mcp.mcp_instance)
    async with mcp_client:
        await mcp_client.ping()

        tool_list = await mcp_client.list_tools()
        _LOGGER.info("tool_list: %s", tool_list)

        prompt_list = await mcp_client.list_prompts()
        _LOGGER.info("prompt_list: %s", prompt_list)

        for prompt in prompt_list:
            prompt_result = await mcp_client.get_prompt(name=prompt.name)
            _LOGGER.info("prompt_result, %s, %s", prompt.name, prompt_result.model_dump_json())

    # MIoT device MCP
    miot_device_mcp = MIoTDeviceMcp(
        interface=MIoTDeviceMcpInterface(
            translate_async=i18n.translate_async,
            get_homes_async=miot_client.get_homes_async,
            get_devices_async=miot_client.get_devices_async,
            get_prop_async=miot_client.http_client.get_prop_async,
            set_prop_async=miot_client.http_client.set_prop_async,
            action_async=miot_client.http_client.action_async
        ),
        spec_parser=spec_parser
    )
    await miot_device_mcp.init_async()
    mcp_client = Client(miot_device_mcp.mcp_instance)

    async with mcp_client:
        await mcp_client.ping()

        tool_list = await mcp_client.list_tools()
        _LOGGER.info("tool_list: %s", tool_list)

        prompt_list = await mcp_client.list_prompts()
        _LOGGER.info("prompt_list: %s", prompt_list)

        for prompt in prompt_list:
            prompt_result = await mcp_client.get_prompt(name=prompt.name)
            _LOGGER.info("prompt_result, %s, %s", prompt.name, prompt_result.model_dump_json())

    await miot_client.deinit_async()


@pytest.mark.asyncio
@pytest.mark.dependency()
async def test_ha_mcp_async(
    test_cache_path: str,
    test_domain_ha_cache: str,
    test_name_ha_oauth_info: str,
    test_lang: str,
    test_ha_url: str,
    test_ha_token: str
):
    """Test Home Assistant Scene MCP."""
    # use OAuth2 token
    # miot_storage = MIoTStorage(test_cache_path)
    # oauth_info = await miot_storage.load_async(
    #     domain=test_domain_ha_cache, name=test_name_ha_oauth_info, type_=dict)
    # assert isinstance(oauth_info, Dict)
    # oauth_info = BaseOAuthInfo(**oauth_info)

    i18n: MIoTI18n = MIoTI18n(lang=test_lang, loop=asyncio.get_running_loop())

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

    mcp_client = Client(ha_scene_mcp.mcp_instance)

    async with mcp_client:
        await mcp_client.ping()

        tool_list = await mcp_client.list_tools()
        _LOGGER.info("tool_list: %s", tool_list)

        prompt_list = await mcp_client.list_prompts()
        _LOGGER.info("prompt_list: %s", prompt_list)

        for prompt in prompt_list:
            prompt_result = await mcp_client.get_prompt(name=prompt.name)
            _LOGGER.info("prompt_result, %s, %s", prompt.name, prompt_result)

    await ha_http.deinit_async()
