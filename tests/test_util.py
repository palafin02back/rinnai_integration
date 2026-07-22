"""Tests for schedule string parsing utilities."""
import os
import sys

import pytest

core_path = os.path.join(
    os.path.dirname(__file__), "..", "custom_components", "rinnai", "core"
)
sys.path.insert(0, core_path)

from util import (  # noqa: E402
    decode_schedule_bitmap,
    format_schedule_string,
    parse_schedule_string,
)


class TestParseScheduleString:
    def test_single_range(self):
        # Hours 6, 7 → byte0 bits 6-7
        assert parse_schedule_string("6-8") == "C00000"

    def test_comma_separated_ranges(self):
        # 6,7 → b0=C0; 18,19,20 → b2 bits 2-4 = 1C
        assert parse_schedule_string("06:00-08:00, 18:00-21:00") == "C0001C"

    def test_slash_separated_ranges(self):
        """The E32 config documents "/" as the range separator."""
        assert parse_schedule_string("06:00-08:00/18:00-21:00") == "C0001C"

    def test_single_hour(self):
        assert parse_schedule_string("6") == "400000"

    def test_off_keywords(self):
        assert parse_schedule_string("off") == "000000"
        assert parse_schedule_string("") == "000000"
        assert parse_schedule_string("none") == "000000"

    def test_all_keyword(self):
        assert parse_schedule_string("all") == "FFFFFF"

    def test_garbage_raises_instead_of_wiping(self):
        """Unparseable input must not silently clear the schedule."""
        with pytest.raises(ValueError):
            parse_schedule_string("garbage")

    def test_hour_out_of_range_raises(self):
        with pytest.raises(ValueError):
            parse_schedule_string("25")

    def test_malformed_range_raises(self):
        with pytest.raises(ValueError):
            parse_schedule_string("06:00-08:00-10:00")

    @pytest.mark.parametrize("schedule", ["8-6", "24-25", "6-6", ",", "/"])
    def test_invalid_or_empty_range_raises(self, schedule):
        """Invalid ranges and separator-only input must not clear a schedule."""
        with pytest.raises(ValueError):
            parse_schedule_string(schedule)

    def test_partially_valid_input_keeps_valid_parts(self):
        # One valid range plus one invalid part → valid part is used
        assert parse_schedule_string("6-8, garbage") == "C00000"

    def test_round_trip_through_bitmap(self):
        hex_str = parse_schedule_string("06:00-08:00/18:00-21:00")
        hours = decode_schedule_bitmap(hex_str)
        assert hours == [6, 7, 18, 19, 20]
        assert format_schedule_string(hours) == "06:00-08:00, 18:00-21:00"
