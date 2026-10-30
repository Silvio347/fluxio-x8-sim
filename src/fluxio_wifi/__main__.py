"""Entry point: python3 -m fluxio_wifi"""

from __future__ import annotations

import logging
import signal
import sys
import threading

from .config import ConfigError, load_config
from .controller import Controller
from .nm import AP_ADDRESS, NetworkManager
from .portal import PortalServer

log = logging.getLogger("fluxio_wifi")


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    # journald adds its own timestamps.
    logging.basicConfig(level=config.log_level, format="%(levelname)-7s %(name)s: %(message)s")

    def open_portal(controller: Controller) -> PortalServer:
        return PortalServer(controller, config.device_id, AP_ADDRESS, config.portal_port).start()

    controller = Controller(
        NetworkManager(config.iface),
        open_portal,
        config.ap_ssid,
        config.ap_password,
        config.timing,
    )
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    log.info(
        "Watching %s; access point %s after %.0fs without Wi-Fi",
        config.iface, config.ap_ssid, config.timing.grace_s,
    )
    controller.run(stop)
    log.info("Stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
