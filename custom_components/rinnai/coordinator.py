"""Data update coordinator for Rinnai integration."""
from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .core.client import RinnaiClient
from .const import DOMAIN
from .models.device import RinnaiDevice, RinnaiDeviceState
from .core.entity_utils import get_state_value

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.energy_data"


class RinnaiCoordinator(DataUpdateCoordinator):
    """Data update coordinator for Rinnai devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: RinnaiClient,
        update_interval: int = 300,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.client = client
        self._first_update = True
        self._devices: dict[str, RinnaiDevice] = {}
        self._last_http_update: dict[str, float] = {}
        self.data = {"devices": {}, "device_states": {}}

        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

        hass.create_task(self._load_energy_data())

    async def _load_energy_data(self) -> None:
        """Load saved energy data from storage."""
        try:
            if saved_data := await self._store.async_load():
                for device_id, energy_data in saved_data.items():
                    if device := self._devices.get(device_id):
                        device.state.raw_data.update(energy_data)
                        _LOGGER.debug("Loaded saved energy data for device %s", device_id)
        except (ValueError, TypeError, KeyError) as err:
            _LOGGER.error("Error loading energy data: %s", err)

    async def _save_energy_data(self) -> None:
        """Save energy data to storage."""
        try:
            energy_data = {}
            for device_id, device in self._devices.items():
                if not device.config:
                    continue
                    
                # Get energy keys from config features
                energy_keys = device.config.features.get("energy_data_keys", [])
                device_energy = {}
                
                for key in energy_keys:
                    if key in device.state.raw_data:
                        device_energy[key] = device.state.raw_data[key]
                
                # Legacy support: save gasConsumption if present
                if "gasConsumption" in device.state.raw_data:
                    device_energy["gasConsumption"] = device.state.raw_data["gasConsumption"]

                energy_data[device_id] = device_energy

            await self._store.async_save(energy_data)
            _LOGGER.debug("Saved energy data for all devices")
        except (ValueError, TypeError, KeyError) as err:
            _LOGGER.error("Error saving energy data: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via API."""

        def handle_error(msg: str) -> None:
            """Handle error in data update."""
            _LOGGER.error(msg)
            raise HomeAssistantError(msg)

        try:
            if not await self.client.login():
                handle_error("Failed to login to Rinnai API")

            if self._first_update or not self.client.devices:
                _LOGGER.debug("Performing initial/full HTTP update for devices")
                if not await self.client.fetch_devices():
                    _LOGGER.warning("Failed to fetch devices from HTTP API")

                for device_id in self.client.devices:
                    _LOGGER.debug("Fetching initial state for device: %s", device_id)
                    if not await self.client.fetch_device_state(device_id):
                        _LOGGER.warning("Failed to fetch state for device: %s", device_id)

                self._first_update = False
                self._process_devices_data()
                
                for device_id in self.client.devices:
                    await self.async_refresh_schedule(device_id)
            else:
                _LOGGER.debug("Skipping HTTP device fetch, using MQTT data only")
                current_time = time.time()
                for device_id in self.client.devices:
                    device_state = self.client.device_states.get(device_id, {})
                    if (not device_state or 
                        getattr(self, "_last_http_update", {}).get(device_id, 0) < current_time - 3600):
                        _LOGGER.debug("Fetching HTTP state update for device: %s", device_id)
                        if await self.client.fetch_device_state(device_id):
                            self._last_http_update[device_id] = current_time

                self._process_device_states()

            self._log_device_states()

        except (ValueError, TypeError, KeyError) as err:
            handle_error(f"Error updating Rinnai data: {err}")

        return {
            "devices": self._devices,
            "device_states": {
                device_id: device.state for device_id, device in self._devices.items()
            },
            "raw_devices": self.client.devices,
            "raw_device_states": self.client.device_states,
        }

    def _process_devices_data(self) -> None:
        """Process devices data from client into structured format."""
        for device_id, device_data in self.client.devices.items():
            if device_id not in self._devices:
                self._devices[device_id] = RinnaiDevice(device_id=device_id)
                self.client.register_callback(
                    device_id, 
                    lambda data, did=device_id: self._handle_device_update(did, data)
                )

            self._devices[device_id].update_from_api_data(device_data)

            if device_id in self.client.device_states:
                self._devices[device_id].update_state(
                    self.client.device_states[device_id], is_command=False
                )

    def _process_device_states(self) -> None:
        """Process device states from client into structured format."""
        for device_id, state_data in self.client.device_states.items():
            if device_id in self._devices:
                _LOGGER.debug("Received state data from client: %s: %s", device_id, state_data)
                self._devices[device_id].update_state(state_data, is_command=False)
                self.hass.create_task(self._save_energy_data())
            else:
                _LOGGER.warning("Received state for unknown device %s, fetching device info", device_id)
                self._process_devices_data()

    def process_device_states(self) -> None:
        """Process device states from client (public method)."""
        self._process_device_states()
        self.async_set_updated_data(self.data)

    def _handle_device_update(self, device_id: str, data: dict[str, Any]) -> None:
        """Handle real-time update from client."""
        if device_id in self._devices:
            _LOGGER.debug("Received real-time update for device %s", device_id)
            if not self._devices[device_id].online:
                _LOGGER.info("Device %s is sending updates, marking as online", device_id)
                self._devices[device_id].online = True
                
            self._devices[device_id].update_state(data, is_command=False)
            self.async_set_updated_data(self.data)

    async def async_send_command(self, device_id: str, command: dict[str, Any]) -> bool:
        """Send command to a device."""
        result = await self.client.send_command(device_id, command)

        if result and device_id in self._devices:
            self._devices[device_id].update_state(command, is_command=True)
            self.async_set_updated_data(self.data)
            self.data["device_states"][device_id] = self._devices[device_id].state

            _LOGGER.debug("Command sent successfully to %s: %s", device_id, command)
        else:
            _LOGGER.warning("Command Send Failed: %s", command)

        return result

    async def async_refresh_schedule(self, device_id: str) -> None:
        """Refresh schedule info for a device."""
        _LOGGER.debug("Refreshing schedule info for device: %s", device_id)
        schedule_data = await self.client.get_schedule_info(device_id)
        if schedule_data:
            if device_id in self._devices:
                self._devices[device_id].update_from_api_data(schedule_data)
                self.async_set_updated_data(self.data)

    def get_device(self, device_id: str) -> RinnaiDevice | None:
        """Get device by ID."""
        return self._devices.get(device_id)

    def get_device_state(self, device_id: str) -> RinnaiDeviceState | None:
        """Get device state by ID."""
        device = self.get_device(device_id)
        return device.state if device else None

    def _log_device_states(self) -> None:
        """Log detailed state information for all devices."""
        for device_id, device in self._devices.items():
            _LOGGER.debug("Device %s (%s) - Online: %s", device.device_name, device_id, device.online)
