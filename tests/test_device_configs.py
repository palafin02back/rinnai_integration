"""
Comprehensive tests for all device configurations.

Validates that each device JSON config:
  1. Is internally consistent (state_mapping keys match processors / energy_data_keys)
  2. Has correct processor chains for known raw values
  3. Declares the expected entity platforms for its device family
  4. Uses correct temperature encoding (hex2 vs hex4)
  5. Has complete climate transitions (boilers only)
"""
from __future__ import annotations

import json
import os
import pytest

# ── path setup ────────────────────────────────────────────────────────────────
import sys
_CORE = os.path.join(os.path.dirname(__file__), "..", "custom_components", "rinnai", "core")
sys.path.insert(0, _CORE)

from processor import process_value, process_data  # noqa: E402

DEVICES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "custom_components", "rinnai", "devices"
)

# ── helpers ───────────────────────────────────────────────────────────────────

def load(device_type: str) -> dict:
    path = os.path.join(DEVICES_DIR, f"{device_type}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


ALL_DEVICE_TYPES = [
    f[:-5] for f in os.listdir(DEVICES_DIR) if f.endswith(".json")
]

BOILER_TYPES   = ["0F06000C", "0F060016", "0F060G55"]
E_SERIES_TYPES = ["02720E86", "0272000E", "02720022", "02720010", "0272001C",
                   "02720E76", "02720E66", "0272000D"]
E_MASSAGE      = ["02720E86", "0272000E", "02720022", "02720010", "0272001C"]
E_CYCLE        = ["02720E86", "0272000E", "02720022"]
E_THICK_THIN   = ["02720010", "0272001C"]
SOFTENER_TYPES = ["0F070006"]
RTC626_TYPES   = ["0F090004"]
HEATPUMP_TYPES = ["0F090011"]

CLIMATE_MODES  = ["standby", "normal", "energy_saving", "outdoor", "rapid"]


# ═════════════════════════════════════════════════════════════════════════════
# 1. JSON structure – every device
# ═════════════════════════════════════════════════════════════════════════════

class TestJsonStructure:
    """Every device JSON must have the required top-level keys."""

    @pytest.mark.parametrize("device_type", ALL_DEVICE_TYPES)
    def test_required_top_level_keys(self, device_type):
        d = load(device_type)
        for key in ("features", "processors", "state_mapping", "entities"):
            assert key in d, f"{device_type}: missing top-level key '{key}'"

    @pytest.mark.parametrize("device_type", ALL_DEVICE_TYPES)
    def test_heat_type_present(self, device_type):
        d = load(device_type)
        assert "heat_type" in d["features"], \
            f"{device_type}: features.heat_type missing"

    @pytest.mark.parametrize("device_type", ALL_DEVICE_TYPES)
    def test_entity_configs_have_key_and_name(self, device_type):
        d = load(device_type)
        for platform, configs in d["entities"].items():
            for cfg in configs:
                assert "key" in cfg, \
                    f"{device_type}/{platform}: entity config missing 'key'"
                assert "name" in cfg, \
                    f"{device_type}/{platform}: entity config missing 'name'"


# ═════════════════════════════════════════════════════════════════════════════
# 2. state_mapping ↔ processors/energy_data_keys consistency – every device
# ═════════════════════════════════════════════════════════════════════════════

class TestStateMappingConsistency:
    """
    Every raw key referenced by state_mapping must be reachable in raw_data,
    meaning it is either:
      - a key in processors (applied to device-info MQTT fields), OR
      - a key in energy_data_keys (extracted from stg/ MQTT energy push), OR
      - a non-processed field (operationMode, burningState, etc.)

    The critical class of bug: energy_data_keys says "gasUsed" but
    state_mapping points to "gasConsumption" → sensor always unknown.
    """

    # Fields that arrive directly from inf/ MQTT without being in processors
    # (device sends them pre-decoded as plain strings/numbers)
    _DIRECT_FIELDS = {
        # boiler / water heater common
        "operationMode", "burningState", "byteStr",
        "heatingReservationMode", "hotWaterReservationMode",
        "faultCode", "errorCode",
        # E-series extras
        "massageMode", "temporaryCycleInsulationSetting",
        "cycleReservationSetting1",
        # water softener
        "workMode", "saltLevel", "saltLow", "saltAlarm",
        "waterHardness", "regenCount", "outWaterFlow",
        "workStatus", "waterVelocity",
        # RTC-626 / heat pump
        "power", "powerStatus", "runningState", "onlineStatus",
        "thermalStatus", "hpUnitOperationMode", "hpUnitPower",
        "hpUnitConnect", "heatingReservationTime",
        "operMode", "roomTemperatureDisplay",
        # E89 bath injection
        "bathWaterInjectionSetting",
        # C66L direct mode fields (separate booleans instead of operationMode)
        "power", "summerWinter", "ecoMode", "outdoorMode",
        "rapidHeating", "heatingReservationMode", "hotWaterReservationMode",
        # Synthetic fields injected by coordinator (not from MQTT/processors)
        "monthlyGasConsumption", "yearlyGasConsumption",
        "todayGasConsumption", "yesterdayGasConsumption",
    }

    @pytest.mark.parametrize("device_type", ALL_DEVICE_TYPES)
    def test_state_mapping_targets_are_reachable(self, device_type):
        d = load(device_type)
        processors    = set(d.get("processors", {}).keys())
        energy_keys   = set(d.get("features", {}).get("energy_data_keys", []))
        reachable     = processors | energy_keys | self._DIRECT_FIELDS

        for attr, raw_key in d["state_mapping"].items():
            assert raw_key in reachable, (
                f"{device_type}: state_mapping['{attr}'] → '{raw_key}' "
                f"is not in processors, energy_data_keys, or known direct fields"
            )

    @pytest.mark.parametrize("device_type", BOILER_TYPES)
    def test_boiler_energy_keys_match_processors(self, device_type):
        """For boilers, every energy_data_key must have a processor entry."""
        d = load(device_type)
        energy_keys = d["features"]["energy_data_keys"]
        processors  = d["processors"]
        for key in energy_keys:
            assert key in processors, (
                f"{device_type}: energy_data_key '{key}' has no processor "
                f"(sensor will display raw hex string)"
            )

    @pytest.mark.parametrize("device_type", E_SERIES_TYPES)
    def test_e_series_gas_consumption_processor(self, device_type):
        """E-series gas field must be gasConsumption in both energy_keys and processors."""
        d = load(device_type)
        energy_keys = d["features"]["energy_data_keys"]
        assert "gasConsumption" in energy_keys, \
            f"{device_type}: energy_data_keys missing 'gasConsumption'"
        assert "gasConsumption" in d["processors"], \
            f"{device_type}: processors missing 'gasConsumption'"
        assert d["state_mapping"].get("gas_usage") == "gasConsumption", \
            f"{device_type}: state_mapping gas_usage should point to 'gasConsumption'"


# ═════════════════════════════════════════════════════════════════════════════
# 3. Processor chain correctness
# ═════════════════════════════════════════════════════════════════════════════

class TestProcessorChains:
    """Verify processor chains produce correct values for known raw inputs."""

    # ── Boiler G56/G58/G55 ───────────────────────────────────────────────────

    @pytest.mark.parametrize("device_type", BOILER_TYPES)
    def test_boiler_hot_water_temp_hex2(self, device_type):
        """hotWaterTempSetting: hex2 "2A" → 42°C"""
        d = load(device_type)
        chain = d["processors"]["hotWaterTempSetting"]
        assert process_value("2A", chain) == 42

    @pytest.mark.parametrize("device_type", BOILER_TYPES)
    def test_boiler_gas_used_to_m3(self, device_type):
        """gasUsed: "00002710" (10000 dec) → 1.0 m³ (÷10000)"""
        d = load(device_type)
        chain = d["processors"]["gasUsed"]
        assert process_value("00002710", chain) == pytest.approx(1.0)

    @pytest.mark.parametrize("device_type", BOILER_TYPES)
    def test_boiler_supply_time_to_days(self, device_type):
        """supplyTime: "A87" (2695 dec hours) → ~112.3 days (÷24)"""
        d = load(device_type)
        chain = d["processors"]["supplyTime"]
        result = process_value("A87", chain)
        assert result == pytest.approx(2695 / 24, rel=1e-4)

    @pytest.mark.parametrize("device_type", BOILER_TYPES)
    def test_boiler_total_power_supply_time_to_days(self, device_type):
        """totalPowerSupplyTime: hours → days via ÷24"""
        d = load(device_type)
        chain = d["processors"]["totalPowerSupplyTime"]
        assert process_value("18", chain) == pytest.approx(24 / 24)  # 0x18=24h → 1 day

    @pytest.mark.parametrize("device_type", BOILER_TYPES)
    def test_boiler_burning_time_stays_hours(self, device_type):
        """totalHeatingBurningTime: no divide, stays in hours"""
        d = load(device_type)
        chain = d["processors"]["totalHeatingBurningTime"]
        # "07E6" = 2022 dec → 2022 h (no divide)
        assert process_value("7E6", chain) == 2022

    @pytest.mark.parametrize("device_type", BOILER_TYPES)
    def test_boiler_heating_temp_nm(self, device_type):
        """heatingTempSettingNM: "38" → 56°C"""
        d = load(device_type)
        chain = d["processors"]["heatingTempSettingNM"]
        assert process_value("38", chain) == 56

    # ── E-series ─────────────────────────────────────────────────────────────

    @pytest.mark.parametrize("device_type", E_SERIES_TYPES)
    def test_e_series_hot_water_temp_hex_to_int(self, device_type):
        """hotWaterTempSetting hex4_to_int: "2A00" → 42°C (E-series uses 4-byte hex)"""
        d = load(device_type)
        chain = d["processors"]["hotWaterTempSetting"]
        assert process_value("2A00", chain) == 42

    @pytest.mark.parametrize("device_type", E_SERIES_TYPES)
    def test_e_series_gas_consumption_to_m3(self, device_type):
        """gasConsumption: "00004E20" (20000 dec) → 2.0 m³"""
        d = load(device_type)
        chain = d["processors"]["gasConsumption"]
        assert process_value("00004E20", chain) == pytest.approx(2.0)

    # ── RTC-626 温控器 ────────────────────────────────────────────────────────

    def test_rtc626_room_temp_setting(self):
        d = load("0F090004")
        chain = d["processors"]["roomTempSetting"]
        assert process_value("14", chain) == 20  # 0x14=20

    def test_rtc626_room_temperature_sensor(self):
        d = load("0F090004")
        chain = d["processors"]["roomTemperature"]
        assert process_value("16", chain) == 22

    # ── 热泵温控器 ────────────────────────────────────────────────────────────

    def test_heatpump_cold_temp_setting(self):
        d = load("0F090011")
        chain = d["processors"]["hpUnitColdTempSetting"]
        assert process_value("18", chain) == 24

    def test_heatpump_hot_temp_setting(self):
        d = load("0F090011")
        chain = d["processors"]["hpUnitHotTempSetting"]
        assert process_value("1C", chain) == 28


# ═════════════════════════════════════════════════════════════════════════════
# 4. Temperature encoding (hex2 vs hex4)
# ═════════════════════════════════════════════════════════════════════════════

class TestTemperatureEncoding:
    """
    Boiler water heater: no temp_format (defaults to hex2) → 40°C encodes as "28"
    E-series water heater: temp_format="hex4"               → 40°C encodes as "2800"
    """

    @pytest.mark.parametrize("device_type", BOILER_TYPES)
    def test_boiler_water_heater_uses_hex2(self, device_type):
        d = load(device_type)
        wh = d["entities"]["water_heater"][0]
        fmt = wh.get("temp_format", "hex2")
        assert fmt == "hex2", \
            f"{device_type}: water_heater should use hex2, got '{fmt}'"

    @pytest.mark.parametrize("device_type", E_SERIES_TYPES)
    def test_e_series_water_heater_uses_hex4(self, device_type):
        d = load(device_type)
        wh = d["entities"]["water_heater"][0]
        assert wh.get("temp_format") == "hex4", \
            f"{device_type}: water_heater should declare temp_format=hex4"

    def test_hex2_encoding_40c(self):
        """40°C → hex2 → "28" (2-char)"""
        t = 40
        encoded = hex(t)[2:].upper().zfill(2)
        assert encoded == "28"
        assert len(encoded) == 2

    def test_hex4_encoding_40c(self):
        """40°C → hex4 → "2800" (4-char with trailing 00)"""
        t = 40
        encoded = hex(t)[2:].upper().zfill(2) + "00"
        assert encoded == "2800"
        assert len(encoded) == 4

    def test_hex2_min_max_boiler_water(self):
        """Boiler water heater range 35-65°C → hex2"""
        assert hex(35)[2:].upper().zfill(2) == "23"
        assert hex(65)[2:].upper().zfill(2) == "41"

    def test_hex2_min_max_boiler_heating(self):
        """Boiler heating range 35-85°C → hex2"""
        assert hex(35)[2:].upper().zfill(2) == "23"
        assert hex(85)[2:].upper().zfill(2) == "55"


# ═════════════════════════════════════════════════════════════════════════════
# 5. Entity platform completeness
# ═════════════════════════════════════════════════════════════════════════════

class TestEntityPlatforms:
    """Each device family must declare the correct set of entity platforms."""

    @pytest.mark.parametrize("device_type", BOILER_TYPES)
    def test_boiler_has_all_platforms(self, device_type):
        d = load(device_type)
        entities = d["entities"]
        for p in ("water_heater", "climate", "sensor", "switch", "select", "text"):
            assert p in entities, f"{device_type}: missing platform '{p}'"

    @pytest.mark.parametrize("device_type", E_SERIES_TYPES)
    def test_e_series_has_water_heater_and_sensor(self, device_type):
        d = load(device_type)
        for p in ("water_heater", "sensor"):
            assert p in d["entities"], f"{device_type}: missing platform '{p}'"

    @pytest.mark.parametrize("device_type", E_SERIES_TYPES)
    def test_e_series_no_climate(self, device_type):
        d = load(device_type)
        assert "climate" not in d["entities"], \
            f"{device_type}: E-series should NOT have climate platform"

    @pytest.mark.parametrize("device_type", E_MASSAGE)
    def test_e_massage_has_massage_switch(self, device_type):
        d = load(device_type)
        switches = d["entities"].get("switch", [])
        keys = [s["key"] for s in switches]
        assert "massage_mode" in keys, \
            f"{device_type}: missing massage_mode switch"

    @pytest.mark.parametrize("device_type", E_CYCLE)
    def test_e_cycle_has_cycle_insulation_switch(self, device_type):
        d = load(device_type)
        switches = d["entities"].get("switch", [])
        keys = [s["key"] for s in switches]
        assert "cycle_insulation" in keys, \
            f"{device_type}: missing cycle_insulation switch"

    @pytest.mark.parametrize("device_type", E_THICK_THIN)
    def test_e_thick_thin_has_operation_mode_select(self, device_type):
        """E65/E75 must have a select for 浓薄水 (thick/thin water) mode."""
        d = load(device_type)
        selects = d["entities"].get("select", [])
        keys = [s["key"] for s in selects]
        assert "operation_mode" in keys, \
            f"{device_type}: missing operation_mode select (thick/thin water)"

    def test_e89_min_temp_is_32(self):
        """E89 (bath injection) has higher minimum temperature."""
        d = load("02720022")
        wh = d["entities"]["water_heater"][0]
        assert wh["min_temp"] == 32, "E89 water_heater min_temp should be 32°C"

    def test_softener_has_force_regen_switch(self):
        d = load("0F070006")
        switches = d["entities"].get("switch", [])
        keys = [s["key"] for s in switches]
        assert "force_regen" in keys, "0F070006: missing force_regen switch"

    def test_softener_has_required_sensors(self):
        d = load("0F070006")
        sensors = d["entities"].get("sensor", [])
        keys = [s["key"] for s in sensors]
        for expected in ("salt_level", "water_hardness", "fault_code"):
            assert expected in keys, f"0F070006: missing sensor '{expected}'"

    def test_rtc626_has_power_switch_and_number(self):
        d = load("0F090004")
        assert "switch" in d["entities"]
        assert "number" in d["entities"]
        num_keys = [n["key"] for n in d["entities"]["number"]]
        assert "room_temp_setpoint" in num_keys

    def test_heatpump_has_three_number_entities(self):
        d = load("0F090011")
        numbers = d["entities"].get("number", [])
        assert len(numbers) == 3, \
            f"0F090011: expected 3 number entities, got {len(numbers)}"
        keys = {n["key"] for n in numbers}
        assert keys == {
            "room_temp_setpoint",
            "hp_unit_cold_temp_setpoint",
            "hp_unit_hot_temp_setpoint",
        }

    def test_heatpump_has_mode_select(self):
        d = load("0F090011")
        selects = d["entities"].get("select", [])
        keys = [s["key"] for s in selects]
        assert "hp_unit_operation_mode" in keys, "0F090011: missing hp_unit_operation_mode select"


# ═════════════════════════════════════════════════════════════════════════════
# 6. Climate transitions completeness (boilers)
# ═════════════════════════════════════════════════════════════════════════════

class TestClimateTransitions:
    """All N×(N-1) mode transitions must be defined for boiler climate entities."""

    @pytest.mark.parametrize("device_type", BOILER_TYPES)
    def test_all_transitions_present(self, device_type):
        d = load(device_type)
        climate = d["entities"]["climate"][0]
        transitions = climate["transitions"]
        mode_keys = [m for m in climate["modes"] if m != "standby"]
        all_modes = ["standby"] + mode_keys

        missing = []
        for src in all_modes:
            for dst in all_modes:
                if src != dst:
                    key = f"{src}_to_{dst}"
                    if key not in transitions:
                        missing.append(key)

        assert not missing, \
            f"{device_type}: missing transitions: {missing}"

    @pytest.mark.parametrize("device_type", BOILER_TYPES)
    def test_standby_to_normal_uses_summer_winter(self, device_type):
        """Turning on heating always starts with summerWinter command."""
        d = load(device_type)
        climate = d["entities"]["climate"][0]
        steps = climate["transitions"]["standby_to_normal"]
        cmds = [s["cmd"] for s in steps]
        assert "summerWinter" in cmds, \
            f"{device_type}: standby_to_normal must include summerWinter command"

    @pytest.mark.parametrize("device_type", BOILER_TYPES)
    def test_any_to_standby_uses_summer_winter(self, device_type):
        """All →standby transitions use summerWinter (toggle off)."""
        d = load(device_type)
        climate = d["entities"]["climate"][0]
        for src in ("normal", "energy_saving", "outdoor", "rapid"):
            key = f"{src}_to_standby"
            steps = climate["transitions"][key]
            cmds = [s["cmd"] for s in steps]
            assert "summerWinter" in cmds, \
                f"{device_type}: {key} must include summerWinter command"

    @pytest.mark.parametrize("device_type", BOILER_TYPES)
    def test_mode_codes_cover_all_modes(self, device_type):
        """mode_codes must include entries for all 5 modes."""
        d = load(device_type)
        climate = d["entities"]["climate"][0]
        mode_codes = climate["mode_codes"]
        for mode in CLIMATE_MODES:
            assert mode in mode_codes, \
                f"{device_type}: mode_codes missing '{mode}'"
            assert len(mode_codes[mode]) > 0, \
                f"{device_type}: mode_codes['{mode}'] is empty"

    @pytest.mark.parametrize("device_type", BOILER_TYPES)
    def test_temp_settings_for_normal_and_energy_saving(self, device_type):
        """normal and energy_saving modes must have read/write temp settings."""
        d = load(device_type)
        climate = d["entities"]["climate"][0]
        ts = climate["temp_settings"]
        for mode in ("normal", "energy_saving"):
            assert mode in ts, f"{device_type}: temp_settings missing '{mode}'"
            assert "read" in ts[mode], \
                f"{device_type}: temp_settings['{mode}'] missing 'read'"
            assert "write" in ts[mode], \
                f"{device_type}: temp_settings['{mode}'] missing 'write'"

    @pytest.mark.parametrize("device_type", BOILER_TYPES)
    def test_outdoor_and_rapid_have_fixed_temps(self, device_type):
        """outdoor and rapid modes have fixed temperatures (no adjustable setpoint)."""
        d = load(device_type)
        climate = d["entities"]["climate"][0]
        ts = climate["temp_settings"]
        for mode in ("outdoor", "rapid"):
            assert "fixed" in ts.get(mode, {}), \
                f"{device_type}: temp_settings['{mode}'] should have 'fixed' temp"


# ═════════════════════════════════════════════════════════════════════════════
# 7. process_data pipeline integration (end-to-end state simulation)
# ═════════════════════════════════════════════════════════════════════════════

class TestEndToEndStatePipeline:
    """Simulate a full MQTT inf/ payload going through process_data."""

    def test_g56_full_inf_payload(self):
        """G56: full device state MQTT payload → correct processed values."""
        d = load("0F06000C")
        raw = {
            "hotWaterTempSetting":   "2A",   # 42°C
            "heatingTempSettingNM":  "38",   # 56°C
            "heatingTempSettingHES": "37",   # 55°C
            "operationMode":         "3",    # normal heating
            "burningState":          "30",   # standby
        }
        result = process_data(raw, d["processors"])
        assert result["hotWaterTempSetting"]   == 42
        assert result["heatingTempSettingNM"]  == 56
        assert result["heatingTempSettingHES"] == 55
        assert result["operationMode"]         == "3"   # not in processors, unchanged

    def test_g56_energy_stg_payload(self):
        """G56: stg/ energy push → gas m³ and time in days."""
        d = load("0F06000C")
        # energy data extracted from egy[] array by _process_energy_data
        raw = {
            "gasUsed":                "00002710",  # 10000 dec → 1.0 m³
            "supplyTime":             "A87",        # 2695 dec hours → ~112.3 d
            "totalPowerSupplyTime":   "A87",        # same
            "totalHeatingBurningTime":"7E6",        # 2022 dec hours (no divide)
            "heatingBurningTimes":    "71",         # 113 dec
        }
        result = process_data(raw, d["processors"])
        assert result["gasUsed"] == pytest.approx(1.0)
        assert result["supplyTime"] == pytest.approx(2695 / 24, rel=1e-4)
        assert result["totalPowerSupplyTime"] == pytest.approx(2695 / 24, rel=1e-4)
        assert result["totalHeatingBurningTime"] == 2022  # unchanged, hours
        assert result["heatingBurningTimes"] == 113       # no multiply, raw count

    def test_e86_full_inf_payload(self):
        """E86: water heater temp with hex4_to_int ("2A00" → 42°C)."""
        d = load("02720E86")
        raw = {
            "hotWaterTempSetting": "2A00",   # 42°C in hex4 format
            "gasConsumption":      "00004E20",  # 20000 dec → 2.0 m³
            "burningState":        "30",
        }
        result = process_data(raw, d["processors"])
        assert result["hotWaterTempSetting"] == 42
        assert result["gasConsumption"] == pytest.approx(2.0)

    def test_rtc626_payload(self):
        """RTC-626: room temperature and setpoint processing."""
        d = load("0F090004")
        raw = {
            "roomTemperature":  "15",  # 21°C
            "roomTempSetting":  "16",  # 22°C
        }
        result = process_data(raw, d["processors"])
        assert result["roomTemperature"] == 21
        assert result["roomTempSetting"]  == 22

    def test_heatpump_payload(self):
        """Heat pump: all three temperature setpoints processed correctly."""
        d = load("0F090011")
        raw = {
            "roomTempSetting":      "16",  # 22°C
            "hpUnitColdTempSetting": "1A", # 26°C
            "hpUnitHotTempSetting":  "1E", # 30°C
        }
        result = process_data(raw, d["processors"])
        assert result["roomTempSetting"]       == 22
        assert result["hpUnitColdTempSetting"] == 26
        assert result["hpUnitHotTempSetting"]  == 30


# ═════════════════════════════════════════════════════════════════════════════
# 8. Water heater temperature range validation
# ═════════════════════════════════════════════════════════════════════════════

class TestWaterHeaterTempRanges:

    EXPECTED_RANGES = {
        "0F06000C": (35, 65),  # G56 boiler DHW
        "0F060016": (35, 65),
        "0F060G55": (35, 65),
        "02720E86": (35, 65),  # E86
        "0272000E": (35, 65),  # E88
        "02720022": (32, 65),  # E89 – bath injection, higher minimum
        "02720010": (35, 65),  # E65
        "0272001C": (35, 65),  # E75
        "02720E76": (35, 65),  # E76
        "02720E66": (35, 65),  # E66
        "0272000D": (35, 60),  # E51 basic
    }

    @pytest.mark.parametrize("device_type,expected", EXPECTED_RANGES.items())
    def test_water_heater_temp_range(self, device_type, expected):
        d = load(device_type)
        wh = d["entities"]["water_heater"][0]
        assert wh["min_temp"] == expected[0], \
            f"{device_type}: min_temp {wh['min_temp']} != {expected[0]}"
        assert wh["max_temp"] == expected[1], \
            f"{device_type}: max_temp {wh['max_temp']} != {expected[1]}"
