# Roadmap

## Phase 0 — Simulated device on Linux (done)

- [x] Same backend and MQTT contract as `fluxio_esp32`: credentials and
      channel fetch, retained status heartbeat, last will, telemetry with the
      10 s keepalive, `manual`/`do`/`ao`/`get_channels` commands.
- [x] Random but readable I/O behind the `IoSource` interface.
- [x] RGB LED: connection state, plus DO0-DO3 mirrored as red, green, blue and
      white.
- [x] Wi-Fi fallback access point with a captive setup page, as a host
      systemd service. Like the firmware, the page is also open on the
      regular network for 10 minutes after start.
- [x] Unit tests (standard library only), also run on the board's Python 3.10
      and inside the container.

## Phase 1 — I/O on the M4 core

Goal: the STM32H747 M4 core owns the I/O state and Linux only talks to
Fluxio. The values on the dashboard come from the sketch, and DO/AO commands
reach the M4 and come back in telemetry.

1. Toolchain: Arduino IDE 2 with the "Arduino Mbed OS Portenta Boards" core.
   Upload a minimal sketch to the M4 over ADB and read its serial output.
2. Check on this image (LmP 4.0.11) how `m4-proxy` exposes RPC to Linux:
   ports, and how a container reaches it.
3. Sketch in `firmware/m4_io/`: the phase 0 signal model (AI random walk, DI
   toggles, DO/AO state) with RPC functions such as `io_read`, `io_set_do`,
   `io_set_ao` and `io_set_ai_ranges`.
4. `M4Io` implementing `IoSource` with a small MessagePack-RPC client over
   TCP, using `msgpack` directly instead of the unmaintained
   msgpack-rpc-python/tornado stack. Timeouts and reconnect included.
5. Failure behavior: if the M4 stops answering, MQTT stays up, telemetry is
   not sent with stale values, and the LED shows an "I/O lost" pattern.
6. Tests against a fake RPC server; on the board, a DO command round-trips
   through the M4.
7. Measure RPC round-trip latency (median and p99) as the baseline for
   phase 2.

Done when `FLUXIO_IO_SOURCE=m4` runs the whole dashboard flow, and
restarting the sketch or `m4-proxy` recovers without restarting the
simulator.

## Phase 2 — Real plant on a carrier board

Goal: the thermal plant validated with the ESP32 (LM35, SSR, heater)
controlled by the M4 and supervised from Fluxio.

1. Carrier board with an analog input and a 3.3 V GPIO (Hat Carrier or Mid
   Carrier).
2. LM35 on an H7 ADC input (16-bit, 3.3 V reference), scaled to engineering
   units consistently with the channel's `mapMin`/`mapMax`.
3. SSR driven from a 3.3 V GPIO; check the relay board input and add a
   transistor stage if needed.
4. Control on the M4: port the PID (with its anti-windup) and TPO blocks from
   the firmware's `logic.cpp`. Gains and setpoint come from the Fluxio logic
   program's PID block.
5. Safety on the M4: maximum temperature cutoff, open/shorted sensor
   detection, heater off when Linux or the network is gone for too long.
6. Experiment: same plant and gains on the ESP32 and on the X8, comparing
   overshoot, settling time, steady-state band and sensor noise.

## Backlog

- White LED pattern while the fallback access point is up.
- Start the simulator container at boot (`restart: unless-stopped`).
- paho reports the same disconnect twice in the log.
- Logic engine and OTA simulation, left out of phase 0 on purpose.
- Own LmP/Yocto image with OTA and per-device MQTT credentials. The board's
  current image belongs to a Foundries factory that no longer accepts it.
