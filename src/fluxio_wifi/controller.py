"""Decides when the board falls back to its own access point and when it goes back."""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .nm import Network

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Timing:
    check_s: float = 5.0
    # How long without a Wi-Fi client connection before the access point
    # comes up. Long enough for NetworkManager to rejoin a known network at
    # boot or after a short router outage.
    grace_s: float = 60.0
    # Same as the firmware: the AP stays up for 2 minutes, then the board
    # retries its saved networks.
    ap_window_s: float = 120.0
    client_retry_s: float = 30.0


@dataclass(frozen=True)
class Credentials:
    ssid: str
    password: str = field(repr=False)


class Portal(Protocol):
    def close(self) -> None: ...


class NetworkControl(Protocol):
    def client_connected(self) -> bool: ...

    def scan(self) -> list[Network]: ...

    def start_hotspot(self, ssid: str, password: str) -> bool: ...

    def stop_hotspot(self) -> None: ...

    def stations(self) -> int: ...

    def connect(self, ssid: str, password: str) -> tuple[bool, str]: ...


class Controller:
    def __init__(
        self,
        nm: NetworkControl,
        open_portal: Callable[["Controller"], Portal],
        ap_ssid: str,
        ap_password: str,
        timing: Timing = Timing(),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._nm = nm
        self._open_portal = open_portal
        self._ap_ssid = ap_ssid
        self._ap_password = ap_password
        self._timing = timing
        self._clock = clock
        self._last_ok = clock()
        self._ap_since = 0.0
        self._portal: Portal | None = None
        # Filled by the portal's HTTP threads, consumed by tick().
        self._pending: queue.Queue[Credentials] = queue.Queue(maxsize=1)
        self.mode = "monitor"
        self.networks: list[Network] = []
        self.last_error = ""

    def submit(self, creds: Credentials) -> bool:
        try:
            self._pending.put_nowait(creds)
            return True
        except queue.Full:
            return False

    def tick(self) -> None:
        now = self._clock()
        if self.mode == "monitor":
            if self._nm.client_connected():
                self._last_ok = now
            elif now - self._last_ok >= self._timing.grace_s:
                log.warning(
                    "No Wi-Fi for %.0fs; starting access point %s",
                    now - self._last_ok, self._ap_ssid,
                )
                self._start_ap(now)
            return

        try:
            creds = self._pending.get_nowait()
        except queue.Empty:
            creds = None
        if creds is not None:
            self._try_credentials(creds)
            return

        if now - self._ap_since >= self._timing.ap_window_s:
            if self._nm.stations() > 0:
                return  # someone is on the portal; don't pull the AP from under them
            log.info(
                "Access point window over; retrying saved networks for %.0fs",
                self._timing.client_retry_s,
            )
            self._stop_ap()
            self._retry_ap_later(now)

    def run(self, stop: threading.Event) -> None:
        try:
            while not stop.is_set():
                self.tick()
                stop.wait(self._timing.check_s)
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        if self.mode == "ap":
            self._stop_ap()
            self.mode = "monitor"

    def _retry_ap_later(self, now: float) -> None:
        self.mode = "monitor"
        # Reopen the AP after client_retry_s instead of the full grace period.
        self._last_ok = now - self._timing.grace_s + self._timing.client_retry_s

    def _start_ap(self, now: float) -> None:
        # The radio can't scan while it is the access point, so the portal
        # offers the list taken right before.
        self.networks = self._nm.scan()
        if not self._nm.start_hotspot(self._ap_ssid, self._ap_password):
            self._retry_ap_later(now)
            return
        try:
            self._portal = self._open_portal(self)
        except OSError as exc:
            log.error("Could not open the portal: %s", exc)
            self._nm.stop_hotspot()
            self._retry_ap_later(now)
            return
        self._ap_since = now
        self.mode = "ap"
        log.info("Access point %s is up with %d networks to offer", self._ap_ssid, len(self.networks))

    def _stop_ap(self) -> None:
        if self._portal is not None:
            self._portal.close()
            self._portal = None
        self._nm.stop_hotspot()

    def _try_credentials(self, creds: Credentials) -> None:
        log.info("Trying network %r from the portal", creds.ssid)
        self._stop_ap()
        self.mode = "monitor"
        ok, error = self._nm.connect(creds.ssid, creds.password)
        now = self._clock()
        if ok:
            log.info("Connected to %r", creds.ssid)
            self.last_error = ""
            self._last_ok = now
            return
        log.warning("Could not connect to %r: %s", creds.ssid, error)
        self.last_error = f"Could not connect to {creds.ssid}: {error}"
        self._start_ap(now)
