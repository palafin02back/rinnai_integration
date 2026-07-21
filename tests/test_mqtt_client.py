"""Tests for the Rinnai MQTT connection lifecycle."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mqtt_client_module(monkeypatch):
    """Import the MQTT client with lightweight Paho and HA stubs."""
    integration_dir = Path(__file__).parents[1] / "custom_components" / "rinnai"
    custom_components = ModuleType("custom_components")
    custom_components.__path__ = [str(integration_dir.parent)]
    rinnai = ModuleType("custom_components.rinnai")
    rinnai.__path__ = [str(integration_dir)]
    core = ModuleType("custom_components.rinnai.core")
    core.__path__ = [str(integration_dir / "core")]
    monkeypatch.setitem(sys.modules, "custom_components", custom_components)
    monkeypatch.setitem(sys.modules, "custom_components.rinnai", rinnai)
    monkeypatch.setitem(sys.modules, "custom_components.rinnai.core", core)

    paho = ModuleType("paho")
    paho.__path__ = []
    paho_mqtt = ModuleType("paho.mqtt")
    paho_mqtt.__path__ = []
    paho_client = ModuleType("paho.mqtt.client")
    client = MagicMock()
    paho_client.Client = MagicMock(return_value=client)
    paho_client.MQTT_ERR_SUCCESS = 0
    paho_client.error_string = lambda rc: f"error {rc}"
    monkeypatch.setitem(sys.modules, "paho", paho)
    monkeypatch.setitem(sys.modules, "paho.mqtt", paho_mqtt)
    monkeypatch.setitem(sys.modules, "paho.mqtt.client", paho_client)

    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []
    homeassistant_core = ModuleType("homeassistant.core")
    homeassistant_core.HomeAssistant = object
    homeassistant_core.callback = lambda func: func
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.core", homeassistant_core)

    const = ModuleType("custom_components.rinnai.const")
    const.RINNAI_HOST = "mqtt.example.test"
    const.RINNAI_PORT = 8883
    monkeypatch.setitem(sys.modules, "custom_components.rinnai.const", const)

    sys.modules.pop("custom_components.rinnai.core.mqtt_client", None)
    module = importlib.import_module("custom_components.rinnai.core.mqtt_client")
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    return module, client


class FakeHass:
    """Minimal Home Assistant executor facade."""

    def __init__(self):
        self.loop = MagicMock()

    async def async_add_executor_job(self, func, *args):
        return func(*args)


@pytest.mark.asyncio
async def test_connect_uses_paho_background_reconnect_once(mqtt_client_module):
    """connect_async and loop_start are each invoked only once."""
    module, paho_client = mqtt_client_module
    hass = FakeHass()
    client = module.RinnaiMQTTClient(hass, "user", "password")

    assert await client.async_connect() is False
    assert await client.async_connect() is False

    paho_client.connect_async.assert_called_once_with(
        module.RINNAI_HOST, module.RINNAI_PORT, 60
    )
    paho_client.loop_start.assert_called_once_with()
    paho_client.reconnect_delay_set.assert_called_once_with(
        min_delay=5, max_delay=120
    )


@pytest.mark.asyncio
async def test_initial_connect_exception_can_be_retried(mqtt_client_module):
    """A synchronous connect_async failure does not poison later attempts."""
    module, paho_client = mqtt_client_module
    hass = FakeHass()
    client = module.RinnaiMQTTClient(hass, "user", "password")
    paho_client.connect_async.side_effect = OSError("broker unavailable")

    assert await client.async_connect() is False
    assert client._connect_requested is False
    assert client._loop_started is False

    paho_client.connect_async.side_effect = None
    assert await client.async_connect() is False
    assert paho_client.connect_async.call_count == 2
    paho_client.loop_start.assert_called_once_with()


@pytest.mark.asyncio
async def test_successful_connect_resubscribes_with_stored_qos(mqtt_client_module):
    """A Paho reconnect activates subscriptions registered while offline."""
    module, paho_client = mqtt_client_module
    hass = FakeHass()
    client = module.RinnaiMQTTClient(hass, "user", "password")
    callback = MagicMock()

    await client.async_subscribe("device/topic", callback, qos=1)
    assert await client.async_connect() is False
    paho_client.subscribe.assert_not_called()

    paho_client.on_connect(paho_client, None, None, 0)

    assert client.connected is True
    paho_client.subscribe.assert_called_once_with("device/topic", 1)


@pytest.mark.asyncio
async def test_unexpected_disconnect_leaves_reconnect_to_paho(mqtt_client_module):
    """The disconnect callback must not launch a competing HA reconnect task."""
    module, paho_client = mqtt_client_module
    hass = FakeHass()
    client = module.RinnaiMQTTClient(hass, "user", "password")

    await client.async_connect()
    paho_client.on_disconnect(paho_client, None, 1)

    assert client.connected is False
    hass.loop.call_soon_threadsafe.assert_not_called()


@pytest.mark.asyncio
async def test_disconnect_stops_loop_and_allows_clean_restart(mqtt_client_module):
    """Unload stops Paho's loop and resets the one-shot lifecycle flags."""
    module, paho_client = mqtt_client_module
    hass = FakeHass()
    client = module.RinnaiMQTTClient(hass, "user", "password")

    await client.async_connect()
    await client.async_disconnect()

    paho_client.disconnect.assert_called_once_with()
    paho_client.loop_stop.assert_called_once_with()
    assert client.connected is False
    assert client._connect_requested is False
    assert client._loop_started is False
