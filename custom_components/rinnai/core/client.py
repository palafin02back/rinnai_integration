"""Unified client for Rinnai integration."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
import hashlib
import json
import logging
import time
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import AK, INFO_URL, LOGIN_URL, PROCESS_PARAMETER_URL, REFESH_TIME, BASE_URL
from .config_manager import config_manager
from .mqtt_client import RinnaiMQTTClient

_LOGGER = logging.getLogger(__name__)


class RinnaiClient:
    """Unified client for interacting with Rinnai devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        update_interval: int = 300,
        connect_timeout: int = 30,
    ) -> None:
        """Initialize the unified Rinnai client."""
        self.hass = hass
        self.username = username
        # MD5 hash for HTTP API
        self.password_hash = str.upper(
            hashlib.md5(password.encode("utf-8")).hexdigest()
        )
        self.connect_timeout = connect_timeout
        self.update_interval = update_interval

        # HTTP session
        self._session = async_get_clientsession(hass)
        self._token: str | None = None
        self._lock = asyncio.Lock()
        self._last_login_time = 0

        # Device data storage
        self.devices: dict[str, dict[str, Any]] = {}
        self.device_states: dict[str, dict[str, Any]] = {}
        self._device_configs: dict[str, Any] = {}

        # Callbacks
        self._state_callbacks: dict[str, list[Callable[[dict[str, Any]], None]]] = {}

        # Initialize custom MQTT client
        self._mqtt_client = RinnaiMQTTClient(hass, self.username, self.password_hash)

        # Track MQTT subscriptions
        self._mqtt_subscriptions: dict[str, Callable[[], None]] = {}

        # Track initialization status
        self._initialized = False

    def register_callback(
        self, device_id: str, callback_func: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Register a callback for device state updates."""
        if device_id not in self._state_callbacks:
            self._state_callbacks[device_id] = []

        self._state_callbacks[device_id].append(callback_func)

        def remove_callback() -> None:
            """Remove the callback."""
            if device_id in self._state_callbacks:
                if callback_func in self._state_callbacks[device_id]:
                    self._state_callbacks[device_id].remove(callback_func)

        return remove_callback

    async def async_initialize(self) -> bool:
        """Initialize the client and fetch initial device data."""
        if not await self.login():
            return False

        # Get devices
        if not await self.fetch_devices():
            return False

        # Connect to MQTT
        if not await self._mqtt_client.async_connect():
            _LOGGER.warning("Failed to connect to Rinnai MQTT broker, will retry later")

        # Setup MQTT for each device
        for device_id in self.devices:
            await self._setup_mqtt_for_device(device_id)

        self._initialized = True
        return True

    async def login(self) -> bool:
        """Log in to the Rinnai HTTP API."""
        now = time.time()
        if self._token and now - self._last_login_time < REFESH_TIME:
            return True

        async with self._lock:
            now = time.time()
            if self._token and now - self._last_login_time < REFESH_TIME:
                return True

            try:
                async with asyncio.timeout(self.connect_timeout):
                    login_data = {
                        "username": self.username,
                        "password": self.password_hash,
                        "accessKey": AK,
                        "appType": "2",
                        "appVersion": "1.0.0",
                        "identityLevel": "0",
                    }

                    response = await self._session.get(
                        LOGIN_URL,
                        params=login_data,
                        headers={"Content-Type": "application/json"},
                    )

                    resp_json = await response.json()
                    if resp_json.get("success") is not True:
                        _LOGGER.error(
                            "Failed to login to Rinnai: %s",
                            resp_json.get("msg", "Unknown error"),
                        )
                        return False

                    self._token = resp_json.get("data", {}).get("token")
                    self._last_login_time = time.time()
                    return True
            except (TimeoutError, aiohttp.ClientError) as err:
                _LOGGER.error("Error connecting to Rinnai API: %s", err)
                return False

    async def fetch_devices(self) -> bool:
        """Fetch devices from the Rinnai API."""
        if not self._token and not await self.login():
            return False

        try:
            async with asyncio.timeout(self.connect_timeout):
                headers = {"Authorization": f"Bearer {self._token}"}
                response = await self._session.get(INFO_URL, headers=headers)
                resp_json = await response.json()

                if resp_json.get("success") is not True:
                    _LOGGER.error(
                        "Failed to get devices: %s",
                        resp_json.get("msg", "Unknown error"),
                    )
                    return False

                devices_list = resp_json.get("data", {}).get("list", [])
                if not devices_list:
                    _LOGGER.warning("No devices found")
                    return False

                for device in devices_list:
                    device_id = device.get("id")
                    if not device_id:
                        continue

                    self.devices[device_id] = device
                    if device_id not in self.device_states:
                        self.device_states[device_id] = {}
                    
                    device_type = device.get("deviceType", "Unknown")
                    self._device_configs[device_id] = config_manager.get_config(device_type)

                return True
        except (TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error("Error getting devices from Rinnai API: %s", err)
            return False

    async def fetch_device_state(self, device_id: str) -> bool:
        """Fetch the state of a device via HTTP API."""
        if not self._token and not await self.login():
            return False

        try:
            async with asyncio.timeout(self.connect_timeout):
                headers = {"Authorization": f"Bearer {self._token}"}
                response = await self._session.get(
                    PROCESS_PARAMETER_URL,
                    params={"deviceId": device_id},
                    headers=headers,
                )
                resp_json = await response.json()

                if resp_json.get("success") is not True:
                    _LOGGER.error(
                        "Failed to get device %s: %s",
                        device_id,
                        resp_json.get("msg", "Unknown error"),
                    )
                    return False

                self.device_states[device_id] = resp_json.get("data", {})
                return True

        except (TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error("Error setting parameter: %s", err)
            return False

    async def perform_request(self, device_id: str, request_name: str, **kwargs) -> dict[str, Any] | bool | None:
        """
        Perform a configurable request.
        
        Args:
            device_id: The device ID.
            request_name: The name of the request in config (e.g., 'get_schedule').
            **kwargs: Parameters to substitute in the request template.
        """
        if not self._token and not await self.login():
            return None

        device = self.devices.get(device_id)
        if not device:
            _LOGGER.error("Device %s not found", device_id)
            return None
            
        config = self._device_configs.get(device_id)
        if not config:
            _LOGGER.error("No config for device %s", device_id)
            return None
            
        request_config = config.requests.get(request_name)
        if not request_config:
            _LOGGER.error("Request %s not defined in config for device %s", request_name, device_id)
            return None

        # Prepare context for substitution
        context = {
            "mac": device.get("mac"),
            "device_id": device_id,
            **config.features, # Include features like heat_type
            **kwargs
        }
        
        url_path = request_config.get("url", "")
        method = request_config.get("method", "GET")
        
        # Construct full URL
        # If url_path starts with http, use it as is, otherwise append to BASE_URL
        if url_path.startswith("http"):
            url = url_path
        else:
            # Remove leading slash if present to avoid double slash issue if BASE_URL ends with slash
            # But simple concatenation is usually fine if we are careful
            url = f"{BASE_URL}{url_path}"

        # Substitute params
        params = request_config.get("params", {})
        data = request_config.get("data", {})
        
        # Helper to substitute values
        def substitute(obj):
            if isinstance(obj, dict):
                return {k: substitute(v) for k, v in obj.items()}
            if isinstance(obj, str):
                try:
                    return obj.format(**context)
                except KeyError as e:
                    _LOGGER.warning("Missing key %s for request %s", e, request_name)
                    return obj
            return obj

        final_params = substitute(params)
        final_data = substitute(data)

        try:
            async with asyncio.timeout(self.connect_timeout):
                headers = {"Authorization": f"Bearer {self._token}"}
                
                if method == "GET":
                    response = await self._session.get(url, params=final_params, headers=headers)
                elif method == "POST":
                    response = await self._session.post(url, data=final_data, headers=headers)
                else:
                    _LOGGER.error("Unsupported method %s", method)
                    return None

                resp_json = await response.json()
                
                if resp_json.get("success") is not True:
                    _LOGGER.error(
                        "Request %s failed: %s",
                        request_name,
                        resp_json.get("msg", "Unknown error"),
                    )
                    return False

                return resp_json.get("data", True)

        except (TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error("Error performing request %s: %s", request_name, err)
            return None

    async def get_schedule_info(self, device_id: str) -> dict[str, Any] | None:
        """Get schedule info using configurable request."""
        return await self.perform_request(device_id, "get_schedule")

    async def save_schedule_hour(self, device_id: str, schedule_data: str) -> bool:
        """Save schedule info using configurable request."""
        result = await self.perform_request(device_id, "save_schedule", data=schedule_data)
        return bool(result)

    @callback
    def _handle_state_update(self, device_id: str, state_data: dict[str, Any]) -> None:
        """Handle state updates from MQTT."""
        if device_id not in self.device_states:
            self.device_states[device_id] = {}

        self.device_states[device_id].update(state_data)
        
        # Sync heatingReservationMode to byteStr if present
        if "heatingReservationMode" in state_data:
            self.device_states[device_id]["byteStr"] = state_data["heatingReservationMode"]

        # Notify callbacks
        if device_id in self._state_callbacks:
            for callback_func in self._state_callbacks[device_id]:
                try:
                    callback_func(self.device_states[device_id])
                except Exception as err:
                    _LOGGER.error("Error in state callback for device %s: %s", device_id, err)

    async def _setup_mqtt_for_device(self, device_id: str) -> None:
        """Set up MQTT subscriptions for a device."""
        if not self._mqtt_client.connected:
            if not await self._mqtt_client.async_connect():
                return

        device_mac = self.devices.get(device_id, {}).get("mac")
        if not device_mac:
            return

        topics = {
            "inf": f"rinnai/SR/01/SR/{device_mac}/inf/",
            "stg": f"rinnai/SR/01/SR/{device_mac}/stg/",
        }

        for topic_type, topic in topics.items():
            @callback
            def message_received(msg, topic_type=topic_type, device_id=device_id):
                try:
                    payload = json.loads(msg.payload)
                    
                    if (topic_type == "inf" and payload.get("enl") and payload.get("code") == "FFFF"):
                        state_data = self._process_device_info(payload)
                        if state_data:
                            self._handle_state_update(device_id, state_data)
                    elif (topic_type == "stg" and payload.get("egy") and payload.get("ptn") == "J05"):
                        state_data = self._process_energy_data(payload, device_id)
                        if state_data:
                            self._handle_state_update(device_id, state_data)
                    elif (topic_type == "inf" and payload.get("enl") and payload.get("code") == "03F1"):
                        state_data = self._process_reservation_info(payload)
                        if state_data:
                            self._handle_state_update(device_id, state_data)
                            
                except Exception as err:
                    _LOGGER.error("Error processing MQTT message: %s", err)

            subscription = await self._mqtt_client.async_subscribe(topic, message_received)
            self._mqtt_subscriptions[f"{device_id}_{topic_type}"] = subscription

    def _process_device_info(self, parsed_data: dict[str, Any]) -> dict[str, Any]:
        state_data = {}
        for param in parsed_data.get("enl", []):
            if param_id := param.get("id"):
                state_data[param_id] = param.get("data")
        return state_data
    
    def _process_reservation_info(self, parsed_data: dict[str, Any]) -> dict[str, Any]:
        return self._process_device_info(parsed_data)

    def _process_energy_data(self, parsed_data: dict[str, Any], device_id: str) -> dict[str, Any]:
        updates = {}
        device_config = self._device_configs.get(device_id)
        
        energy_keys = []
        if device_config:
            energy_keys = device_config.features.get("energy_data_keys", [])
            
        for param in parsed_data.get("egy", []):
            if isinstance(param, dict):
                for key in energy_keys:
                    if key in param:
                        updates[key] = param[key]
        return updates

    async def send_command(self, device_id: str, command: dict[str, Any]) -> bool:
        """Send command to a device via MQTT."""
        if not self._mqtt_client.connected:
            if not await self._mqtt_client.async_connect():
                return False

        if device_id not in self.devices:
            return False

        device_data = self.devices[device_id]
        auth_code = device_data.get("authCode", "03F1")
        device_mac = device_data.get("mac")
        if not device_mac:
            return False

        device_classid = device_data.get("classID")
        set_topic = f"rinnai/SR/01/SR/{device_mac}/set/"
        rinnai_message = {
            "code": auth_code,
            "enl": [{"data": str(value), "id": key} for key, value in command.items()],
            "id": device_classid,
            "ptn": "J00",
            "sum": "1",
        }

        try:
            return await self._mqtt_client.async_publish(
                set_topic, json.dumps(rinnai_message), qos=1
            )
        except Exception as err:
            _LOGGER.error("Error sending MQTT command: %s", err)
            return False

    async def async_close(self) -> None:
        """Close the client connections."""
        for unsub in self._mqtt_subscriptions.values():
            if callable(unsub):
                unsub()
        self._mqtt_subscriptions.clear()
        await self._mqtt_client.async_disconnect()
