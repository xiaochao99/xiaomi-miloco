# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
DLNA Service - UPnP/DLNA device discovery and media casting control.
DLNA服务 - 封装设备发现和投屏控制逻辑
"""

import asyncio
import logging
import socket
from typing import Optional, List, Dict, Callable, Awaitable
from dataclasses import dataclass, field

from miloco_server.dlna.dlna_device import DLNADevice, DLNADeviceInfo

logger = logging.getLogger(__name__)

# SSDP (Simple Service Discovery Protocol) 常量
SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
SSDP_MX = 3
SSDP_ST = "urn:schemas-upnp-org:device:MediaRenderer:1"

# 备用搜索目标
SSDP_ST_FALLBACKS = [
    "ssdp:all",
    "urn:schemas-upnp-org:device:MediaRenderer:1",
    "urn:schemas-upnp-org:service:AVTransport:1",
]

_dlna_service_instance: Optional["DLNAService"] = None


@dataclass
class SSDPResponse:
    """SSDP响应解析结果"""
    location: str = ""
    usn: str = ""
    st: str = ""
    server: str = ""
    headers: Dict[str, str] = field(default_factory=dict)


class DLNAService:
    """
    DLNA服务
    提供局域网DLNA设备发现和媒体投屏控制功能
    """

    def __init__(self):
        self._devices: Dict[str, DLNADevice] = {}
        self._discovering = False
        self._on_device_found_callbacks: List[Callable[[DLNADevice], Awaitable[None]]] = []
        self._on_device_lost_callbacks: List[Callable[[str], Awaitable[None]]] = []

    @property
    def devices(self) -> List[DLNADevice]:
        """获取所有已发现的设备"""
        return list(self._devices.values())

    @property
    def device_count(self) -> int:
        """获取设备数量"""
        return len(self._devices)

    def get_device(self, device_id: str) -> Optional[DLNADevice]:
        """根据ID获取设备"""
        return self._devices.get(device_id)

    def on_device_found(self, callback: Callable[[DLNADevice], Awaitable[None]]):
        """注册设备发现回调"""
        self._on_device_found_callbacks.append(callback)

    def on_device_lost(self, callback: Callable[[str], Awaitable[None]]):
        """注册设备丢失回调"""
        self._on_device_lost_callbacks.append(callback)

    async def discover_devices(self, timeout: int = 5) -> List[DLNADevice]:
        """
        发现局域网内的DLNA设备
        
        Args:
            timeout: 发现超时时间(秒)
            
        Returns:
            发现的设备列表
        """
        if self._discovering:
            logger.warning("Discovery already in progress")
            return self.devices

        self._discovering = True
        discovered_devices: List[DLNADevice] = []

        try:
            # 发送SSDP M-SEARCH请求
            responses = await self._send_ssdp_search(timeout)
            logger.info("Received %d SSDP responses", len(responses))

            # 解析每个响应获取设备信息
            for response in responses:
                try:
                    device_info = await self._fetch_device_description(response)
                    if device_info and self._is_media_renderer(device_info):
                        device = DLNADevice(device_info)
                        self._devices[device.udn] = device
                        discovered_devices.append(device)
                        logger.info("Discovered DLNA device: %s (%s)", device.name, device.host)

                        # 触发回调
                        for callback in self._on_device_found_callbacks:
                            try:
                                await callback(device)
                            except Exception as e:
                                logger.error("Error in device found callback: %s", e)
                except Exception as e:
                    logger.warning("Failed to process SSDP response: %s", e)

            logger.info("DLNA discovery completed. Found %d devices", len(discovered_devices))
            return discovered_devices

        except Exception as e:
            logger.error("DLNA discovery failed: %s", e)
            return []
        finally:
            self._discovering = False

    async def cast_to_device(
        self,
        device_id: str,
        audio_url: str,
        metadata: str = ""
    ) -> bool:
        """
        将音频投屏到指定设备
        
        Args:
            device_id: 目标设备ID
            audio_url: 音频URL
            metadata: 媒体元数据
            
        Returns:
            是否成功
        """
        device = self._devices.get(device_id)
        if not device:
            logger.error("Device not found: %s", device_id)
            return False

        # 设置URI
        success = await device.set_av_transport_uri(audio_url, metadata)
        if not success:
            return False

        # 开始播放
        return await device.play()

    async def stop_cast(self, device_id: str) -> bool:
        """
        停止投屏
        
        Args:
            device_id: 目标设备ID
            
        Returns:
            是否成功
        """
        device = self._devices.get(device_id)
        if not device:
            logger.error("Device not found: %s", device_id)
            return False

        return await device.stop()

    async def _send_ssdp_search(self, timeout: int) -> List[SSDPResponse]:
        """
        发送SSDP M-SEARCH请求
        
        Args:
            timeout: 超时时间(秒)
            
        Returns:
            SSDP响应列表
        """
        responses: List[SSDPResponse] = []
        seen_locations = set()

        for st in [SSDP_ST] + SSDP_ST_FALLBACKS:
            try:
                message = (
                    f"M-SEARCH * HTTP/1.1\r\n"
                    f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
                    f"MAN: \"ssdp:discover\"\r\n"
                    f"MX: {SSDP_MX}\r\n"
                    f"ST: {st}\r\n"
                    f"\r\n"
                )

                # 创建UDP socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.settimeout(timeout)

                try:
                    # 发送M-SEARCH
                    sock.sendto(message.encode(), (SSDP_ADDR, SSDP_PORT))

                    # 接收响应
                    import time
                    end_time = time.time() + timeout
                    while time.time() < end_time:
                        try:
                            data, addr = sock.recvfrom(4096)
                            response = self._parse_ssdp_response(data.decode(errors='ignore'))
                            if response.location and response.location not in seen_locations:
                                seen_locations.add(response.location)
                                responses.append(response)
                        except socket.timeout:
                            break
                        except Exception as e:
                            logger.debug("Error receiving SSDP response: %s", e)
                            break
                finally:
                    sock.close()

            except Exception as e:
                logger.warning("SSDP search for ST=%s failed: %s", st, e)

        return responses

    def _parse_ssdp_response(self, data: str) -> SSDPResponse:
        """解析SSDP响应"""
        response = SSDPResponse()
        for line in data.split('\r\n'):
            if ':' in line:
                key, _, value = line.partition(':')
                key = key.strip().upper()
                value = value.strip()
                if key == 'LOCATION':
                    response.location = value
                elif key == 'USN':
                    response.usn = value
                elif key == 'ST':
                    response.st = value
                elif key == 'SERVER':
                    response.server = value
                response.headers[key] = value
        return response

    async def _fetch_device_description(
        self,
        response: SSDPResponse
    ) -> Optional[DLNADeviceInfo]:
        """
        获取设备描述信息
        
        Args:
            response: SSDP响应
            
        Returns:
            设备信息
        """
        if not response.location:
            return None

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    response.location,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        return None

                    xml_text = await resp.text()
                    return self._parse_device_description(xml_text, response)

        except Exception as e:
            logger.warning("Failed to fetch device description from %s: %s", response.location, e)
            return None

    def _parse_device_description(
        self,
        xml_text: str,
        ssdp_response: SSDPResponse
    ) -> Optional[DLNADeviceInfo]:
        """解析设备描述XML"""
        try:
            import re

            # 提取设备信息
            udn_match = re.search(r"<UDN>(.*?)</UDN>", xml_text)
            name_match = re.search(r"<friendlyName>(.*?)</friendlyName>", xml_text)
            type_match = re.search(r"<deviceType>(.*?)</deviceType>", xml_text)
            manufacturer_match = re.search(r"<manufacturer>(.*?)</manufacturer>", xml_text)
            model_match = re.search(r"<modelName>(.*?)</modelName>", xml_text)

            if not udn_match or not name_match:
                return None

            # 提取主机和端口
            from urllib.parse import urlparse
            parsed = urlparse(ssdp_response.location)
            host = parsed.hostname or ""
            port = parsed.port or 80

            # 提取服务URL
            services: Dict[str, str] = {}
            service_pattern = re.compile(
                r"<service>.*?<serviceType>(.*?)</serviceType>.*?<controlURL>(.*?)</controlURL>.*?</service>",
                re.DOTALL
            )
            for match in service_pattern.finditer(xml_text):
                service_type = match.group(1)
                control_url = match.group(2)
                # 构建完整URL
                if not control_url.startswith("http"):
                    control_url = f"http://{host}:{port}{control_url}"
                services[service_type] = control_url

            return DLNADeviceInfo(
                udn=udn_match.group(1),
                name=name_match.group(1),
                device_type=type_match.group(1) if type_match else "MediaRenderer",
                host=host,
                port=port,
                manufacturer=manufacturer_match.group(1) if manufacturer_match else "",
                model_name=model_match.group(1) if model_match else "",
                location=ssdp_response.location,
                services=services,
            )

        except Exception as e:
            logger.error("Error parsing device description: %s", e)
            return None

    def _is_media_renderer(self, device_info: DLNADeviceInfo) -> bool:
        """判断是否为媒体渲染器设备"""
        return "MediaRenderer" in device_info.device_type


def get_dlna_service() -> DLNAService:
    """获取DLNA服务单例"""
    global _dlna_service_instance
    if _dlna_service_instance is None:
        _dlna_service_instance = DLNAService()
    return _dlna_service_instance
