"""Tests for the state manager module."""
import pytest
import time
import sys
import os
from unittest.mock import patch

# Add core module to path for direct imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom_components', 'rinnai', 'core'))

from state_manager import RinnaiStateManager


class TestStateManagerBasic:
    """Basic tests for RinnaiStateManager."""

    def test_initial_state_empty(self):
        """Test initial state is empty."""
        manager = RinnaiStateManager()
        assert manager.get_display_state() == {}
        assert manager.raw_remote_state == {}

    def test_update_remote(self):
        """Test updating remote state."""
        manager = RinnaiStateManager()
        
        manager.update_remote({"temp": 40, "mode": "heating"})
        
        assert manager.get_display_state() == {"temp": 40, "mode": "heating"}
        assert manager.raw_remote_state == {"temp": 40, "mode": "heating"}

    def test_update_remote_merges(self):
        """Test remote updates merge with existing state."""
        manager = RinnaiStateManager()
        
        manager.update_remote({"temp": 40})
        manager.update_remote({"mode": "heating"})
        
        assert manager.get_display_state() == {"temp": 40, "mode": "heating"}


class TestStateManagerDesiredState:
    """Tests for desired state management."""

    def test_set_desired(self):
        """Test setting desired state."""
        manager = RinnaiStateManager()
        manager.update_remote({"temp": 40})
        
        manager.set_desired({"temp": 50})
        
        # Display state should show desired value
        assert manager.get_display_state()["temp"] == 50
        # Raw remote should still be old value
        assert manager.raw_remote_state["temp"] == 40

    def test_desired_syncs_with_remote(self):
        """Test desired state syncs when remote matches."""
        manager = RinnaiStateManager()
        manager.update_remote({"temp": 40})
        
        # Set desired
        manager.set_desired({"temp": 50})
        assert manager.get_display_state()["temp"] == 50
        
        # Remote catches up
        manager.update_remote({"temp": 50})
        
        # Now should show remote value (desired cleared)
        assert manager.get_display_state()["temp"] == 50
        assert manager.raw_remote_state["temp"] == 50

    def test_desired_ignores_old_remote(self):
        """Test desired state ignores stale remote updates."""
        manager = RinnaiStateManager()
        
        # Set desired first
        manager.set_desired({"temp": 50})
        
        # Old remote value comes in
        manager.update_remote({"temp": 40})
        
        # Should still show desired
        assert manager.get_display_state()["temp"] == 50

    def test_desired_timeout(self):
        """Test desired state expires after timeout."""
        manager = RinnaiStateManager(timeout=0.1)  # 100ms timeout
        
        manager.set_desired({"temp": 50})
        assert manager.get_display_state()["temp"] == 50
        
        # Wait for timeout
        time.sleep(0.15)
        
        # Remote update should now take effect
        manager.update_remote({"temp": 40})
        assert manager.get_display_state()["temp"] == 40

    def test_desired_timeout_lazy_cleanup(self):
        """Test expired desired states are cleaned up lazily."""
        manager = RinnaiStateManager(timeout=0.1)
        
        manager.set_desired({"temp": 50})
        
        # Wait for timeout
        time.sleep(0.15)
        
        # get_display_state should clean up expired states
        manager.update_remote({"temp": 40})
        display = manager.get_display_state()
        
        assert display["temp"] == 40


class TestStateManagerStringComparison:
    """Tests for string comparison in state sync."""

    def test_sync_with_string_match(self):
        """Test sync works with string/int comparison."""
        manager = RinnaiStateManager()
        
        # Set desired as string
        manager.set_desired({"temp": "50"})
        
        # Remote comes in as int
        manager.update_remote({"temp": 50})
        
        # Should sync (strings compare equal)
        assert manager.get_display_state()["temp"] == 50

    def test_sync_with_int_match(self):
        """Test sync works with int/string comparison."""
        manager = RinnaiStateManager()
        
        # Set desired as int
        manager.set_desired({"temp": 50})
        
        # Remote comes in as string
        manager.update_remote({"temp": "50"})
        
        # Should sync
        assert manager.get_display_state()["temp"] == "50"


class TestStateManagerMultipleKeys:
    """Tests for managing multiple keys."""

    def test_multiple_desired_keys(self):
        """Test setting multiple desired keys."""
        manager = RinnaiStateManager()
        
        manager.set_desired({"temp": 50, "mode": "fast"})
        
        display = manager.get_display_state()
        assert display["temp"] == 50
        assert display["mode"] == "fast"

    def test_partial_sync(self):
        """Test partial sync of multiple keys."""
        manager = RinnaiStateManager()
        
        manager.set_desired({"temp": 50, "mode": "fast"})
        manager.update_remote({"temp": 50})  # Only temp syncs
        
        display = manager.get_display_state()
        assert display["temp"] == 50
        assert display["mode"] == "fast"  # Still desired

    def test_independent_key_updates(self):
        """Test keys update independently."""
        manager = RinnaiStateManager()
        manager.update_remote({"temp": 40, "mode": "normal"})
        
        # Only change temp
        manager.set_desired({"temp": 50})
        
        display = manager.get_display_state()
        assert display["temp"] == 50  # Desired
        assert display["mode"] == "normal"  # Remote unchanged
