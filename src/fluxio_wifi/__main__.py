"""Entry point: python3 -m fluxio_wifi"""

from __future__ import annotations

import logging
import signal
import sys
import threading

from .config import ConfigError, load_config
from .controller import Controller
from .nm import NetworkManager
from .portal import PortalServer

log = logging.getLogger("fluxio_wifi")

# Every interface: the access point and, like the firmware, the regular network.
PORTAL_HOST = "0.0.0.0"


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    # journald adds its own timestamps.
    logging.basicConfig(level=config.log_level, format="%(levelname)-7s %(name)s: %(message)s")

    def open_portal(controller: Controller) -> PortalServer:
        return PortalServer(controller, config.device_id, PORTAL_HOST, config.portal_port).start()

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
        "Watching %s; access point %s after %.0fs without Wi-Fi; setup page on the regular network for %.0fs",
        config.iface, config.ap_ssid, config.timing.grace_s, config.timing.lan_portal_s,
    )
    controller.run(stop)
    log.info("Stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
