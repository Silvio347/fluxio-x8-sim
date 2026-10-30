import json
import unittest

from fluxio_sim.io_source import RandomIo
from fluxio_sim.protocol import ControlMessage
from fluxio_sim.state import REFRESH_CHANNELS, TELEMETRY_KEEPALIVE_S, DeviceState


class DeviceStateTest(unittest.TestCase):
    def setUp(self):
        self.io = RandomIo()
        self.state = DeviceState("0.1.0", start_time=100.0)

    def test_no_telemetry_until_enabled(self):
        self.assertIsNone(self.state.next_telemetry(self.io, 101.0))

    def test_telemetry_streams_with_increasing_seq(self):
        self.state.apply(ControlMessage(telemetry=True), self.io, 100.0)
        first = json.loads(self.state.next_telemetry(self.io, 101.0))
        second = json.loads(self.state.next_telemetry(self.io, 102.0))
        self.assertEqual((first["seq"], second["seq"]), (0, 1))
        self.assertEqual((first["ms"], second["ms"]), (1000, 2000))

    def test_telemetry_stops_without_keepalive(self):
        self.state.apply(ControlMessage(telemetry=True), self.io, 100.0)
        self.assertIsNotNone(self.state.next_telemetry(self.io, 100.0 + TELEMETRY_KEEPALIVE_S - 0.1))
        self.assertIsNone(self.state.next_telemetry(self.io, 100.0 + TELEMETRY_KEEPALIVE_S))
        self.assertFalse(self.state.telemetry_enabled)

    def test_keepalive_extends_streaming(self):
        self.state.apply(ControlMessage(telemetry=True), self.io, 100.0)
        self.state.apply(ControlMessage(telemetry=True), self.io, 108.0)
        self.assertIsNotNone(self.state.next_telemetry(self.io, 115.0))

    def test_telemetry_false_stops_immediately(self):
        self.state.apply(ControlMessage(telemetry=True), self.io, 100.0)
        self.state.apply(ControlMessage(telemetry=False), self.io, 101.0)
        self.assertIsNone(self.state.next_telemetry(self.io, 101.5))

    def test_outputs_follow_commands(self):
        self.state.apply(ControlMessage(do=(1, 1), ao=(3, 42.5)), self.io, 100.0)
        snap = self.io.read()
        self.assertEqual(snap.do, (0, 1, 0, 0))
        self.assertEqual(snap.ao, (0.0, 0.0, 0.0, 42.5))

    def test_invalid_indexes_are_ignored(self):
        self.state.apply(ControlMessage(do=(4, 1), ao=(-1, 5.0)), self.io, 100.0)
        snap = self.io.read()
        self.assertEqual(snap.do, (0, 0, 0, 0))
        self.assertEqual(snap.ao, (0.0, 0.0, 0.0, 0.0))

    def test_manual_mode(self):
        self.state.apply(ControlMessage(manual=True), self.io, 100.0)
        self.assertTrue(self.state.manual_mode)

    def test_effects(self):
        self.assertEqual(self.state.apply(ControlMessage(type="get_channels"), self.io, 100.0), {REFRESH_CHANNELS})
        for kind in ("logic", "logic_get", "logic_sync", "ota", "whatever"):
            with self.subTest(kind=kind):
                self.assertEqual(self.state.apply(ControlMessage(type=kind), self.io, 100.0), set())

    def test_millis_wraps_like_uint32(self):
        self.assertEqual(self.state.millis(100.0 + 2**32 / 1000 + 1.0), 1000)

    def test_status_payload(self):
        status = json.loads(self.state.status_payload("10.0.0.2", 165.9))
        self.assertEqual(status, {"online": True, "ip": "10.0.0.2", "uptime": 65, "fwVersion": "0.1.0"})


if __name__ == "__main__":
    unittest.main()
