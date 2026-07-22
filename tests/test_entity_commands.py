"""Tests for config-driven entity command behavior."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
RINNAI_ROOT = ROOT / "custom_components" / "rinnai"


def _install_homeassistant_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install enough Home Assistant modules to import entity classes."""
    modules: dict[str, ModuleType] = {}
    for name in (
        "homeassistant",
        "homeassistant.components",
        "homeassistant.components.water_heater",
        "homeassistant.components.number",
        "homeassistant.components.select",
        "homeassistant.components.switch",
        "homeassistant.components.text",
        "homeassistant.components.sensor",
        "homeassistant.config_entries",
        "homeassistant.const",
        "homeassistant.core",
        "homeassistant.helpers",
        "homeassistant.helpers.entity",
        "homeassistant.helpers.entity_platform",
        "homeassistant.helpers.entity_registry",
        "homeassistant.helpers.restore_state",
        "homeassistant.helpers.update_coordinator",
    ):
        modules[name] = ModuleType(name)
        monkeypatch.setitem(sys.modules, name, modules[name])

    class CoordinatorEntity:
        def __init__(self, coordinator: Any) -> None:
            self.coordinator = coordinator

        @property
        def available(self) -> bool:
            return True

        def async_write_ha_state(self) -> None:
            self._write_count = getattr(self, "_write_count", 0) + 1
            self._written_operations = getattr(self, "_written_operations", [])
            self._written_operations.append(
                getattr(self, "_attr_current_operation", None)
            )

    class Entity:
        pass

    class WaterHeaterEntity:
        @property
        def min_temp(self) -> int:
            return self._attr_min_temp

        @property
        def max_temp(self) -> int:
            return self._attr_max_temp

        def async_write_ha_state(self) -> None:
            self._write_count = getattr(self, "_write_count", 0) + 1
            self._written_operations = getattr(self, "_written_operations", [])
            self._written_operations.append(
                getattr(self, "_attr_current_operation", None)
            )

    class SelectEntity:
        @property
        def options(self) -> list[str]:
            return self._attr_options

        def async_write_ha_state(self) -> None:
            self._write_count = getattr(self, "_write_count", 0) + 1

    class NumberEntity:
        def async_write_ha_state(self) -> None:
            self._write_count = getattr(self, "_write_count", 0) + 1

    class NumberDeviceClass:
        TEMPERATURE = "temperature"

    class NumberMode:
        BOX = "box"

    class SensorEntity:
        def async_write_ha_state(self) -> None:
            self._write_count = getattr(self, "_write_count", 0) + 1

    class SwitchEntity:
        def async_write_ha_state(self) -> None:
            self._write_count = getattr(self, "_write_count", 0) + 1

    class TextEntity:
        def async_write_ha_state(self) -> None:
            self._write_count = getattr(self, "_write_count", 0) + 1

    class SensorEntityDescription:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    class SensorDeviceClass:
        DURATION = "duration"
        GAS = "gas"
        TEMPERATURE = "temperature"

    class SensorStateClass:
        TOTAL_INCREASING = "total_increasing"

    class RestoreEntity:
        async def async_added_to_hass(self) -> None:
            return None

    class WaterHeaterEntityFeature:
        TARGET_TEMPERATURE = 1

    modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = CoordinatorEntity
    modules["homeassistant.helpers.entity"].Entity = Entity
    modules["homeassistant.components.water_heater"].WaterHeaterEntity = WaterHeaterEntity
    modules["homeassistant.components.water_heater"].WaterHeaterEntityFeature = WaterHeaterEntityFeature
    modules["homeassistant.components.number"].NumberEntity = NumberEntity
    modules["homeassistant.components.number"].NumberDeviceClass = NumberDeviceClass
    modules["homeassistant.components.number"].NumberMode = NumberMode
    modules["homeassistant.components.select"].SelectEntity = SelectEntity
    modules["homeassistant.components.switch"].SwitchEntity = SwitchEntity
    modules["homeassistant.components.text"].TextEntity = TextEntity
    modules["homeassistant.components.sensor"].SensorEntity = SensorEntity
    modules["homeassistant.components.sensor"].SensorEntityDescription = SensorEntityDescription
    modules["homeassistant.components.sensor"].SensorDeviceClass = SensorDeviceClass
    modules["homeassistant.components.sensor"].SensorStateClass = SensorStateClass
    modules["homeassistant.config_entries"].ConfigEntry = object
    modules["homeassistant.const"].ATTR_TEMPERATURE = "temperature"
    modules["homeassistant.const"].EntityCategory = str
    modules["homeassistant.const"].UnitOfTemperature = SimpleNamespace(CELSIUS="C")
    modules["homeassistant.const"].UnitOfTime = SimpleNamespace(HOURS="h")
    modules["homeassistant.core"].HomeAssistant = object
    modules["homeassistant.core"].callback = lambda func: func
    modules["homeassistant.helpers.entity_platform"].AddEntitiesCallback = object
    modules["homeassistant.helpers.restore_state"].RestoreEntity = RestoreEntity
    modules["homeassistant.helpers.entity_registry"].async_get = lambda hass: None
    modules["homeassistant.helpers"].entity_registry = modules[
        "homeassistant.helpers.entity_registry"
    ]


def _load_module(name: str, path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def entity_modules(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    _install_homeassistant_stubs(monkeypatch)

    for name in list(sys.modules):
        if name == "custom_components" or name.startswith("custom_components.rinnai"):
            monkeypatch.delitem(sys.modules, name, raising=False)

    custom_components = ModuleType("custom_components")
    custom_components.__path__ = [str(ROOT / "custom_components")]
    rinnai_pkg = ModuleType("custom_components.rinnai")
    rinnai_pkg.__path__ = [str(RINNAI_ROOT)]
    core_pkg = ModuleType("custom_components.rinnai.core")
    core_pkg.__path__ = [str(RINNAI_ROOT / "core")]

    monkeypatch.setitem(sys.modules, "custom_components", custom_components)
    monkeypatch.setitem(sys.modules, "custom_components.rinnai", rinnai_pkg)
    monkeypatch.setitem(sys.modules, "custom_components.rinnai.core", core_pkg)

    coordinator_mod = ModuleType("custom_components.rinnai.coordinator")
    coordinator_mod.RinnaiCoordinator = object
    monkeypatch.setitem(sys.modules, "custom_components.rinnai.coordinator", coordinator_mod)

    _load_module("custom_components.rinnai.const", RINNAI_ROOT / "const.py", monkeypatch)
    _load_module(
        "custom_components.rinnai.core.entity_utils",
        RINNAI_ROOT / "core" / "entity_utils.py",
        monkeypatch,
    )
    _load_module("custom_components.rinnai.core.util", RINNAI_ROOT / "core" / "util.py", monkeypatch)
    _load_module(
        "custom_components.rinnai.core.schedule_manager",
        RINNAI_ROOT / "core" / "schedule_manager.py",
        monkeypatch,
    )
    _load_module("custom_components.rinnai.entity", RINNAI_ROOT / "entity.py", monkeypatch)
    water_heater = _load_module(
        "custom_components.rinnai.water_heater",
        RINNAI_ROOT / "water_heater.py",
        monkeypatch,
    )
    number = _load_module(
        "custom_components.rinnai.number",
        RINNAI_ROOT / "number.py",
        monkeypatch,
    )
    select = _load_module(
        "custom_components.rinnai.select",
        RINNAI_ROOT / "select.py",
        monkeypatch,
    )
    switch = _load_module(
        "custom_components.rinnai.switch",
        RINNAI_ROOT / "switch.py",
        monkeypatch,
    )
    text = _load_module(
        "custom_components.rinnai.text",
        RINNAI_ROOT / "text.py",
        monkeypatch,
    )
    sensor = _load_module(
        "custom_components.rinnai.sensor",
        RINNAI_ROOT / "sensor.py",
        monkeypatch,
    )

    return SimpleNamespace(
        water_heater=water_heater,
        number=number,
        select=select,
        switch=switch,
        text=text,
        sensor=sensor,
    )


class StubCoordinator:
    def __init__(
        self,
        raw_data: dict[str, Any],
        state_mapping: dict[str, str],
        temperature_steps: list[int] | None = None,
        stale_refreshes: int = 0,
        schedule_config: dict[str, Any] | None = None,
        schedule_channels: dict[str, Any] | None = None,
    ) -> None:
        self.commands: list[dict[str, Any]] = []
        self.optimistic_states: list[dict[str, Any] | None] = []
        self.refresh_count = 0
        self.temperature_steps = temperature_steps
        self.stale_refreshes = stale_refreshes
        self.client = SimpleNamespace(save_schedule_hour=AsyncMock(return_value=True))
        self.async_refresh_schedule = AsyncMock()
        self.state = SimpleNamespace(raw_data=raw_data)
        self.device = SimpleNamespace(
            online=True,
            device_name="Test Device",
            device_type="02720E32",
            config=SimpleNamespace(
                state_mapping=state_mapping,
                schedule_config=schedule_config or {},
                schedule_channels=schedule_channels or {},
                features={},
                entities={},
            ),
        )

    def get_device(self, device_id: str) -> Any:
        return self.device

    def get_device_state(self, device_id: str) -> Any:
        return self.state

    async def async_send_command(self, device_id: str, command: Any) -> bool:
        self.commands.append(getattr(command, "payload", command))
        self.optimistic_states.append(getattr(command, "optimistic_state", None))
        return True

    async def async_request_refresh(self) -> None:
        self.refresh_count += 1
        if self.stale_refreshes > 0:
            self.stale_refreshes -= 1
            return
        command = self.commands[-1] if self.commands else {}
        if command.get("hotWaterTempOperate") == "01":
            self._step_temperature(1)
        elif command.get("hotWaterTempOperate") == "00":
            self._step_temperature(-1)

    async def async_refresh_device_state(self, device_id: str) -> bool:
        await self.async_request_refresh()
        return True

    def _step_temperature(self, direction: int) -> None:
        current = self.state.raw_data["hotWaterTempSetting"]
        if self.temperature_steps and current in self.temperature_steps:
            idx = self.temperature_steps.index(current) + direction
            if 0 <= idx < len(self.temperature_steps):
                self.state.raw_data["hotWaterTempSetting"] = self.temperature_steps[idx]
                return
        self.state.raw_data["hotWaterTempSetting"] += direction


def _e32_config() -> dict[str, Any]:
    with open(RINNAI_ROOT / "devices" / "02720E32.json", encoding="utf-8") as file:
        return json.load(file)


def _e51_config() -> dict[str, Any]:
    with open(RINNAI_ROOT / "devices" / "0272000D.json", encoding="utf-8") as file:
        return json.load(file)


def _e32_water_heater_config() -> dict[str, Any]:
    config = json.loads(json.dumps(_e32_config()["entities"]["water_heater"][0]))
    config["relative_temperature_control"]["step_delay_seconds"] = 0
    return config


def _e51_water_heater_config() -> dict[str, Any]:
    return json.loads(json.dumps(_e51_config()["entities"]["water_heater"][0]))


@pytest.mark.asyncio
async def test_relative_temperature_increases_one_step(entity_modules: SimpleNamespace) -> None:
    config = _e32_water_heater_config()
    coordinator = StubCoordinator(
        {"hotWaterTempSetting": 40, "operationMode": "E0"},
        {"hot_water_temp": "hotWaterTempSetting", "operation_mode": "operationMode"},
    )
    entity = entity_modules.water_heater.RinnaiWaterHeaterEntity(coordinator, "dev1", config)

    await entity.async_set_temperature(temperature=41)

    assert coordinator.commands == [{"hotWaterTempOperate": "01"}]
    assert coordinator.refresh_count == 1
    assert coordinator.state.raw_data["hotWaterTempSetting"] == 41


@pytest.mark.asyncio
async def test_relative_temperature_decreases_one_step(entity_modules: SimpleNamespace) -> None:
    config = _e32_water_heater_config()
    coordinator = StubCoordinator(
        {"hotWaterTempSetting": 41, "operationMode": "E0"},
        {"hot_water_temp": "hotWaterTempSetting", "operation_mode": "operationMode"},
    )
    entity = entity_modules.water_heater.RinnaiWaterHeaterEntity(coordinator, "dev1", config)

    await entity.async_set_temperature(temperature=40)

    assert coordinator.commands == [{"hotWaterTempOperate": "00"}]
    assert coordinator.refresh_count == 1
    assert coordinator.state.raw_data["hotWaterTempSetting"] == 40


@pytest.mark.asyncio
async def test_relative_temperature_reaches_requested_target(
    entity_modules: SimpleNamespace,
) -> None:
    config = _e32_water_heater_config()
    coordinator = StubCoordinator(
        {"hotWaterTempSetting": 40, "operationMode": "E0"},
        {"hot_water_temp": "hotWaterTempSetting", "operation_mode": "operationMode"},
    )
    entity = entity_modules.water_heater.RinnaiWaterHeaterEntity(coordinator, "dev1", config)

    await entity.async_set_temperature(temperature=43)

    assert coordinator.commands == [
        {"hotWaterTempOperate": "01"},
        {"hotWaterTempOperate": "01"},
        {"hotWaterTempOperate": "01"},
    ]
    assert coordinator.refresh_count == 3
    assert coordinator.state.raw_data["hotWaterTempSetting"] == 43


@pytest.mark.asyncio
async def test_relative_temperature_displays_changing_operation(
    entity_modules: SimpleNamespace,
) -> None:
    config = _e32_water_heater_config()
    coordinator = StubCoordinator(
        {"hotWaterTempSetting": 40, "operationMode": "E0"},
        {"hot_water_temp": "hotWaterTempSetting", "operation_mode": "operationMode"},
    )
    entity = entity_modules.water_heater.RinnaiWaterHeaterEntity(coordinator, "dev1", config)

    await entity.async_set_temperature(temperature=41)

    assert "正在更改至41℃" in entity._written_operations
    assert entity._attr_current_operation == "热水"
    assert entity._written_operations[-1] == "热水"


@pytest.mark.asyncio
async def test_relative_temperature_uses_allowed_temperature_steps(
    entity_modules: SimpleNamespace,
) -> None:
    config = _e32_water_heater_config()
    allowed = config["relative_temperature_control"]["allowed_temps_by_mode"]["E0"]
    coordinator = StubCoordinator(
        {"hotWaterTempSetting": 48, "operationMode": "E0"},
        {"hot_water_temp": "hotWaterTempSetting", "operation_mode": "operationMode"},
        temperature_steps=allowed,
    )
    entity = entity_modules.water_heater.RinnaiWaterHeaterEntity(coordinator, "dev1", config)

    await entity.async_set_temperature(temperature=55)

    assert coordinator.commands == [
        {"hotWaterTempOperate": "01"},
        {"hotWaterTempOperate": "01"},
    ]
    assert coordinator.refresh_count == 2
    assert coordinator.state.raw_data["hotWaterTempSetting"] == 55


@pytest.mark.asyncio
async def test_relative_temperature_retries_stale_refresh(
    entity_modules: SimpleNamespace,
) -> None:
    config = _e32_water_heater_config()
    config["relative_temperature_control"]["refresh_retries"] = 2
    coordinator = StubCoordinator(
        {"hotWaterTempSetting": 40, "operationMode": "E0"},
        {"hot_water_temp": "hotWaterTempSetting", "operation_mode": "operationMode"},
        stale_refreshes=1,
    )
    entity = entity_modules.water_heater.RinnaiWaterHeaterEntity(coordinator, "dev1", config)

    await entity.async_set_temperature(temperature=41)

    assert coordinator.commands == [{"hotWaterTempOperate": "01"}]
    assert coordinator.refresh_count == 2
    assert coordinator.state.raw_data["hotWaterTempSetting"] == 41


@pytest.mark.asyncio
async def test_relative_temperature_equal_sends_no_command(entity_modules: SimpleNamespace) -> None:
    config = _e32_water_heater_config()
    coordinator = StubCoordinator(
        {"hotWaterTempSetting": 40, "operationMode": "E0"},
        {"hot_water_temp": "hotWaterTempSetting", "operation_mode": "operationMode"},
    )
    entity = entity_modules.water_heater.RinnaiWaterHeaterEntity(coordinator, "dev1", config)

    await entity.async_set_temperature(temperature=40)

    assert coordinator.commands == []
    assert coordinator.refresh_count == 0


@pytest.mark.asyncio
async def test_relative_temperature_rejects_disallowed_mode_value(
    entity_modules: SimpleNamespace,
) -> None:
    config = _e32_water_heater_config()
    config["relative_temperature_control"]["adjust_unsupported_temperature"] = False
    coordinator = StubCoordinator(
        {"hotWaterTempSetting": 40, "operationMode": "C1"},
        {"hot_water_temp": "hotWaterTempSetting", "operation_mode": "operationMode"},
    )
    entity = entity_modules.water_heater.RinnaiWaterHeaterEntity(coordinator, "dev1", config)

    await entity.async_set_temperature(temperature=45)

    assert coordinator.commands == []
    assert coordinator.refresh_count == 0


@pytest.mark.asyncio
async def test_relative_temperature_adjusts_disallowed_value_to_nearest(
    entity_modules: SimpleNamespace,
) -> None:
    config = _e32_water_heater_config()
    coordinator = StubCoordinator(
        {"hotWaterTempSetting": 40, "operationMode": "C1"},
        {"hot_water_temp": "hotWaterTempSetting", "operation_mode": "operationMode"},
    )
    entity = entity_modules.water_heater.RinnaiWaterHeaterEntity(coordinator, "dev1", config)

    await entity.async_set_temperature(temperature=45)

    assert coordinator.commands == [
        {"hotWaterTempOperate": "01"},
        {"hotWaterTempOperate": "01"},
    ]
    assert coordinator.refresh_count == 2
    assert coordinator.state.raw_data["hotWaterTempSetting"] == 42
    assert entity._attr_extra_state_attributes == {
        "温度提示": "不支持45℃，已切换至最近支持的42℃",
    }
    assert "正在更改至42℃" in entity._written_operations
    assert entity._written_operations[-1] == "热水"


@pytest.mark.asyncio
async def test_direct_temperature_path_unchanged_for_hex4(
    entity_modules: SimpleNamespace,
) -> None:
    config = {
        "name": "Water Heater",
        "key": "main",
        "min_temp": 35,
        "max_temp": 65,
        "step": 1,
        "command_topic": "hotWaterTempSetting",
        "temp_format": "hex4",
        "state_attribute": "hot_water_temp",
        "operation_mode": "Hot Water",
    }
    coordinator = StubCoordinator(
        {"hotWaterTempSetting": 40},
        {"hot_water_temp": "hotWaterTempSetting"},
    )
    entity = entity_modules.water_heater.RinnaiWaterHeaterEntity(coordinator, "dev1", config)

    await entity.async_set_temperature(temperature=41)

    assert coordinator.commands == [{"hotWaterTempSetting": "2900"}]
    assert coordinator.refresh_count == 0


@pytest.mark.asyncio
async def test_e51_water_heater_uses_dynamic_temperature_bounds(
    entity_modules: SimpleNamespace,
) -> None:
    config = _e51_water_heater_config()
    coordinator = StubCoordinator(
        {
            "hotWaterTempSetting": 40,
            "tempSettinglower": 37,
            "tempSettingUpper": 55,
        },
        {
            "hot_water_temp": "hotWaterTempSetting",
            "temp_setting_lower": "tempSettinglower",
            "temp_setting_upper": "tempSettingUpper",
        },
    )
    entity = entity_modules.water_heater.RinnaiWaterHeaterEntity(
        coordinator,
        "dev1",
        config,
    )

    assert entity.min_temp == 37
    assert entity.max_temp == 55

    coordinator.state.raw_data["tempSettinglower"] = 38
    coordinator.state.raw_data["tempSettingUpper"] = 45
    entity._update_attributes()

    assert entity.min_temp == 38
    assert entity.max_temp == 45

    await entity.async_set_temperature(temperature=46)
    await entity.async_set_temperature(temperature=37)
    assert coordinator.commands == []

    await entity.async_set_temperature(temperature=45)
    assert coordinator.commands == [{"hotWaterTempSetting": "2D00"}]


@pytest.mark.asyncio
async def test_g58_water_heater_preserves_heating_temperature_in_combined_command(
    entity_modules: SimpleNamespace,
) -> None:
    config = {
        "name": "Hot Water",
        "key": "main",
        "min_temp": 35,
        "max_temp": 60,
        "step": 1,
        "command_topic": "tempSetting",
        "temp_format": "hex4",
        "combined_temperature_position": "hot_water",
        "companion_state_attribute": "heating_temp",
        "state_attribute": "hot_water_temp",
    }
    coordinator = StubCoordinator(
        {"hotWaterTempSetting": 42, "heatTempSetting": 55},
        {
            "hot_water_temp": "hotWaterTempSetting",
            "heating_temp": "heatTempSetting",
        },
    )
    entity = entity_modules.water_heater.RinnaiWaterHeaterEntity(
        coordinator, "dev1", config
    )

    await entity.async_set_temperature(temperature=45)

    assert coordinator.commands == [{"tempSetting": "2D003700"}]


@pytest.mark.asyncio
async def test_g58_heating_number_preserves_hot_water_temperature_in_combined_command(
    entity_modules: SimpleNamespace,
) -> None:
    config = {
        "name": "Heating Temperature",
        "key": "heating_temp_setpoint",
        "command_key": "tempSetting",
        "state_attribute": "heating_temp",
        "companion_state_attribute": "hot_water_temp",
        "combined_temperature_position": "heating",
        "min": 40,
        "max": 80,
        "step": 1,
        "temp_format": "hex4",
    }
    coordinator = StubCoordinator(
        {"hotWaterTempSetting": 42, "heatTempSetting": 55},
        {
            "hot_water_temp": "hotWaterTempSetting",
            "heating_temp": "heatTempSetting",
        },
    )
    entity = entity_modules.number.RinnaiNumberEntity(coordinator, "dev1", config)

    await entity.async_set_native_value(60)

    assert coordinator.commands == [{"tempSetting": "2A003C00"}]


@pytest.mark.asyncio
async def test_option_commands_can_send_different_command_keys(
    entity_modules: SimpleNamespace,
) -> None:
    config = {
        "name": "Operation Mode",
        "key": "operation_mode",
        "command_key": "operationMode",
        "options_map": {
            "Regular": "E0",
            "Kitchen": "C1",
            "Shower": "90",
        },
        "option_commands": {
            "Regular": {"regularMode": "01"},
            "Kitchen": {"kitchenMode": "01"},
            "Shower": {"showerMode": "01"},
        },
        "state_attribute": "operation_mode",
    }
    coordinator = StubCoordinator(
        {"operationMode": "E0"},
        {"operation_mode": "operationMode"},
    )
    entity = entity_modules.select.RinnaiCommandSelect(coordinator, "dev1", config)

    await entity.async_select_option("Kitchen")

    assert coordinator.commands == [{"kitchenMode": "01"}]


@pytest.mark.asyncio
async def test_options_map_default_behavior_unchanged(entity_modules: SimpleNamespace) -> None:
    config = {
        "name": "Operation Mode",
        "key": "operation_mode",
        "command_key": "operationMode",
        "options_map": {
            "Normal": "00",
            "Eco": "01",
        },
        "state_attribute": "operation_mode",
    }
    coordinator = StubCoordinator(
        {"operationMode": "01"},
        {"operation_mode": "operationMode"},
    )
    entity = entity_modules.select.RinnaiCommandSelect(coordinator, "dev1", config)

    assert entity._attr_current_option == "Eco"

    await entity.async_select_option("Normal")

    assert coordinator.commands == [{"operationMode": "00"}]


@pytest.mark.asyncio
async def test_e32_cycle_mode_uses_raw_string_values(
    entity_modules: SimpleNamespace,
) -> None:
    config = next(
        item
        for item in _e32_config()["entities"]["select"]
        if item["key"] == "cycle_mode"
    )
    coordinator = StubCoordinator(
        {"cycleModeSetting": "1"},
        {"cycle_mode": "cycleModeSetting"},
    )
    entity = entity_modules.select.RinnaiCommandSelect(coordinator, "dev1", config)

    assert entity._attr_current_option == "节能"

    await entity.async_select_option("舒适")

    assert coordinator.commands == [{"cycleModeSetting": "02"}]


@pytest.mark.parametrize(
    ("raw_value", "expected_option"),
    [
        ("0", "普通模式"),
        ("00", "普通模式"),
        ("1", "厨房模式"),
        ("01", "厨房模式"),
        ("2", "淋浴模式"),
        ("02", "淋浴模式"),
    ],
)
def test_e51_operation_mode_maps_observed_values(
    entity_modules: SimpleNamespace,
    raw_value: str,
    expected_option: str,
) -> None:
    config = next(
        item
        for item in _e51_config()["entities"]["select"]
        if item["key"] == "operation_mode"
    )
    coordinator = StubCoordinator(
        {"operationMode": raw_value},
        {"operation_mode": "operationMode"},
    )
    entity = entity_modules.select.RinnaiCommandSelect(coordinator, "dev1", config)

    assert entity._attr_current_option == expected_option


@pytest.mark.asyncio
async def test_e51_operation_mode_sends_mobile_app_wire_values(
    entity_modules: SimpleNamespace,
) -> None:
    config = next(
        item
        for item in _e51_config()["entities"]["select"]
        if item["key"] == "operation_mode"
    )
    coordinator = StubCoordinator(
        {"operationMode": "0"},
        {"operation_mode": "operationMode"},
    )
    entity = entity_modules.select.RinnaiCommandSelect(coordinator, "dev1", config)

    await entity.async_select_option("厨房模式")

    assert coordinator.commands == [{"operationMode": "01"}]


@pytest.mark.parametrize(
    ("raw_value", "expected_option"),
    [
        ("5a", "一般节能"),
        ("5A", "一般节能"),
        ("50", "标准节能"),
        ("46", "强力节能"),
    ],
)
def test_e51_eco_heat_load_maps_observed_values(
    entity_modules: SimpleNamespace,
    raw_value: str,
    expected_option: str,
) -> None:
    config = next(
        item
        for item in _e51_config()["entities"]["select"]
        if item["key"] == "eco_heat_load"
    )
    coordinator = StubCoordinator(
        {"ecoHeatLoad": raw_value},
        {"eco_heat_load": "ecoHeatLoad"},
    )
    entity = entity_modules.select.RinnaiCommandSelect(coordinator, "dev1", config)

    assert entity._attr_current_option == expected_option


@pytest.mark.asyncio
async def test_e51_eco_heat_load_sends_selected_value(
    entity_modules: SimpleNamespace,
) -> None:
    config = next(
        item
        for item in _e51_config()["entities"]["select"]
        if item["key"] == "eco_heat_load"
    )
    coordinator = StubCoordinator(
        {"ecoHeatLoad": "50"},
        {"eco_heat_load": "ecoHeatLoad"},
    )
    entity = entity_modules.select.RinnaiCommandSelect(coordinator, "dev1", config)

    await entity.async_select_option("强力节能")

    assert coordinator.commands == [{"ecoHeatLoad": "46"}]


@pytest.mark.parametrize(
    ("raw_value", "expected_option"),
    [
        ("E0", "普通"),
        ("A0", "普通"),
        ("80", "普通"),
        ("C1", "厨房"),
        ("81", "厨房"),
        ("C0", "厨房"),
        ("90", "淋浴"),
        ("D0", "淋浴"),
    ],
)
def test_e32_operation_mode_maps_observed_values(
    entity_modules: SimpleNamespace,
    raw_value: str,
    expected_option: str,
) -> None:
    config = next(
        item
        for item in _e32_config()["entities"]["select"]
        if item["key"] == "operation_mode"
    )
    coordinator = StubCoordinator(
        {"operationMode": raw_value},
        {"operation_mode": "operationMode"},
    )
    entity = entity_modules.select.RinnaiCommandSelect(coordinator, "dev1", config)

    assert entity._attr_current_option == expected_option


def test_e32_operation_mode_does_not_display_off_option(
    entity_modules: SimpleNamespace,
) -> None:
    config = next(
        item
        for item in _e32_config()["entities"]["select"]
        if item["key"] == "operation_mode"
    )
    coordinator = StubCoordinator(
        {"operationMode": "20"},
        {"operation_mode": "operationMode"},
    )
    entity = entity_modules.select.RinnaiCommandSelect(coordinator, "dev1", config)

    assert entity._attr_options == ["普通", "厨房", "淋浴"]
    assert entity._attr_current_option is None


def test_schedule_text_exposes_notes(entity_modules: SimpleNamespace) -> None:
    config = _e32_config()["entities"]["text"][0]
    coordinator = StubCoordinator(
        {"byteStr": "0100C0FF7F000000000000000000000000"},
        {"byte_str": "byteStr"},
    )
    entity = entity_modules.text.RinnaiGenericText(coordinator, "dev1", config)

    assert entity._attr_extra_state_attributes["说明"].startswith("按 24 小时位图")
    assert entity._attr_extra_state_attributes["格式"] == "HH:MM-HH:MM，例如 06:00-23:00。"


@pytest.mark.asyncio
async def test_softener_regeneration_time_text_encodes_command(
    entity_modules: SimpleNamespace,
) -> None:
    config = {
        "key": "regen_start_time",
        "name": "Regeneration Start Time",
        "command_type": "time_hex_pair",
        "command_key": "regenStartTime",
        "state_attribute": "regen_start_time",
    }
    coordinator = StubCoordinator(
        {"regenStartTime": "02,1E"},
        {"regen_start_time": "regenStartTime"},
    )
    entity = entity_modules.text.RinnaiGenericText(coordinator, "dev1", config)

    assert entity._attr_native_value == "02:30"

    await entity.async_set_value("23:59")

    assert coordinator.commands == [{"regenStartTime": "17,3B"}]
    assert entity._attr_native_value == "23:59"


@pytest.mark.asyncio
async def test_schedule_entity_uses_its_configured_channel(
    entity_modules: SimpleNamespace,
) -> None:
    config = {
        "key": "hot_water_schedule",
        "name": "热水预约",
        "command_type": "schedule_data",
        "schedule_channel": "hot_water",
        "state_attribute": "hot_water_schedule",
        "mode_index": 1,
    }
    schedule_config = {
        "total_length": 10,
        "status_byte_index": 0,
        "mode_byte_index": 1,
        "data_start_byte_index": 2,
        "bytes_per_mode": 3,
        "mode_count": 1,
    }
    coordinator = StubCoordinator(
        {"hotWaterReservationMode": "0101FFFFFF"},
        {"hot_water_schedule": "hotWaterReservationMode"},
        schedule_channels={
            "hot_water": {"schedule_config": schedule_config}
        },
    )
    entity = entity_modules.text.RinnaiGenericText(coordinator, "dev1", config)

    assert entity.schedule_manager is not None
    assert entity.schedule_manager.mode_count == 1
    await entity.async_set_value("00:00-01:00")

    coordinator.client.save_schedule_hour.assert_awaited_once()
    assert coordinator.client.save_schedule_hour.await_args.kwargs == {
        "schedule_channel": "hot_water"
    }
    coordinator.async_refresh_schedule.assert_awaited_once_with(
        "dev1", schedule_channel="hot_water"
    )


def test_reservation_sensor_uses_localized_labels_and_notes(
    entity_modules: SimpleNamespace,
) -> None:
    config = next(
        item for item in _e32_config()["entities"]["sensor"] if item["key"] == "hot_water_reservation"
    )
    coordinator = StubCoordinator(
        {"byteStr": "0100C0FF7F000000000000000000000000"},
        {"byte_str": "byteStr"},
    )
    entity = entity_modules.sensor.RinnaiHeatingReservationSensor(
        coordinator,
        "dev1",
        config,
    )

    assert entity._attr_native_value == "开启"
    assert entity._attr_extra_state_attributes["说明"].startswith("E32 循环预约")


@pytest.mark.parametrize(
    (
        "switch_key",
        "on_value",
        "off_value",
        "command_on",
        "command_off",
        "optimistic_on",
        "optimistic_off",
    ),
    [
        ("power", "31", "30", "01", "01", "31", "30"),
        ("eco_mode", "31", "30", "01", "01", "31", "30"),
        ("cycle_insulation", "31", "30", "31", "30", None, None),
        ("cycle_mode", "1", "0", "01", "00", None, None),
        ("pressurization_mode", "31", "30", "31", "30", None, None),
    ],
)
@pytest.mark.asyncio
async def test_e51_command_switches_match_observed_values(
    entity_modules: SimpleNamespace,
    switch_key: str,
    on_value: str,
    off_value: str,
    command_on: str,
    command_off: str,
    optimistic_on: str | None,
    optimistic_off: str | None,
) -> None:
    config = next(
        item for item in _e51_config()["entities"]["switch"] if item["key"] == switch_key
    )
    raw_key = config["command_key"]
    state_attribute = config["state_attribute"]
    coordinator = StubCoordinator(
        {raw_key: on_value},
        {state_attribute: raw_key},
    )
    entity = entity_modules.switch.RinnaiCommandSwitch(coordinator, "dev1", config)

    assert entity._attr_is_on is True

    coordinator.state.raw_data[raw_key] = off_value
    entity._update_attributes()
    assert entity._attr_is_on is False

    await entity.async_turn_on()
    await entity.async_turn_off()

    assert coordinator.commands == [
        {raw_key: command_on},
        {raw_key: command_off},
    ]
    assert coordinator.optimistic_states == [
        {raw_key: optimistic_on} if optimistic_on is not None else None,
        {raw_key: optimistic_off} if optimistic_off is not None else None,
    ]


@pytest.mark.asyncio
async def test_command_switch_supports_atomic_multi_field_payloads(
    entity_modules: SimpleNamespace,
) -> None:
    config = {
        "key": "heating_reservation",
        "name": "Heating Reservation",
        "command_key": "heatingReservationSetting",
        "command_on": "31",
        "command_off": "30",
        "command_on_rules": [
            {
                "state_attribute": "operation_mode",
                "not_in_values": ["0", "00", "2", "02"],
                "command": {"operationMode": "00"},
            },
            {
                "state_attribute": "rapid_heating",
                "in_values": ["1", "01"],
                "command": {"rapidHeatingSetting": "00"},
            },
        ],
        "state_attribute": "heating_reservation_setting",
        "on_value": "31",
    }
    coordinator = StubCoordinator(
        {
            "cycleReservationSetting": "30",
            "operationMode": "03",
            "rapidHeatingSetting": "01",
        },
        {
            "heating_reservation_setting": "cycleReservationSetting",
            "operation_mode": "operationMode",
            "rapid_heating": "rapidHeatingSetting",
        },
    )
    entity = entity_modules.switch.RinnaiCommandSwitch(coordinator, "dev1", config)

    assert entity._attr_is_on is False
    coordinator.state.raw_data["cycleReservationSetting"] = "31"
    entity._update_attributes()
    assert entity._attr_is_on is True

    await entity.async_turn_on()
    await entity.async_turn_off()

    assert coordinator.commands == [
        {
            "operationMode": "00",
            "rapidHeatingSetting": "00",
            "heatingReservationSetting": "31",
        },
        {"heatingReservationSetting": "30"},
    ]


@pytest.mark.asyncio
async def test_command_select_supports_conditional_option_payloads(
    entity_modules: SimpleNamespace,
) -> None:
    config = {
        "key": "rapid_heating",
        "name": "Rapid Heating",
        "command_key": "rapidHeatingSetting",
        "options_map": {"Off": "00", "Rapid": "01", "Eco rapid": "02"},
        "option_command_rules": {
            "Rapid": [
                {
                    "state_attribute": "operation_mode",
                    "not_in_values": ["0", "00", "2", "02"],
                    "command": {"operationMode": "00"},
                },
                {
                    "state_attribute": "heating_reservation",
                    "in_values": ["1", "01", "31"],
                    "command": {"heatingReservationSetting": "30"},
                },
            ]
        },
        "state_attribute": "rapid_heating",
    }
    coordinator = StubCoordinator(
        {
            "rapidHeatingSetting": "00",
            "operationMode": "03",
            "cycleReservationSetting": "31",
        },
        {
            "rapid_heating": "rapidHeatingSetting",
            "operation_mode": "operationMode",
            "heating_reservation": "cycleReservationSetting",
        },
    )
    entity = entity_modules.select.RinnaiCommandSelect(coordinator, "dev1", config)

    await entity.async_select_option("Rapid")

    assert coordinator.commands == [
        {
            "operationMode": "00",
            "heatingReservationSetting": "30",
            "rapidHeatingSetting": "01",
        }
    ]


@pytest.mark.parametrize(
    "raw_value",
    ["E0", "A0", "80", "C1", "81", "C0", "90", "D0"],
)
def test_e32_power_matches_all_observed_on_values(
    entity_modules: SimpleNamespace,
    raw_value: str,
) -> None:
    config = next(item for item in _e32_config()["entities"]["switch"] if item["key"] == "power")
    coordinator = StubCoordinator(
        {"operationMode": raw_value},
        {"operation_mode": "operationMode"},
    )
    entity = entity_modules.switch.RinnaiCommandSwitch(coordinator, "dev1", config)

    assert entity._attr_is_on is True



def test_e32_power_matches_off_value(entity_modules: SimpleNamespace) -> None:
    config = next(item for item in _e32_config()["entities"]["switch"] if item["key"] == "power")
    coordinator = StubCoordinator(
        {"operationMode": "20"},
        {"operation_mode": "operationMode"},
    )
    entity = entity_modules.switch.RinnaiCommandSwitch(coordinator, "dev1", config)

    assert entity._attr_is_on is False


def test_command_switch_default_on_value_behavior_unchanged(
    entity_modules: SimpleNamespace,
) -> None:
    config = {
        "name": "Cycle Insulation",
        "key": "cycle_insulation",
        "command_key": "temporaryCycleInsulationSetting",
        "command_on": "01",
        "command_off": "00",
        "state_attribute": "cycle_insulation",
        "on_value": 1,
    }
    coordinator = StubCoordinator(
        {"temporaryCycleInsulationSetting": 1},
        {"cycle_insulation": "temporaryCycleInsulationSetting"},
    )
    entity = entity_modules.switch.RinnaiCommandSwitch(coordinator, "dev1", config)

    assert entity._attr_is_on is True

    coordinator.state.raw_data["temporaryCycleInsulationSetting"] = 0
    entity._update_attributes()

    assert entity._attr_is_on is False


@pytest.mark.parametrize(
    ("raw_value", "expected_is_on"),
    [("1", True), ("01", True), ("0", False), ("00", False)],
)
def test_e32_cycle_insulation_matches_observed_string_values(
    entity_modules: SimpleNamespace,
    raw_value: str,
    expected_is_on: bool,
) -> None:
    config = next(
        item
        for item in _e32_config()["entities"]["switch"]
        if item["key"] == "cycle_insulation"
    )
    coordinator = StubCoordinator(
        {"temporaryCycleInsulationSetting": raw_value},
        {"cycle_insulation": "temporaryCycleInsulationSetting"},
    )
    entity = entity_modules.switch.RinnaiCommandSwitch(coordinator, "dev1", config)

    assert entity._attr_is_on is expected_is_on


@pytest.mark.parametrize("raw_mode", ["80", "C0", "D0"])
@pytest.mark.asyncio
async def test_e32_relative_temperature_accepts_observed_mode_aliases(
    entity_modules: SimpleNamespace,
    raw_mode: str,
) -> None:
    config = _e32_water_heater_config()
    coordinator = StubCoordinator(
        {"hotWaterTempSetting": 40, "operationMode": raw_mode},
        {"hot_water_temp": "hotWaterTempSetting", "operation_mode": "operationMode"},
    )
    entity = entity_modules.water_heater.RinnaiWaterHeaterEntity(coordinator, "dev1", config)

    await entity.async_set_temperature(temperature=41)

    assert coordinator.commands == [{"hotWaterTempOperate": "01"}]
    assert coordinator.state.raw_data["hotWaterTempSetting"] == 41


def test_command_switch_can_use_off_values_without_on_values(
    entity_modules: SimpleNamespace,
) -> None:
    config = {
        "name": "Power",
        "key": "power",
        "command_key": "power",
        "command_on": "01",
        "command_off": "00",
        "state_attribute": "operation_mode",
        "off_values": ["20"],
    }
    coordinator = StubCoordinator(
        {"operationMode": "E0"},
        {"operation_mode": "operationMode"},
    )
    entity = entity_modules.switch.RinnaiCommandSwitch(coordinator, "dev1", config)

    assert entity._attr_is_on is True

    coordinator.state.raw_data["operationMode"] = "20"
    entity._update_attributes()

    assert entity._attr_is_on is False


def test_sensor_fallback_uses_error_code_when_fault_code_is_empty(
    entity_modules: SimpleNamespace,
) -> None:
    config = next(
        item for item in _e32_config()["entities"]["sensor"] if item["key"] == "fault_code"
    )
    coordinator = StubCoordinator(
        {"faultCode": "00", "errorCode": "12"},
        {"fault_code": "faultCode", "error_code": "errorCode"},
    )
    entity = entity_modules.sensor.RinnaiGenericSensor(
        coordinator,
        "dev1",
        config,
    )

    entity._update_attributes()

    assert entity._attr_native_value == "12"
