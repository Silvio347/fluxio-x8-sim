import random
import unittest

from fluxio_sim.io_source import RandomIo, make_io_source


class RandomIoTest(unittest.TestCase):
    def setUp(self):
        self.io = RandomIo(random.Random(1234))

    def test_ai_stays_inside_ranges(self):
        self.io.set_ai_ranges([(0.0, 10.0), (20.0, 60.0), (5.0, 5.0), (100.0, 0.0)])
        for _ in range(5000):
            self.io.step()
            ai = self.io.read().ai
            self.assertTrue(0.0 <= ai[0] <= 10.0)
            self.assertTrue(20.0 <= ai[1] <= 60.0)
            self.assertEqual(ai[2], 5.0)
            self.assertTrue(0.0 <= ai[3] <= 100.0)

    def test_ai_actually_moves(self):
        values = set()
        for _ in range(50):
            self.io.step()
            values.add(self.io.read().ai[0])
        self.assertGreater(len(values), 10)

    def test_new_range_recenters_out_of_range_values(self):
        self.io.set_ai_ranges([(500.0, 600.0)] * 4)
        self.assertEqual(self.io.read().ai, (550.0, 550.0, 550.0, 550.0))

    def test_di_toggles_sometimes(self):
        flips = 0
        last = self.io.read().di
        for _ in range(1000):
            self.io.step()
            now = self.io.read().di
            flips += sum(a != b for a, b in zip(last, now))
            last = now
        # 4 inputs * 1000 steps * 2% ~= 80 flips
        self.assertTrue(40 < flips < 140, flips)

    def test_outputs_hold_commands(self):
        self.io.set_do(0, 5)
        self.io.set_ao(2, 12)
        self.io.step()
        snap = self.io.read()
        self.assertEqual(snap.do, (1, 0, 0, 0))
        self.assertEqual(snap.ao, (0.0, 0.0, 12.0, 0.0))

    def test_factory(self):
        self.assertIsInstance(make_io_source("random"), RandomIo)
        with self.assertRaises(ValueError):
            make_io_source("m4")


if __name__ == "__main__":
    unittest.main()
