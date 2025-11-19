"""Device configuration models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass
class TemperatureConfig:
    """Temperature configuration."""
    min: int
    max: int
    step: int

@dataclass
class HeatingModeConfig:
    """Heating mode configuration."""
    display: str
    codes: list[str]
    command: str
    value: str
    requires_normal: bool
    temperature_attribute: str | None = None
    temp_set_command: str | None = None

@dataclass
class RinnaiDeviceConfig:
    """Rinnai device configuration."""
    name: str
    supported_models: list[str]
    temperature: TemperatureConfig | None
    heating_modes: dict[str, HeatingModeConfig] | None
    burning_states: dict[str, str]
    features: dict[str, Any] = field(default_factory=dict)
    field_mapping: dict[str, str] = field(default_factory=dict)
    defaults: dict[str, str] = field(default_factory=dict)
    state_parameters: list[str] = field(default_factory=list)

    @property
    def code_to_mode(self) -> dict[str, str]:
        """Get mapping from mode code to mode key."""
        if not self.heating_modes:
            return {}
        return {
            code: mode 
            for mode, config in self.heating_modes.items() 
            for code in config.codes
        }
    
    @property
    def off_mode_key(self) -> str:
        """Get the key for off mode."""
        return self.defaults.get("off_mode", "standby")

    @property
    def normal_mode_key(self) -> str:
        """Get the key for normal mode."""
        return self.defaults.get("normal_mode", "normal")

    @property
    def energy_saving_codes(self) -> list[str]:
        """Get energy saving mode codes."""
        if not self.heating_modes:
            return []
        return self.heating_modes.get("energy_saving", HeatingModeConfig("", [], "", "", False)).codes

    @property
    def outdoor_codes(self) -> list[str]:
        """Get outdoor mode codes."""
        if not self.heating_modes:
            return []
        return self.heating_modes.get("outdoor", HeatingModeConfig("", [], "", "", False)).codes

    @property
    def rapid_heating_codes(self) -> list[str]:
        """Get rapid heating mode codes."""
        if not self.heating_modes:
            return []
        return self.heating_modes.get("rapid", HeatingModeConfig("", [], "", "", False)).codes

    @property
    def heating_off_codes(self) -> list[str]:
        """Get heating off mode codes."""
        if not self.heating_modes:
            return []
        return self.heating_modes.get("standby", HeatingModeConfig("", [], "", "", False)).codes

    @property
    def active_heating_states(self) -> list[str]:
        """Get active heating state codes."""
        return self.features.get("active_heating_states", ["31", "32"])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RinnaiDeviceConfig:
        """Create config from dictionary."""
        temp_data = data.get("temperature")
        temperature = None
        if temp_data:
            temperature = TemperatureConfig(
                min=temp_data.get("min", 35),
                max=temp_data.get("max", 65),
                step=temp_data.get("step", 1)
            )

        heating_modes = None
        heating_modes_data = data.get("heating_modes")
        if heating_modes_data:
            heating_modes = {}
            for mode, mode_data in heating_modes_data.items():
                heating_modes[mode] = HeatingModeConfig(
                    display=mode_data.get("display", ""),
                    codes=mode_data.get("codes", []),
                    command=mode_data.get("command", ""),
                    value=mode_data.get("value", ""),
                    requires_normal=mode_data.get("requires_normal", False),
                    temperature_attribute=mode_data.get("temperature_attribute"),
                    temp_set_command=mode_data.get("temp_set_command")
                )

        return cls(
            name=data.get("name", "Unknown"),
            supported_models=data.get("supported_models", []),
            temperature=temperature,
            heating_modes=heating_modes,
            burning_states=data.get("burning_states", {}),
            features=data.get("features", {}),
            field_mapping=data.get("field_mapping", {}),
            defaults=data.get("defaults", {}),
            state_parameters=data.get("state_parameters", [])
        )
