"""Runtime configuration, read from environment variables (see config.example.env)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Mapping

from . import __version__

# The Fluxio web app only accepts IDs in the ESP32 firmware's format.
DEVICE_ID_PATTERN = re.compile(r"^esp32_[0-9a-fA-F]{12}$")

_REQUIRED = ("FLUXIO_BACKEND_URL", "FLUXIO_BACKEND_TOKEN", "FLUXIO_DEVICE_ID")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    backend_url: str
    backend_token: str = field(repr=False)
    device_id: str = ""
    fw_version: str = __version__
    io_source: str = "random"
    led_dir: str | None = None
    log_level: str = "INFO"


def _get(env: Mapping[str, str], key: str) -> str:
    return env.get(key, "").strip()


def load_config(env: Mapping[str, str] = os.environ) -> Config:
    missing = [key for key in _REQUIRED if not _get(env, key)]
    if missing:
        raise ConfigError(f"missing required settings: {', '.join(missing)}")

    device_id = _get(env, "FLUXIO_DEVICE_ID")
    if not DEVICE_ID_PATTERN.match(device_id):
        raise ConfigError(
            f"FLUXIO_DEVICE_ID {device_id!r} must look like esp32_XXXXXXXXXXXX "
            "(12 hex digits), or the Fluxio app will not accept it"
        )

    return Config(
        backend_url=_get(env, "FLUXIO_BACKEND_URL").rstrip("/"),
        backend_token=_get(env, "FLUXIO_BACKEND_TOKEN"),
        device_id=device_id,
        fw_version=_get(env, "FLUXIO_FW_VERSION") or __version__,
        io_source=_get(env, "FLUXIO_IO_SOURCE") or "random",
        led_dir=_get(env, "FLUXIO_LED_DIR") or None,
        log_level=_get(env, "FLUXIO_LOG_LEVEL").upper() or "INFO",
    )
