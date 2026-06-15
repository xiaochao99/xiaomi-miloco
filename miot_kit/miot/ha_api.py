# -*- coding: utf-8 -*-
# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
"""
Home Assistant API clients (REST + WebSocket).
"""
# pylint: disable=too-many-arguments, too-many-positional-arguments
# pylint: disable=too-many-instance-attributes
import asyncio
from datetime import datetime
import json
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
import aiohttp

from .types import HAAutomationInfo, HAStateInfo

from .oauth2 import BaseOAuth2Client

_LOGGER = logging.getLogger(__name__)

HA_HTTP_API_TIMEOUT: int = 30
HA_WS_RECONNECT_INTERVAL: int = 5
HA_WS_PING_INTERVAL: int = 30

SUPPORT_ENTITY_CLASSES = {
    "light": {
        "name": "Light"
    }
}


class HAOAuth2Client(BaseOAuth2Client):
    """OAuth2 agent url, default: product env."""

    async def revoke_token_async(self, refresh_token: str) -> None:
        """Revoke access token.

        Args:
            refresh_token (str): Refresh token.

        Returns:
            bool: True if success, False otherwise.
        """
        if not refresh_token:
            raise ValueError("invalid refresh_token")

        http_res = await self._session.post(
            url=f"{self._base_url}/auth/revoke",
            data={
                "token": refresh_token,
                "action": "revoke"
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=self._AUTH_API_TIMEOUT
        )
        if http_res.status != 200:
            raise ValueError(f"revoke token failed, {http_res.status}")


class HAHttpClient:
    """
    Home Assistant http client.
    Successful calls will return status code 200 or 201. Other status codes that can return are:
    400 (Bad Request)
    401 (Unauthorized)
    404 (Not Found)
    405 (Method Not Allowed)
    """
    _main_loop: asyncio.AbstractEventLoop
    _session: aiohttp.ClientSession
    _base_url: str
    _token: str

    _states_buffer: Dict[str, HAStateInfo]

    def __init__(
        self, base_url: str, access_token: str,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> None:
        """Initialize."""
        self._main_loop = loop or asyncio.get_running_loop()
        if not base_url or not access_token:
            raise ValueError("invalid init params")
        self._base_url = base_url
        self._token = access_token

        self._states_buffer = {}

        self._session = aiohttp.ClientSession(loop=self._main_loop)

    async def deinit_async(self) -> None:
        """Deinit the client."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __api_get_async(
        self, url_path: str, params: Dict,
        timeout: int = HA_HTTP_API_TIMEOUT
    ) -> Dict:
        """Get data from ha api with http get."""
        http_res = await self._session.get(
            url=f"{self._base_url}{url_path}",
            params=params,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token}"
            },
            timeout=aiohttp.ClientTimeout(total=timeout))
        if http_res.status == 401:
            raise TypeError("ha api get failed, unauthorized(401)")
        if http_res.status not in [200, 201]:
            raise TypeError(f"ha api get failed, {http_res.status}, {url_path}, {params}")
        return await http_res.json()

    async def __api_post_async(
        self, url_path: str, data: Dict,
        timeout: int = HA_HTTP_API_TIMEOUT
    ) -> Dict:
        """Get data from ha api with http post."""
        http_res = await self._session.post(
            url=f"{self._base_url}{url_path}",
            json=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token}"
            },
            timeout=aiohttp.ClientTimeout(total=timeout))
        if http_res.status == 401:
            raise TypeError("ha api get failed, unauthorized(401)")
        if http_res.status not in [200, 201]:
            raise TypeError(f"ha api post failed, {http_res.status}, {url_path}, {data}")
        return await http_res.json()

    async def update_info_async(self, token: str) -> None:
        """Update the url and token."""
        if not token:
            raise ValueError("invalid token")
        self._token = token

    async def check_token_async(self) -> bool:
        """Check the token."""
        return await HAHttpClient.validate_async(url=self._base_url, token=self._token, loop=self._main_loop)

    @staticmethod
    async def validate_async(
        url: str,
        token: str,
        loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> bool:
        """Validate the token."""
        if not isinstance(url, str) or url.strip() == "":
            raise ValueError("invalid url")
        if not isinstance(token, str) or token.strip() == "":
            raise ValueError("invalid token")
        async with aiohttp.ClientSession(loop=loop or asyncio.get_running_loop()) as session:
            http_res = await session.get(
                url=f"{url}/api/",
                params={},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                },
                timeout=10
            )
            if http_res.status == 401:
                raise TypeError("ha api get failed, unauthorized(401)")
            if http_res.status not in [200, 201]:
                raise TypeError(f"ha auth get failed, code={http_res.status}")
            res_obj = await http_res.json()
            if "message" not in res_obj:
                raise TypeError(f"invalid response, {res_obj}")
            _LOGGER.debug("Token is valid: %s", res_obj)
            return True
        _LOGGER.error("Failed to validate token, %s", url)
        return False

    async def get_states_async(
        self, entity_id: Optional[str] = None, force_update: bool = True
    ) -> Dict[str, HAStateInfo]:
        """Get states."""
        if not force_update and self._states_buffer:
            if entity_id:
                if entity_id in self._states_buffer:
                    return {entity_id: self._states_buffer[entity_id]}
            else:
                return self._states_buffer
        res_obj = await self.__api_get_async(
            url_path="/api/states" + (f"/{entity_id}" if entity_id else ""),
            params={}
        )
        if entity_id:
            if not isinstance(res_obj, Dict):
                raise TypeError(f"invalid response, {res_obj}")
        elif not isinstance(res_obj, List):
            raise TypeError(f"invalid response, {res_obj}")
        states: Dict[str, HAStateInfo] = {}

        for state in res_obj if isinstance(res_obj, List) else [res_obj]:
            if (
                "entity_id" not in state
                or "state" not in state
                or "attributes" not in state
                or "friendly_name" not in state["attributes"]
            ):
                _LOGGER.warning("unknown state: %s", state)
                continue
            eid: str = state["entity_id"]
            states[eid] = HAStateInfo(
                entity_id=eid,
                domain=eid.partition(".")[0],
                state=state["state"],
                friendly_name=state["attributes"]["friendly_name"],
                last_changed=state.get("last_changed", 0),
                last_reported=state.get("last_reported", 0),
                last_updated=state.get("last_updated", 0),
                attributes=state.get("attributes", {}),
                context=state.get("context", {})
            )

        return states

    async def call_service(self, domain: str, service: str, entity_id: str) -> bool:
        """Call a service."""
        if not domain or not service or not entity_id:
            raise ValueError("invalid params")
        res_obj = await self.__api_post_async(
            url_path=f"/api/services/{domain}/{service}",
            data={
                "entity_id": entity_id
            }
        )
        if not isinstance(res_obj, List):
            raise TypeError(f"invalid response, {res_obj}")
        return True

    async def get_automations_async(self, force_update: bool = True) -> Dict[str, HAAutomationInfo]:
        """Get all automations."""
        res_obj = await self.get_states_async(force_update=force_update)
        automations: Dict[str, HAAutomationInfo] = {}
        for e_id, item in res_obj.items():
            if item.domain != "automation":
                continue
            last_triggered = item.attributes.get("last_triggered", None)
            last_triggered_ts = 0
            if last_triggered:
                try:
                    last_triggered_ts = int(datetime.fromisoformat(
                        last_triggered).timestamp()*1000)
                except Exception:  # pylint: disable=broad-except
                    pass
            automations[e_id] = HAAutomationInfo(
                **item.model_dump(),
                last_triggered=last_triggered_ts,
                attr_id=item.attributes.get("id", ""),
                attr_mode=item.attributes.get("mode", "")
            )
        return automations

    async def trigger_automation_async(self, automation: str | HAAutomationInfo) -> bool:
        """Trigger automation."""
        return await self.call_service(
            domain="automation",
            service="trigger",
            entity_id=automation if isinstance(automation, str) else automation.entity_id
        )

    async def render_template_async(self, template_str: str, timeout: int = HA_HTTP_API_TIMEOUT) -> str:
        """Render a Home Assistant template."""
        if not template_str:
            raise ValueError("invalid template")
        http_res = await self._session.post(
            url=f"{self._base_url}/api/template",
            json={"template": template_str},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token}"
            },
            timeout=aiohttp.ClientTimeout(total=timeout)
        )

        if http_res.status == 401:
            raise TypeError("ha api get failed, unauthorized(401)")
        if http_res.status not in [200, 201]:
            raise TypeError(f"ha api template failed, {http_res.status}")

        return await http_res.text()

    async def get_config_async(self) -> Dict:
        """Get configuration."""
        return await self.__api_get_async(url_path="/api/config", params={})


class HAWebSocketClient:
    """
    Home Assistant WebSocket client.
    
    Maintains a persistent WebSocket connection for faster device queries and control.
    Supports auto-reconnection and real-time state change subscriptions.
    
    Usage:
        ws = HAWebSocketClient("http://192.168.31.10:8123", "token")
        await ws.connect()
        states = await ws.get_states()
        await ws.call_service("light", "turn_on", {"entity_id": "light.living_room"})
        await ws.disconnect()
    """

    def __init__(
        self,
        base_url: str,
        access_token: str,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self._main_loop = loop or asyncio.get_event_loop()
        self._base_url = base_url.rstrip("/")
        self._token = access_token
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._connected = False
        self._msg_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._state_subscribers: List[Callable[[Dict[str, Any]], Coroutine]] = []
        self._recv_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._last_states: Dict[str, HAStateInfo] = {}

    @property
    def ws_url(self) -> str:
        """Convert http(s):// to ws(s)://."""
        url = self._base_url
        if url.startswith("https://"):
            url = "wss://" + url[8:]
        elif url.startswith("http://"):
            url = "ws://" + url[5:]
        else:
            url = "ws://" + url
        return f"{url}/api/websocket"

    async def connect(self) -> bool:
        """Connect to HA WebSocket and authenticate."""
        try:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(loop=self._main_loop)

            self._ws = await self._session.ws_connect(
                self.ws_url,
                heartbeat=HA_WS_PING_INTERVAL,
                timeout=aiohttp.ClientTimeout(total=10),
            )

            # Wait for auth required
            msg = await self._ws.receive(timeout=5)
            if msg.type != aiohttp.WSMsgType.TEXT:
                _LOGGER.error("HA WS: unexpected message type: %s", msg.type)
                return False

            data = json.loads(msg.data)
            if data.get("type") != "auth_required":
                _LOGGER.error("HA WS: expected auth_required, got: %s", data.get("type"))
                return False

            # Send auth
            await self._ws.send_json({
                "type": "auth",
                "access_token": self._token,
            })

            # Wait for auth result
            msg = await self._ws.receive(timeout=5)
            if msg.type != aiohttp.WSMsgType.TEXT:
                _LOGGER.error("HA WS: unexpected message type during auth: %s", msg.type)
                return False

            data = json.loads(msg.data)
            if data.get("type") == "auth_ok":
                _LOGGER.info("HA WS: connected and authenticated")
                self._connected = True
                # Start background receiver
                self._recv_task = asyncio.ensure_future(self._recv_loop())
                return True
            else:
                _LOGGER.error("HA WS: auth failed: %s", data)
                return False

        except Exception as e:  # pylint: disable=broad-except
            _LOGGER.error("HA WS: connection failed: %s", e)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from HA WebSocket."""
        self._connected = False
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        self._ws = None
        self._session = None
        _LOGGER.info("HA WS: disconnected")

    async def _recv_loop(self) -> None:
        """Background task to receive WebSocket messages."""
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    msg_id = data.get("id")
                    # Resolve pending request
                    if msg_id and msg_id in self._pending:
                        fut = self._pending.pop(msg_id)
                        if not fut.done():
                            fut.set_result(data)
                    # Handle state change events
                    elif data.get("type") == "state_changed":
                        event = data.get("event", {})
                        new_state = event.get("new_state")
                        if new_state:
                            self._update_state_cache(new_state)
                            for subscriber in self._state_subscribers:
                                try:
                                    await subscriber(new_state)
                                except Exception as e:  # pylint: disable=broad-except
                                    _LOGGER.debug("HA WS subscriber error: %s", e)
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    _LOGGER.warning("HA WS: connection lost (type=%s)", msg.type)
                    self._connected = False
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:  # pylint: disable=broad-except
            _LOGGER.error("HA WS: recv loop error: %s", e)
            self._connected = False

        # Auto-reconnect
        if self._connected is False:
            self._reconnect_task = asyncio.ensure_future(self._reconnect())

    async def _reconnect(self) -> None:
        """Auto-reconnect loop."""
        while not self._connected:
            try:
                _LOGGER.info("HA WS: attempting reconnect in %ds...", HA_WS_RECONNECT_INTERVAL)
                await asyncio.sleep(HA_WS_RECONNECT_INTERVAL)
                if await self.connect():
                    # Re-subscribe to state changes after reconnect
                    await self._subscribe_state_changes()
                    break
            except asyncio.CancelledError:
                break
            except Exception as e:  # pylint: disable=broad-except
                _LOGGER.error("HA WS: reconnect failed: %s", e)

    async def _send_command(self, msg_type: str, data: Optional[Dict] = None,
                            timeout: float = 10.0) -> Dict:
        """Send a command and wait for response."""
        if not self._connected or not self._ws:
            raise ConnectionError("HA WS not connected")

        self._msg_id += 1
        msg_id = self._msg_id

        payload = {"id": msg_id, "type": msg_type}
        if data:
            payload.update(data)

        fut = self._main_loop.create_future()
        self._pending[msg_id] = fut

        await self._ws.send_json(payload)

        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"HA WS command '{msg_type}' timed out after {timeout}s")

        if result.get("success") is False:
            error = result.get("error", {})
            raise RuntimeError(f"HA WS error: {error.get('code', 'unknown')} - {error.get('message', '')}")

        return result

    async def ensure_connected(self) -> bool:
        """Ensure WebSocket is connected, reconnect if needed."""
        if self._connected and self._ws and not self._ws.closed:
            return True
        return await self.connect()

    # ── High-level API methods ──

    async def get_states(self) -> Dict[str, HAStateInfo]:
        """Get all entity states via WebSocket (single command, no HTTP overhead)."""
        await self.ensure_connected()
        result = await self._send_command("get_states", timeout=15)
        states: Dict[str, HAStateInfo] = {}
        for state in result.get("result", []):
            if (
                "entity_id" not in state
                or "state" not in state
                or "attributes" not in state
            ):
                continue
            eid = state["entity_id"]
            states[eid] = HAStateInfo(
                entity_id=eid,
                domain=eid.partition(".")[0],
                state=state["state"],
                friendly_name=state.get("attributes", {}).get("friendly_name", eid),
                last_changed=0,
                last_reported=0,
                last_updated=0,
                attributes=state.get("attributes", {}),
                context=state.get("context", {}),
            )
        self._last_states = states
        return states

    async def get_state(self, entity_id: str) -> Optional[HAStateInfo]:
        """Get a single entity state via WebSocket."""
        await self.ensure_connected()
        result = await self._send_command("get_states", timeout=10)
        for state in result.get("result", []):
            if state.get("entity_id") == entity_id:
                return HAStateInfo(
                    entity_id=entity_id,
                    domain=entity_id.partition(".")[0],
                    state=state["state"],
                    friendly_name=state.get("attributes", {}).get("friendly_name", entity_id),
                    last_changed=0,
                    last_reported=0,
                    last_updated=0,
                    attributes=state.get("attributes", {}),
                    context=state.get("context", {}),
                )
        return None

    async def call_service(
        self,
        domain: str,
        service: str,
        service_data: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
    ) -> bool:
        """Call a service via WebSocket (faster than REST API)."""
        await self.ensure_connected()
        data: Dict[str, Any] = {
            "domain": domain,
            "service": service,
        }
        if service_data:
            data["service_data"] = service_data

        result = await self._send_command("call_service", data, timeout=timeout)
        return result.get("success", False)

    async def subscribe_state_changes(self) -> bool:
        """Subscribe to all state change events (real-time push)."""
        await self.ensure_connected()
        result = await self._send_command("subscribe_events", {"event_type": "state_changed"})
        return result.get("success", False)

    async def _subscribe_state_changes(self) -> None:
        """Internal: re-subscribe after reconnect."""
        try:
            await self.subscribe_state_changes()
        except Exception as e:  # pylint: disable=broad-except
            _LOGGER.debug("HA WS: re-subscribe failed: %s", e)

    def on_state_change(self, callback: Callable[[Dict[str, Any]], Coroutine]) -> None:
        """Register a state change callback."""
        self._state_subscribers.append(callback)

    def _update_state_cache(self, state_data: Dict) -> None:
        """Update internal state cache from state_changed event."""
        eid = state_data.get("entity_id")
        if not eid:
            return
        attrs = state_data.get("attributes", {})
        self._last_states[eid] = HAStateInfo(
            entity_id=eid,
            domain=eid.partition(".")[0],
            state=state_data.get("state", ""),
            friendly_name=attrs.get("friendly_name", eid),
            last_changed=0,
            last_reported=0,
            last_updated=0,
            attributes=attrs,
            context=state_data.get("context", {}),
        )

    def get_cached_states(self) -> Dict[str, HAStateInfo]:
        """Get cached states without making any network call."""
        return self._last_states

    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected and self._ws is not None and not self._ws.closed
