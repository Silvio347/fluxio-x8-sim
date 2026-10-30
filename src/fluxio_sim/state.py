"""Control and telemetry rules, kept free of MQTT so they can be tested directly."""

from __future__ import annotations

import logging

from .io_source import IoSource
from .protocol import AO_COUNT, DO_COUNT, ControlMessage, build_status, build_telemetry

log = logging.getLogger(__name__)

# The dashboard has to keep re-sending {"telemetry": true}; the firmware stops
# streaming on its own when the last one is older than this.
TELEMETRY_KEEPALIVE_S = 10.0

REFRESH_CHANNELS = "refresh_channels"

_NOT_SIMULATED = frozenset({"logic", "logic_get", "logic_sync", "ota"})


class DeviceState:
    def __init__(self, fw_version: str, start_time: float) -> None:
        self.fw_version = fw_version
        self.manual_mode = False
        self.telemetry_enabled = False
        self._start = start_time
        self._last_telemetry_cmd = start_time
        self._seq = 0

    def uptime_s(self, now: float) -> int:
        return int(now - self._start)

    def millis(self, now: float) -> int:
        # Same uint32 wrap as the ESP32's millis(); the dashboard already handles it.
        return int((now - self._start) * 1000) & 0xFFFFFFFF

    def status_payload(self, ip: str, now: float) -> str:
        return build_status(ip, self.uptime_s(now), self.fw_version)

    def apply(self, msg: ControlMessage, io: IoSource, now: float) -> set[str]:
        effects: set[str] = set()

        if msg.manual is not None:
            self.manual_mode = msg.manual
            log.info("Manual mode %s", "ON" if msg.manual else "OFF")

        if msg.telemetry is not None:
            if msg.telemetry != self.telemetry_enabled:
                log.info("Telemetry %s", "ON" if msg.telemetry else "OFF")
            self.telemetry_enabled = msg.telemetry
            self._last_telemetry_cmd = now

        if msg.do is not None:
            index, value = msg.do
            if 0 <= index < DO_COUNT:
                io.set_do(index, value)
                log.info("DO[%d] = %d", index, value)
            else:
                log.warning("DO command with invalid index: %d", index)

        if msg.ao is not None:
            index, value = msg.ao
            if 0 <= index < AO_COUNT:
                io.set_ao(index, value)
                log.info("AO[%d] = %.2f", index, value)
            else:
                log.warning("AO command with invalid index: %d", index)

        if msg.type == "get_channels":
            effects.add(REFRESH_CHANNELS)
        elif msg.type in _NOT_SIMULATED:
            log.info("Ignoring '%s' command: not simulated in phase 0", msg.type)

        return effects

    def next_telemetry(self, io: IoSource, now: float) -> str | None:
        if not self.telemetry_enabled:
            return None
        if now - self._last_telemetry_cmd >= TELEMETRY_KEEPALIVE_S:
            self.telemetry_enabled = False
            log.info(
                "Telemetry auto-disabled: no enable command in the last %.0fs",
                TELEMETRY_KEEPALIVE_S,
            )
            return None

        payload = build_telemetry(self.millis(now), self._seq, io.read())
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        return payload
