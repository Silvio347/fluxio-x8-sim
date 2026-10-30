import json
import unittest

from fluxio_sim.protocol import (
    IoSnapshot,
    build_status,
    build_telemetry,
    parse_ai_ranges,
    parse_control_message,
    parse_mqtt_credentials,
    topics_for,
)


class TopicsTest(unittest.TestCase):
    def test_matches_firmware_pattern(self):
        t = topics_for("esp32_C209DAB7022B")
        self.assertEqual(t.control, "device/esp32_C209DAB7022B/control")
        self.assertEqual(t.telemetry, "device/esp32_C209DAB7022B/telemetry")
        self.assertEqual(t.ota, "device/esp32_C209DAB7022B/ota")
        self.assertEqual(t.logic, "device/esp32_C209DAB7022B/logic")
        self.assertEqual(t.status, "device/esp32_C209DAB7022B/status")


class PayloadTest(unittest.TestCase):
    def test_status_is_compact_and_ordered_like_firmware(self):
        self.assertEqual(
            build_status("192.168.0.105", 42, "0.1.0"),
            '{"online":true,"ip":"192.168.0.105","uptime":42,"fwVersion":"0.1.0"}',
        )

    def test_telemetry_fields(self):
        io = IoSnapshot(ai=(1.5, 2.0, 3.25, 4.0), ao=(0.0, 50.0, 0.0, 0.0), di=(0, 1, 0, 0), do=(1, 0, 0, 0))
        payload = build_telemetry(1234, 7, io)
        self.assertEqual(
            payload,
            '{"ms":1234,"seq":7,"ai":[1.5,2.0,3.25,4.0],"ao":[0.0,50.0,0.0,0.0],"di":[0,1,0,0],"do":[1,0,0,0]}',
        )
        self.assertEqual(list(json.loads(payload)), ["ms", "seq", "ai", "ao", "di", "do"])


class ParseControlTest(unittest.TestCase):
    def test_flags(self):
        msg = parse_control_message(b'{"manual": true, "telemetry": false}')
        self.assertIs(msg.manual, True)
        self.assertIs(msg.telemetry, False)

    def test_non_bool_flags_are_ignored(self):
        msg = parse_control_message(b'{"manual": 1, "telemetry": "yes"}')
        self.assertIsNone(msg.manual)
        self.assertIsNone(msg.telemetry)

    def test_do_and_ao(self):
        msg = parse_control_message(b'{"do": {"index": 2, "value": 1}, "ao": {"index": 0, "value": 50}}')
        self.assertEqual(msg.do, (2, 1))
        self.assertEqual(msg.ao, (0, 50.0))

    def test_missing_index_becomes_invalid(self):
        msg = parse_control_message(b'{"do": {"value": 1}, "ao": {"index": true, "value": 3}}')
        self.assertEqual(msg.do, (-1, 1))
        self.assertEqual(msg.ao, (-1, 3.0))

    def test_do_value_is_normalized(self):
        self.assertEqual(parse_control_message(b'{"do": {"index": 0, "value": 7}}').do, (0, 1))
        self.assertEqual(parse_control_message(b'{"do": {"index": 0}}').do, (0, 0))

    def test_type(self):
        self.assertEqual(parse_control_message(b'{"type": "get_channels"}').type, "get_channels")
        self.assertEqual(parse_control_message(b'{"type": 3}').type, "")

    def test_keepalive_detection(self):
        self.assertTrue(parse_control_message(b'{"telemetry": true}').is_telemetry_keepalive())
        self.assertFalse(
            parse_control_message(b'{"telemetry": true, "do": {"index": 0, "value": 1}}').is_telemetry_keepalive()
        )
        self.assertFalse(parse_control_message(b'{"manual": true}').is_telemetry_keepalive())

    def test_invalid_payloads(self):
        for payload in (b"not json", b"[1, 2]", b"\xff\xfe"):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    parse_control_message(payload)


class ParseCredentialsTest(unittest.TestCase):
    def test_valid(self):
        creds = parse_mqtt_credentials(
            {"mqtt": {"host": "broker.example", "port": 8883, "user": "u", "pass": "secret"}}
        )
        self.assertEqual((creds.host, creds.port, creds.user, creds.password), ("broker.example", 8883, "u", "secret"))
        self.assertNotIn("secret", repr(creds))

    def test_invalid(self):
        bad = [
            {},
            {"mqtt": []},
            {"mqtt": {"host": "", "port": 8883, "user": "u", "pass": "p"}},
            {"mqtt": {"host": "h", "port": "8883", "user": "u", "pass": "p"}},
            {"mqtt": {"host": "h", "port": True, "user": "u", "pass": "p"}},
            {"mqtt": {"host": "h", "port": 8883, "user": "u"}},
        ]
        for doc in bad:
            with self.subTest(doc=doc):
                with self.assertRaises(ValueError):
                    parse_mqtt_credentials(doc)


class ParseAiRangesTest(unittest.TestCase):
    DEFAULT = [(0.0, 10.0)] * 4

    def test_partial_update_keeps_previous_values(self):
        doc = {"ai": {"0": {"mapMin": 0, "mapMax": 1000}, "2": {"mapMax": 50}}}
        self.assertEqual(
            parse_ai_ranges(doc, self.DEFAULT),
            [(0.0, 1000.0), (0.0, 10.0), (0.0, 50.0), (0.0, 10.0)],
        )

    def test_ignores_bad_keys_and_shapes(self):
        doc = {"ai": {"x": {"mapMax": 1}, "9": {"mapMax": 1}, "1": "nope", "3": {"mapMin": "5"}}}
        self.assertEqual(parse_ai_ranges(doc, self.DEFAULT), self.DEFAULT)
        self.assertEqual(parse_ai_ranges({"ai": []}, self.DEFAULT), self.DEFAULT)
        self.assertEqual(parse_ai_ranges(None, self.DEFAULT), self.DEFAULT)


if __name__ == "__main__":
    unittest.main()
