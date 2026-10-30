import unittest

from fluxio_sim import __version__
from fluxio_sim.config import ConfigError, load_config

BASE = {
    "FLUXIO_BACKEND_URL": "https://backend.example/api/devices/",
    "FLUXIO_BACKEND_TOKEN": "token-value",
    "FLUXIO_DEVICE_ID": "esp32_C209DAB7022B",
}


class LoadConfigTest(unittest.TestCase):
    def test_defaults(self):
        cfg = load_config(BASE)
        self.assertEqual(cfg.backend_url, "https://backend.example/api/devices")
        self.assertEqual(cfg.fw_version, __version__)
        self.assertEqual(cfg.io_source, "random")
        self.assertIsNone(cfg.led_dir)
        self.assertEqual(cfg.log_level, "INFO")
        self.assertNotIn("token-value", repr(cfg))

    def test_overrides(self):
        cfg = load_config({**BASE, "FLUXIO_LED_DIR": "/leds", "FLUXIO_LOG_LEVEL": "debug", "FLUXIO_FW_VERSION": "9.9.9"})
        self.assertEqual((cfg.led_dir, cfg.log_level, cfg.fw_version), ("/leds", "DEBUG", "9.9.9"))

    def test_missing_required(self):
        with self.assertRaisesRegex(ConfigError, "FLUXIO_BACKEND_TOKEN"):
            load_config({**BASE, "FLUXIO_BACKEND_TOKEN": "  "})

    def test_device_id_format(self):
        for bad in ("x8_C209DAB7022B", "esp32_C209DAB7022", "esp32_C209DAB7022BZ", "esp32_GGGGGGGGGGGG"):
            with self.subTest(bad=bad):
                with self.assertRaises(ConfigError):
                    load_config({**BASE, "FLUXIO_DEVICE_ID": bad})
        self.assertEqual(load_config({**BASE, "FLUXIO_DEVICE_ID": "esp32_c209dab7022b"}).device_id, "esp32_c209dab7022b")


if __name__ == "__main__":
    unittest.main()
