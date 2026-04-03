"""Tests for the data processor module."""
import pytest
import sys
import os

# Add custom_components to path for direct imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom_components', 'rinnai', 'core'))

from processor import (
    hex_to_int,
    hex4_to_int,
    multiply,
    divide,
    to_type,
    process_value,
    process_data,
)


class TestHexToInt:
    """Tests for hex_to_int function."""

    def test_hex_string_conversion(self):
        """Test converting hex string to int."""
        assert hex_to_int("28") == 40
        assert hex_to_int("37") == 55
        assert hex_to_int("FF") == 255
        assert hex_to_int("ff") == 255
        assert hex_to_int("00002710") == 10000

    def test_already_int(self):
        """Test passing int returns same value."""
        assert hex_to_int(40) == 40
        assert hex_to_int(0) == 0
        assert hex_to_int(255) == 255

    def test_empty_string(self):
        """Test empty string returns 0."""
        assert hex_to_int("") == 0

    def test_invalid_hex(self):
        """Test invalid hex returns 0."""
        assert hex_to_int("xyz") == 0
        assert hex_to_int("GG") == 0

    def test_none_value(self):
        """Test None returns 0."""
        assert hex_to_int(None) == 0


class TestHex4ToInt:
    """Tests for hex4_to_int function (E-series 4-byte hex temp encoding)."""

    def test_normal_conversion(self):
        """Standard hex4 values: last 2 chars are always '00'."""
        assert hex4_to_int("2800") == 40
        assert hex4_to_int("2A00") == 42
        assert hex4_to_int("0F00") == 15
        assert hex4_to_int("3C00") == 60

    def test_already_int(self):
        assert hex4_to_int(40) == 40

    def test_short_input_returns_zero(self):
        """Inputs shorter than 4 chars are invalid hex4 and should return 0."""
        assert hex4_to_int("2A") == 0
        assert hex4_to_int("28") == 0
        assert hex4_to_int("") == 0

    def test_none_returns_zero(self):
        assert hex4_to_int(None) == 0

    def test_invalid_hex_returns_zero(self):
        assert hex4_to_int("XXXX") == 0


class TestMultiply:
    """Tests for multiply function."""

    def test_integer_multiplication(self):
        """Test integer multiplication."""
        assert multiply(10, 5) == 50
        assert multiply(100, 2) == 200

    def test_float_multiplication(self):
        """Test float multiplication."""
        assert multiply(10.5, 2) == 21.0
        assert multiply(5, 0.5) == 2.5

    def test_string_number(self):
        """Test string number multiplication."""
        assert multiply("10", 5) == 50

    def test_zero_multiplication(self):
        """Test zero multiplication."""
        assert multiply(100, 0) == 0

    def test_invalid_value(self):
        """Test invalid value returns 0."""
        assert multiply("abc", 5) == 0


class TestDivide:
    """Tests for divide function."""

    def test_integer_division(self):
        """Test integer division."""
        assert divide(100, 10) == 10.0
        assert divide(50, 2) == 25.0

    def test_float_division(self):
        """Test float division."""
        assert divide(10, 4) == 2.5

    def test_string_number(self):
        """Test string number division."""
        assert divide("100", 10) == 10.0

    def test_divide_by_zero(self):
        """Test division by zero returns 0."""
        assert divide(100, 0) == 0.0

    def test_invalid_value(self):
        """Test invalid value returns 0."""
        assert divide("abc", 5) == 0.0


class TestToType:
    """Tests for to_type function."""

    def test_to_int(self):
        """Test converting to int."""
        assert to_type("42", "int") == 42
        assert to_type(42.7, "int") == 42

    def test_to_float(self):
        """Test converting to float."""
        assert to_type("42.5", "float") == 42.5
        assert to_type(42, "float") == 42.0

    def test_to_str(self):
        """Test converting to str."""
        assert to_type(42, "str") == "42"
        assert to_type(42.5, "str") == "42.5"

    def test_invalid_conversion(self):
        """Test invalid conversion returns original value."""
        assert to_type("abc", "int") == "abc"


class TestProcessValue:
    """Tests for process_value function."""

    def test_single_processor_string(self):
        """Test single processor as string."""
        result = process_value("28", ["hex_to_int"])
        assert result == 40

    def test_processor_with_args(self):
        """Test processor with arguments."""
        result = process_value(100, [{"func": "divide", "args": [10]}])
        assert result == 10.0

    def test_chained_processors(self):
        """Test chaining multiple processors."""
        # Convert hex -> divide by 10000
        result = process_value("00002710", [
            "hex_to_int",
            {"func": "divide", "args": [10000]}
        ])
        assert result == 1.0

    def test_empty_processor_list(self):
        """Test empty processor list returns original value."""
        result = process_value("test", [])
        assert result == "test"


class TestProcessData:
    """Tests for process_data function."""

    def test_basic_processing(self):
        """Test basic data processing."""
        raw_data = {
            "hotWaterTempSetting": "28",
            "gasConsumption": "00002710",
        }
        processors = {
            "hotWaterTempSetting": ["hex_to_int"],
            "gasConsumption": [
                "hex_to_int",
                {"func": "divide", "args": [10000]}
            ],
        }
        
        result = process_data(raw_data, processors)
        
        assert result["hotWaterTempSetting"] == 40
        assert result["gasConsumption"] == 1.0

    def test_unprocessed_fields_copied(self):
        """Test fields without processors are copied."""
        raw_data = {
            "temp": "28",
            "status": "on",
        }
        processors = {
            "temp": ["hex_to_int"],
        }
        
        result = process_data(raw_data, processors)
        
        assert result["temp"] == 40
        assert result["status"] == "on"

    def test_missing_field_ignored(self):
        """Test processors for missing fields are ignored."""
        raw_data = {"temp": "28"}
        processors = {
            "temp": ["hex_to_int"],
            "nonexistent": ["hex_to_int"],
        }
        
        result = process_data(raw_data, processors)
        
        assert result["temp"] == 40
        assert "nonexistent" not in result
