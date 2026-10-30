"""HTTP calls to the Fluxio backend, the same ones the firmware makes at boot."""

from __future__ import annotations

from typing import Any, Sequence

import requests

from .protocol import MqttCredentials, parse_ai_ranges, parse_mqtt_credentials

TIMEOUT_S = 8.0


class BackendError(Exception):
    pass


class DeviceNotRegistered(BackendError):
    pass


class Backend:
    def __init__(self, base_url: str, token: str, device_id: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._device_id = device_id
        self._session = requests.Session()
        self._session.headers["x-api-key"] = token

    def _get(self, path: str) -> Any:
        try:
            resp = self._session.get(
                f"{self._base_url}/{path}",
                params={"deviceId": self._device_id},
                timeout=TIMEOUT_S,
            )
        except requests.RequestException as exc:
            raise BackendError(f"GET /{path} failed: {exc}") from exc

        if resp.status_code == 404 and path == "mqtt":
            raise DeviceNotRegistered(self._device_id)
        if resp.status_code != 200:
            raise BackendError(f"GET /{path} returned HTTP {resp.status_code}")
        try:
            return resp.json()
        except ValueError as exc:
            raise BackendError(f"GET /{path} returned invalid JSON") from exc

    def fetch_mqtt_credentials(self) -> MqttCredentials:
        try:
            return parse_mqtt_credentials(self._get("mqtt"))
        except ValueError as exc:
            raise BackendError(f"unexpected /mqtt response: {exc}") from exc

    def fetch_ai_ranges(
        self, current: Sequence[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        return parse_ai_ranges(self._get("get-all-channels"), current)
