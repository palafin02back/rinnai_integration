"""Support for Rinnai sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.helpers import entity_registry as er

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_EXPERIMENTAL_SENSORS, DOMAIN
from .coordinator import RinnaiCoordinator
from .entity import RinnaiEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Rinnai sensors based on a config entry."""
    coordinator: RinnaiCoordinator = hass.data[DOMAIN][entry.entry_id]

    experimental_enabled = entry.options.get(CONF_EXPERIMENTAL_SENSORS, False)

    entities = []
    for device_id in coordinator.data["devices"]:
        device = coordinator.get_device(device_id)
        if not device or not device.config:
            continue

        if sensor_configs := device.config.entities.get("sensor"):
            for config in sensor_configs:
                sensor_type = config.get("type", "generic")
                if sensor_type == "reservation_sensor":
                    entities.append(RinnaiHeatingReservationSensor(coordinator, device_id, config))
                elif sensor_type == "circulation_sensor":
                    entities.append(RinnaiCirculationSensor(coordinator, device_id, config))
                else:
                    entities.append(RinnaiGenericSensor(coordinator, device_id, config, experimental_enabled))

    _LOGGER.debug("Setting up %d sensor entities", len(entities))
    async_add_entities(entities)

    # Sync experimental sensor visibility with the option.
    # entity_registry_enabled_default only applies to first-time registration;
    # we must explicitly update already-registered entries.
    ent_reg = er.async_get(hass)
    for entity in entities:
        if not isinstance(entity, RinnaiGenericSensor) or not entity.experimental:
            continue
        entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, entity.unique_id)
        if not entity_id:
            continue
        reg_entry = ent_reg.async_get(entity_id)
        if not reg_entry:
            continue
        if not experimental_enabled and reg_entry.disabled_by is None:
            ent_reg.async_update_entity(
                entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
            )
        elif experimental_enabled and reg_entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION:
            ent_reg.async_update_entity(entity_id, disabled_by=None)


class RinnaiGenericSensor(RinnaiEntity, SensorEntity, RestoreEntity):
    """Representation of a generic Rinnai sensor defined in config."""

    def __init__(
        self,
        coordinator: RinnaiCoordinator,
        device_id: str,
        config: dict[str, Any],
        experimental_enabled: bool = False,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_id, config)

        self.experimental: bool = config.get("experimental", False)
        if self.experimental and not experimental_enabled:
            self._attr_entity_registry_enabled_default = False

        description = SensorEntityDescription(
            key=config["key"],
            name=config["name"],
            device_class=config.get("device_class"),
            state_class=config.get("state_class"),
            native_unit_of_measurement=config.get("unit_of_measurement"),
            entity_category=EntityCategory(config["entity_category"]) if config.get("entity_category") else None,
        )
        self.entity_description = description
        self._attr_translation_key = config["key"]
        self._value_map = config.get("value_map")
        self._state_attribute = config.get("state_attribute")
        self._fallback_state_attribute = config.get("fallback_state_attribute")
        self._fallback_when = {
            str(value)
            for value in config.get("fallback_when", ["", "0", "00", "Error", "error"])
        }
        self._restored_native_value = None

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        if (last_state := await self.async_get_last_state()) is not None:
            try:
                if last_state.state not in (None, "unknown", "unavailable"):
                    if self.device_class in (SensorDeviceClass.DURATION, SensorDeviceClass.GAS, SensorDeviceClass.TEMPERATURE):
                        self._restored_native_value = float(last_state.state)
                    else:
                        self._restored_native_value = last_state.state
            except (ValueError, TypeError):
                pass
        
        self._update_attributes()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle device updates."""
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        """Update sensor attributes based on device state."""
        if not self._state_attribute:
            return

        raw_value = self._state_value_with_fallback()
        
        if self._value_map and str(raw_value) in self._value_map:
            current_value = self._value_map[str(raw_value)]
        else:
            current_value = raw_value
            
        is_cumulative = self.entity_description.state_class == SensorStateClass.TOTAL_INCREASING
        if (current_value is None or (is_cumulative and current_value == 0)) and self._restored_native_value is not None:
             self._attr_native_value = self._restored_native_value
        else:
             self._attr_native_value = current_value

    def _state_value_with_fallback(self) -> Any:
        """Return the configured state value, applying fallback when needed."""
        raw_value = self.get_state_value(self._state_attribute)
        if (
            not self._fallback_state_attribute
            or str(raw_value) not in self._fallback_when
        ):
            return raw_value

        fallback_value = self.get_state_value(self._fallback_state_attribute)
        if (
            fallback_value is not None
            and str(fallback_value) not in self._fallback_when
        ):
            return fallback_value

        return raw_value


class RinnaiHeatingReservationSensor(RinnaiEntity, SensorEntity):
    """Representation of Rinnai heating reservation status."""

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str, config: dict[str, Any]) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_id, config)
        self._attr_translation_key = "heating_reservation"
        self._state_attribute = config["state_attribute"]
        self._on_label = config.get("on_label", "On")
        self._off_label = config.get("off_label", "Off")
        self._extra_state_attributes = config.get("extra_state_attributes", {})
        self._update_attributes()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        if not self.schedule_manager:
            return

        raw_hex = self.get_state_value(self._state_attribute)
        
        if not self.schedule_manager.validate_hex(raw_hex):
            self._attr_native_value = "Unknown"
            self._attr_extra_state_attributes = dict(self._extra_state_attributes)
            return

        is_on = self.schedule_manager.parse_status(raw_hex)
        mode_index = self.schedule_manager.parse_mode_index(raw_hex)
        
        self._attr_native_value = self._on_label if is_on else self._off_label
        
        attrs = dict(self._extra_state_attributes)
        attrs.update({
            "current_mode_index": mode_index,
            "raw_hex": raw_hex
        })
        
        # Parse modes using manager
        for i in range(self.schedule_manager.mode_count):
            idx = i + 1
            schedule_str = self.schedule_manager.parse_schedule(raw_hex, idx)
            if schedule_str:
                attrs[f"mode_{idx}_schedule"] = schedule_str
                if idx == mode_index:
                    attrs["current_schedule"] = schedule_str
        
        self._attr_extra_state_attributes = attrs


class RinnaiCirculationSensor(RinnaiEntity, SensorEntity):
    """Sensor for Q85 one-key circulation status (derived from operationMode Byte3)."""

    def __init__(self, coordinator: RinnaiCoordinator, device_id: str, config: dict[str, Any]) -> None:
        super().__init__(coordinator, device_id, config)
        self._state_attribute = config["state_attribute"]
        self._update_attributes()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attributes()
        self.async_write_ha_state()

    def _update_attributes(self) -> None:
        raw_value = self.get_state_value(self._state_attribute)
        if raw_value is None:
            self._attr_native_value = "Unknown"
            return

        raw_str = str(raw_value)
        # operationMode is 6 hex chars (3 bytes), Byte3 = last 2 chars
        if len(raw_str) >= 6:
            byte3 = raw_str[4:6].upper()
            if byte3 == "0C":
                self._attr_native_value = "Active"
            else:
                self._attr_native_value = "Inactive"
        else:
            self._attr_native_value = "Unknown"

        self._attr_extra_state_attributes = {
            "raw_operation_mode": raw_str,
        }
