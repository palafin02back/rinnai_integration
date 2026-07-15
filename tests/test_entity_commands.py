"""Tests for config-driven entity command behavior."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

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
    ) -> None:
        self.commands: list[dict[str, Any]] = []
        self.refresh_count = 0
        self.temperature_steps = temperature_steps
        self.stale_refreshes = stale_refreshes
        self.state = SimpleNamespace(raw_data=raw_data)
        self.device = SimpleNamespace(
            online=True,
            device_name="Test Device",
            device_type="02720E32",
            config=SimpleNamespace(
                state_mapping=state_mapping,
                schedule_config={},
                features={},
                entities={},
            ),
        )

    def get_device(self, device_id: str) -> Any:
        return self.device

    def get_device_state(self, device_id: str) -> Any:
        return self.state

    async def async_send_command(self, device_id: str, command: dict[str, Any]) -> bool:
        self.commands.append(command)
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


def _e32_water_heater_config() -> dict[str, Any]:
    config = json.loads(json.dumps(_e32_config()["entities"]["water_heater"][0]))
    config["relative_temperature_control"]["step_delay_seconds"] = 0
    return config


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
        ("E0", "普通"),
        ("A0", "普通"),
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
    "raw_value",
    ["E0", "A0", "C1", "81", "C0", "90", "D0"],
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


@pytest.mark.parametrize("raw_mode", ["C0", "D0"])
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
