import unittest

from fluxio_wifi.config import ConfigError, load_config

BASE = {"FLUXIO_DEVICE_ID": "esp32_C209DAB7022B", "FLUXIO_AP_PASSWORD": "secret123"}


class WifiConfigTest(unittest.TestCase):
    def test_defaults(self):
        cfg = load_config(BASE)
        self.assertEqual(cfg.ap_ssid, "Fluxio-022B")
        self.assertEqual((cfg.iface, cfg.portal_port), ("wlan0", 80))
        self.assertEqual((cfg.timing.grace_s, cfg.timing.ap_window_s, cfg.timing.client_retry_s), (60.0, 120.0, 30.0))
        self.assertNotIn("secret123", repr(cfg))

    def test_overrides(self):
        cfg = load_config({**BASE, "FLUXIO_WIFI_GRACE_S": "15", "FLUXIO_PORTAL_PORT": "8080", "FLUXIO_WIFI_IFACE": "wlan1"})
        self.assertEqual((cfg.timing.grace_s, cfg.portal_port, cfg.iface), (15.0, 8080, "wlan1"))

    def test_invalid(self):
        cases = [
            {"FLUXIO_AP_PASSWORD": "secret123"},
            {**BASE, "FLUXIO_AP_PASSWORD": "short"},
            {**BASE, "FLUXIO_WIFI_GRACE_S": "soon"},
            {**BASE, "FLUXIO_WIFI_AP_WINDOW_S": "0"},
            {**BASE, "FLUXIO_PORTAL_PORT": "http"},
        ]
        for env in cases:
            with self.subTest(env=env):
                with self.assertRaises(ConfigError):
                    load_config(env)


if __name__ == "__main__":
    unittest.main()
