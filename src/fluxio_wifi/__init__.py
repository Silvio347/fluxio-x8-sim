"""Wi-Fi fallback access point for the Portenta X8, modeled on the Fluxio firmware's AP mode.

Runs on the host (systemd, the board's own Python 3.10, standard library only),
not in Docker: it is what keeps the board reachable when the network fails.
"""

__version__ = "0.1.0"
