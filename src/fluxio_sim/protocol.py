"""Wire contract shared with the Fluxio ESP32 firmware (FluxioProject/fluxio_esp32).

Topic names, payload shapes and field defaults here must match the firmware,
because the backend and dashboard cannot tell the two devices apart.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Sequence

AI_COUNT = 4
AO_COUNT = 4
DI_COUNT = 4
DO_COUNT = 4

# setInitChannels() in the firmware uses 0-10 until the backend says otherwise.
DEFAULT_AI_RANGE = (0.0, 10.0)

OFFLINE_PAYLOAD = '{"online":false}'

_COMPACT = (",", ":")


@dataclass(frozen=True)
class Topics:
    control: str
    telemetry: str
    ota: str
    logic: str
    status: str


def topics_for(device_id: str) -> Topics:
    base = f"device/{device_id}"
    return Topics(
        control=f"{base}/control",
        telemetry=f"{base}/telemetry",
        ota=f"{base}/ota",
        logic=f"{base}/logic",
        status=f"{base}/status",
    )


@dataclass(frozen=True)
class IoSnapshot:
    ai: tuple[float, ...]
    ao: tuple[float, ...]
    di: tuple[int, ...]
    do: tuple[int, ...]


def build_status(ip: str, uptime_s: int, fw_version: str) -> str:
    return json.dumps(
        {"online": True, "ip": ip, "uptime": uptime_s, "fwVersion": fw_version},
        separators=_COMPACT,
    )


def build_telemetry(ms: int, seq: int, io: IoSnapshot) -> str:
    return json.dumps(
        {
            "ms": ms,
            "seq": seq,
            "ai": list(io.ai),
            "ao": list(io.ao),
            "di": list(io.di),
            "do": list(io.do),
        },
        separators=_COMPACT,
    )


@dataclass(frozen=True)
class ControlMessage:
    manual: bool | None = None
    telemetry: bool | None = None
    do: tuple[int, int] | None = None
    ao: tuple[int, float] | None = None
    type: str = ""

    def is_telemetry_keepalive(self) -> bool:
        return (
            self.telemetry is not None
            and self.manual is None
            and self.do is None
            and self.ao is None
            and not self.type
        )


def _number(value: Any) -> int | float | None:
    # bool is an int subclass in Python, but the firmware's ArduinoJson
    # defaults treat true/false as "not a number".
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def parse_control_message(payload: bytes | str) -> ControlMessage:
    """Raises ValueError for anything the firmware would reject as invalid JSON."""
    doc = json.loads(payload)
    if not isinstance(doc, dict):
        raise ValueError("control payload must be a JSON object")

    do_cmd = None
    if isinstance(doc.get("do"), dict):
        index = _number(doc["do"].get("index"))
        value = _number(doc["do"].get("value"))
        do_cmd = (int(index) if index is not None else -1, 1 if value else 0)

    ao_cmd = None
    if isinstance(doc.get("ao"), dict):
        index = _number(doc["ao"].get("index"))
        value = _number(doc["ao"].get("value"))
        ao_cmd = (
            int(index) if index is not None else -1,
            float(value) if value is not None else 0.0,
        )

    manual = doc.get("manual")
    telemetry = doc.get("telemetry")
    msg_type = doc.get("type")
    return ControlMessage(
        manual=manual if isinstance(manual, bool) else None,
        telemetry=telemetry if isinstance(telemetry, bool) else None,
        do=do_cmd,
        ao=ao_cmd,
        type=msg_type if isinstance(msg_type, str) else "",
    )


@dataclass(frozen=True)
class MqttCredentials:
    host: str
    port: int
    user: str
    password: str = field(repr=False)


def parse_mqtt_credentials(doc: Any) -> MqttCredentials:
    mqtt = doc.get("mqtt") if isinstance(doc, dict) else None
    if not isinstance(mqtt, dict):
        raise ValueError("response has no 'mqtt' object")

    host = mqtt.get("host")
    port = mqtt.get("port")
    user = mqtt.get("user")
    password = mqtt.get("pass")
    if not isinstance(host, str) or not host:
        raise ValueError("missing MQTT host")
    if isinstance(port, bool) or not isinstance(port, int) or port <= 0:
        raise ValueError("missing MQTT port")
    if not isinstance(user, str) or not isinstance(password, str):
        raise ValueError("missing MQTT user or password")
    return MqttCredentials(host=host, port=port, user=user, password=password)


def parse_ai_ranges(
    doc: Any, current: Sequence[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Applies get-all-channels mapMin/mapMax on top of the current ranges.

    Like the firmware, a channel missing from the response (or missing a
    field) keeps its previous value.
    """
    ranges = list(current)
    channels = doc.get("ai") if isinstance(doc, dict) else None
    if not isinstance(channels, dict):
        return ranges

    for key, cfg in channels.items():
        try:
            index = int(key)
        except ValueError:
            continue
        if not 0 <= index < AI_COUNT or not isinstance(cfg, dict):
            continue
        lo, hi = ranges[index]
        new_lo = _number(cfg.get("mapMin"))
        new_hi = _number(cfg.get("mapMax"))
        ranges[index] = (
            float(new_lo) if new_lo is not None else lo,
            float(new_hi) if new_hi is not None else hi,
        )
    return ranges
