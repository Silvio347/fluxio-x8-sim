"""NetworkManager through nmcli, the same tool you would use by hand on the board."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import Callable, Sequence

log = logging.getLogger(__name__)

AP_CONNECTION = "fluxio-ap"
# NetworkManager's address for the board in shared (hotspot) mode.
AP_ADDRESS = "10.42.0.1"

Runner = Callable[[Sequence[str], float], "subprocess.CompletedProcess[str]"]


def run(args: Sequence[str], timeout: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(list(args), capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(list(args), 124, "", f"timed out after {timeout:.0f}s")
    except FileNotFoundError:
        return subprocess.CompletedProcess(list(args), 127, "", f"{args[0]} not found")


@dataclass(frozen=True)
class Network:
    ssid: str
    signal: int
    secure: bool


def split_terse(line: str) -> list[str]:
    """Splits a line of `nmcli -t` output, where ':' and '\\' inside values are backslash-escaped."""
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for ch in line:
        if escaped:
            current.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(ch)
    fields.append("".join(current))
    return fields


def parse_scan(output: str) -> list[Network]:
    """Parses `nmcli -t -f SSID,SIGNAL,SECURITY dev wifi list`: one entry per SSID, strongest first."""
    best: dict[str, Network] = {}
    for line in output.splitlines():
        fields = split_terse(line)
        if len(fields) < 3 or not fields[0]:
            continue
        ssid, signal, security = fields[0], fields[1], fields[2].strip()
        try:
            strength = int(signal)
        except ValueError:
            strength = 0
        network = Network(ssid=ssid, signal=strength, secure=security not in ("", "--"))
        if ssid not in best or strength > best[ssid].signal:
            best[ssid] = network
    return sorted(best.values(), key=lambda n: (-n.signal, n.ssid.lower()))


def parse_device_state(output: str) -> tuple[bool, str]:
    """Parses `nmcli -t -f GENERAL.STATE,GENERAL.CONNECTION dev show IFACE`."""
    connected = False
    connection = ""
    for line in output.splitlines():
        fields = split_terse(line)
        if len(fields) < 2:
            continue
        key, value = fields[0], ":".join(fields[1:])
        if key == "GENERAL.STATE":
            connected = value.startswith("100")
        elif key == "GENERAL.CONNECTION":
            connection = "" if value == "--" else value
    return connected, connection


def parse_lines(output: str) -> set[str]:
    return {line.strip() for line in output.splitlines() if line.strip()}


def count_stations(output: str) -> int:
    return sum(1 for line in output.splitlines() if line.startswith("Station "))


class NetworkManager:
    def __init__(self, iface: str, runner: Runner = run) -> None:
        self.iface = iface
        self._runner = runner

    def _nmcli(self, *args: str, timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
        return self._runner(["nmcli", "-c", "no", *args], timeout)

    def client_connected(self) -> bool:
        r = self._nmcli("-t", "-f", "GENERAL.STATE,GENERAL.CONNECTION", "dev", "show", self.iface)
        if r.returncode != 0:
            return False
        connected, connection = parse_device_state(r.stdout)
        return connected and connection != AP_CONNECTION

    def scan(self) -> list[Network]:
        r = self._nmcli(
            "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list",
            "ifname", self.iface, "--rescan", "yes",
            timeout=30.0,
        )
        if r.returncode != 0:
            log.warning("Wi-Fi scan failed: %s", r.stderr.strip())
            return []
        return parse_scan(r.stdout)

    def start_hotspot(self, ssid: str, password: str) -> bool:
        self.stop_hotspot()
        r = self._nmcli(
            "dev", "wifi", "hotspot", "ifname", self.iface,
            "con-name", AP_CONNECTION, "ssid", ssid, "password", password,
            timeout=40.0,
        )
        if r.returncode != 0:
            log.error("Could not start the access point: %s", (r.stderr or r.stdout).strip())
            return False
        return True

    def stop_hotspot(self) -> None:
        # Deleting the profile keeps NetworkManager from ever bringing the
        # access point back on its own at boot.
        self._nmcli("con", "down", AP_CONNECTION)
        self._nmcli("con", "delete", AP_CONNECTION)

    def stations(self) -> int:
        r = self._runner(["iw", "dev", self.iface, "station", "dump"], 5.0)
        return count_stations(r.stdout) if r.returncode == 0 else 0

    def _profile_uuids(self) -> set[str]:
        r = self._nmcli("-t", "-f", "UUID", "con", "show")
        return parse_lines(r.stdout) if r.returncode == 0 else set()

    def connect(self, ssid: str, password: str, timeout_s: float = 40.0) -> tuple[bool, str]:
        before = self._profile_uuids()
        args = ["--wait", str(int(timeout_s)), "dev", "wifi", "connect", ssid]
        if password:
            args += ["password", password]
        args += ["ifname", self.iface]
        r = self._nmcli(*args, timeout=timeout_s + 10)
        if r.returncode == 0:
            return True, ""

        # Don't leave a profile with a wrong password behind; older profiles
        # (like the network that was working before) are never touched.
        for uuid in self._profile_uuids() - before:
            self._nmcli("con", "delete", "uuid", uuid)
        return False, (r.stderr or r.stdout).strip() or f"nmcli exited with {r.returncode}"
