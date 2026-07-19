"""Utility functions for Rinnai integration."""
from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

def decode_schedule_bitmap(hex_str: str) -> list[int]:
    """Decode a 6-char hex string (3 bytes) into a list of active hours (0-23).
    
    Format: LSB First.
    Byte 0: 00:00 - 07:00 (Bit 0 = 00:00)
    Byte 1: 08:00 - 15:00 (Bit 0 = 08:00)
    Byte 2: 16:00 - 23:00 (Bit 0 = 16:00)
    """
    if len(hex_str) != 6:
        return []
        
    try:
        # Parse bytes
        b0 = int(hex_str[0:2], 16)
        b1 = int(hex_str[2:4], 16)
        b2 = int(hex_str[4:6], 16)
        
        active_hours = []
        
        # Byte 0 (0-7)
        for i in range(8):
            if (b0 >> i) & 1:
                active_hours.append(i)
                
        # Byte 1 (8-15)
        for i in range(8):
            if (b1 >> i) & 1:
                active_hours.append(i + 8)
                
        # Byte 2 (16-23)
        for i in range(8):
            if (b2 >> i) & 1:
                active_hours.append(i + 16)
                
        return active_hours
    except ValueError:
        return []

def format_schedule_string(active_hours: list[int]) -> str:
    """Format a list of active hours into a readable string range.
    
    Example: [6, 7, 18, 19, 20] -> "06:00-08:00, 18:00-21:00"
    Note: The end time is exclusive in the range string for readability (e.g. 6-7 is 06:00-07:00 active).
    Wait, usually "06:00-08:00" means 6 and 7 are active.
    """
    if not active_hours:
        return "Off"
        
    active_hours = sorted(list(set(active_hours)))
    ranges = []
    
    if not active_hours:
        return "Off"
        
    start = active_hours[0]
    prev = active_hours[0]
    
    for h in active_hours[1:]:
        if h == prev + 1:
            prev = h
        else:
            # End of a range
            # Range is start to prev. Display as start:00 - (prev+1):00
            ranges.append(f"{start:02d}:00-{prev+1:02d}:00")
            start = h
            prev = h
            
    # Add last range
    ranges.append(f"{start:02d}:00-{prev+1:02d}:00")
    
    return ", ".join(ranges)

def parse_schedule_string(schedule_str: str) -> str:
    """Parse a schedule string into a 6-char hex string.
    
    Supported formats:
    - "6-8" (means 6, 7 active)
    - "6" (means 6 active)
    - "6-8, 18-21"
    - "all"
    - "off"
    """
    schedule_str = schedule_str.lower().strip()
    if schedule_str in ["off", "none", ""]:
        return "000000"
    if schedule_str == "all":
        return "FFFFFF"
        
    active_hours = set()
    parts = schedule_str.split(",")
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
            
        if "-" in part:
            try:
                start_s, end_s = part.split("-")
                # Handle "06:00" format if user types it
                start = int(start_s.split(":")[0])
                end = int(end_s.split(":")[0])
                
                # Range is inclusive of start, exclusive of end? 
                # User input "6-8" usually means 6, 7. 
                # If user inputs "06:00-08:00", they expect 2 hours.
                # So range(start, end)
                
                # Boundary check
                start = max(0, min(23, start))
                end = max(0, min(24, end))
                
                for h in range(start, end):
                    active_hours.add(h)
            except ValueError:
                _LOGGER.warning("Invalid range format: %s", part)
        else:
            try:
                h = int(part.split(":")[0])
                if 0 <= h <= 23:
                    active_hours.add(h)
            except ValueError:
                _LOGGER.warning("Invalid hour format: %s", part)
                
    # Encode to hex
    b0 = 0
    b1 = 0
    b2 = 0
    
    for h in active_hours:
        if 0 <= h <= 7:
            b0 |= (1 << h)
        elif 8 <= h <= 15:
            b1 |= (1 << (h - 8))
        elif 16 <= h <= 23:
            b2 |= (1 << (h - 16))
            
    return f"{b0:02X}{b1:02X}{b2:02X}"
