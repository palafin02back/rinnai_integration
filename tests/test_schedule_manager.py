"""Tests for the schedule manager module."""
import pytest
import sys
import os

# Add core module to path for direct imports
core_path = os.path.join(os.path.dirname(__file__), '..', 'custom_components', 'rinnai', 'core')
sys.path.insert(0, core_path)

# Import util first to make it available as a module
import util  # noqa: F401

# Now we can import schedule_manager which does "from .util import ..."
# But since we patched sys.path, we need to mock the relative import
# Let's use importlib to handle this properly
import importlib.util
spec = importlib.util.spec_from_file_location(
    "schedule_manager", 
    os.path.join(core_path, "schedule_manager.py"),
    submodule_search_locations=[core_path]
)
schedule_manager_module = importlib.util.module_from_spec(spec)
sys.modules['schedule_manager'] = schedule_manager_module

# Patch the relative import before loading
import types
fake_core = types.ModuleType('custom_components.rinnai.core')
fake_core.util = util
sys.modules['custom_components'] = types.ModuleType('custom_components')
sys.modules['custom_components.rinnai'] = types.ModuleType('custom_components.rinnai')
sys.modules['custom_components.rinnai.core'] = fake_core
sys.modules['custom_components.rinnai.core.util'] = util

# Now load the module
spec.loader.exec_module(schedule_manager_module)

RinnaiScheduleManager = schedule_manager_module.RinnaiScheduleManager


@pytest.fixture
def schedule_manager():
    """Create a schedule manager with default config."""
    config = {
        "total_length": 34,
        "status_byte_index": 0,
        "mode_byte_index": 1,
        "data_start_byte_index": 2,
        "bytes_per_mode": 3,
        "mode_count": 5,
    }
    return RinnaiScheduleManager(config)


@pytest.fixture
def valid_hex():
    """Valid schedule hex string."""
    # ON (01), Mode 3 (03), then 5 modes * 3 bytes each = 15 bytes of schedule data
    return "0103DB446CDB006E4818C680017F80017F"


class TestScheduleManagerValidation:
    """Tests for hex validation."""

    def test_validate_valid_hex(self, schedule_manager, valid_hex):
        """Test validating valid hex string."""
        assert schedule_manager.validate_hex(valid_hex) is True

    def test_validate_short_hex(self, schedule_manager):
        """Test validating too short hex string."""
        assert schedule_manager.validate_hex("0103") is False

    def test_validate_none(self, schedule_manager):
        """Test validating None."""
        assert schedule_manager.validate_hex(None) is False

    def test_validate_empty(self, schedule_manager):
        """Test validating empty string."""
        assert schedule_manager.validate_hex("") is False


class TestScheduleManagerParseStatus:
    """Tests for parsing status."""

    def test_parse_status_on(self, schedule_manager):
        """Test parsing ON status."""
        hex_str = "0103DB446CDB006E4818C680017F80017F"  # 01 = ON
        assert schedule_manager.parse_status(hex_str) is True

    def test_parse_status_off(self, schedule_manager):
        """Test parsing OFF status."""
        hex_str = "0003DB446CDB006E4818C680017F80017F"  # 00 = OFF
        assert schedule_manager.parse_status(hex_str) is False

    def test_parse_status_invalid(self, schedule_manager):
        """Test parsing invalid hex returns False."""
        assert schedule_manager.parse_status("01") is False


class TestScheduleManagerParseModeIndex:
    """Tests for parsing mode index."""

    def test_parse_mode_index_1(self, schedule_manager):
        """Test parsing mode index 1."""
        hex_str = "0101DB446CDB006E4818C680017F80017F"
        assert schedule_manager.parse_mode_index(hex_str) == 1

    def test_parse_mode_index_3(self, schedule_manager):
        """Test parsing mode index 3."""
        hex_str = "0103DB446CDB006E4818C680017F80017F"
        assert schedule_manager.parse_mode_index(hex_str) == 3

    def test_parse_mode_index_5(self, schedule_manager):
        """Test parsing mode index 5."""
        hex_str = "0105DB446CDB006E4818C680017F80017F"
        assert schedule_manager.parse_mode_index(hex_str) == 5

    def test_parse_mode_index_invalid(self, schedule_manager):
        """Test parsing invalid hex returns None."""
        assert schedule_manager.parse_mode_index("01") is None


class TestScheduleManagerUpdateStatus:
    """Tests for updating status."""

    def test_update_status_to_on(self, schedule_manager):
        """Test updating status to ON."""
        hex_str = "0003DB446CDB006E4818C680017F80017F"  # OFF
        result = schedule_manager.update_status(hex_str, True)
        assert result.startswith("01")  # Now ON

    def test_update_status_to_off(self, schedule_manager):
        """Test updating status to OFF."""
        hex_str = "0103DB446CDB006E4818C680017F80017F"  # ON
        result = schedule_manager.update_status(hex_str, False)
        assert result.startswith("00")  # Now OFF

    def test_update_status_preserves_data(self, schedule_manager):
        """Test updating status preserves other data."""
        hex_str = "0003DB446CDB006E4818C680017F80017F"
        result = schedule_manager.update_status(hex_str, True)
        # Only first 2 chars should change
        assert result[2:] == hex_str[2:]

    def test_update_status_invalid(self, schedule_manager):
        """Test updating invalid hex returns None."""
        assert schedule_manager.update_status("01", True) is None


class TestScheduleManagerUpdateModeIndex:
    """Tests for updating mode index."""

    def test_update_mode_index_to_1(self, schedule_manager):
        """Test updating mode index to 1."""
        hex_str = "0103DB446CDB006E4818C680017F80017F"
        result = schedule_manager.update_mode_index(hex_str, 1)
        assert result[2:4] == "01"

    def test_update_mode_index_to_5(self, schedule_manager):
        """Test updating mode index to 5."""
        hex_str = "0101DB446CDB006E4818C680017F80017F"
        result = schedule_manager.update_mode_index(hex_str, 5)
        assert result[2:4] == "05"

    def test_update_mode_index_preserves_data(self, schedule_manager):
        """Test updating mode index preserves other data."""
        hex_str = "0103DB446CDB006E4818C680017F80017F"
        result = schedule_manager.update_mode_index(hex_str, 5)
        # Status and schedule data should be unchanged
        assert result[0:2] == hex_str[0:2]
        assert result[4:] == hex_str[4:]

    def test_update_mode_index_invalid(self, schedule_manager):
        """Test updating invalid hex returns None."""
        assert schedule_manager.update_mode_index("01", 1) is None


class TestScheduleManagerParseSchedule:
    """Tests for parsing schedule data."""

    def test_parse_schedule_mode_1(self, schedule_manager, valid_hex):
        """Test parsing schedule for mode 1."""
        result = schedule_manager.parse_schedule(valid_hex, 1)
        # Should return a formatted schedule string
        assert result is not None
        assert isinstance(result, str)

    def test_parse_schedule_mode_invalid_low(self, schedule_manager, valid_hex):
        """Test parsing schedule with mode 0 returns None."""
        assert schedule_manager.parse_schedule(valid_hex, 0) is None

    def test_parse_schedule_mode_invalid_high(self, schedule_manager, valid_hex):
        """Test parsing schedule with mode > mode_count returns None."""
        assert schedule_manager.parse_schedule(valid_hex, 6) is None

    def test_parse_schedule_invalid_hex(self, schedule_manager):
        """Test parsing schedule with invalid hex returns None."""
        assert schedule_manager.parse_schedule("01", 1) is None


class TestScheduleManagerUpdateScheduleData:
    """Tests for updating schedule data."""

    def test_update_schedule_data_mode_1(self, schedule_manager, valid_hex):
        """Test updating schedule for mode 1."""
        result = schedule_manager.update_schedule_data(valid_hex, 1, "00:00-06:00")
        assert result is not None
        assert len(result) == len(valid_hex)

    def test_update_schedule_data_preserves_other_modes(self, schedule_manager, valid_hex):
        """Test updating one mode preserves others."""
        result = schedule_manager.update_schedule_data(valid_hex, 1, "00:00-06:00")
        # Mode 2-5 data should be the same
        # Mode 1 ends at char 10 (bytes 2-4), Mode 2 starts at char 10
        # We check mode 3-5 which are definitely unchanged
        mode_3_start = 4 + (2 * 3 * 2)  # status + mode + 2 modes * 3 bytes * 2 chars
        assert result[mode_3_start:] == valid_hex[mode_3_start:]

    def test_update_schedule_data_invalid_mode(self, schedule_manager, valid_hex):
        """Test updating invalid mode returns None."""
        assert schedule_manager.update_schedule_data(valid_hex, 0, "00:00-06:00") is None
        assert schedule_manager.update_schedule_data(valid_hex, 6, "00:00-06:00") is None

    def test_update_schedule_data_invalid_hex(self, schedule_manager):
        """Test updating invalid hex returns None."""
        assert schedule_manager.update_schedule_data("01", 1, "00:00-06:00") is None


class TestScheduleManagerRoundTrip:
    """Integration tests for parse/update cycle."""

    def test_status_round_trip(self, schedule_manager, valid_hex):
        """Test status can be toggled and read back."""
        # Start ON
        assert schedule_manager.parse_status(valid_hex) is True
        
        # Turn OFF
        off_hex = schedule_manager.update_status(valid_hex, False)
        assert schedule_manager.parse_status(off_hex) is False
        
        # Turn back ON
        on_hex = schedule_manager.update_status(off_hex, True)
        assert schedule_manager.parse_status(on_hex) is True

    def test_mode_index_round_trip(self, schedule_manager, valid_hex):
        """Test mode index can be changed and read back."""
        original_mode = schedule_manager.parse_mode_index(valid_hex)
        
        # Change to different mode
        new_mode = 5 if original_mode != 5 else 1
        updated_hex = schedule_manager.update_mode_index(valid_hex, new_mode)
        
        # Read back
        assert schedule_manager.parse_mode_index(updated_hex) == new_mode
