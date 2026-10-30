"""Wi-Fi setup page served on the access point, modeled on the firmware's pages.h."""

from __future__ import annotations

import html
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Sequence
from urllib.parse import parse_qs

from .controller import Controller, Credentials
from .nm import Network

log = logging.getLogger(__name__)

MAX_FORM_BYTES = 4096

_STYLE = """
body { background-color: #121212; color: #ffffff; font-family: Arial, sans-serif;
  display: flex; justify-content: center; align-items: center; min-height: 100vh;
  margin: 0; padding: 0 16px; text-align: center; flex-direction: column; }
h1 { color: #00bcd4; margin-bottom: 20px; }
a { color: #00bcd4; text-decoration: none; font-size: 1.2em; margin-top: 15px; display: inline-block; }
form { display: inline-block; }
input, select { padding: 10px; margin: 5px 0; border: 1px solid #00bcd4; border-radius: 5px;
  background-color: #1e1e1e; color: #ffffff; width: 300px; max-width: 100%; box-sizing: border-box; }
input[type='submit'] { background-color: #00bcd4; border: none; cursor: pointer; }
.muted { opacity: 0.7; font-size: 14px; max-width: 300px; }
.error { color: #ff6b6b; max-width: 300px; }
"""


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body>{body}</body></html>"
    )


def render_home(device_id: str) -> str:
    return _page(
        "Fluxio setup",
        "<h1>Fluxio Configuration</h1>"
        f"<p class='muted'>Device ID:<br><strong>{html.escape(device_id)}</strong></p>"
        "<p><a href='/wifi'>Configure Wi-Fi</a></p>",
    )


def render_wifi_form(networks: Sequence[Network], error: str = "") -> str:
    # SSIDs come from whoever is broadcasting nearby, so they are escaped like any user input.
    options = "".join(
        f"<option value='{html.escape(n.ssid)}'>"
        f"{html.escape(n.ssid)} ({n.signal}%{'' if n.secure else ', open'})</option>"
        for n in networks
    )
    error_html = f"<p class='error'>{html.escape(error)}</p>" if error else ""
    return _page(
        "Configure Wi-Fi",
        "<h1>Configure Wi-Fi</h1>"
        f"{error_html}"
        "<form action='/wifi' method='POST'>"
        f"<select name='ssid'><option value=''>Choose a network</option>{options}</select><br>"
        "<input type='text' name='ssid_other' placeholder='Or type the network name' maxlength='32'><br>"
        "<input type='password' name='password' placeholder='Password' maxlength='63'><br>"
        "<input type='submit' value='Save'>"
        "</form>"
        "<a href='/'>Go Back</a>",
    )


def render_connecting(ssid: str, via_access_point: bool) -> str:
    if via_access_point:
        detail = (
            "This access point turns off now. If the connection fails, "
            "it comes back in a minute and shows the error on the Wi-Fi page."
        )
    else:
        detail = (
            "The board is leaving this network now, so this page stops responding. "
            "If the new network fails, it goes back to a saved one or opens its access point."
        )
    return _page(
        "Connecting",
        f"<h1>Connecting to {html.escape(ssid)}</h1><p class='muted'>{detail}</p>",
    )


def validate_form(form: dict[str, list[str]]) -> tuple[Credentials | None, str]:
    typed = (form.get("ssid_other") or [""])[0].strip()
    ssid = typed or (form.get("ssid") or [""])[0]
    password = (form.get("password") or [""])[0]
    if not ssid:
        return None, "Choose or type a network name."
    if len(ssid.encode("utf-8")) > 32:
        return None, "Network names have at most 32 bytes."
    if password and not 8 <= len(password) <= 63:
        return None, "Wi-Fi passwords have 8 to 63 characters."
    return Credentials(ssid=ssid, password=password), ""


class PortalServer:
    def __init__(self, controller: Controller, device_id: str, host: str, port: int) -> None:
        self.controller = controller
        self.device_id = device_id
        self.host = host
        self._port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        assert self._server is not None
        return self._server.server_address[1]

    def start(self, bind_attempts: int = 10, retry_s: float = 1.0) -> PortalServer:
        handler = _make_handler(self)
        for attempt in range(bind_attempts):
            try:
                self._server = ThreadingHTTPServer((self.host, self._port), handler)
                break
            except OSError:
                # The port can still be held for a moment by a previous run.
                if attempt == bind_attempts - 1:
                    raise
                time.sleep(retry_s)
        assert self._server is not None
        self._thread = threading.Thread(target=self._server.serve_forever, name="wifi-portal", daemon=True)
        self._thread.start()
        log.info("Portal listening on http://%s:%d/", self.host, self.port)
        return self

    def close(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None


def _make_handler(portal: PortalServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "FluxioPortal/1"

        def log_message(self, format: str, *args: object) -> None:
            log.debug("%s " + format, self.address_string(), *args)

        def _send(self, code: int, body: str, headers: dict[str, str] | None = None) -> None:
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def _redirect_home(self) -> None:
            # Phones probe a known URL to detect captive portals; with DNS on
            # the access point pointing every name here, this redirect makes
            # them open the page. Relative, so it also works from the LAN.
            self._send(302, "", {"Location": "/"})

        def _form(self, error: str) -> None:
            self._send(200, render_wifi_form(portal.controller.networks, error))

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send(200, render_home(portal.device_id))
            elif path == "/wifi":
                self._form(portal.controller.last_error)
            else:
                self._redirect_home()

        def do_POST(self) -> None:
            if self.path.split("?", 1)[0] != "/wifi":
                self._redirect_home()
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if not 0 <= length <= MAX_FORM_BYTES:
                self._send(400, "Bad request")
                return

            form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"), keep_blank_values=True)
            creds, error = validate_form(form)
            if creds is None:
                self._form(error)
            elif not portal.controller.submit(creds):
                self._form("Already trying a network, wait a moment.")
            else:
                self._send(200, render_connecting(creds.ssid, portal.controller.mode == "ap"))

    return Handler
