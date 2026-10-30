"""I/O sources the simulated device reads from and writes to."""

from __future__ import annotations

import random
import threading
from typing import Protocol, Sequence

from .protocol import AI_COUNT, AO_COUNT, DEFAULT_AI_RANGE, DI_COUNT, DO_COUNT, IoSnapshot


class IoSource(Protocol):
    """What the device needs from its I/O. Phase 1 adds an implementation backed by the M4 core."""

    def step(self) -> None: ...

    def read(self) -> IoSnapshot: ...

    def set_do(self, index: int, value: int) -> None: ...

    def set_ao(self, index: int, value: float) -> None: ...

    def set_ai_ranges(self, ranges: Sequence[tuple[float, float]]) -> None: ...


def _bounds(r: tuple[float, float]) -> tuple[float, float]:
    lo, hi = r
    return (lo, hi) if lo <= hi else (hi, lo)


class RandomIo:
    """Random but readable signals: each AI random-walks inside its channel range
    and each DI toggles every minute or so. Outputs hold whatever was commanded."""

    AI_STEP_FRACTION = 0.01
    DI_FLIP_PROBABILITY = 0.02

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        # Written from the MQTT thread (commands) and read from the main loop.
        self._lock = threading.Lock()
        self._ranges = [DEFAULT_AI_RANGE] * AI_COUNT
        self._ai = [sum(_bounds(r)) / 2 for r in self._ranges]
        self._ao = [0.0] * AO_COUNT
        self._di = [0] * DI_COUNT
        self._do = [0] * DO_COUNT

    def step(self) -> None:
        with self._lock:
            for i, r in enumerate(self._ranges):
                lo, hi = _bounds(r)
                v = self._ai[i] + self._rng.gauss(0.0, (hi - lo) * self.AI_STEP_FRACTION)
                # Reflect instead of clamping so the walk doesn't stick to a bound.
                if v > hi:
                    v = 2 * hi - v
                if v < lo:
                    v = 2 * lo - v
                self._ai[i] = min(max(v, lo), hi)

            for i in range(DI_COUNT):
                if self._rng.random() < self.DI_FLIP_PROBABILITY:
                    self._di[i] ^= 1

    def read(self) -> IoSnapshot:
        with self._lock:
            return IoSnapshot(
                ai=tuple(round(v, 2) for v in self._ai),
                ao=tuple(self._ao),
                di=tuple(self._di),
                do=tuple(self._do),
            )

    def set_do(self, index: int, value: int) -> None:
        with self._lock:
            self._do[index] = 1 if value else 0

    def set_ao(self, index: int, value: float) -> None:
        with self._lock:
            self._ao[index] = float(value)

    def set_ai_ranges(self, ranges: Sequence[tuple[float, float]]) -> None:
        with self._lock:
            self._ranges = list(ranges)
            # A value left outside a new range would take many steps to walk back in.
            for i, r in enumerate(self._ranges):
                lo, hi = _bounds(r)
                if not lo <= self._ai[i] <= hi:
                    self._ai[i] = (lo + hi) / 2


def make_io_source(name: str) -> IoSource:
    if name == "random":
        return RandomIo()
    raise ValueError(f"unknown IO source {name!r} (available: random)")
