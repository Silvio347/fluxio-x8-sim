# fluxio-x8-sim

A simulated [Fluxio](https://github.com/FluxioProject) device that runs on an
Arduino Portenta X8. To the backend and the dashboard it looks like one more
ESP32 running `fluxio_esp32`: same HTTP calls, same MQTT topics, payloads and
timing. The hardware I/O is replaced by simulated signals.

It has two parts:

- `fluxio_sim`: the simulated device, in Docker.
- `fluxio_wifi`: a Wi-Fi fallback access point with a setup page, as a
  systemd service on the host.

## Roadmap

| Phase | I/O comes from | Status |
|---|---|---|
| 0 | Random signals generated on Linux | done |
| 1 | A sketch on the STM32H747 M4 core, read over RPC | **next** |
| 2 | Real ADC/GPIO on a carrier board (LM35 + SSR plant) | planned |

The I/O sits behind the `IoSource` interface, so each phase only adds an
implementation and flips `FLUXIO_IO_SOURCE`. Tasks per phase are in
[ROADMAP.md](ROADMAP.md).

## What phase 0 does

- `GET /mqtt` and `GET /get-all-channels` on the backend with `x-api-key`.
- MQTT over TLS, client ID = device ID, keepalive 30 s, retained
  `{"online":false}` last will.
- Retained status every 2 s: `{"online":true,"ip":...,"uptime":...,"fwVersion":...}`.
- Telemetry every 1 s, only while the dashboard keeps sending
  `{"telemetry": true}` (it stops on its own after 10 s without one):
  `{"ms":...,"seq":...,"ai":[4],"ao":[4],"di":[4],"do":[4]}`.
- AI values random-walk inside each channel's `mapMin`..`mapMax`; DI toggle
  about once a minute; `do`/`ao` commands are echoed back in telemetry, and
  the DO states are mirrored on the RGB LED (see below).
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
| Short green blink every 2 s | Online, all digital outputs off |
| Cyan flash | Telemetry message sent |
| Magenta flash | Command received (other than a DO command) |

While online, the digital outputs take over the LED so dashboard commands are
visible on the board:

| Output on | LED |
|---|---|
| DO0 | Red |
| DO1 | Green |
| DO2 | Blue |
| DO3 | White (all three) |

The colors mix, so DO0 + DO1 is yellow and DO1 + DO2 is cyan. While any
output is on, the cyan and magenta flashes become a short blink-off instead,
so the output color stays readable.

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

## Wi-Fi fallback access point

Like the firmware's AP mode, the board brings up its own access point when it
can't join a Wi-Fi network, so it can be configured from a phone.

| Step | What happens |
|---|---|
| No Wi-Fi client connection for 60 s | Scans the networks around, then starts the access point `Fluxio-<last 4 of the device ID>` (WPA2) |
| Phone joins the access point | Every DNS name answers `10.42.0.1`, so the phone pops up the setup page |
| Network chosen and saved on `/wifi` | The access point goes down and the board joins that network; NetworkManager keeps it for later boots |
| Wrong password | The access point comes back and the Wi-Fi page shows the error |
| 2 minutes with nobody on the access point | It goes down for 30 s so the saved networks can be retried, then comes back if they still fail |

Unlike the firmware, the setup page only exists while the access point is up
and only listens on its address, so nobody on the regular network can change
the board's Wi-Fi.

It runs on the host as a systemd service, not in Docker, because it is what
keeps the board reachable when something else breaks. It only uses the
board's own Python 3.10 standard library and `nmcli`.

Install (as root on the board, from the repository root):

```sh
install -d -m 700 /etc/fluxio
cp wifi-portal.example.env /etc/fluxio/wifi-portal.env   # then edit it
sh deploy/install-wifi-portal.sh
journalctl -u fluxio-wifi-portal -f
```

Remove with `sh deploy/uninstall-wifi-portal.sh`. ADB over USB keeps working
whatever the Wi-Fi state is, so it is always a way back in.

## Tests

The tests only need the standard library:

```sh
PYTHONPATH=src python -m unittest discover -s tests
```

On Windows PowerShell: `$env:PYTHONPATH = "src"; python -m unittest discover -s tests`.
Inside the container: `sudo docker compose run --rm fluxio-x8-sim python -m unittest discover -s tests`.
The Wi-Fi fallback on the board's own Python:
`PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_wifi*.py'`.
