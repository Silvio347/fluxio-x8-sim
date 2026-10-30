"""Settings for the Wi-Fi fallback, read from environment variables (see wifi-portal.example.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

from .controller import Timing


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class WifiConfig:
    device_id: str
    ap_password: str = field(repr=False)
    iface: str = "wlan0"
    portal_port: int = 80
    timing: Timing = field(default_factory=Timing)
    log_level: str = "INFO"

    @property
    def ap_ssid(self) -> str:
        return f"Fluxio-{self.device_id[-4:].upper()}"


def _get(env: Mapping[str, str], key: str) -> str:
    return env.get(key, "").strip()


def _seconds(env: Mapping[str, str], key: str, default: float) -> float:
    raw = _get(env, key)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{key} must be a number of seconds, got {raw!r}") from None
    if value <= 0:
        raise ConfigError(f"{key} must be greater than zero")
    return value


def load_config(env: Mapping[str, str] = os.environ) -> WifiConfig:
    device_id = _get(env, "FLUXIO_DEVICE_ID")
    if not device_id:
        raise ConfigError("missing required setting: FLUXIO_DEVICE_ID")

    # Not stripped: spaces are valid in a WPA passphrase.
    ap_password = env.get("FLUXIO_AP_PASSWORD", "")
    if not 8 <= len(ap_password) <= 63:
        raise ConfigError("FLUXIO_AP_PASSWORD must have 8 to 63 characters (WPA2)")

    defaults = Timing()
    timing = Timing(
        check_s=defaults.check_s,
        grace_s=_seconds(env, "FLUXIO_WIFI_GRACE_S", defaults.grace_s),
        ap_window_s=_seconds(env, "FLUXIO_WIFI_AP_WINDOW_S", defaults.ap_window_s),
        client_retry_s=_seconds(env, "FLUXIO_WIFI_CLIENT_RETRY_S", defaults.client_retry_s),
    )

    port_raw = _get(env, "FLUXIO_PORTAL_PORT") or "80"
    try:
        port = int(port_raw)
    except ValueError:
        raise ConfigError(f"FLUXIO_PORTAL_PORT must be an integer, got {port_raw!r}") from None

    return WifiConfig(
        device_id=device_id,
        ap_password=ap_password,
        iface=_get(env, "FLUXIO_WIFI_IFACE") or "wlan0",
        portal_port=port,
        timing=timing,
        log_level=_get(env, "FLUXIO_LOG_LEVEL").upper() or "INFO",
    )
