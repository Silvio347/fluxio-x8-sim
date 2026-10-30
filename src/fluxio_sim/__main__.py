"""Entry point: python -m fluxio_sim"""

from __future__ import annotations

import logging
import signal
import sys

from .backend import Backend
from .config import ConfigError, load_config
from .device import SimulatedDevice
from .io_source import make_io_source
from .led import StatusLed

log = logging.getLogger("fluxio_sim")


def main() -> int:
    try:
        config = load_config()
        io = make_io_source(config.io_source)
    except (ConfigError, ValueError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    device = SimulatedDevice(
        config,
        Backend(config.backend_url, config.backend_token, config.device_id),
        io,
        StatusLed(config.led_dir),
    )
    signal.signal(signal.SIGTERM, lambda *_: device.stop())
    signal.signal(signal.SIGINT, lambda *_: device.stop())

    log.info("Fluxio X8 simulator %s starting as %s", config.fw_version, config.device_id)
    device.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
