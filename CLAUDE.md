# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dev dependencies
uv sync --extra test

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_processor.py

# Run a single test
uv run pytest tests/test_processor.py::test_hex_to_int

# Run tests with coverage
uv run pytest --cov=custom_components/rinnai

```

The integration has no build step — it is installed directly into Home Assistant's `custom_components/` directory.

## Architecture

This is a Home Assistant custom integration for Rinnai (林内) heating/water heater devices. It communicates via **dual channels**: HTTP REST API for initial device discovery/state, and a custom **MQTT over TLS** connection (`mqtt.rinnai.com.cn:8883`) for real-time push updates and command sending.

### Data Flow

```
HA Setup → RinnaiClient.async_initialize()
              ├─ HTTP login → fetch device list → fetch initial states
              └─ MQTT connect → subscribe per-device topics (inf/, stg/, sys/, res/)

Runtime:
  MQTT push → RinnaiClient._handle_state_update()
                → RinnaiCoordinator._handle_device_update()
                  → RinnaiDevice.update_state(is_command=False)
                    → RinnaiStateManager.update_remote()
                      → RinnaiDeviceState.update_from_api_data()  [runs processors]
                        → coordinator.async_set_updated_data()  [notifies HA entities]

User command → coordinator.async_send_command()
                → RinnaiDevice.update_state(is_command=True)  [optimistic update]
                  → RinnaiStateManager.set_desired()  [locks key for 10s]
                → RinnaiClient.send_command()  [publishes MQTT]
```

### Key Classes

| Class | File | Role |
|---|---|---|
| `RinnaiClient` | `core/client.py` | Unified HTTP + MQTT client; owns auth token, device data dicts |
| `RinnaiMQTTClient` | `core/mqtt_client.py` | Wraps paho-mqtt; runs paho loop in executor thread, bridges callbacks to HA event loop; exponential-backoff reconnect |
| `RinnaiCoordinator` | `coordinator.py` | HA `DataUpdateCoordinator`; owns `RinnaiDevice` objects, persists energy data to HA storage |
| `RinnaiDevice` | `models/device.py` | Per-device model holding state + config; delegates state reconciliation to `RinnaiStateManager` |
| `RinnaiStateManager` | `core/state_manager.py` | Optimistic state: desired state overrides remote for 10 s, then reverts |
| `ConfigManager` | `core/config_manager.py` | Singleton; loads `devices/*.json` files, looks up config by `deviceType` field |
| `RinnaiEntity` | `entity.py` | Base HA entity; provides `get_state_value()` via config `state_mapping`, lazy `schedule_manager` |

### Entity Platforms

| Platform | Class | Config key in JSON |
|---|---|---|
| `climate` | `RinnaiClimateEntity` | `entities.climate` |
| `water_heater` | `RinnaiWaterHeaterEntity` | `entities.water_heater` |
| `sensor` | `RinnaiSensorEntity` | `entities.sensor` |
| `switch` | `RinnaiCommandSwitch` / `RinnaiHeatingReservationSwitch` | `entities.switch` |
| `select` | `RinnaiCommandSelect` / reservation select | `entities.select` |
| `number` | `RinnaiNumberEntity` | `entities.number` |
| `text` | schedule text input | `entities.text` |

### Device Configuration System

All device-specific behavior is defined in `devices/<deviceType>.json` (e.g., `0F06000C.json` for G56). The JSON schema includes:

- **`entities`**: Declares which HA entity types to create and their parameters (temp ranges, modes, MQTT command keys, etc.)
- **`state_mapping`**: Maps generic HA attribute names → raw API field names (e.g., `"hot_water_temp"` → `"hotWaterTempSetting"`)
- **`processors`**: Per-field transform chains applied when raw data arrives (e.g., `hex_to_int`, `divide`)
- **`features`**: Device-specific constants (MQTT `heat_type`, energy key names, reservation mode presets)
- **`schedule_config`**: Byte layout of the schedule hex string parsed by `RinnaiScheduleManager`
- **`supported_requests`**: Which named requests in `API_DEFINITIONS` (see `const.py`) this device supports

**To add a new device model**, create a new `devices/<deviceType>.json`. No Python code changes are needed unless new entity types or processor functions are required.

### Supported Device Types

| File | Device | Key Features |
|---|---|---|
| `0F06000C.json` | G56 采暖炉 | climate (5 modes), water_heater, schedule, energy |
| `0F060016.json` | G58 采暖炉 | same as G56 |
| `0F060G55.json` | G55 采暖炉 | same as G56 |
| `02720E86.json` | E86 热水器 | water_heater (hex4 temp), massage, cycle insulation, schedule |
| `0272000E.json` | E88 热水器 | same feature set as E86 |
| `02720022.json` | E89 热水器 | same + bath injection, min_temp=32°C |
| `02720010.json` | E65 热水器 | massage, 浓薄水 mode |
| `0272001C.json` | E75 热水器 | massage, 浓薄水 mode |
| `02720E76.json` | E76 热水器 | mid-range |
| `02720E66.json` | E66 热水器 | mid-range |
| `0272000D.json` | E51 热水器 | basic, 3 operation modes |
| `0F090004.json` | RTC-626 温控器 | power switch, room temp sensor, room_temp number setpoint |
| `0F090011.json` | 热泵温控器 | power switch, mode select, 3 number setpoints |
| `0F070006.json` | 净水软水器 | forceRegen switch, salt/water sensors |

### Temperature Encoding

Water heater `command_topic` values are hex-encoded integers:
- `temp_format: "hex2"` — G56/boiler style: 40°C → `"28"`
- `temp_format: "hex4"` — E-series water heater style: 40°C → `"2800"`

The `water_heater.py` and `number.py` both read `temp_format` from the entity config to pick the correct encoding. Default is `"hex2"`.

### MQTT Protocol

- Topics: `rinnai/SR/01/SR/{mac}/{inf|stg|set|sys|res}/`
- `inf/` — device state push (`code=FFFF`) and reservation push (`code=03F1`)
- `stg/` — energy data push (`ptn=J05`)
- `set/` — command publish (`ptn=J00`, `sum=1`)
- `sys/` — online/offline notification (`ptn=JA3`); heartbeat (`ptn=JA4`)
- `res/` — response to active queries sent on `get/` (heat pump, etc.)
- MQTT username: `a:rinnai:SR:01:SR:{username}`; password: MD5(plaintext) uppercased
- Reconnect: exponential backoff `[5, 10, 30, 60, 120]` seconds on unexpected disconnect

### Optimistic State

`coordinator.async_send_command()` applies a desired state immediately (via `RinnaiStateManager.set_desired()`) that blocks remote updates for that key for 10 seconds. This prevents the UI from flickering back before the device confirms. All command paths (switches, selects, water_heater, number, climate transitions) must go through the coordinator, not `client.send_command` directly.

### Schedule Hex String Format

Schedules are encoded as hex strings (34 bytes for G56/E-series). `RinnaiScheduleManager` handles encoding/decoding based on `schedule_config` from the device JSON. Utility functions `decode_schedule_bitmap` / `parse_schedule_string` / `format_schedule_string` live in `core/util.py`.

### Tests

Tests in `tests/` do not use Home Assistant test harness — they test the core logic (`processor.py`, `state_manager.py`, `schedule_manager.py`) with plain `pytest` and `unittest.mock`. The `conftest.py` adds `custom_components` to `sys.path`.
