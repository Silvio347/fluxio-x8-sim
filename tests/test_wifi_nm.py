import subprocess
import unittest

from fluxio_wifi.nm import (
    AP_CONNECTION,
    Network,
    NetworkManager,
    count_stations,
    parse_device_state,
    parse_scan,
    run,
    split_terse,
)


def done(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class FakeRunner:
    """Answers nmcli calls from a list of (predicate, result) rules and records every call."""

    def __init__(self):
        self.calls = []
        self.rules = []

    def on(self, predicate, result):
        self.rules.insert(0, (predicate, result))

    def __call__(self, args, timeout):
        args = list(args)
        self.calls.append(args)
        for predicate, result in self.rules:
            if predicate(args):
                return result(args) if callable(result) else result
        return done()


def has(*words):
    return lambda args: all(w in args for w in words)


class ParsingTest(unittest.TestCase):
    def test_split_terse_unescapes(self):
        self.assertEqual(split_terse(r"My\:Net:80:WPA2"), ["My:Net", "80", "WPA2"])
        self.assertEqual(split_terse(r"back\\slash:1:"), ["back\\slash", "1", ""])

    def test_scan_dedupes_sorts_and_flags_open_networks(self):
        output = "\n".join([
            "Home:40:WPA2",
            "Home:72:WPA2",
            ":90:WPA2",
            "Cafe:55:",
            "Lab:55:--",
            "Weird:n/a:WPA1 WPA2",
        ])
        self.assertEqual(parse_scan(output), [
            Network("Home", 72, True),
            Network("Cafe", 55, False),
            Network("Lab", 55, False),
            Network("Weird", 0, True),
        ])

    def test_device_state(self):
        self.assertEqual(
            parse_device_state("GENERAL.STATE:100 (connected)\nGENERAL.CONNECTION:Silvio de Oliveira"),
            (True, "Silvio de Oliveira"),
        )
        self.assertEqual(
            parse_device_state("GENERAL.STATE:30 (disconnected)\nGENERAL.CONNECTION:--"),
            (False, ""),
        )
        self.assertEqual(parse_device_state(r"GENERAL.CONNECTION:a\:b"), (False, "a:b"))

    def test_count_stations(self):
        self.assertEqual(count_stations("Station aa:bb (on wlan0)\n\tinactive\nStation cc:dd (on wlan0)\n"), 2)
        self.assertEqual(count_stations(""), 0)

    def test_run_reports_timeouts_and_missing_binaries(self):
        self.assertEqual(run(["definitely-not-a-real-binary-x8"], 1).returncode, 127)


class NetworkManagerTest(unittest.TestCase):
    def setUp(self):
        self.runner = FakeRunner()
        self.nm = NetworkManager("wlan0", self.runner)

    def test_client_connected_ignores_our_own_hotspot(self):
        self.runner.on(has("dev", "show"), done("GENERAL.STATE:100 (connected)\nGENERAL.CONNECTION:Home"))
        self.assertTrue(self.nm.client_connected())
        self.runner.on(has("dev", "show"), done(f"GENERAL.STATE:100 (connected)\nGENERAL.CONNECTION:{AP_CONNECTION}"))
        self.assertFalse(self.nm.client_connected())
        self.runner.on(has("dev", "show"), done(returncode=10))
        self.assertFalse(self.nm.client_connected())

    def test_hotspot_is_recreated_from_scratch(self):
        self.assertTrue(self.nm.start_hotspot("Fluxio-022B", "secret123"))
        self.assertEqual(self.runner.calls[0][-2:], ["down", AP_CONNECTION])
        self.assertEqual(self.runner.calls[1][-2:], ["delete", AP_CONNECTION])
        hotspot = self.runner.calls[2]
        self.assertIn("hotspot", hotspot)
        self.assertEqual(hotspot[hotspot.index("ssid") + 1], "Fluxio-022B")
        self.assertEqual(hotspot[hotspot.index("password") + 1], "secret123")

    def test_hotspot_failure(self):
        self.runner.on(has("hotspot"), done(returncode=4, stderr="Error: no AP mode"))
        with self.assertLogs("fluxio_wifi.nm", "ERROR"):
            self.assertFalse(self.nm.start_hotspot("Fluxio-022B", "secret123"))

    def test_connect_success_keeps_profiles(self):
        self.runner.on(has("UUID"), done("old-1\n"))
        ok, error = self.nm.connect("Home", "password1")
        self.assertEqual((ok, error), (True, ""))
        connect = next(c for c in self.runner.calls if "connect" in c)
        self.assertEqual(connect[connect.index("--wait") + 1], "40")
        self.assertEqual(connect[-2:], ["ifname", "wlan0"])
        self.assertFalse(any("delete" in c for c in self.runner.calls))

    def test_connect_failure_removes_only_new_profiles(self):
        snapshots = iter([done("old-1\n"), done("old-1\nnew-2\n")])
        self.runner.on(has("UUID"), lambda args: next(snapshots))
        self.runner.on(has("connect"), done(returncode=4, stderr="Error: Secrets were required"))
        ok, error = self.nm.connect("Home", "wrongpass")
        self.assertFalse(ok)
        self.assertIn("Secrets were required", error)
        deletes = [c for c in self.runner.calls if "delete" in c]
        self.assertEqual(deletes, [["nmcli", "-c", "no", "con", "delete", "uuid", "new-2"]])

    def test_open_network_has_no_password_argument(self):
        self.nm.connect("Cafe", "")
        connect = next(c for c in self.runner.calls if "connect" in c)
        self.assertNotIn("password", connect)

    def test_scan_failure_returns_empty_list(self):
        self.runner.on(has("list"), done(returncode=8, stderr="busy"))
        with self.assertLogs("fluxio_wifi.nm", "WARNING"):
            self.assertEqual(self.nm.scan(), [])


if __name__ == "__main__":
    unittest.main()
