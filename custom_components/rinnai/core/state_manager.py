"""State manager for Rinnai devices."""

from __future__ import annotations

import logging
import time
DEFAULT_DESIRED_STATE_TIMEOUT = 10.0  # Seconds


class RinnaiStateManager:
    """Manages the state reconciliation between remote (MQTT) and desired (User) states."""

    def __init__(self, timeout: float = DEFAULT_DESIRED_STATE_TIMEOUT) -> None:
        """Initialize the state manager."""
        self._remote_state: dict[str, Any] = {}
        # _desired_state: key -> (value, timestamp)
        self._desired_state: dict[str, tuple[Any, float]] = {}
        self._timeout = timeout

    def update_remote(self, data: dict[str, Any]) -> None:
        """Update the remote state from MQTT/API."""
        current_time = time.time()
        
        for key, value in data.items():
            self._remote_state[key] = value
            
            # Check if this update matches our desired state
            if key in self._desired_state:
                desired_value, timestamp = self._desired_state[key]
                
                # If value matches, we are synced. Remove desired state.
                # We convert to string for comparison to handle type mismatches (e.g. "31" vs 31)
                if str(value) == str(desired_value):
                    _LOGGER.debug("State synced for %s: %s", key, value)
                    del self._desired_state[key]
                # If timeout expired, we also remove desired state (give up)
                elif current_time - timestamp > self._timeout:
                    _LOGGER.debug("Desired state timeout for %s. Reverting to remote: %s", key, value)
                    del self._desired_state[key]
                else:
                    _LOGGER.debug(
                        "Ignoring remote update for %s: %s (waiting for %s)", 
                        key, value, desired_value
                    )

    def set_desired(self, data: dict[str, Any]) -> None:
        """Set the desired state (from user command)."""
        current_time = time.time()
        for key, value in data.items():
            self._desired_state[key] = (value, current_time)
            _LOGGER.debug("Set desired state for %s: %s", key, value)

    def get_display_state(self) -> dict[str, Any]:
        """Get the final state to display to the user."""
        current_time = time.time()
        display_state = self._remote_state.copy()
        
        # Overlay valid desired states
        keys_to_remove = []
        for key, (value, timestamp) in self._desired_state.items():
            if current_time - timestamp <= self._timeout:
                display_state[key] = value
            else:
                # Clean up expired states lazily
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._desired_state[key]
            
        return display_state

    @property
    def raw_remote_state(self) -> dict[str, Any]:
        """Get the raw remote state (for debugging)."""
        return self._remote_state
