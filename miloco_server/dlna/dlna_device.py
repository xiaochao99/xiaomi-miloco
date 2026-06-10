# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
DLNA Device - Abstract representation of DLNA/UPnP devices.
DLNA设备抽象 - 封装UPnP设备的通用操作接口
"""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DLNADeviceInfo:
    """DLNA设备信息"""
    udn: str  # Unique Device Name
    name: str
    device_type: str = "MediaRenderer"
    host: str = ""
    port: int = 0
    manufacturer: str = ""
    model_name: str = ""
    location: str = ""
    services: Dict[str, str] = field(default_factory=dict)  # service_type -> control_url

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.udn,
            "name": self.name,
            "type": self.device_type,
            "host": self.host,
            "port": self.port,
            "manufacturer": self.manufacturer,
            "model": self.model_name,
        }


class DLNADevice:
    """
    DLNA设备操作封装
    封装UPnP AVTransport服务的控制操作
    """

    def __init__(self, device_info: DLNADeviceInfo):
        self.device_info = device_info
        self._av_transport_url: Optional[str] = None
        self._rendering_control_url: Optional[str] = None
        self._parse_services()

    def _parse_services(self):
        """解析设备服务URL"""
        for service_type, control_url in self.device_info.services.items():
            if "AVTransport" in service_type:
                self._av_transport_url = control_url
            elif "RenderingControl" in service_type:
                self._rendering_control_url = control_url

    @property
    def name(self) -> str:
        return self.device_info.name

    @property
    def udn(self) -> str:
        return self.device_info.udn

    @property
    def host(self) -> str:
        return self.device_info.host

    @property
    def is_media_renderer(self) -> bool:
        return "MediaRenderer" in self.device_info.device_type

    async def set_av_transport_uri(self, uri: str, metadata: str = "") -> bool:
        """
        设置AV传输URI (开始投屏)
        
        Args:
            uri: 媒体资源URI
            metadata: 媒体元数据(DIDL-Lite XML)
            
        Returns:
            是否成功
        """
        if not self._av_transport_url:
            logger.error("AVTransport service not available for device %s", self.name)
            return False

        try:
            import aiohttp
            soap_body = self._build_soap_action(
                "AVTransport",
                "SetAVTransportURI",
                {
                    "InstanceID": "0",
                    "CurrentURI": uri,
                    "CurrentURIMetaData": metadata,
                }
            )

            async with aiohttp.ClientSession() as session:
                headers = {
                    "Content-Type": 'text/xml; charset="utf-8"',
                    "SOAPAction": '"urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI"',
                }
                async with session.post(
                    self._av_transport_url,
                    data=soap_body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        logger.info("Set AV transport URI for device %s: %s", self.name, uri)
                        return True
                    else:
                        logger.error("Failed to set AV transport URI: HTTP %d", resp.status)
                        return False
        except Exception as e:
            logger.error("Error setting AV transport URI: %s", e)
            return False

    async def play(self) -> bool:
        """开始播放"""
        return await self._av_transport_action("Play", {"Speed": "1"})

    async def pause(self) -> bool:
        """暂停播放"""
        return await self._av_transport_action("Pause", {})

    async def stop(self) -> bool:
        """停止播放"""
        return await self._av_transport_action("Stop", {})

    async def seek(self, position_seconds: float) -> bool:
        """
        跳转到指定位置
        
        Args:
            position_seconds: 目标位置(秒)
            
        Returns:
            是否成功
        """
        hours = int(position_seconds // 3600)
        minutes = int((position_seconds % 3600) // 60)
        seconds = int(position_seconds % 60)
        target = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return await self._av_transport_action("Seek", {"Target": target, "Unit": "REL_TIME"})

    async def get_transport_info(self) -> Optional[Dict[str, str]]:
        """获取传输状态信息"""
        if not self._av_transport_url:
            return None

        try:
            import aiohttp
            soap_body = self._build_soap_action(
                "AVTransport",
                "GetTransportInfo",
                {"InstanceID": "0"}
            )

            async with aiohttp.ClientSession() as session:
                headers = {
                    "Content-Type": 'text/xml; charset="utf-8"',
                    "SOAPAction": '"urn:schemas-upnp-org:service:AVTransport:1#GetTransportInfo"',
                }
                async with session.post(
                    self._av_transport_url,
                    data=soap_body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        # 简单解析XML响应
                        import re
                        state_match = re.search(r"<CurrentTransportState>(.*?)</CurrentTransportState>", text)
                        status_match = re.search(r"<CurrentTransportStatus>(.*?)</CurrentTransportStatus>", text)
                        speed_match = re.search(r"<CurrentSpeed>(.*?)</CurrentSpeed>", text)
                        return {
                            "state": state_match.group(1) if state_match else "UNKNOWN",
                            "status": status_match.group(1) if status_match else "UNKNOWN",
                            "speed": speed_match.group(1) if speed_match else "1",
                        }
                    return None
        except Exception as e:
            logger.error("Error getting transport info: %s", e)
            return None

    async def set_volume(self, volume: int) -> bool:
        """
        设置音量
        
        Args:
            volume: 音量值 (0-100)
            
        Returns:
            是否成功
        """
        if not self._rendering_control_url:
            logger.error("RenderingControl service not available for device %s", self.name)
            return False

        try:
            import aiohttp
            soap_body = self._build_soap_action(
                "RenderingControl",
                "SetVolume",
                {
                    "InstanceID": "0",
                    "Channel": "Master",
                    "DesiredVolume": str(max(0, min(100, volume))),
                }
            )

            async with aiohttp.ClientSession() as session:
                headers = {
                    "Content-Type": 'text/xml; charset="utf-8"',
                    "SOAPAction": '"urn:schemas-upnp-org:service:RenderingControl:1#SetVolume"',
                }
                async with session.post(
                    self._rendering_control_url,
                    data=soap_body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error("Error setting volume: %s", e)
            return False

    async def _av_transport_action(self, action: str, params: Dict[str, str]) -> bool:
        """执行AVTransport操作"""
        if not self._av_transport_url:
            logger.error("AVTransport service not available for device %s", self.name)
            return False

        try:
            import aiohttp
            soap_body = self._build_soap_action("AVTransport", action, params)

            async with aiohttp.ClientSession() as session:
                headers = {
                    "Content-Type": 'text/xml; charset="utf-8"',
                    "SOAPAction": f'"urn:schemas-upnp-org:service:AVTransport:1#{action}"',
                }
                async with session.post(
                    self._av_transport_url,
                    data=soap_body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        logger.info("Executed %s on device %s", action, self.name)
                        return True
                    else:
                        logger.error("Failed to execute %s: HTTP %d", action, resp.status)
                        return False
        except Exception as e:
            logger.error("Error executing %s: %s", action, e)
            return False

    def _build_soap_action(
        self,
        service: str,
        action: str,
        params: Dict[str, str]
    ) -> str:
        """构建SOAP请求体"""
        service_type = f"urn:schemas-upnp-org:service:{service}:1"
        
        params_xml = ""
        for key, value in params.items():
            params_xml += f"<{key}>{value}</{key}>"

        return f'''<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:{action} xmlns:u="{service_type}">
      {params_xml}
    </u:{action}>
  </s:Body>
</s:Envelope>'''
