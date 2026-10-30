# fluxio-x8-sim — Agent Instructions

## Project Overview

Python service that impersonates a Fluxio ESP32 device from an Arduino
Portenta X8 (Linux on the i.MX8M Mini, running in Docker). See README.md for
the phases and the user-facing behavior.

## Source of Truth

The wire contract belongs to the firmware, `FluxioProject/fluxio_esp32`:
`lib/mqtt/mqtt.cpp`, `lib/backend/backend.cpp` and `lib/app_state/app_state.cpp`.
Any change to `protocol.py` or `state.py` must match what the firmware does.
If the firmware and this repo disagree, the firmware wins.

## Layout

```
src/fluxio_sim/
  protocol.py   — topics, payload builders, command/response parsing (no I/O)
  state.py      — telemetry keepalive and command rules (no MQTT)
  io_source.py  — IoSource interface + RandomIo (phase 0)
  led.py        — status LED through sysfs
  backend.py    — HTTP calls to the Fluxio backend (requests)
  device.py     — MQTT wiring and the main loop (paho-mqtt)
  config.py     — environment variables
tests/          — unittest, standard library only
```

## Rules

- Everything in English: code, identifiers, comments, docs, commit messages.
- Comments are for humans: explain why or a non-obvious constraint. No
  narration of what the code does and no commented-out code.
- No AI attribution in commits or PRs (no Co-Authored-By trailers, no
  generated-by footers).
- Never commit `config.env` or any credential. The backend token and MQTT
  password must never appear in logs or reprs.
- Keep `protocol.py`, `state.py`, `io_source.py`, `led.py` and `config.py`
  free of third-party imports so the tests run with plain Python.
- The LED must never crash the simulator: sysfs errors disable it.

## Test

```sh
PYTHONPATH=src python -m unittest discover -s tests
```

## Portenta X8 Notes

- Docker needs `sudo` on the board.
- `compose.yaml` mounts `/sys/devices/platform/leds/leds`, not
  `/sys/class/leds`: the class entries are relative symlinks that break inside
  the container.
- On the STM32H747, the M7 core runs Arduino's bridge firmware and is not
  available. Phase 1 code goes on the M4 core, talking to Linux over RPC
  (`m4-proxy`).
- From Windows PowerShell 5.1, quoting inside `adb shell '...'` gets mangled.
  Push a script with `adb push` and run it instead of inlining commands.
