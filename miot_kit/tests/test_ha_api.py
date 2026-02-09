# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Unit test for miot_client.py.
"""
import asyncio
import logging
import time
from typing import Dict, Optional
import webbrowser
import pytest

from miot.ha_api import HAHttpClient, HAOAuth2Client
from miot.storage import MIoTStorage
from miot.types import BaseOAuthInfo


# pylint: disable=import-outside-toplevel, unused-argument, missing-function-docstring
_LOGGER = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.dependency()
async def test_ha_oauth_auth_async(
    test_cache_path: str,
    test_domain_ha_cache: str,
    test_ha_url: str,
    test_ha_oauth2_client_id: str,
    test_ha_oauth2_redirect_uri: str,
    test_name_ha_oauth_info: str
):
    """Test Home Assistant OAuth2 Authorization."""
    miot_storage = MIoTStorage(test_cache_path)

    ha_oauth = HAOAuth2Client(
        base_url=test_ha_url,
        client_id=test_ha_oauth2_client_id,
        redirect_uri=test_ha_oauth2_redirect_uri,
    )

    oauth_info: Optional[BaseOAuthInfo] = None
    load_info = await miot_storage.load_async(domain=test_domain_ha_cache, name=test_name_ha_oauth_info, type_=dict)
    if (
        isinstance(load_info, dict)
        and "access_token" in load_info
        and "expires_ts" in load_info
        and load_info["expires_ts"] > int(time.time())
    ):
        _LOGGER.info("load ha oauth info, %s", load_info)
        oauth_info = BaseOAuthInfo(**load_info)

    if oauth_info is None:
        # gen oauth url
        auth_url: str = await ha_oauth.gen_auth_url_async()
        assert isinstance(auth_url, str)
        _LOGGER.info("auth url: %s", auth_url)
        # get code
        webbrowser.open(auth_url)
        code: str = input("input code: ")
        assert code is not None
        # get access_token
        res_obj = await ha_oauth.get_access_token_async(code=code)
        assert res_obj is not None
        oauth_info = res_obj
        _LOGGER.info("get_access_token result: %s", res_obj)
        rc = await miot_storage.save_async(
            test_domain_ha_cache,
            test_name_ha_oauth_info,
            oauth_info.model_dump())
        assert rc
        _LOGGER.info("saved ha oauth info")

    access_token = oauth_info.access_token
    assert isinstance(access_token, str)
    _LOGGER.info("access_token: %s", access_token)
    refresh_token = oauth_info.refresh_token
    assert isinstance(refresh_token, str)
    _LOGGER.info("refresh_token: %s", refresh_token)

    await ha_oauth.deinit_async()


@pytest.mark.asyncio
@pytest.mark.dependency()
async def test_ha_oauth_refresh_async(
    test_cache_path: str,
    test_domain_ha_cache: str,
    test_ha_url: str,
    test_ha_oauth2_client_id: str,
    test_ha_oauth2_redirect_uri: str,
    test_name_ha_oauth_info: str
):
    """Test Home Assistant OAuth2 Refresh Token."""
    miot_storage = MIoTStorage(test_cache_path)
    oauth_info = await miot_storage.load_async(domain=test_domain_ha_cache, name=test_name_ha_oauth_info, type_=dict)
    assert isinstance(oauth_info, Dict)
    oauth_info = BaseOAuthInfo(**oauth_info)
    remaining_time = oauth_info.expires_ts - int(time.time())
    _LOGGER.info("ha token remaining valid time: %ss", remaining_time)
    # Refresh token
    ha_oauth = HAOAuth2Client(
        base_url=test_ha_url,
        client_id=test_ha_oauth2_client_id,
        redirect_uri=test_ha_oauth2_redirect_uri,
    )
    update_info = await ha_oauth.refresh_access_token_async(refresh_token=oauth_info.refresh_token)
    assert update_info
    remaining_time = update_info.expires_ts - int(time.time())
    assert remaining_time > 0
    _LOGGER.info("refresh ha token, remaining valid time: %ss", remaining_time)
    # Save oauth2 info
    rc = await miot_storage.save_async(
        test_domain_ha_cache,
        test_name_ha_oauth_info,
        update_info.model_dump()
    )
    assert rc
    _LOGGER.info("refresh ha token success, %s", update_info)

    await ha_oauth.deinit_async()


@pytest.mark.asyncio
@pytest.mark.dependency()
async def test_ha_oauth_revoke_async(
    test_cache_path: str,
    test_domain_ha_cache: str,
    test_ha_url: str,
    test_ha_oauth2_client_id: str,
    test_ha_oauth2_redirect_uri: str,
    test_name_ha_oauth_info: str
):
    """Test Home Assistant OAuth2 Revoke Token."""
    miot_storage = MIoTStorage(test_cache_path)
    oauth_info = await miot_storage.load_async(domain=test_domain_ha_cache, name=test_name_ha_oauth_info, type_=dict)
    assert isinstance(oauth_info, Dict)
    oauth_info = BaseOAuthInfo(**oauth_info)

    ha_oauth = HAOAuth2Client(
        base_url=test_ha_url,
        client_id=test_ha_oauth2_client_id,
        redirect_uri=test_ha_oauth2_redirect_uri,
    )
    # Revoke token
    await ha_oauth.revoke_token_async(refresh_token=oauth_info.refresh_token)
    _LOGGER.info("revoke ha token success")
    # try to refresh token
    update_info = None
    try:
        update_info = await ha_oauth.refresh_access_token_async(refresh_token=oauth_info.refresh_token)
    except Exception:  # pylint: disable=broad-except
        pass
    assert update_info is None

    # Clear oauth2 info
    rc = await miot_storage.remove_async(
        test_domain_ha_cache,
        test_name_ha_oauth_info,
        type_=dict
    )
    assert rc

    await ha_oauth.deinit_async()


@pytest.mark.asyncio
@pytest.mark.dependency()
async def test_http_validate_async(
    test_cache_path: str,
    test_domain_ha_cache: str,
    test_ha_url: str,
    test_name_ha_oauth_info: str
):
    """Test validate Token."""
    miot_storage = MIoTStorage(test_cache_path)
    oauth_info = await miot_storage.load_async(domain=test_domain_ha_cache, name=test_name_ha_oauth_info, type_=dict)
    assert isinstance(oauth_info, Dict)
    oauth_info = BaseOAuthInfo(**oauth_info)

    rc = await HAHttpClient.validate_async(url=test_ha_url, token=oauth_info.access_token,)
    assert rc
    _LOGGER.info("validate result: %s", rc)


@pytest.mark.asyncio
@pytest.mark.dependency()
async def test_http_get_states_async(
    test_cache_path: str,
    test_domain_ha_cache: str,
    test_ha_url: str,
    test_name_ha_oauth_info: str,
    test_name_ha_states: str
):
    """Test get states."""
    miot_storage = MIoTStorage(test_cache_path)
    oauth_info = await miot_storage.load_async(domain=test_domain_ha_cache, name=test_name_ha_oauth_info, type_=dict)
    assert isinstance(oauth_info, Dict)
    oauth_info = BaseOAuthInfo(**oauth_info)

    ha_http = HAHttpClient(
        base_url=test_ha_url,
        access_token=oauth_info.access_token,
        loop=asyncio.get_running_loop()
    )

    states = await ha_http.get_states_async()
    assert isinstance(states, Dict)
    _LOGGER.info("ha states: %s", len(states))

    # Save states
    rc = await miot_storage.save_async(
        test_domain_ha_cache,
        test_name_ha_states,
        {s_id: item.model_dump() for s_id, item in states.items()}
    )
    assert rc
    _LOGGER.info("saved ha states")

    await ha_http.deinit_async()


@pytest.mark.asyncio
@pytest.mark.dependency()
async def test_oauth2_validate_async(
    test_cache_path: str,
    test_domain_ha_cache: str,
    test_ha_url: str,
    test_name_ha_oauth_info: str
):
    """Test validate Token."""
    miot_storage = MIoTStorage(test_cache_path)
    oauth_info = await miot_storage.load_async(domain=test_domain_ha_cache, name=test_name_ha_oauth_info, type_=dict)
    assert isinstance(oauth_info, Dict)
    oauth_info = BaseOAuthInfo(**oauth_info)

    result = await HAHttpClient.validate_async(url=test_ha_url, token=oauth_info.access_token,)
    assert result is True
    _LOGGER.info("validate access_token result: %s", result)


@pytest.mark.asyncio
@pytest.mark.dependency()
async def test_get_automations_async(
    test_cache_path: str,
    test_domain_ha_cache: str,
    test_ha_url: str,
    test_name_ha_oauth_info: str,
    test_name_ha_automations: str
):
    """Test get automations."""
    miot_storage = MIoTStorage(test_cache_path)
    oauth_info = await miot_storage.load_async(domain=test_domain_ha_cache, name=test_name_ha_oauth_info, type_=dict)
    assert isinstance(oauth_info, Dict)
    oauth_info = BaseOAuthInfo(**oauth_info)

    ha_http = HAHttpClient(
        base_url=test_ha_url,
        access_token=oauth_info.access_token,
        loop=asyncio.get_running_loop()
    )

    automations = await ha_http.get_automations_async()
    assert isinstance(automations, Dict)
    _LOGGER.info("automations: %s", len(automations))

    # Save automations
    rc = await miot_storage.save_async(
        test_domain_ha_cache,
        test_name_ha_automations,
        {e_id: item.model_dump() for e_id, item in automations.items()}
    )
    assert rc
    _LOGGER.info("saved ha automations")

    # Trigger automation
    automation = list(automations.values())[0]
    rc = await ha_http.trigger_automation_async(automation)
    assert rc
    _LOGGER.info("trigger automation: %s", automation.entity_id)

    await ha_http.deinit_async()
