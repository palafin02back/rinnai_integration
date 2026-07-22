"""Tests for Rinnai HTTP request metadata."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
import time
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest


@pytest.fixture
def client_module(monkeypatch):
    """Import the client with lightweight Home Assistant and MQTT stubs."""
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

    aiohttp = ModuleType("aiohttp")

    class ClientError(Exception):
        """Stub aiohttp client error."""

    class ContentTypeError(ClientError):
        """Stub aiohttp content type error."""

    aiohttp.ClientError = ClientError
    aiohttp.ContentTypeError = ContentTypeError
    monkeypatch.setitem(sys.modules, "aiohttp", aiohttp)

    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []
    homeassistant_core = ModuleType("homeassistant.core")
    homeassistant_core.HomeAssistant = object
    homeassistant_core.callback = lambda func: func
    homeassistant_helpers = ModuleType("homeassistant.helpers")
    homeassistant_helpers.__path__ = []
    homeassistant_aiohttp = ModuleType("homeassistant.helpers.aiohttp_client")
    homeassistant_aiohttp.async_get_clientsession = MagicMock()

    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.core", homeassistant_core)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", homeassistant_helpers)
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.aiohttp_client", homeassistant_aiohttp
    )

    mqtt_client = ModuleType("custom_components.rinnai.core.mqtt_client")
    mqtt_client.RinnaiMQTTClient = MagicMock()
    monkeypatch.setitem(
        sys.modules, "custom_components.rinnai.core.mqtt_client", mqtt_client
    )

    config_manager = ModuleType("custom_components.rinnai.core.config_manager")
    config_manager.config_manager = MagicMock()
    monkeypatch.setitem(
        sys.modules, "custom_components.rinnai.core.config_manager", config_manager
    )

    sys.modules.pop("custom_components.rinnai.core.client", None)
    module = importlib.import_module("custom_components.rinnai.core.client")
    return module


@pytest.mark.asyncio
async def test_login_uses_app_user_agent_and_version(client_module):
    """The login request must look like the current mobile app."""
    session = MagicMock()
    response = MagicMock()
    response.json = AsyncMock(return_value={"success": True, "data": {"token": "token"}})
    session.get = AsyncMock(return_value=response)
    client_module.async_get_clientsession = MagicMock(return_value=session)

    client = client_module.RinnaiClient(MagicMock(), "user", "password")

    assert await client.login() is True
    request = session.get.await_args
    assert request.kwargs["headers"] == {
        "User-Agent": client_module.API_HEADERS["User-Agent"]
    }
    assert request.kwargs["params"]["appVersion"] == client_module.APP_VERSION


def test_authenticated_headers_include_user_agent(client_module):
    """Authenticated API requests must retain the mobile app User-Agent."""
    client_module.async_get_clientsession = MagicMock(return_value=MagicMock())
    client = client_module.RinnaiClient(MagicMock(), "user", "password")
    client._token = "token"

    assert client._http_headers(authenticated=True) == {
        "User-Agent": client_module.API_HEADERS["User-Agent"],
        "Authorization": "Basic token",
    }


def test_stale_request_cannot_clear_newer_token(client_module):
    """Concurrent stale responses must preserve an already refreshed token."""
    client_module.async_get_clientsession = MagicMock(return_value=MagicMock())
    client = client_module.RinnaiClient(MagicMock(), "user", "password")
    client._token = "fresh-token"

    assert client._invalidate_token("stale-token") is False
    assert client._token == "fresh-token"


def _response(payload):
    response = MagicMock()
    response.json = AsyncMock(return_value=payload)
    return response


def _configured_client(client_module, session):
    client_module.async_get_clientsession = MagicMock(return_value=session)
    client = client_module.RinnaiClient(MagicMock(), "user", "password")
    client.devices["device-id"] = {"mac": "device-mac"}
    client._device_configs["device-id"] = SimpleNamespace(
        supported_requests=["get_schedule"],
        features={"heat_type": "1"},
    )
    client._token = "stale-token"
    client._last_login_time = time.time()
    return client


@pytest.mark.asyncio
async def test_perform_request_refreshes_rejected_token_and_retries(client_module):
    """A generic API request retries once with a newly issued token."""
    session = MagicMock()
    session.get = AsyncMock(
        side_effect=[
            _response({"success": False, "msg": "token expired"}),
            _response({"success": True, "data": {"token": "fresh-token"}}),
            _response({"success": True, "data": {"schedule": "value"}}),
        ]
    )
    client = _configured_client(client_module, session)

    result = await client.perform_request("device-id", "get_schedule")

    assert result == {"schedule": "value"}
    assert session.get.await_count == 3
    first_request, login_request, retry_request = session.get.await_args_list
    assert first_request.kwargs["headers"]["Authorization"] == "Basic stale-token"
    assert "Authorization" not in login_request.kwargs["headers"]
    assert retry_request.kwargs["headers"]["Authorization"] == "Basic fresh-token"


@pytest.mark.asyncio
async def test_perform_request_retries_only_once(client_module):
    """Repeated API rejection must not cause an infinite login loop."""
    session = MagicMock()
    session.get = AsyncMock(
        side_effect=[
            _response({"success": False, "msg": "token expired"}),
            _response({"success": True, "data": {"token": "fresh-token"}}),
            _response({"success": False, "msg": "still rejected"}),
        ]
    )
    client = _configured_client(client_module, session)

    assert await client.perform_request("device-id", "get_schedule") is False
    assert session.get.await_count == 3
    assert client._token is None


@pytest.mark.asyncio
async def test_get_schedule_info_merges_configured_channels(client_module):
    """One request type can expose multiple named schedule state fields."""
    client_module.async_get_clientsession = MagicMock(return_value=MagicMock())
    client = client_module.RinnaiClient(MagicMock(), "user", "password")
    client.devices["device-id"] = {"mac": "device-mac"}
    client._device_configs["device-id"] = SimpleNamespace(
        supported_requests=["get_schedule", "save_schedule"],
        features={"heat_type": "legacy"},
        schedule_channels={
            "heating": {
                "get_type": "0",
                "save_type": "1",
                "response_key": "heatingReservationMode",
                "state_key": "heatingReservationMode",
            },
            "hot_water": {
                "get_type": "0",
                "save_type": "2",
                "response_key": "hotWaterReservationMode",
                "state_key": "hotWaterReservationMode",
            },
        },
    )
    client.perform_request = AsyncMock(
        return_value={
            "heatingReservationMode": "HEATING",
            "hotWaterReservationMode": "HOT_WATER",
        }
    )

    assert await client.get_schedule_info("device-id") == {
        "heatingReservationMode": "HEATING",
        "hotWaterReservationMode": "HOT_WATER",
    }
    client.perform_request.assert_awaited_once_with(
        "device-id", "get_schedule", heat_type="0"
    )


@pytest.mark.asyncio
async def test_get_schedule_info_queries_distinct_channel_types(client_module):
    """Q85-style schedule channels require one query per app type."""
    client_module.async_get_clientsession = MagicMock(return_value=MagicMock())
    client = client_module.RinnaiClient(MagicMock(), "user", "password")
    client.devices["device-id"] = {"mac": "device-mac"}
    client._device_configs["device-id"] = SimpleNamespace(
        supported_requests=["get_schedule"],
        features={"heat_type": "Q85_HEAT_OVEN"},
        schedule_channels={
            "heating": {
                "get_type": "Q85_HEAT_OVEN",
                "response_key": "byteStr",
                "state_key": "heatingReservationMode",
            },
            "hot_water": {
                "get_type": "Q85_HOT_WATER",
                "response_key": "byteStr",
                "state_key": "hotWaterReservationMode",
            },
        },
    )
    client.perform_request = AsyncMock(
        side_effect=[{"byteStr": "HEATING"}, {"byteStr": "HOT_WATER"}]
    )

    assert await client.get_schedule_info("device-id") == {
        "heatingReservationMode": "HEATING",
        "hotWaterReservationMode": "HOT_WATER",
    }
    assert client.perform_request.await_args_list == [
        call("device-id", "get_schedule", heat_type="Q85_HEAT_OVEN"),
        call("device-id", "get_schedule", heat_type="Q85_HOT_WATER"),
    ]


@pytest.mark.asyncio
async def test_save_schedule_uses_channel_specific_type(client_module):
    client_module.async_get_clientsession = MagicMock(return_value=MagicMock())
    client = client_module.RinnaiClient(MagicMock(), "user", "password")
    client.devices["device-id"] = {"mac": "device-mac"}
    client._device_configs["device-id"] = SimpleNamespace(
        supported_requests=["save_schedule"],
        features={"heat_type": "legacy"},
        schedule_channels={"hot_water": {"save_type": "2"}},
    )
    client.perform_request = AsyncMock(return_value=True)

    assert await client.save_schedule_hour(
        "device-id", "AABB", schedule_channel="hot_water"
    )
    client.perform_request.assert_awaited_once_with(
        "device-id", "save_schedule", data="AABB", heat_type="2"
    )
