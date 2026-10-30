import os
import tempfile
import time
import unittest

from fluxio_sim.led import (
    BLUE,
    CHANNELS,
    CYAN,
    GREEN,
    MAGENTA,
    OFF,
    RED,
    WHITE,
    YELLOW,
    StatusLed,
    outputs_color,
)


class FakeClock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


class PatternTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.led = StatusLed(None, clock=self.clock)

    def test_connecting_blinks_blue(self):
        self.assertEqual(self.led.color_at(0.1), BLUE)
        self.assertEqual(self.led.color_at(0.3), OFF)
        self.assertEqual(self.led.color_at(0.6), BLUE)

    def test_online_idle_is_a_short_green_tick(self):
        self.led.set_state("online")
        self.assertEqual(self.led.color_at(0.05), GREEN)
        self.assertEqual(self.led.color_at(0.5), OFF)
        self.assertEqual(self.led.color_at(1.9), OFF)
        self.assertEqual(self.led.color_at(2.05), GREEN)

    def test_error_blinks_red(self):
        self.led.set_state("error")
        self.assertEqual(self.led.color_at(0.2), RED)
        self.assertEqual(self.led.color_at(0.7), OFF)

    def test_flash_overrides_then_expires(self):
        self.led.set_state("online")
        self.clock.t = 10.5
        self.led.flash(CYAN, 0.08)
        self.assertEqual(self.led.color_at(10.55), CYAN)
        self.assertEqual(self.led.color_at(10.6), OFF)

    def test_outputs_take_over_while_online(self):
        self.led.set_state("online")
        self.led.set_outputs((1, 0, 0, 0))
        for t in (0.05, 0.5, 1.9):
            self.assertEqual(self.led.color_at(t), RED)

    def test_flash_winks_off_over_outputs(self):
        self.led.set_state("online")
        self.led.set_outputs((0, 0, 1, 0))
        self.clock.t = 3.0
        self.led.flash(CYAN, 0.08)
        self.assertEqual(self.led.color_at(3.05), OFF)
        self.assertEqual(self.led.color_at(3.1), BLUE)

    def test_outputs_ignored_when_not_online(self):
        self.led.set_outputs((1, 0, 0, 0))
        self.assertEqual(self.led.color_at(0.1), BLUE)
        self.assertEqual(self.led.color_at(0.3), OFF)

    def test_all_outputs_off_returns_to_idle_pattern(self):
        self.led.set_state("online")
        self.led.set_outputs((0, 1, 0, 0))
        self.led.set_outputs((0, 0, 0, 0))
        self.assertEqual(self.led.color_at(0.5), OFF)

    def test_unknown_state(self):
        with self.assertRaises(ValueError):
            self.led.set_state("party")

    def test_disabled_led_start_stop_is_noop(self):
        self.led.start()
        self.led.stop()


class OutputsColorTest(unittest.TestCase):
    def test_mapping(self):
        cases = {
            (0, 0, 0, 0): OFF,
            (1, 0, 0, 0): RED,
            (0, 1, 0, 0): GREEN,
            (0, 0, 1, 0): BLUE,
            (1, 1, 0, 0): YELLOW,
            (1, 0, 1, 0): MAGENTA,
            (0, 0, 0, 1): WHITE,
            (1, 0, 0, 1): WHITE,
        }
        for do, color in cases.items():
            with self.subTest(do=do):
                self.assertEqual(outputs_color(do), color)


class SysfsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        triggers = {"ledR": "none [gpio] heartbeat", "ledG": "[none] gpio heartbeat", "ledB": "none gpio [heartbeat]"}
        brightness = {"ledR": "0", "ledG": "1", "ledB": "1"}
        for ch in CHANNELS:
            os.makedirs(os.path.join(self.dir, ch))
            self._put(ch, "trigger", triggers[ch])
            self._put(ch, "brightness", brightness[ch])

    def tearDown(self):
        self.tmp.cleanup()

    def _put(self, ch, attr, value):
        with open(os.path.join(self.dir, ch, attr), "w") as f:
            f.write(value)

    def _get(self, ch, attr):
        with open(os.path.join(self.dir, ch, attr)) as f:
            return f.read()

    def test_drives_brightness_and_restores_triggers(self):
        led = StatusLed(self.dir)
        led.set_state("online")
        led.set_outputs((1, 0, 1, 0))
        led.start()
        self.assertEqual([self._get(ch, "trigger") for ch in CHANNELS], ["none"] * 3)

        expected = ["1", "0", "1"]
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and [self._get(ch, "brightness") for ch in CHANNELS] != expected:
            time.sleep(0.01)
        self.assertEqual([self._get(ch, "brightness") for ch in CHANNELS], expected)

        led.stop()
        self.assertEqual(
            [self._get(ch, "trigger") for ch in CHANNELS], ["gpio", "none", "heartbeat"]
        )
        self.assertEqual(self._get("ledG", "brightness"), "1")

    def test_missing_led_disables_quietly(self):
        led = StatusLed(os.path.join(self.dir, "missing"))
        with self.assertLogs("fluxio_sim.led", "WARNING"):
            led.start()
        led.stop()


if __name__ == "__main__":
    unittest.main()
