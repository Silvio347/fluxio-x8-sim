# fluxio-x8-sim — Agent Instructions

## Project Overview

Two Python services for an Arduino Portenta X8 (Linux on the i.MX8M Mini):

- `fluxio_sim` impersonates a Fluxio ESP32 device. Runs in Docker.
- `fluxio_wifi` brings up a fallback access point with a Wi-Fi setup page
  when the board can't join a network. Runs on the host under systemd.

See README.md for the phases and the user-facing behavior.

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
  led.py        — status LED through sysfs; mirrors DO0-DO3 as red/green/blue/white
  backend.py    — HTTP calls to the Fluxio backend (requests)
  device.py     — MQTT wiring and the main loop (paho-mqtt)
  config.py     — environment variables
src/fluxio_wifi/
  nm.py         — nmcli wrapper and output parsing
  controller.py — when to start/stop the access point (state machine)
  portal.py     — setup pages and their HTTP server
  config.py     — environment variables
deploy/         — systemd unit, captive DNS config, install/uninstall scripts
tests/          — unittest, standard library only
```

The Wi-Fi fallback mirrors the firmware's `lib/webserver/` (AP mode and
`pages.h`), except that its page only listens on the access point.

## Rules

- Everything in English: code, identifiers, comments, docs, commit messages.
- Comments are for humans: explain why or a non-obvious constraint. No
  narration of what the code does and no commented-out code.
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:`,
  `test:`, `refactor:`, `chore:`, with an optional scope such as
  `feat(led):`).
- No AI attribution in commits or PRs (no Co-Authored-By trailers, no
  generated-by footers).
- Never commit `config.env` or any credential. The backend token and MQTT
  password must never appear in logs or reprs.
- Keep `protocol.py`, `state.py`, `io_source.py`, `led.py` and `config.py`
  free of third-party imports so the tests run with plain Python.
- `fluxio_wifi` runs on the board's own Python 3.10 with no packages
  installed: standard library only, nothing newer than 3.10.
- Never log or repr Wi-Fi passwords. SSIDs come from nearby strangers, so
  escape them like any user input.
- The LED must never crash the simulator: sysfs errors disable it.
- The "online" LED pattern must not be a solid single color, or it would be
  confused with a digital output being on.

## Test

```sh
PYTHONPATH=src python -m unittest discover -s tests
```

Run the `test_wifi*` tests on the board too (`python3` there is 3.10), since
that is the interpreter `fluxio_wifi` ships to.

## Portenta X8 Notes

- Docker needs `sudo` on the board.
- `compose.yaml` mounts `/sys/devices/platform/leds/leds`, not
  `/sys/class/leds`: the class entries are relative symlinks that break inside
  the container.
- On the STM32H747, the M7 core runs Arduino's bridge firmware and is not
  available. Phase 1 code goes on the M4 core, talking to Linux over RPC
  (`m4-proxy`).
- The Murata Wi-Fi chip supports AP mode; NetworkManager's hotspot gives the
  board `10.42.0.1` and runs dnsmasq, which reads
  `/etc/NetworkManager/dnsmasq-shared.d/` (used for the captive DNS).
- Testing the fallback drops the board off Wi-Fi: keep ADB over USB connected.
- From Windows PowerShell 5.1, quoting inside `adb shell '...'` gets mangled.
  Push a script with `adb push` and run it instead of inlining commands.
