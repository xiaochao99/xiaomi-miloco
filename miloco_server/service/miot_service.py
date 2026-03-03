# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
MiOT service module
"""

import logging
from typing import List, Optional

from miot.types import MIoTUserInfo, MIoTCameraInfo, MIoTDeviceInfo, MIoTManualSceneInfo
from miot.rtsp_camera import RtspCameraInfo

from miloco_server.proxy.miot_proxy import MiotProxy
from miloco_server.schema.trigger_schema import Action
from miloco_server.schema.miot_schema import CameraChannel, CameraImgSeq, CameraInfo, DeviceInfo, SceneInfo
from miloco_server.middleware.exceptions import (
    MiotOAuthException,
    MiotServiceException,
    ValidationException,
    BusinessException,
    ResourceNotFoundException
)
from miloco_server.utils.default_action import DefaultPresetActionManager
from miloco_server.mcp.mcp_client_manager import MCPClientManager

logger = logging.getLogger(__name__)


class MiotService:
    """MiOT service class"""

    def __init__(self, miot_proxy: MiotProxy, mcp_client_manager: MCPClientManager,
                 default_preset_action_manager: Optional[DefaultPresetActionManager] = None):
        self._miot_proxy = miot_proxy
        self._mcp_client_manager = mcp_client_manager
        self._default_preset_action_manager = default_preset_action_manager

    @property
    def miot_client(self):
        """Get the MIoTClient instance."""
        return self._miot_proxy.miot_client

    async def process_xiaomi_home_callback(self, code: str, state: str):
        """
        Process Xiaomi MiOT authorization code
        """
        try:
            logger.info(
                "process_xiaomi_home_callback code: %s, status: %s", code, state)

            await self._miot_proxy.get_miot_auth_info(code=code,
                                                              state=state)
            await self._mcp_client_manager.init_miot_mcp_clients()

        except Exception as e:
            logger.error("Failed to process Xiaomi MiOT authorization code: %s", e)
            raise MiotServiceException(f"Failed to process Xiaomi MiOT authorization code: {str(e)}") from e


    async def refresh_miot_all_info(self) -> dict:
        """
        Refresh MiOT all information
        
        Returns:
            dict: Dictionary containing result of each refresh operation
        """
        try:
            return await self._miot_proxy.refresh_miot_info()
        except Exception as e: # pylint: disable=broad-exception-caught
            logger.error("Failed to refresh MiOT all information: %s", e)
            raise MiotServiceException(f"Failed to refresh MiOT all information: {str(e)}") from e

    async def refresh_miot_cameras(self):
        """
        Refresh MiOT camera information
        """
        try:
            result = await self._miot_proxy.refresh_cameras()
            if not result:
                raise MiotServiceException("Failed to refresh MiOT cameras")
            return True
        except Exception as e:
            logger.error("Failed to refresh MiOT cameras: %s", e)
            raise MiotServiceException(f"Failed to refresh MiOT cameras: {str(e)}") from e

    async def refresh_miot_scenes(self):
        """
        Refresh MiOT scene information
        """
        try:
            result = await self._miot_proxy.refresh_scenes()
            # None means call failed; an empty dict just means no scenes available and should not be treated as an error
            if result is None:
                raise MiotServiceException("Failed to refresh MiOT scenes")
            return True
        except Exception as e:
            logger.error("Failed to refresh MiOT scenes: %s", e)
            raise MiotServiceException(f"Failed to refresh MiOT scenes: {str(e)}") from e

    async def refresh_miot_user_info(self):
        """
        Refresh MiOT user information
        """
        try:
            result = await self._miot_proxy.refresh_user_info()
            if not result:
                raise MiotServiceException("Failed to refresh MiOT user info")
            return True
        except Exception as e:
            logger.error("Failed to refresh MiOT user info: %s", e)
            raise MiotServiceException(f"Failed to refresh MiOT user info: {str(e)}") from e

    async def refresh_miot_devices(self):
        """
        Refresh MiOT device information
        """
        try:
            result = await self._miot_proxy.refresh_devices()
            if not result:
                raise MiotServiceException("Failed to refresh MiOT devices")
            return True
        except Exception as e:
            logger.error("Failed to refresh MiOT devices: %s", e)
            raise MiotServiceException(f"Failed to refresh MiOT devices: {str(e)}") from e

    async def get_miot_login_status(self) -> dict:
        """
        Get MiOT login status

        Returns:
            dict: Dictionary containing status and login_url (if needed)

        Raises:
            MiotOAuthException: When user is not logged in or login status check fails
        """
        try:
            is_token_valid = await self._miot_proxy.check_token_valid()
            if not is_token_valid:
                login_url = await self._miot_proxy.get_miot_login_url()
                return {"is_logged_in": False, "login_url": login_url}
            return {"is_logged_in": True}

        except Exception as e:
            logger.error("Failed to check MiOT login status: %s", e)
            raise MiotOAuthException(f"Failed to check MiOT login status: {str(e)}") from e

    async def get_miot_user_info(self) -> MIoTUserInfo:
        """
        Get MiOT user information

        Returns:
            dict: User information dictionary

        Raises:
            ResourceNotFoundException: When unable to get user information
            ExternalServiceException: When external service call fails
        """
        try:
            user_info = await self._miot_proxy.get_user_info()

            if not user_info:
                raise ResourceNotFoundException("No logged in user information found")

            return user_info
        except Exception as e:
            logger.error("Failed to get MiOT user info: %s", e)
            raise MiotServiceException(f"Failed to get MiOT user info: {str(e)}") from e

    async def get_miot_camera_list(self) -> List[CameraInfo]:
        """
        Get MiOT camera list

        Returns:
            List[CameraInfo]: Camera information list

        Raises:
            MiotServiceException: When getting camera list fails
        """
        try:
            camera_dict: dict[
                str,
                MIoTCameraInfo | RtspCameraInfo] = await self._miot_proxy.get_cameras()
            if not camera_dict:
                raise MiotServiceException("Failed to get MiOT camera list")

            camera_list = [
                CameraInfo.model_validate(camera_info.model_dump())
                for camera_info in camera_dict.values()
            ]

            return camera_list
        except MiotServiceException:
            raise
        except Exception as e:
            logger.error("Failed to get MiOT camera list: %s", e)
            raise MiotServiceException(f"Failed to get MiOT camera list: {str(e)}") from e

    async def get_miot_device_list(self) -> List[DeviceInfo]:
        try:
            device_dict: dict[
                str, MIoTDeviceInfo] = await self._miot_proxy.get_devices()
            if not device_dict:
                raise MiotServiceException("Failed to get MiOT device list")
            device_list = [
                DeviceInfo.model_validate(device_info.model_dump())
                for device_info in device_dict.values()
            ]
            return device_list
        except MiotServiceException:
            raise
        except Exception as e:
            logger.error("Failed to get MiOT device list: %s", e)
            raise MiotServiceException(f"Failed to get MiOT device list: {str(e)}") from e

    async def get_miot_cameras_img(
            self, camera_dids: list[str], vision_use_img_count: int) -> list[CameraImgSeq]:
        logger.info(
            "get_miot_cameras_img, camera_dids: %s", ", ".join(camera_dids))
        try:
            all_camera_info: dict[str, MIoTCameraInfo | RtspCameraInfo] = await self._miot_proxy.get_cameras()
            if not all_camera_info:
                return []

            selected_camera_info: list[MIoTCameraInfo | RtspCameraInfo] = [
                info for info in all_camera_info.values() if (info.did in camera_dids)
            ]

            camera_channels: list[CameraChannel] = []
            for camera_info in selected_camera_info:
                for channel in range(camera_info.channel_count or 1):
                    camera_channels.append(
                        CameraChannel(did=camera_info.did, channel=channel))

            camera_img_seqs = []
            for camera_channel in camera_channels:
                camera_img_seq = self._miot_proxy.get_recent_camera_img(
                    camera_channel.did, camera_channel.channel, vision_use_img_count)
                if not camera_img_seq:
                    logger.error(
                        "get_miot_cameras_img, get recent camera img failed, did: %s, channel: %s",
                        camera_channel.did, camera_channel.channel
                    )
                    continue

                camera_img_seqs.append(camera_img_seq)
            return camera_img_seqs
        except Exception as e:
            logger.error("Failed to get MiOT camera images: %s", e)
            raise MiotServiceException(f"Failed to get MiOT camera images: {str(e)}") from e

    async def get_miot_scene_list(self) -> List[SceneInfo]:
        """
        Get all MiOT scenes

        Returns:
            dict: Scene information dictionary

        Raises:
            MiotServiceException: When getting scenes fails
        """
        try:
            scenes: dict[
                str,
                MIoTManualSceneInfo] | None = await self._miot_proxy.get_all_scenes(
                )

            if scenes is None:
                raise MiotServiceException("Failed to get MiOT scene list")

            scene_info_list = [
                SceneInfo(scene_id=scene_info.scene_id,
                          scene_name=scene_info.scene_name)
                for scene_info in scenes.values()
            ]

            return scene_info_list
        except MiotServiceException:
            raise
        except Exception as e:
            logger.error("Failed to get MiOT scene list: %s", e)
            raise MiotServiceException(f"Failed to get MiOT scene list: {str(e)}") from e

    async def send_notify(self, notify: str) -> None:
        """Send notification"""
        try:
            notify_id = await self._miot_proxy.get_miot_app_notify_id(notify)
            if not notify_id:
                raise ValidationException("MiOT app notification content is inappropriate, please re-enter")
            result = await self._miot_proxy.send_app_notify(notify_id)
            if not result:
                raise BusinessException("Failed to send notification")
        except Exception as e:
            logger.error("Failed to send notification: %s", str(e))
            raise BusinessException(f"Failed to send notification: {str(e)}") from e

    async def start_video_stream(self, camera_id: str, channel: int, callback):
        """
        Start video stream (business layer method)

        Args:
            camera_id: Camera device ID
            channel: Channel number
            callback: Video data callback function

        Raises:
            MiotServiceException: When startup fails
        """
        try:
            logger.info("Starting video stream: camera_id=%s, channel=%s", camera_id, channel)
            if callback:
                await self._miot_proxy.start_camera_raw_stream(
                    camera_id, channel, callback)
            else:
                logger.info("No callback function, only recording startup request: camera_id=%s", camera_id)
        except Exception as e:
            logger.error("Failed to start video stream: %s", e)
            raise MiotServiceException(f"Failed to start video stream: {str(e)}") from e

    async def stop_video_stream(self, camera_id: str, channel: int):
        """
        Stop video stream (business layer method)

        Args:
            camera_id: Camera device ID

        Raises:
            MiotServiceException: When stopping fails
        """
        try:
            logger.info("Stopping video stream: camera_id=%s", camera_id)
            await self._miot_proxy.stop_camera_raw_stream(camera_id, channel)
            logger.info("Video stream stopped successfully: camera_id=%s", camera_id)
        except Exception as e:
            logger.error("Failed to stop video stream: %s", e)
            raise MiotServiceException(f"Failed to stop video stream: {str(e)}") from e

    async def get_miot_scene_actions(self) -> List[Action]:
        """
        Get MiOT scene action list

        Returns:
            dict: MiOT scene action dictionary

        Raises:
            MiotServiceException: When getting scene actions fails
        """
        try:
            if not self._default_preset_action_manager:
                logger.error("DefaultPresetActionManager not initialized")
                raise MiotServiceException("DefaultPresetActionManager not initialized")

            actions = await self._default_preset_action_manager.get_miot_scene_actions()

            return list(actions.values())
        except Exception as e:
            logger.error("Failed to get MiOT scene action list: %s", e)
            raise MiotServiceException(f"Failed to get MiOT scene action list: {str(e)}") from e

    def get_camera_config(self) -> dict:
        """
        Get camera configuration

        Returns:
            dict: Camera configuration including video_quality, vision_img_resolution, frame_interval
        """
        from miloco_server.config.normal_config import CAMERA_CONFIG
        return {
            "video_quality": CAMERA_CONFIG.get("video_quality", "HIGH"),
            "vision_img_resolution": CAMERA_CONFIG.get("vision_img_resolution", 640),
            "frame_interval": CAMERA_CONFIG.get("frame_interval", 500)
        }

    def set_camera_config(self, video_quality: str, vision_img_resolution) -> dict:
        """
        Set camera configuration

        Args:
            video_quality: Video quality (LOW or HIGH)
            vision_img_resolution: Vision image resolution width

        Returns:
            dict: Updated camera configuration
        """
        logger.info("Setting camera config: video_quality=%s, vision_img_resolution=%s", 
                   video_quality, vision_img_resolution)
        
        # Validate video_quality
        if video_quality not in ["LOW", "HIGH"]:
            raise ValueError(f"video_quality must be 'LOW' or 'HIGH', got: {video_quality}")

        # Convert vision_img_resolution to int and validate
        try:
            vision_img_resolution = int(vision_img_resolution)
        except (ValueError, TypeError) as e:
            raise ValueError(f"vision_img_resolution must be a valid integer, got: {vision_img_resolution}") from e
        
        if vision_img_resolution < 0:
            raise ValueError(f"vision_img_resolution must be a non-negative integer, got: {vision_img_resolution}")

        # Update configuration in memory and save to file
        from miloco_server.config.normal_config import CAMERA_CONFIG, save_camera_config
        CAMERA_CONFIG["video_quality"] = video_quality
        CAMERA_CONFIG["vision_img_resolution"] = vision_img_resolution
        
        # Persist to YAML file
        save_camera_config(video_quality, vision_img_resolution)

        # Update miot_proxy dynamically without restart
        self._miot_proxy.update_camera_config(video_quality, vision_img_resolution)

        logger.info("Camera configuration updated and saved successfully")
        return self.get_camera_config()

    # ==================== RTSP Server Configuration ====================

    def get_rtsp_server_config(self) -> dict:
        """
        Get RTSP server configuration.

        Returns:
            dict: RTSP server configuration including enabled and port
        """
        from miloco_server.config.normal_config import RTSP_SERVER_CONFIG
        return {
            "enabled": bool(RTSP_SERVER_CONFIG.get("enabled", True)),
            "port": int(RTSP_SERVER_CONFIG.get("port", 8554)),
        }

    def set_rtsp_server_config(self, enabled: bool, port: int) -> dict:
        """
        Set RTSP server configuration.

        Args:
            enabled: Whether RTSP server is enabled
            port: RTSP server listening port

        Returns:
            dict: Updated RTSP server configuration
        """
        logger.info("Setting RTSP server config: enabled=%s, port=%s", enabled, port)

        # Validate port
        try:
            port = int(port)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"port must be a valid integer, got: {port}") from exc

        if port <= 0 or port > 65535:
            raise ValueError(f"port must be between 1 and 65535, got: {port}")

        # Persist to YAML file
        from miloco_server.config.normal_config import save_rtsp_server_config
        save_rtsp_server_config(bool(enabled), port)

        # Update miot_proxy dynamically without restart
        try:
            self._miot_proxy.update_rtsp_server_config(bool(enabled), port)
        except AttributeError:
            # Older MiotProxy without dynamic update support, ignore
            logger.warning("MiotProxy does not support dynamic RTSP server update")

        logger.info("RTSP server configuration updated and saved successfully")
        return self.get_rtsp_server_config()

    # ==================== RTSP Camera Management ====================

    def get_rtsp_cameras(self) -> List[dict]:
        """
        Get all RTSP camera configurations

        Returns:
            List[dict]: List of RTSP camera configurations
        """
        from miloco_server.config.normal_config import RTSP_CAMERA_CONFIG
        cameras = []
        for camera in RTSP_CAMERA_CONFIG:
            cameras.append({
                "did": camera.get("did", ""),
                "name": camera.get("name", ""),
                "rtsp_url": camera.get("rtsp_url", ""),
                "enable_audio": camera.get("enable_audio", False),
                "transport": camera.get("transport", "udp"),
                "home_name": camera.get("home_name", "家"),
                "room_name": camera.get("room_name", "客厅"),
                "codec": camera.get("codec", None),
                "vendor": camera.get("vendor", None),
                "model": camera.get("model", "rtsp_camera"),
                "icon": camera.get("icon", None)
            })
        return cameras

    def create_rtsp_camera(self, camera_data: dict) -> dict:
        """
        Create a new RTSP camera

        Args:
            camera_data: Camera configuration data

        Returns:
            dict: Created camera configuration

        Raises:
            ValueError: If camera with same did already exists
        """
        from miloco_server.config.normal_config import RTSP_CAMERA_CONFIG

        did = camera_data.get("did")

        # Check if camera with same did exists
        for camera in RTSP_CAMERA_CONFIG:
            if camera.get("did") == did:
                raise ValueError(f"Camera with did '{did}' already exists")

        # Validate transport
        transport = camera_data.get("transport", "udp")
        if transport not in ["tcp", "udp"]:
            raise ValueError("transport must be 'tcp' or 'udp'")

        # Create new camera config with all required fields for RtspCameraConfig
        new_camera = {
            "did": did,
            "name": camera_data.get("name", ""),
            "rtsp_url": camera_data.get("rtsp_url", ""),
            "enable_audio": camera_data.get("enable_audio", False),
            "transport": transport,
            "home_name": camera_data.get("home_name", "家"),
            "room_name": camera_data.get("room_name", "客厅"),
            "codec": camera_data.get("codec", None),
            "vendor": camera_data.get("vendor", None),
            "model": camera_data.get("model", "rtsp_camera"),
            "icon": camera_data.get("icon", None)
        }

        RTSP_CAMERA_CONFIG.append(new_camera)
        
        # Persist to YAML file
        from miloco_server.config.normal_config import save_rtsp_cameras
        save_rtsp_cameras(RTSP_CAMERA_CONFIG.copy())
        
        # Update miot_proxy dynamically without restart
        import asyncio
        try:
            asyncio.create_task(self._miot_proxy.update_rtsp_camera_configs(RTSP_CAMERA_CONFIG.copy()))
            logger.info("RTSP camera configs update scheduled: %s", did)
        except Exception as e:
            logger.warning("Failed to schedule RTSP camera config update: %s", e)
        
        logger.info("RTSP camera created and saved: %s", did)

        return new_camera

    def update_rtsp_camera(self, did: str, camera_data: dict) -> dict:
        """
        Update an existing RTSP camera

        Args:
            did: Camera unique id
            camera_data: Camera configuration data to update

        Returns:
            dict: Updated camera configuration

        Raises:
            ValueError: If camera not found
        """
        from miloco_server.config.normal_config import RTSP_CAMERA_CONFIG

        # Find camera by did
        for camera in RTSP_CAMERA_CONFIG:
            if camera.get("did") == did:
                # Update fields
                if "name" in camera_data:
                    camera["name"] = camera_data["name"]
                if "rtsp_url" in camera_data:
                    camera["rtsp_url"] = camera_data["rtsp_url"]
                if "enable_audio" in camera_data:
                    camera["enable_audio"] = camera_data["enable_audio"]
                if "transport" in camera_data:
                    transport = camera_data["transport"]
                    if transport not in ["tcp", "udp"]:
                        raise ValueError("transport must be 'tcp' or 'udp'")
                    camera["transport"] = transport
                if "home_name" in camera_data:
                    camera["home_name"] = camera_data["home_name"]
                if "room_name" in camera_data:
                    camera["room_name"] = camera_data["room_name"]
                if "codec" in camera_data:
                    camera["codec"] = camera_data["codec"]
                if "vendor" in camera_data:
                    camera["vendor"] = camera_data["vendor"]
                if "model" in camera_data:
                    camera["model"] = camera_data["model"]
                if "icon" in camera_data:
                    camera["icon"] = camera_data["icon"]

                # Persist to YAML file
                from miloco_server.config.normal_config import save_rtsp_cameras
                save_rtsp_cameras(RTSP_CAMERA_CONFIG.copy())
                
                # Update miot_proxy dynamically without restart
                import asyncio
                try:
                    asyncio.create_task(self._miot_proxy.update_rtsp_camera_configs(RTSP_CAMERA_CONFIG.copy()))
                    logger.info("RTSP camera configs update scheduled after update: %s", did)
                except Exception as e:
                    logger.warning("Failed to schedule RTSP camera config update: %s", e)
                
                logger.info("RTSP camera updated and saved: %s", did)
                return {
                    "did": camera["did"],
                    "name": camera["name"],
                    "rtsp_url": camera["rtsp_url"],
                    "enable_audio": camera["enable_audio"],
                    "transport": camera.get("transport", "udp"),
                    "home_name": camera.get("home_name", "家"),
                    "room_name": camera.get("room_name", "客厅"),
                    "codec": camera.get("codec", None),
                    "vendor": camera.get("vendor", None),
                    "model": camera.get("model", "rtsp_camera"),
                    "icon": camera.get("icon", None)
                }

        raise ValueError(f"Camera with did '{did}' not found")

    def delete_rtsp_camera(self, did: str) -> bool:
        """
        Delete an RTSP camera

        Args:
            did: Camera unique id

        Returns:
            bool: True if deleted successfully

        Raises:
            ValueError: If camera not found
        """
        from miloco_server.config.normal_config import RTSP_CAMERA_CONFIG

        for i, camera in enumerate(RTSP_CAMERA_CONFIG):
            if camera.get("did") == did:
                RTSP_CAMERA_CONFIG.pop(i)
                
                # Persist to YAML file
                from miloco_server.config.normal_config import save_rtsp_cameras
                save_rtsp_cameras(RTSP_CAMERA_CONFIG.copy())
                
                # Update miot_proxy dynamically without restart
                import asyncio
                try:
                    asyncio.create_task(self._miot_proxy.update_rtsp_camera_configs(RTSP_CAMERA_CONFIG.copy()))
                    logger.info("RTSP camera configs update scheduled after delete: %s", did)
                except Exception as e:
                    logger.warning("Failed to schedule RTSP camera config update: %s", e)
                
                logger.info("RTSP camera deleted and saved: %s", did)
                return True

        raise ValueError(f"Camera with did '{did}' not found")
