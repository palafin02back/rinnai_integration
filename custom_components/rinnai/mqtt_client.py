"""Custom MQTT client for Rinnai integration."""

import asyncio
from collections.abc import Callable
import datetime
import logging
import ssl
from typing import Any

import paho.mqtt.client as mqtt

from homeassistant.core import HomeAssistant, callback

from .const import RINNAI_HOST, RINNAI_PORT

_LOGGER = logging.getLogger(__name__)


class RinnaiMQTTClient:
    """Custom MQTT client for Rinnai devices."""

    def __init__(self, hass: HomeAssistant, username: str, password: str) -> None:
        """Initialize the MQTT client."""
        self.hass = hass
        self.username = f"a:rinnai:SR:01:SR:{username}"
        self.password = password
        ts = datetime.datetime.now()
        self.client_id = f"{self.username}:{ts.second}{ts.microsecond}"
        self.client = mqtt.Client(client_id=self.client_id)
        self.connected = False
        self._subscribes = {}
        self._loop_task = None
        self._connect_lock = asyncio.Lock()

        self.client.username_pw_set(self.username, self.password)
        self.hass.async_add_executor_job(
            self.client.tls_set,
            None,  # ca_certs
            None,  # certfile
            None,  # keyfile
            ssl.CERT_NONE,  # cert_reqs
            ssl.PROTOCOL_TLSv1_2,  # tls_version
            None,  # ciphers
        )

        _LOGGER.debug(
            "MQTT client initialized with host=%s, port=%s, username=%s, password=%s, client_id=%s",
            RINNAI_HOST,
            RINNAI_PORT,
            self.username,
            self.password,
            self.client_id,
        )

    async def async_connect(self) -> bool:
        """Connect to the Rinnai MQTT broker."""
        async with self._connect_lock:
            if self.connected:
                return True

            def on_connect(client, userdata, flags, rc):
                """Handle connection established."""
                _LOGGER.debug("Connected to Rinnai MQTT broker with result code %s", rc)
                if rc == 0:
                    self.connected = True
                    for topic in self._subscribes:
                        client.subscribe(topic)
                    _LOGGER.info("MQTT client connected successfully")
                else:
                    _LOGGER.error(
                        "Failed to connect to MQTT broker with result code %s: %s",
                        rc,
                        mqtt.error_string(rc),
                    )

            def on_disconnect(client, userdata, rc):
                """Handle disconnection."""
                _LOGGER.debug(
                    "Disconnected from Rinnai MQTT broker with result code %s", rc
                )
                self.connected = False
                if rc != 0:
                    _LOGGER.warning(
                        "Unexpected disconnection from MQTT broker with code %s: %s",
                        rc,
                        mqtt.error_string(rc),
                    )

            def on_message(client, userdata, msg):
                """Handle incoming message."""
                _LOGGER.debug("Received message on topic %s", msg.topic)
                if msg.topic in self._subscribes:
                    callback_func = self._subscribes[msg.topic][0]
                    self.hass.loop.call_soon_threadsafe(callback_func, msg)

            self.client.on_connect = on_connect
            self.client.on_disconnect = on_disconnect
            self.client.on_message = on_message

            try:
                _LOGGER.info(
                    "Connecting to MQTT broker at %s:%s", RINNAI_HOST, RINNAI_PORT
                )
                await self.hass.async_add_executor_job(
                    self.client.connect, RINNAI_HOST, RINNAI_PORT, 60
                )

                self.client.loop_start()
                _LOGGER.debug("MQTT client loop started")

                for i in range(10):
                    if self.connected:
                        break
                    await asyncio.sleep(0.5)
                    if i == 9 and not self.connected:
                        _LOGGER.warning("MQTT connection timeout after 5 seconds")

            except (ValueError, TypeError, KeyError) as err:
                _LOGGER.error("Error connecting to Rinnai MQTT broker: %s", err)
                return False
            return self.connected

    async def async_disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        if self.client:
            _LOGGER.info("Disconnecting from MQTT broker")
            await self.hass.async_add_executor_job(self.client.disconnect)
            await self.hass.async_add_executor_job(self.client.loop_stop)
            self.connected = False
            _LOGGER.debug("MQTT client disconnected and loop stopped")

    async def async_publish(self, topic: str, payload: str, qos: int = 0) -> bool:
        """Publish a message to the MQTT broker."""
        if not self.connected:
            if not await self.async_connect():
                return False

        try:
            _LOGGER.debug("Publishing to topic %s: %s", topic, payload)
            result = await self.hass.async_add_executor_job(
                self.client.publish, topic, payload, qos
            )

        except (ValueError, TypeError, KeyError) as err:
            _LOGGER.error("Error publishing to Rinnai MQTT broker: %s", err)
            return False
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    async def async_subscribe(
        self, topic: str, callback_func: Callable[[Any], None], qos: int = 0
    ) -> Callable[[], None]:
        """Subscribe to a topic with a callback."""
        if not self.connected:
            if not await self.async_connect():
                _LOGGER.error("Cannot subscribe to topic: MQTT client not connected")
                return lambda: None

        self._subscribes[topic] = (callback_func, qos)
        _LOGGER.info("Subscribing to topic %s with QoS %s", topic, qos)

        try:
            await self.hass.async_add_executor_job(self.client.subscribe, topic, qos)
        except (ValueError, TypeError, KeyError) as err:
            _LOGGER.error("Error subscribing to topic %s: %s", topic, err)
            return lambda: None

        @callback
        def _unsub_callback():
            self._unsubscribe(topic)

        return _unsub_callback

    def _unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a topic."""
        if topic in self._subscribes:
            del self._subscribes[topic]
            _LOGGER.info("Unsubscribed from topic %s", topic)

        if self.connected:
            try:
                self.client.unsubscribe(topic)
            except (ValueError, TypeError, KeyError) as err:
                _LOGGER.error("Error unsubscribing from topic %s: %s", topic, err)
