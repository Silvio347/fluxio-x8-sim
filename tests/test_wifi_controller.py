import unittest

from fluxio_wifi.controller import Controller, Credentials, Timing
from fluxio_wifi.nm import Network

TIMING = Timing(check_s=5.0, grace_s=60.0, ap_window_s=120.0, client_retry_s=30.0)


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeNm:
    def __init__(self):
        self.connected = True
        self.hotspot_ok = True
        self.hotspot_up = False
        self.station_count = 0
        self.connect_result = (True, "")
        self.events = []

    def client_connected(self):
        return self.connected

    def scan(self):
        self.events.append("scan")
        return [Network("Home", 70, True)]

    def start_hotspot(self, ssid, password):
        self.events.append(("hotspot", ssid, password))
        self.hotspot_up = self.hotspot_ok
        return self.hotspot_ok

    def stop_hotspot(self):
        self.events.append("stop")
        self.hotspot_up = False

    def stations(self):
        return self.station_count

    def connect(self, ssid, password):
        self.events.append(("connect", ssid, password))
        ok, _ = self.connect_result
        self.connected = ok
        return self.connect_result


class FakePortal:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class ControllerTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.nm = FakeNm()
        self.portals = []
        self.controller = Controller(self.nm, self._open_portal, "Fluxio-022B", "secret123", TIMING, self.clock)

    def _open_portal(self, controller):
        portal = FakePortal()
        self.portals.append(portal)
        return portal

    def advance(self, seconds):
        self.clock.t += seconds
        self.controller.tick()

    def go_to_ap(self):
        self.nm.connected = False
        self.advance(1)
        self.advance(TIMING.grace_s)
        self.assertEqual(self.controller.mode, "ap")

    def test_stays_in_monitor_while_connected(self):
        for _ in range(100):
            self.advance(5)
        self.assertEqual(self.controller.mode, "monitor")
        self.assertEqual(self.nm.events, [])

    def test_short_outage_does_not_start_the_ap(self):
        self.nm.connected = False
        self.advance(TIMING.grace_s - 5)
        self.nm.connected = True
        self.advance(5)
        self.advance(TIMING.grace_s)
        self.assertEqual(self.controller.mode, "monitor")

    def test_ap_after_grace_scans_first(self):
        self.go_to_ap()
        self.assertEqual(self.nm.events[:2], ["scan", ("hotspot", "Fluxio-022B", "secret123")])
        self.assertEqual(len(self.portals), 1)
        self.assertEqual([n.ssid for n in self.controller.networks], ["Home"])

    def test_ap_window_ends_then_retries_clients_then_ap_again(self):
        self.go_to_ap()
        self.advance(TIMING.ap_window_s)
        self.assertEqual(self.controller.mode, "monitor")
        self.assertTrue(self.portals[0].closed)
        self.assertFalse(self.nm.hotspot_up)

        self.advance(TIMING.client_retry_s - 1)
        self.assertEqual(self.controller.mode, "monitor")
        self.advance(1)
        self.assertEqual(self.controller.mode, "ap")

    def test_ap_stays_while_a_phone_is_connected(self):
        self.go_to_ap()
        self.nm.station_count = 1
        self.advance(TIMING.ap_window_s * 3)
        self.assertEqual(self.controller.mode, "ap")
        self.nm.station_count = 0
        self.advance(5)
        self.assertEqual(self.controller.mode, "monitor")

    def test_network_recovering_during_retry_cancels_the_ap(self):
        self.go_to_ap()
        self.advance(TIMING.ap_window_s)
        self.nm.connected = True
        self.advance(TIMING.client_retry_s)
        self.advance(TIMING.grace_s)
        self.assertEqual(self.controller.mode, "monitor")

    def test_good_credentials_connect_and_leave_ap(self):
        self.go_to_ap()
        self.assertTrue(self.controller.submit(Credentials("Home", "password1")))
        self.advance(5)
        self.assertEqual(self.controller.mode, "monitor")
        self.assertIn(("connect", "Home", "password1"), self.nm.events)
        self.assertTrue(self.portals[0].closed)
        self.assertFalse(self.nm.hotspot_up)
        self.assertEqual(self.controller.last_error, "")

    def test_bad_credentials_bring_the_ap_back_with_the_error(self):
        self.go_to_ap()
        self.nm.connect_result = (False, "Secrets were required")
        self.controller.submit(Credentials("Home", "wrongpass"))
        self.advance(5)
        self.assertEqual(self.controller.mode, "ap")
        self.assertEqual(len(self.portals), 2)
        self.assertIn("Secrets were required", self.controller.last_error)

    def test_only_one_pending_submission(self):
        self.go_to_ap()
        self.assertTrue(self.controller.submit(Credentials("Home", "password1")))
        self.assertFalse(self.controller.submit(Credentials("Other", "password2")))

    def test_hotspot_failure_retries_later(self):
        self.nm.hotspot_ok = False
        self.nm.connected = False
        self.advance(1)
        self.advance(TIMING.grace_s)
        self.assertEqual(self.controller.mode, "monitor")
        self.nm.hotspot_ok = True
        self.advance(TIMING.client_retry_s)
        self.assertEqual(self.controller.mode, "ap")

    def test_portal_failure_takes_the_hotspot_down(self):
        def broken_portal(controller):
            raise OSError("address in use")

        controller = Controller(self.nm, broken_portal, "Fluxio-022B", "secret123", TIMING, self.clock)
        self.nm.connected = False
        self.clock.t += TIMING.grace_s
        with self.assertLogs("fluxio_wifi.controller", "ERROR"):
            controller.tick()
        self.assertEqual(controller.mode, "monitor")
        self.assertFalse(self.nm.hotspot_up)

    def test_shutdown_tears_the_ap_down(self):
        self.go_to_ap()
        self.controller.shutdown()
        self.assertFalse(self.nm.hotspot_up)
        self.assertTrue(self.portals[0].closed)


if __name__ == "__main__":
    unittest.main()
