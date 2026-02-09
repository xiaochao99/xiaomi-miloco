# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Unit test miot spec.
"""
import yaml
import logging
import pytest

from miot.spec import MIoTSpecParser, MIoTSpecTypeClass
from miot.storage import MIoTStorage

_LOGGER = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_spec(test_cache_path: str,):
    """Test miot spec."""
    miot_storage = MIoTStorage(root_path=test_cache_path)

    spec_parser = MIoTSpecParser(storage=miot_storage, lang='zh-Hans')
    await spec_parser.init_async()

    spec1 = await spec_parser.parse_async(urn='urn:miot-spec-v2:device:nas:0000A0E6:xiaomi-rp05:1')
    assert spec1 is not None

    # _LOGGER.info('spec1: %s', spec1)
    _LOGGER.info('spec1: %s', spec1.model_dump_json(by_alias=True, exclude_none=True))


@pytest.mark.asyncio
async def test_spec_type(test_cache_path: str):
    """Test miot spec type."""
    miot_storage = MIoTStorage(root_path=test_cache_path)

    spec_type = MIoTSpecTypeClass(storage=miot_storage)
    await spec_type.init_async()

    with open('./types_default.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(spec_type.data.model_dump(by_alias=True), f, allow_unicode=True)
    # _LOGGER.info('device_types: %s', spec_type.data.model_dump_json(by_alias=True))
