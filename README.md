# fluxio-x8-sim

A simulated [Fluxio](https://github.com/FluxioProject) device that runs on an
Arduino Portenta X8. To the backend and the dashboard it looks like one more
ESP32 running `fluxio_esp32`: same HTTP calls, same MQTT topics, payloads and
timing. The hardware I/O is replaced by simulated signals.

## Roadmap

| Phase | I/O comes from | Status |
|---|---|---|
| 0 | Random signals generated on Linux | **current** |
| 1 | A sketch on the STM32H747 M4 core, read over RPC | planned |
| 2 | Real ADC/GPIO on a carrier board (LM35 + SSR plant) | planned |

The I/O sits behind the `IoSource` interface, so each phase only adds an
implementation and flips `FLUXIO_IO_SOURCE`.

## What phase 0 does

- `GET /mqtt` and `GET /get-all-channels` on the backend with `x-api-key`.
- MQTT over TLS, client ID = device ID, keepalive 30 s, retained
  `{"online":false}` last will.
- Retained status every 2 s: `{"online":true,"ip":...,"uptime":...,"fwVersion":...}`.
- Telemetry every 1 s, only while the dashboard keeps sending
  `{"telemetry": true}` (it stops on its own after 10 s without one):
  `{"ms":...,"seq":...,"ai":[4],"ao":[4],"di":[4],"do":[4]}`.
- AI values random-walk inside each channel's `mapMin`..`mapMax`; DI toggle
  about once a minute; `do`/`ao` commands are echoed back in telemetry.
- `manual` and `get_channels` are handled. `logic`, `logic_get`,
  `logic_sync` and `ota` are logged and ignored.
- On a clean stop it publishes `{"online":false}` itself, since the broker only
  sends the last will on an unexpected disconnect.

## Status LED

| LED | Meaning |
|---|---|
| Blue blinking fast | Connecting to the broker |
| Yellow blinking | Device ID not registered in Fluxio yet |
| Red blinking | Backend or broker error, retrying |
| Solid green | Online |
| Cyan flash | Telemetry message sent |
| Magenta flash | Command received |

When the simulator stops, the LED goes back to the board's default
(blue heartbeat).

## Running on the Portenta X8

1. Register the device ID (default `esp32_C209DAB7022B`) in the Fluxio app.
2. Copy the project to the board, e.g. `~/fluxio-x8-sim`, and create
   `config.env` from `config.example.env`. Keep it readable by its owner only
   (`chmod 600 config.env`).
3. Build and start:

   ```sh
   cd ~/fluxio-x8-sim
   sudo docker compose up -d --build
   sudo docker compose logs -f
   ```

4. Stop with `sudo docker compose down`.

The container has no restart policy yet, so it does not come back after a
reboot.

## Tests

The tests only need the standard library:

```sh
PYTHONPATH=src python -m unittest discover -s tests
```

On Windows PowerShell: `$env:PYTHONPATH = "src"; python -m unittest discover -s tests`.
Inside the container: `sudo docker compose run --rm fluxio-x8-sim python -m unittest discover -s tests`.
