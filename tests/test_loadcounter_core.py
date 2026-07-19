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

    def trigger_settings(self, sensor_order=None):
        settings = self.core.default_settings()
        settings.update({
            "threshold_cm": 20,
            "timeout_ms": 1000,
            "cooldown_ms": 2000,
            "sensor_order": sensor_order or self.core.SENSOR_ORDER_AB,
            "base_distance_1_cm": 100,
            "base_distance_2_cm": 100,
        })
        return settings

    def run_trigger_stream(self, samples, settings=None, initial_state=None):
        settings = settings or self.trigger_settings()
        state = initial_state or self.core.default_trigger_state()
        last_valid_1 = None
        last_valid_2 = None
        events = []

        for now, raw_1, raw_2 in samples:
            filtered_1, ignored_1, last_valid_1 = self.core.effective_distance(
                raw_1,
                settings["base_distance_1_cm"],
                last_valid_1,
            )
            filtered_2, ignored_2, last_valid_2 = self.core.effective_distance(
                raw_2,
                settings["base_distance_2_cm"],
                last_valid_2,
            )
            threshold_1 = settings["base_distance_1_cm"] - settings["threshold_cm"]
            threshold_2 = settings["base_distance_2_cm"] - settings["threshold_cm"]
            sensor_a, sensor_b = self.core.logical_sensor_values(settings, filtered_1, filtered_2)
            threshold_a, threshold_b = self.core.logical_sensor_values(settings, threshold_1, threshold_2)
            state, event = self.core.process_counter_sample(
                settings,
                state,
                now,
                sensor_a,
                sensor_b,
                threshold_a,
                threshold_b,
            )
            event = event.copy()
            event["ignored_1"] = ignored_1
            event["ignored_2"] = ignored_2
            events.append(event)

        return events, state

    def test_count_triggers_when_sensor_a_then_sensor_b_cross_threshold(self):
        events, state = self.run_trigger_stream([
            (0.0, 100, 100),
            (0.1, 70, 100),
            (0.3, 70, 70),
            (0.6, 100, 100),
        ])

        self.assertEqual(sum(event["counted"] for event in events), 1)
        self.assertEqual(state["last_counted_at"], 0.3)
        self.assertIsNone(state["sensor1_triggered_at"])

    def test_wrong_direction_does_not_count_when_b_is_already_blocked(self):
        events, state = self.run_trigger_stream([
            (0.0, 100, 100),
            (0.1, 100, 70),
            (0.2, 70, 70),
            (0.4, 100, 100),
        ])

        self.assertEqual(sum(event["counted"] for event in events), 0)
        self.assertFalse(any(event["timed_out"] for event in events))
        self.assertIsNone(state["last_counted_at"])

    def test_constantly_triggered_sensors_do_not_increment_count(self):
        settings = self.trigger_settings()
        settings["cooldown_ms"] = 250
        events, state = self.run_trigger_stream(
            [
                (0.2, 70, 70),
                (0.3, 70, 70),
                (0.5, 70, 70),
                (0.6, 70, 70),
                (0.8, 70, 70),
                (0.9, 70, 70),
                (1.1, 70, 70),
                (1.2, 70, 70),
                (1.4, 70, 70),
                (1.5, 70, 70),
            ],
            settings=settings,
            initial_state=self.core.default_trigger_state(
                sensor1_triggered_at=0.0,
                sensor2_ready_after_sensor1=True,
            ),
        )

        counted_events = sum(event["counted"] for event in events)
        self.assertEqual(counted_events, 0, f"stuck sensors produced {counted_events} counts")
        self.assertIsNone(state["last_counted_at"])

    def test_sensor_b_must_trigger_before_timeout(self):
        events, state = self.run_trigger_stream([
            (0.0, 100, 100),
            (0.1, 70, 100),
            (1.3, 70, 100),
            (1.4, 70, 70),
        ])

        self.assertEqual(sum(event["counted"] for event in events), 0)
        self.assertTrue(any(event["timed_out"] for event in events))
        self.assertIsNone(state["last_counted_at"])

    def test_cooldown_suppresses_repeated_counts_until_it_expires(self):
        events, state = self.run_trigger_stream([
            (0.0, 100, 100),
            (0.1, 70, 100),
            (0.2, 70, 70),
            (0.4, 100, 100),
            (0.8, 70, 100),
            (0.9, 70, 70),
            (2.3, 100, 100),
            (2.4, 70, 100),
            (2.5, 70, 70),
        ])

        self.assertEqual(sum(event["counted"] for event in events), 2)
        self.assertTrue(any(event["cooldown_active"] for event in events))
        self.assertEqual(state["last_counted_at"], 2.5)

    def test_saved_ba_order_counts_physical_sensor_2_then_sensor_1(self):
        events, state = self.run_trigger_stream(
            [
                (0.0, 100, 100),
                (0.1, 100, 70),
                (0.3, 70, 70),
            ],
            settings=self.trigger_settings(sensor_order=self.core.SENSOR_ORDER_BA),
        )

        self.assertEqual(sum(event["counted"] for event in events), 1)
        self.assertEqual(state["last_counted_at"], 0.3)

    def test_ignored_high_reading_does_not_replace_last_valid_distance(self):
        events, _ = self.run_trigger_stream([
            (0.0, 100, 100),
            (0.1, 70, 130),
            (0.2, 70, 70),
        ])

        self.assertTrue(events[1]["ignored_2"])
        self.assertFalse(events[1]["counted"])
        self.assertTrue(events[2]["counted"])


if __name__ == "__main__":
    unittest.main()
