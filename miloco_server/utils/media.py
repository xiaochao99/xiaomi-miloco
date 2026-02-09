# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Media manager."""
import asyncio
import hashlib
import logging
import os
from datetime import datetime
from typing import List, Optional

import aiofiles
from miloco_server.config.normal_config import IMAGE_DIR

_LOGGER = logging.getLogger(name=__name__)


class ImageManager:
    """Image manager."""
    _base_path: str
    _url_prefix: Optional[str]
    _counter: int
    _counter_lock: asyncio.Lock
    _dt_prefix: str

    def __init__(self, base_path: str, url_prefix: Optional[str] = None):
        # Create base path if not exists
        os.makedirs(base_path, exist_ok=True)
        self._base_path = base_path
        self._url_prefix = url_prefix
        self._counter = 0
        self._counter_lock = asyncio.Lock()
        # Create date path if not exists
        self._dt_prefix = datetime.now().strftime('%y%m%d')
        os.makedirs(os.path.join(base_path, self._dt_prefix), exist_ok=True)

    @property
    def base_path(self) -> str:
        """Get base path."""
        return self._base_path

    @property
    def url_prefix(self) -> Optional[str]:
        """Get url prefix."""
        return self._url_prefix

    async def save_image_async(self, did: str, raw_img: bytes, channel: int = 0) -> str:
        """Save image."""
        image_name = await self.__generate_name(did, channel)
        try:
            async with aiofiles.open(os.path.join(self._base_path, image_name), 'wb') as f:
                await f.write(raw_img)
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOGGER.error('Save image error, %s: %s', image_name, err)
        if not self._url_prefix:
            return image_name
        return os.path.join(self._url_prefix, image_name)

    async def save_image_list_async(self, did: str, raw_img_list: List, channel: int = 0) -> List:
        """Save image list."""
        image_name_list = []
        tasks = []
        for raw_img in raw_img_list:
            tasks.append(self.save_image_async(did, raw_img, channel))
        image_name_list = await asyncio.gather(*tasks, return_exceptions=True)
        return image_name_list

    async def load_image_async(self, image_name: str) -> Optional[bytes]:
        """Load image."""
        try:
            if self._url_prefix:
                image_name = image_name.removeprefix(self._url_prefix + '/')
            async with aiofiles.open(os.path.join(self._base_path, image_name), 'rb') as f:
                return await f.read()
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOGGER.error('Load image error, %s: %s', image_name, err)
            return None

    async def load_image_list_async(self, image_name_list: List) -> List:
        """Load image list."""
        image_list = []
        tasks = []
        for image_name in image_name_list:
            tasks.append(self.load_image_async(image_name))
        image_list = await asyncio.gather(*tasks, return_exceptions=True)
        return image_list

    async def delete_image_async(self, image_name: str) -> bool:
        """Delete image."""
        try:
            if self._url_prefix:
                image_name = image_name.removeprefix(self._url_prefix + '/')
            await asyncio.to_thread(os.remove, os.path.join(self._base_path,  image_name))
            _LOGGER.info('Delete image success, %s', image_name)
            return True
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOGGER.error('Delete image error, %s: %s', image_name, err)
            return False

    async def delete_image_list_async(self, image_name_list: List) -> bool:
        """Delete image list."""
        image_name_set = set(image_name_list)
        tasks = []
        for image_name in image_name_set:
            tasks.append(self.delete_image_async(image_name))
        result_list = await asyncio.gather(*tasks, return_exceptions=True)
        return all(result_list)

    async def __generate_name(self, did: str, channel: int = 0) -> str:
        dt_now = datetime.now()
        dt_prefix = dt_now.strftime('%y%m%d')
        if dt_prefix != self._dt_prefix:
            # New path
            self.dt_prefix = dt_prefix
            os.makedirs(os.path.join(self._base_path, self.dt_prefix), exist_ok=True)

        id_hash = hashlib.md5(f'{did}{channel}'.encode()).hexdigest()
        ts_now = int(dt_now.timestamp()*1000)
        gen_id = await self.__next_id()

        return os.path.join(self._dt_prefix, f'{id_hash}_{ts_now}_{gen_id:04d}.jpg')

    async def __next_id(self) -> int:
        async with self._counter_lock:
            self._counter += 1
            if self._counter > 9999:
                self._counter = 0
            return self._counter


image_manager = ImageManager(base_path=str(IMAGE_DIR), url_prefix='/static/camera/images')
