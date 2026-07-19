import sys
import types
import unittest


def load_counter_definitions():
    sys.modules.setdefault("serial", types.SimpleNamespace())
    sys.modules.setdefault("adafruit_us100", types.SimpleNamespace())
    sys.modules["rgbmatrix"] = types.SimpleNamespace(
        RGBMatrix=object,
        RGBMatrixOptions=object,
        graphics=types.SimpleNamespace(Color=lambda r, g, b: (r, g, b)),
    )

    with open("load-counter.py", "r", encoding="utf-8") as handle:
        source = handle.read()
    definitions, _, _ = source.partition("\nuart1 =")
    module = types.ModuleType("load_counter_definitions")
    module.__file__ = "load-counter.py"
    exec(compile(definitions, "load-counter.py", "exec"), module.__dict__)
    return module


class LoadCounterCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = load_counter_definitions()

    def test_sanitize_settings_clamps_values_and_sensor_order(self):
        settings = self.core.sanitize_settings({
            "threshold_cm": 999,
            "timeout_ms": -1,
            "cooldown_ms": 999_999,
            "brightness_percent": 0,
            "sensor_order": "B/A",
            "debug_mode": True,
            "base_distance_1_cm": "165",
            "base_distance_2_cm": "bad",
        })

        self.assertEqual(settings["threshold_cm"], self.core.MAX_THRESHOLD)
        self.assertEqual(settings["timeout_ms"], self.core.MIN_TIMEOUT_MS)
        self.assertEqual(settings["cooldown_ms"], self.core.MAX_COOLDOWN_MS)
        self.assertEqual(settings["brightness_percent"], self.core.MIN_BRIGHTNESS_PERCENT)
        self.assertEqual(settings["sensor_order"], self.core.SENSOR_ORDER_BA)
        self.assertTrue(settings["debug_mode"])
        self.assertEqual(settings["base_distance_1_cm"], 165)
        self.assertIsNone(settings["base_distance_2_cm"])

    def test_logical_sensor_values_follow_saved_order(self):
        settings = self.core.default_settings()
        self.assertEqual(self.core.logical_sensor_values(settings, "one", "two"), ("one", "two"))

        settings["sensor_order"] = self.core.SENSOR_ORDER_BA
        self.assertEqual(self.core.logical_sensor_values(settings, "one", "two"), ("two", "one"))
        self.assertEqual(self.core.toggle_sensor_order(settings["sensor_order"]), self.core.SENSOR_ORDER_AB)

    def test_effective_distance_ignores_readings_above_baseline_margin(self):
        distance, ignored, last_valid = self.core.effective_distance(170, 165, 164)

        self.assertEqual(distance, 164)
        self.assertTrue(ignored)
        self.assertEqual(last_valid, 164)

    def test_learning_round_learns_order_and_timing(self):
        learning = self.core.default_learning_state()
        learning.update({
            "round": 1,
            "event_at": 10.0,
            "samples": [
                {"t": 0.0, "d1": 100, "d2": 100},
                {"t": 4.0, "d1": 100, "d2": 100},
                {"t": 8.0, "d1": 100, "d2": 100},
                {"t": 9.0, "d1": 99, "d2": 100},
                {"t": 10.0, "d1": 70, "d2": 100},
                {"t": 10.4, "d1": 70, "d2": 65},
                {"t": 11.0, "d1": 95, "d2": 80},
                {"t": 12.0, "d1": 100, "d2": 100},
            ],
        })

        result, status = self.core.analyze_learning_round(learning, self.core.default_settings())

        self.assertEqual(status, "LEARN OK")
        self.assertEqual(result["sensor_order"], self.core.SENSOR_ORDER_AB)
        self.assertEqual(result["timeout_ms"], 1400)
        self.assertEqual(result["base_distance_1_cm"], 100)
        self.assertEqual(result["base_distance_2_cm"], 100)
        self.assertGreaterEqual(result["threshold_cm"], self.core.MIN_THRESHOLD)
        self.assertGreaterEqual(result["cooldown_ms"], 1000)


if __name__ == "__main__":
    unittest.main()
