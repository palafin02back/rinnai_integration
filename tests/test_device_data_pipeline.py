"""Regression tests for device JSON data through the model pipeline."""
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
DEVICES_DIR = RINNAI_ROOT / "devices"

ALL_DEVICE_TYPES = sorted(path.stem for path in DEVICES_DIR.glob("*.json"))

DIRECT_FIELD_VALUES: dict[str, Any] = {
    "bathWaterInjectionSetting": "1",
    "burningState": "30",
    "childLock": "00",
    "cycleModeSetting": "02",
    "cycleReservationSetting1": "1",
    "errorCode": "00",
    "faucetNotCloseSign": "00",
    "faultCode": "00",
    "heatingReservationMode": "1",
    "hotWaterReservationMode": "1",
    "hotWaterUseableSign": "01",
    "hpUnitConnect": "1",
    "hpUnitOperationMode": "1",
    "hpUnitPower": "1",
    "onlineStatus": "1",
    "operMode": "1",
    "operationMode": "3",
    "power": "1",
    "powerStatus": "1",
    "rapidHeating": "1",
    "roomTemperatureDisplay": "16",
    "runningState": "1",
    "summerWinter": "1",
    "thermalStatus": "1",
    "temporaryCycleInsulationSetting": "01",
    "workMode": "1",
    "workStatus": "1",
}

SYNTHETIC_FIELD_VALUES: dict[str, Any] = {
    "monthlyGasConsumption": 12.3,
    "todayGasConsumption": 1.2,
    "yearlyGasConsumption": 45.6,
    "yesterdayGasConsumption": 0.8,
}


def _load_module(name: str, path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def model_modules(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Load the model/data modules without importing Home Assistant platforms."""
    for name in list(sys.modules):
        if name == "custom_components" or name.startswith("custom_components.rinnai"):
            monkeypatch.delitem(sys.modules, name, raising=False)

    custom_components = ModuleType("custom_components")
    custom_components.__path__ = [str(ROOT / "custom_components")]
    rinnai_pkg = ModuleType("custom_components.rinnai")
    rinnai_pkg.__path__ = [str(RINNAI_ROOT)]
    core_pkg = ModuleType("custom_components.rinnai.core")
    core_pkg.__path__ = [str(RINNAI_ROOT / "core")]
    models_pkg = ModuleType("custom_components.rinnai.models")
    models_pkg.__path__ = [str(RINNAI_ROOT / "models")]

    monkeypatch.setitem(sys.modules, "custom_components", custom_components)
    monkeypatch.setitem(sys.modules, "custom_components.rinnai", rinnai_pkg)
    monkeypatch.setitem(sys.modules, "custom_components.rinnai.core", core_pkg)
    monkeypatch.setitem(sys.modules, "custom_components.rinnai.models", models_pkg)

    processor = _load_module(
        "custom_components.rinnai.core.processor",
        RINNAI_ROOT / "core" / "processor.py",
        monkeypatch,
    )
    _load_module(
        "custom_components.rinnai.core.state_manager",
        RINNAI_ROOT / "core" / "state_manager.py",
        monkeypatch,
    )
    _load_module(
        "custom_components.rinnai.models.config",
        RINNAI_ROOT / "models" / "config.py",
        monkeypatch,
    )
    config_manager_mod = _load_module(
        "custom_components.rinnai.core.config_manager",
        RINNAI_ROOT / "core" / "config_manager.py",
        monkeypatch,
    )
    device = _load_module(
        "custom_components.rinnai.models.device",
        RINNAI_ROOT / "models" / "device.py",
        monkeypatch,
    )
    config_manager_mod.config_manager.load_configs(str(DEVICES_DIR))

    return SimpleNamespace(
        config_manager=config_manager_mod.config_manager,
        process_data=processor.process_data,
        RinnaiDevice=device.RinnaiDevice,
    )


def _load_json(device_type: str) -> dict[str, Any]:
    with open(DEVICES_DIR / f"{device_type}.json", encoding="utf-8") as file:
        return json.load(file)


def _processor_names(processors: list[Any]) -> list[str]:
    names: list[str] = []
    for item in processors:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            names.append(str(item.get("func", "")))
    return names


def _sample_for_processor(processors: list[Any]) -> Any:
    names = _processor_names(processors)
    if "hex4_to_int" in names:
        return "2A00"
    if "hex_to_int" in names:
        return "2A"
    if any(name in names for name in ("divide", "multiply", "to_type")):
        return "2"
    return "1"


def _sample_schedule_hex(config: dict[str, Any]) -> str:
    schedule = config.get("schedule_config", {})
    total_length = int(schedule.get("total_length", 34))
    data = bytearray(total_length // 2)

    status_index = schedule.get("status_byte_index")
    if status_index is not None and status_index < len(data):
        data[int(status_index)] = 1

    mode_index = schedule.get("mode_byte_index")
    mode_count = int(schedule.get("mode_count", 0))
    if mode_count > 1 and mode_index is not None and mode_index < len(data):
        data[int(mode_index)] = 1

    start = int(schedule.get("data_start_byte_index", 2))
    bytes_per_mode = int(schedule.get("bytes_per_mode", 3))
    for offset in range(start, min(start + bytes_per_mode, len(data))):
        data[offset] = 0xFF

    return data.hex().upper()


def _sample_for_raw_key(raw_key: str, config: dict[str, Any]) -> Any:
    if raw_key == "byteStr":
        return _sample_schedule_hex(config)
    if raw_key in SYNTHETIC_FIELD_VALUES:
        return SYNTHETIC_FIELD_VALUES[raw_key]
    return DIRECT_FIELD_VALUES.get(raw_key, "1")


def _sample_payload(config: dict[str, Any]) -> dict[str, Any]:
    payload = {
        field: _sample_for_processor(processors)
        for field, processors in config.get("processors", {}).items()
    }
    for raw_key in config.get("features", {}).get("energy_data_keys", []):
        processors = config.get("processors", {}).get(raw_key)
        payload.setdefault(
            raw_key,
            _sample_for_processor(processors) if processors else "2A",
        )
    for raw_key in config.get("state_mapping", {}).values():
        payload.setdefault(raw_key, _sample_for_raw_key(raw_key, config))
    return payload


@pytest.mark.parametrize("device_type", ALL_DEVICE_TYPES)
def test_device_json_payload_flows_through_model_pipeline(
    model_modules: SimpleNamespace,
    device_type: str,
) -> None:
    """Every device JSON should process generated raw data through model entrypoints."""
    config_json = _load_json(device_type)
    payload = _sample_payload(config_json)
    expected = model_modules.process_data(payload, config_json.get("processors", {}))

    device = model_modules.RinnaiDevice(device_id=f"{device_type}-test")
    device.update_from_api_data(
        {
            "deviceType": device_type,
            "name": f"{device_type} test",
            "online": "1",
            "authCode": "FFFF",
        }
    )
    assert device.config is model_modules.config_manager.get_config(device_type)

    device.update_state(payload)

    for key, value in expected.items():
        assert device.state.raw_data[key] == value, (
            f"{device_type}: processed field {key!r} changed while flowing "
            "through RinnaiDevice.update_state"
        )

    for state_attr, raw_key in config_json.get("state_mapping", {}).items():
        assert raw_key in device.state.raw_data, (
            f"{device_type}: state_mapping[{state_attr!r}] references "
            f"{raw_key!r}, but the model pipeline did not expose it"
        )
