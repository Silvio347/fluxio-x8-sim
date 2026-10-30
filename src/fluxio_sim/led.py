"""Device status on the Portenta X8 RGB LED, through Linux sysfs."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable

log = logging.getLogger(__name__)

Color = tuple[int, int, int]

OFF: Color = (0, 0, 0)
RED: Color = (1, 0, 0)
GREEN: Color = (0, 1, 0)
BLUE: Color = (0, 0, 1)
YELLOW: Color = (1, 1, 0)
CYAN: Color = (0, 1, 1)
MAGENTA: Color = (1, 0, 1)

CHANNELS = ("ledR", "ledG", "ledB")

# state -> (color, seconds on, seconds off); 0 seconds off means solid.
PATTERNS: dict[str, tuple[Color, float, float]] = {
    "connecting": (BLUE, 0.25, 0.25),
    "not_registered": (YELLOW, 0.5, 0.5),
    "error": (RED, 0.5, 0.5),
    "online": (GREEN, 1.0, 0.0),
}

_REFRESH_S = 0.02


class StatusLed:
    """A base pattern per device state, with short flashes on top for events.

    Any sysfs error disables the LED instead of crashing the device: the LED
    is a nice-to-have and must never take the simulator down.
    """

    def __init__(self, led_dir: str | None, clock: Callable[[], float] = time.monotonic) -> None:
        self._dir = led_dir
        self._clock = clock
        self._lock = threading.Lock()
        self._state = "connecting"
        self._flash_color: Color | None = None
        self._flash_until = 0.0
        self._shown: Color | None = None
        self._saved: dict[str, tuple[str, str]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _path(self, channel: str, attr: str) -> str:
        assert self._dir is not None
        return os.path.join(self._dir, channel, attr)

    def _read(self, channel: str, attr: str) -> str:
        with open(self._path(channel, attr)) as f:
            return f.read().strip()

    def _write(self, channel: str, attr: str, value: str) -> None:
        with open(self._path(channel, attr), "w") as f:
            f.write(value)

    def _active_trigger(self, channel: str) -> str:
        text = self._read(channel, "trigger")
        if "[" in text:
            return text[text.index("[") + 1 : text.index("]")]
        return text

    def start(self) -> None:
        if not self._dir:
            return
        try:
            for ch in CHANNELS:
                self._saved[ch] = (self._active_trigger(ch), self._read(ch, "brightness"))
            for ch in CHANNELS:
                self._write(ch, "trigger", "none")
        except OSError as exc:
            log.warning("Status LED disabled: %s", exc)
            self._restore()
            return
        self._thread = threading.Thread(target=self._run, name="status-led", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._restore()

    def set_state(self, state: str) -> None:
        if state not in PATTERNS:
            raise ValueError(f"unknown LED state {state!r}")
        with self._lock:
            self._state = state

    def flash(self, color: Color, seconds: float) -> None:
        with self._lock:
            self._flash_color = color
            self._flash_until = self._clock() + seconds

    def color_at(self, now: float) -> Color:
        with self._lock:
            if self._flash_color is not None and now < self._flash_until:
                return self._flash_color
            color, on_s, off_s = PATTERNS[self._state]
        if off_s <= 0:
            return color
        return color if now % (on_s + off_s) < on_s else OFF

    def _run(self) -> None:
        while not self._stop.wait(_REFRESH_S):
            color = self.color_at(self._clock())
            if color == self._shown:
                continue
            try:
                for ch, value in zip(CHANNELS, color):
                    self._write(ch, "brightness", str(value))
            except OSError as exc:
                log.warning("Status LED disabled: %s", exc)
                return
            self._shown = color

    def _restore(self) -> None:
        for ch, (trigger, brightness) in self._saved.items():
            try:
                self._write(ch, "brightness", "0")
                self._write(ch, "trigger", trigger)
                if trigger == "none":
                    self._write(ch, "brightness", brightness)
            except OSError as exc:
                log.warning("Could not restore %s: %s", ch, exc)
        self._saved.clear()
