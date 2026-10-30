"""MQTT side of the simulated device: same topics, payloads and timing as the firmware."""

from __future__ import annotations

import logging
import socket
import ssl
import threading
import time
from typing import Any, Callable

import certifi
import paho.mqtt.client as mqtt

from .backend import Backend, BackendError, DeviceNotRegistered
from .config import Config
from .io_source import IoSource
from .led import CYAN, MAGENTA, StatusLed
from .protocol import (
    AI_COUNT,
    DEFAULT_AI_RANGE,
    OFFLINE_PAYLOAD,
    MqttCredentials,
    parse_control_message,
    topics_for,
)
from .state import REFRESH_CHANNELS, DeviceState

log = logging.getLogger(__name__)

TICK_S = 1.0
STATUS_EVERY_TICKS = 2  # firmware STATUS_HEARTBEAT_MS = 2000
MQTT_KEEPALIVE_S = 30
NOT_REGISTERED_RETRY_S = 15.0
BACKEND_RETRY_MAX_S = 60.0


def local_ip(target_host: str) -> str:
    # Connecting a UDP socket sends nothing; it only picks the outgoing interface.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((target_host, 9))
            return s.getsockname()[0]
    except OSError:
        return ""


class SimulatedDevice:
    def __init__(
        self,
        config: Config,
        backend: Backend,
        io: IoSource,
        led: StatusLed,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._backend = backend
        self._io = io
        self._led = led
        self._clock = clock
        self._topics = topics_for(config.device_id)
        self._state = DeviceState(config.fw_version, clock())
        # DeviceState is touched by the paho network thread and the main loop.
        self._state_lock = threading.Lock()
        self._stop = threading.Event()
        self._refresh_requested = threading.Event()
        self._client: mqtt.Client | None = None
        self._broker_host = ""
        self._ip = ""
        self._ai_ranges = [DEFAULT_AI_RANGE] * AI_COUNT

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        self._led.start()
        try:
            creds = self._wait_for_credentials()
            if creds is None:
                return
            self._load_channels()
            self._client = self._connect(creds)
            self._loop()
        finally:
            self._shutdown()
            self._led.stop()

    def _wait_for_credentials(self) -> MqttCredentials | None:
        delay = 5.0
        while not self._stop.is_set():
            try:
                creds = self._backend.fetch_mqtt_credentials()
                log.info("MQTT credentials OK")
                return creds
            except DeviceNotRegistered:
                self._led.set_state("not_registered")
                log.warning(
                    "Device %s is not registered in Fluxio; add it in the app. Retrying in %.0fs",
                    self._config.device_id,
                    NOT_REGISTERED_RETRY_S,
                )
                self._stop.wait(NOT_REGISTERED_RETRY_S)
            except BackendError as exc:
                self._led.set_state("error")
                log.warning("Backend error: %s. Retrying in %.0fs", exc, delay)
                self._stop.wait(delay)
                delay = min(delay * 2, BACKEND_RETRY_MAX_S)
        return None

    def _load_channels(self) -> None:
        try:
            self._ai_ranges = self._backend.fetch_ai_ranges(self._ai_ranges)
        except BackendError as exc:
            log.warning("Could not fetch channel config, keeping current AI ranges: %s", exc)
            return
        self._io.set_ai_ranges(self._ai_ranges)
        log.info("AI ranges: %s", self._ai_ranges)

    def _connect(self, creds: MqttCredentials) -> mqtt.Client:
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self._config.device_id,
            protocol=mqtt.MQTTv311,
        )
        client.enable_logger(logging.getLogger("paho"))
        client.username_pw_set(creds.user, creds.password)
        client.tls_set_context(ssl.create_default_context(cafile=certifi.where()))
        client.will_set(self._topics.status, OFFLINE_PAYLOAD, qos=1, retain=True)
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.on_connect = self._on_connect
        client.on_connect_fail = self._on_connect_fail
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message

        self._broker_host = creds.host
        self._led.set_state("connecting")
        log.info("Connecting to %s:%d as %s", creds.host, creds.port, self._config.device_id)
        client.connect_async(creds.host, creds.port, keepalive=MQTT_KEEPALIVE_S)
        client.loop_start()
        return client

    def _loop(self) -> None:
        assert self._client is not None
        tick = 0
        next_tick = self._clock()
        while not self._stop.is_set():
            if self._refresh_requested.is_set():
                self._refresh_requested.clear()
                self._load_channels()

            self._io.step()
            self._led.set_outputs(self._io.read().do)

            if self._client.is_connected():
                with self._state_lock:
                    payload = self._state.next_telemetry(self._io, self._clock())
                if payload is not None:
                    self._client.publish(self._topics.telemetry, payload)
                    self._led.flash(CYAN, 0.08)
                if tick % STATUS_EVERY_TICKS == 0:
                    self._publish_status(self._client)

            tick += 1
            next_tick += TICK_S
            self._stop.wait(max(0.0, next_tick - self._clock()))

    def _publish_status(self, client: mqtt.Client) -> None:
        with self._state_lock:
            payload = self._state.status_payload(self._ip, self._clock())
        client.publish(self._topics.status, payload, retain=True)

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        if reason_code.is_failure:
            self._led.set_state("error")
            log.error("MQTT connection refused: %s", reason_code)
            return
        self._ip = local_ip(self._broker_host)
        client.subscribe(self._topics.control)
        client.subscribe(self._topics.ota)
        self._publish_status(client)
        self._led.set_state("online")
        log.info("MQTT connected; subscribed to %s and %s", self._topics.control, self._topics.ota)

    def _on_connect_fail(self, client: mqtt.Client, userdata: Any) -> None:
        self._led.set_state("error")
        log.warning("MQTT connection failed; retrying")

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        if self._stop.is_set():
            return
        self._led.set_state("connecting")
        log.warning("MQTT disconnected (%s); reconnecting", reason_code)

    def _on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            msg = parse_control_message(message.payload)
        except ValueError as exc:
            log.warning("Invalid JSON on %s: %s", message.topic, exc)
            return

        # A DO command already shows up as an LED color change.
        if msg.do is None and not msg.is_telemetry_keepalive():
            self._led.flash(MAGENTA, 0.4)
        with self._state_lock:
            effects = self._state.apply(msg, self._io, self._clock())
        if msg.do is not None:
            self._led.set_outputs(self._io.read().do)
        # The firmware also avoids HTTP inside the MQTT callback, so the
        # client keeps servicing the connection while the request runs.
        if REFRESH_CHANNELS in effects:
            self._refresh_requested.set()

    def _shutdown(self) -> None:
        client = self._client
        if client is None:
            return
        if client.is_connected():
            # A clean disconnect doesn't fire the last will, so without this the
            # retained status would keep saying "online".
            info = client.publish(self._topics.status, OFFLINE_PAYLOAD, qos=1, retain=True)
            try:
                info.wait_for_publish(timeout=3)
            except (RuntimeError, ValueError):
                pass
        client.disconnect()
        client.loop_stop()
        log.info("Stopped")
