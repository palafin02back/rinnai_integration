"""Schedule manager for Rinnai integration."""
from __future__ import annotations

import logging
from typing import Any

from .util import decode_schedule_bitmap, format_schedule_string, parse_schedule_string

_LOGGER = logging.getLogger(__name__)


class RinnaiScheduleManager:
    """Manager for handling Rinnai schedule data."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the schedule manager."""
        self.total_length = config.get("total_length", 34)
        self.status_byte_index = config.get("status_byte_index", 0)
        self.mode_byte_index = config.get("mode_byte_index", 1)
        self.data_start_byte_index = config.get("data_start_byte_index", 2)
        self.bytes_per_mode = config.get("bytes_per_mode", 3)
        self.mode_count = config.get("mode_count", 5)

    def validate_hex(self, hex_str: str | None) -> bool:
        """Validate hex string length."""
        if not hex_str or len(hex_str) < self.total_length:
            return False
        return True

    def parse_status(self, hex_str: str) -> bool:
        """Parse status (on/off) from hex string."""
        if not self.validate_hex(hex_str):
            return False
        try:
            # Each byte is 2 chars
            start = self.status_byte_index * 2
            byte_val = int(hex_str[start : start + 2], 16)
            return byte_val == 1
        except ValueError:
            return False

    def parse_mode_index(self, hex_str: str) -> int | None:
        """Parse current mode index from hex string."""
        if not self.validate_hex(hex_str):
            return None
        try:
            start = self.mode_byte_index * 2
            return int(hex_str[start : start + 2], 16)
        except ValueError:
            return None

    def parse_schedule(self, hex_str: str, mode_index: int) -> str | None:
        """Parse schedule string for a specific mode index (1-based)."""
        if not self.validate_hex(hex_str):
            return None
        
        if mode_index < 1 or mode_index > self.mode_count:
            return None

        try:
            # Calculate start position for this mode
            # data_start is in bytes, so * 2 for chars
            # bytes_per_mode is in bytes, so * 2 for chars
            # mode_index is 1-based, so -1
            start_byte = self.data_start_byte_index + (mode_index - 1) * self.bytes_per_mode
            start_char = start_byte * 2
            length_char = self.bytes_per_mode * 2
            
            mode_hex = hex_str[start_char : start_char + length_char]
            active_hours = decode_schedule_bitmap(mode_hex)
            return format_schedule_string(active_hours)
        except ValueError:
            return None

    def update_status(self, hex_str: str, is_on: bool) -> str | None:
        """Update status in hex string."""
        if not self.validate_hex(hex_str):
            return None

        try:
            start = self.status_byte_index * 2
            new_byte = "01" if is_on else "00"
            return hex_str[:start] + new_byte + hex_str[start + 2 :]
        except ValueError:
            return None

    def update_mode_index(self, hex_str: str, mode_index: int) -> str | None:
        """Update mode index in hex string."""
        if not self.validate_hex(hex_str):
            return None

        try:
            start = self.mode_byte_index * 2
            new_byte = f"{mode_index:02X}"
            return hex_str[:start] + new_byte + hex_str[start + 2 :]
        except ValueError:
            return None

    def update_schedule_data(self, hex_str: str, mode_index: int, schedule_str: str) -> str | None:
        """Update schedule data for a specific mode."""
        if not self.validate_hex(hex_str):
            return None

        if mode_index < 1 or mode_index > self.mode_count:
            return None

        try:
            new_mode_hex = parse_schedule_string(schedule_str)
            
            start_byte = self.data_start_byte_index + (mode_index - 1) * self.bytes_per_mode
            start_char = start_byte * 2
            length_char = self.bytes_per_mode * 2
            
            return hex_str[:start_char] + new_mode_hex + hex_str[start_char + length_char :]
        except ValueError:
            return None
