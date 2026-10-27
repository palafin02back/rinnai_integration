"""E86/E88 regressions from cloud snapshots and the legacy App protocol."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from .test_entity_commands import StubCoordinator, entity_modules

ROOT = Path(__file__).resolve().parents[1] / 'custom_components' / 'rinnai'


@pytest.fixture(params=['02720E86', '0272000E'])
def profile(request):
    return json.loads((ROOT / 'devices' / f'{request.param}.json').read_text())


def coordinator_for(profile, raw):
    spec = importlib.util.spec_from_file_location('e86_snapshot_processor', ROOT / 'core' / 'processor.py')
    processor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(processor)
    coordinator = StubCoordinator(processor.process_data(raw, profile['processors']), profile['state_mapping'])
    coordinator.device.config.schedule_config = profile.get('schedule_config', {})
    coordinator.device.config.features = profile['features']
    return coordinator


def entity_config(profile, platform, key):
    return next(config for config in profile['entities'][platform] if config['key'] == key)


def test_observed_temperature_and_fault_are_not_zero_or_missing(entity_modules, profile):
    coordinator = coordinator_for(profile, {
        'hotWaterTempSetting': '2A', 'operationMode': 'A0',
        'burningState': '0', 'errorCode': '0',
    })
    temperature = entity_modules.sensor.RinnaiGenericSensor(
        coordinator, 'dev1', entity_config(profile, 'sensor', 'hot_water_temp')
    )
    fault = entity_modules.sensor.RinnaiGenericSensor(
        coordinator, 'dev1', entity_config(profile, 'sensor', 'fault_code')
    )
    temperature._update_attributes()
    fault._update_attributes()
    assert temperature._attr_native_value == 42
    assert fault._attr_native_value == '0'


@pytest.mark.parametrize(('raw', 'expected'), [('0', 'Standby'), ('1', 'Burning')])
def test_burning_flag_uses_device_values(entity_modules, profile, raw, expected):
    coordinator = coordinator_for(profile, {'burningState': raw})
    entity = entity_modules.sensor.RinnaiGenericSensor(
        coordinator, 'dev1', entity_config(profile, 'sensor', 'burning_state')
    )
    entity._update_attributes()
    assert entity._attr_native_value == expected


@pytest.mark.parametrize(('mode', 'label', 'massage', 'powered'), [
    ('A0', '正常', False, True),
    ('E0', '正常', False, True),
    ('90', '淋浴', False, True),
    ('C8', '按摩水', True, True),
    ('84', '浴缸', False, True),
    ('82', '低温', False, True),
    ('81', '厨房', False, True),
    ('00', None, False, False),
])
def test_mode_flags_ignore_circulation_bit(entity_modules, profile, mode, label, massage, powered):
    coordinator = coordinator_for(profile, {'operationMode': mode})
    select = entity_modules.select.RinnaiCommandSelect(
        coordinator, 'dev1', entity_config(profile, 'select', 'operation_mode')
    )
    massage_entity = entity_modules.switch.RinnaiCommandSwitch(
        coordinator, 'dev1', entity_config(profile, 'switch', 'massage_mode')
    )
    power_entity = entity_modules.switch.RinnaiCommandSwitch(
        coordinator, 'dev1', entity_config(profile, 'switch', 'power')
    )
    assert select._attr_current_option == label
    assert massage_entity._attr_is_on is massage
    assert power_entity._attr_is_on is powered


@pytest.mark.parametrize('raw', [None, '', 'invalid', '-1'])
def test_invalid_mode_does_not_become_known_off(entity_modules, profile, raw):
    coordinator = coordinator_for(profile, {'operationMode': raw})
    power = entity_modules.switch.RinnaiCommandSwitch(
        coordinator, 'dev1', entity_config(profile, 'switch', 'power')
    )
    select = entity_modules.select.RinnaiCommandSelect(
        coordinator, 'dev1', entity_config(profile, 'select', 'operation_mode')
    )
    assert power._attr_is_on is None
    assert select._attr_current_option is None



@pytest.mark.parametrize(('raw', 'expected'), [
    ('C0 C0 0F', '06:00-08:00, 14:00-20:00'),
    ('000000', 'Off'),
    ('FFFFFF', '00:00-24:00'),
    (None, None),
    ('invalid', None),
])
def test_cycle_reservation_hours_use_device_bitmap(entity_modules, profile, raw, expected):
    coordinator = coordinator_for(profile, {'cycleReservationTimeSetting': raw})
    entity = entity_modules.sensor.RinnaiScheduleBitmapSensor(
        coordinator, 'dev1', entity_config(profile, 'sensor', 'cycle_reservation_time')
    )
    assert entity._attr_native_value == expected


@pytest.mark.asyncio
async def test_power_and_mode_publish_verified_commands(entity_modules, profile):
    coordinator = coordinator_for(profile, {'operationMode': 'A0'})
    power = entity_modules.switch.RinnaiCommandSwitch(
        coordinator, 'dev1', entity_config(profile, 'switch', 'power')
    )
    select = entity_modules.select.RinnaiCommandSelect(
        coordinator, 'dev1', entity_config(profile, 'select', 'operation_mode')
    )
    await select.async_select_option('淋浴')
    await power.async_turn_off()
    assert coordinator.commands == [{'showerMode': '01'}, {'power': '00'}]
    assert select._attr_current_option == '淋浴'
    assert power._attr_is_on is False


@pytest.mark.asyncio
@pytest.mark.parametrize(('mode', 'current', 'requested', 'expected'), [
    ('A0', 48, 49, 50),
    ('E0', 50, 53, 55),
    ('90', 44, 46, 45),
    ('81', 41, 43, 42),
])
async def test_unsupported_temperature_uses_nearest_mode_setpoint(
    entity_modules, profile, mode, current, requested, expected
):
    config = entity_config(profile, 'water_heater', 'main')
    control = config['relative_temperature_control']
    control['step_delay_seconds'] = 0
    allowed = control['allowed_temps_by_mode'][f'{int(mode, 16) & 0x3F:02X}']
    coordinator = StubCoordinator(
        {'hotWaterTempSetting': current, 'operationMode': mode},
        profile['state_mapping'],
        temperature_steps=allowed,
    )
    entity = entity_modules.water_heater.RinnaiWaterHeaterEntity(
        coordinator, 'dev1', config
    )

    await entity.async_set_temperature(temperature=requested)

    assert coordinator.commands == [{'hotWaterTempOperate': '01'}]
    assert entity._attr_target_temperature == expected
    assert entity._attr_extra_state_attributes['温度提示'] == (
        f'不支持{requested}℃，已切换至最近支持的{expected}℃'
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', [None, 'invalid', '00'])
async def test_temperature_adjustment_does_not_bypass_unknown_mode(
    entity_modules, profile, mode
):
    coordinator = StubCoordinator(
        {'hotWaterTempSetting': 48, 'operationMode': mode},
        profile['state_mapping'],
    )
    entity = entity_modules.water_heater.RinnaiWaterHeaterEntity(
        coordinator, 'dev1', entity_config(profile, 'water_heater', 'main')
    )

    await entity.async_set_temperature(temperature=49)

    assert coordinator.commands == []
    assert entity._attr_target_temperature == 48
