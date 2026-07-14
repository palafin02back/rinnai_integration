"""Tests for Rinnai HTTP request metadata."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

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
