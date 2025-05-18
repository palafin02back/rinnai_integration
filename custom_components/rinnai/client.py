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

from .const import AK, INFO_URL, LOGIN_URL, PROCESS_PARAMETER_URL, REFESH_TIME
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

        # Callbacks
        self._state_callbacks: dict[str, list[Callable[[dict[str, Any]], None]]] = {}

        # Initialize custom MQTT client
        self._mqtt_client = RinnaiMQTTClient(hass, self.username, self.password_hash)

        # Track MQTT subscriptions
        self._mqtt_subscriptions: dict[str, Callable[[], None]] = {}

        # Track initialization status
        self._initialized = False

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
            # 不中断初始化，依然可以通过HTTP获取数据

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
            # Check again inside the lock
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
                    _LOGGER.debug("Login response: %s", resp_json)
                    if resp_json.get("success") is not True:
                        _LOGGER.error(
                            "Failed to login to Rinnai: %s",
                            resp_json.get("msg", "Unknown error"),
                        )
                        return False

                    self._token = resp_json.get("data", {}).get("token")
                    self._last_login_time = time.time()

                    _LOGGER.debug("Logged in to Rinnai API successfully")
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
                _LOGGER.debug("Get devices response: %s", resp_json)

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

                # Process devices
                for device in devices_list:
                    device_id = device.get("id")
                    if not device_id:
                        continue

                    self.devices[device_id] = device
                    # Initialize state data structure
                    if device_id not in self.device_states:
                        self.device_states[device_id] = {}

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

                # Update the device state with the new parameter value
                self.device_states[device_id] = resp_json.get("data", {})
                _LOGGER.debug(
                    "Device %s state: %s", device_id, self.device_states[device_id]
                )
                return True

        except (TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error("Error setting parameter: %s", err)
            return False

    @callback
    def _handle_state_update(self, device_id: str, state_data: dict[str, Any]) -> None:
        """Handle state updates from MQTT."""
        if device_id not in self.device_states:
            self.device_states[device_id] = {}

        _LOGGER.debug("MQTT state update for device %s", device_id)

        self.device_states[device_id].update(state_data)

    async def _setup_mqtt_for_device(self, device_id: str) -> None:
        """Set up MQTT subscriptions for a device."""
        if not self._mqtt_client.connected:
            if not await self._mqtt_client.async_connect():
                _LOGGER.warning(
                    "MQTT not connected, skipping MQTT setup for device %s", device_id
                )
                return

        # Get device MAC address
        device_mac = self.devices.get(device_id, {}).get("mac")
        if not device_mac:
            _LOGGER.warning(
                "No MAC address for device %s, skipping MQTT setup", device_id
            )
            return

        # Set up topics
        topics = {
            "inf": f"rinnai/SR/01/SR/{device_mac}/inf/",
            "stg": f"rinnai/SR/01/SR/{device_mac}/stg/",
            "set": f"rinnai/SR/01/SR/{device_mac}/set/",
        }

        # Subscribe to information topics
        for topic_type, topic in topics.items():
            if topic_type in ["inf", "stg"]:
                # Don't subscribe to the set topic, as we only publish to it
                @callback
                def message_received(msg, topic_type=topic_type, device_id=device_id):
                    """Handle received MQTT message."""
                    try:
                        payload = json.loads(msg.payload)
                        _LOGGER.debug("Received MQTT message: %s", payload)

                        # Process device info message
                        if (
                            topic_type == "inf"
                            and payload.get("enl")
                            and payload.get("code") == "FFFF"
                        ):
                            state_data = self._process_device_info(payload)
                            if state_data:
                                self._handle_state_update(device_id, state_data)

                        # Process energy data message
                        elif (
                            topic_type == "stg"
                            and payload.get("egy")
                            and payload.get("ptn") == "J05"
                        ):
                            state_data = self._process_energy_data(payload)
                            if state_data:
                                self._handle_state_update(device_id, state_data)
                    except json.JSONDecodeError:
                        _LOGGER.error("Invalid JSON in MQTT message: %s", msg.payload)
                    except (ValueError, TypeError, KeyError) as err:
                        _LOGGER.error("Error processing MQTT message: %s", err)

                # Use our custom MQTT client for subscription
                subscription = await self._mqtt_client.async_subscribe(
                    topic, message_received
                )
                self._mqtt_subscriptions[f"{device_id}_{topic_type}"] = subscription

    def _process_device_info(self, parsed_data: dict[str, Any]) -> dict[str, Any]:
        """Extract device information from MQTT message without formatting."""
        state_data = {}
        for param in parsed_data.get("enl", []):
            try:
                param_id = param.get("id")
                param_data = param.get("data")

                if not param_id or not param_data:
                    continue
                state_data[param_id] = param_data

            except (ValueError, TypeError, KeyError) as err:
                _LOGGER.error("Error extracting parameter %s: %s", param_id, err)

        return state_data

    def _process_energy_data(self, parsed_data: dict[str, Any]) -> dict[str, Any]:
        """Extract energy data from MQTT message without formatting."""
        updates = {}

        for param in parsed_data.get("egy", []):
            if not isinstance(param, dict):
                _LOGGER.warning("Skipping invalid parameter: %s", param)
                continue

            if gas_value := param.get("gasConsumption"):
                updates["gasConsumption"] = gas_value

            for key in [
                "totalPowerSupplyTime",
                "actualUseTime",
                "totalHeatingBurningTime",
                "totalHotWaterBurningTime",
                "heatingBurningTimes",
                "hotWaterBurningTimes",
            ]:
                if key in param:
                    updates[key] = param[key]

        return updates

    async def send_command(self, device_id: str, command: dict[str, Any]) -> bool:
        """Send command to a device via MQTT."""
        if not self._mqtt_client.connected:
            if not await self._mqtt_client.async_connect():
                _LOGGER.error("MQTT is not connected, cannot send command")
                return False

        # Make sure the device exists
        if device_id not in self.devices:
            _LOGGER.error("Unknown device ID: %s", device_id)
            return False

        device_data = self.devices[device_id]
        auth_code = device_data.get("authCode", "03F1")
        device_mac = device_data.get("mac")
        if not device_mac:
            _LOGGER.error("No MAC address for device %s", device_id)
            return False

        device_classid = device_data.get("classID")
        # Build Rinnai format message
        set_topic = f"rinnai/SR/01/SR/{device_mac}/set/"
        rinnai_message = {
            "code": auth_code,
            "enl": [{"data": str(value), "id": key} for key, value in command.items()],
            "id": device_classid,
            "ptn": "J00",
            "sum": "1",
        }

        # Use our custom MQTT client for publishing
        try:
            # Use quality of service level 1 (at least once delivery)
            return await self._mqtt_client.async_publish(
                set_topic, json.dumps(rinnai_message), qos=1
            )
        except (ValueError, TypeError, KeyError) as err:
            _LOGGER.error("Error sending MQTT command: %s", err)
            return False

    async def async_close(self) -> None:
        """Close the client connections."""
        # Unsubscribe from all MQTT topics
        for unsub in self._mqtt_subscriptions.values():
            if callable(unsub):
                unsub()
        self._mqtt_subscriptions.clear()

        # Disconnect from MQTT broker
        await self._mqtt_client.async_disconnect()
