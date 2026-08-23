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
            "trigger_distance_cm": 999,
            "neutral_margin_cm": 999,
            "timeout_ms": -1,
            "cooldown_ms": 999_999,
            "brightness_percent": 0,
            "sensor_order": "B/A",
            "debug_mode": True,
            "base_distance_1_cm": "165",
            "base_distance_2_cm": "bad",
        })

        self.assertEqual(settings["trigger_distance_cm"], self.core.MAX_TRIGGER_DISTANCE)
        self.assertEqual(settings["neutral_margin_cm"], self.core.MAX_NEUTRAL_MARGIN)
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

    def test_learning_event_learns_all_detection_parameters(self):
        learning = self.core.default_learning_state()
        learning.update({
            "event_count": 1,
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

        result, status = self.core.analyze_learning_event(learning, self.core.default_settings())

        self.assertEqual(status, "Learned event 1")
        self.assertEqual(result["sensor_order"], self.core.SENSOR_ORDER_AB)
        self.assertEqual(result["timeout_ms"], 1400)
        self.assertEqual(result["base_distance_1_cm"], 100)
        self.assertEqual(result["base_distance_2_cm"], 100)
        self.assertGreaterEqual(result["trigger_distance_cm"], self.core.MIN_TRIGGER_DISTANCE)
        self.assertLess(result["neutral_margin_cm"], result["trigger_distance_cm"])
        self.assertGreaterEqual(result["cooldown_ms"], 1000)

    def test_learning_event_updates_draft_without_changing_live_settings(self):
        settings = self.core.default_settings()
        settings["base_distance_1_cm"] = 100
        settings["base_distance_2_cm"] = 100
        original_settings = settings.copy()
        learning = self.core.default_learning_state()
        self.core.begin_learning_session(learning, settings, 0.0)
        learning["samples"] = [
            {"t": 3.0, "d1": 100, "d2": 100},
            {"t": 7.0, "d1": 99, "d2": 100},
            {"t": 9.7, "d1": 65, "d2": 100},
            {"t": 10.0, "d1": 65, "d2": 60},
            {"t": 11.0, "d1": 100, "d2": 80},
        ]
        self.assertTrue(self.core.mark_learning_event(learning, 10.0))
        previous_logger = self.core.log_event
        self.core.log_event = lambda *args, **kwargs: None
        try:
            changed, status = self.core.update_learning(learning, settings, 12.0, 100, 100)
        finally:
            self.core.log_event = previous_logger

        self.assertTrue(changed)
        self.assertEqual(status, "Learned event 1")
        self.assertEqual(settings, original_settings)
        self.assertNotEqual(learning["draft_settings"]["trigger_distance_cm"], original_settings["trigger_distance_cm"])

    def test_learning_accepts_long_range_neutral_readings_and_a_delayed_tap(self):
        settings = self.core.default_settings()
        settings["base_distance_1_cm"] = 1120
        settings["base_distance_2_cm"] = 234
        learning = self.core.default_learning_state()
        learning.update({
            "event_count": 1,
            "event_at": 10.0,
            "samples": [
                {"t": 1.0, "d1": 1120, "d2": 234},
                {"t": 5.0, "d1": 1120, "d2": 234},
                {"t": 7.0, "d1": 82, "d2": 234},
                {"t": 7.5, "d1": 90, "d2": 87},
                {"t": 8.0, "d1": 1120, "d2": 74},
                {"t": 9.0, "d1": 1120, "d2": 234},
                {"t": 12.0, "d1": 1120, "d2": 234},
            ],
        })

        result, status = self.core.analyze_learning_event(learning, settings)

        self.assertEqual(status, "Learned event 1")
        self.assertEqual(result["sensor_order"], self.core.SENSOR_ORDER_AB)
        self.assertEqual(result["base_distance_1_cm"], 1120)
        self.assertEqual(result["base_distance_2_cm"], 234)
        self.assertEqual(result["trigger_distance_cm"], 80)

    def test_learning_end_saves_draft_and_cancel_discards_it(self):
        settings = self.core.default_settings()
        learning = self.core.default_learning_state()
        self.core.begin_learning_session(learning, settings, 1.0)
        learning["draft_settings"]["trigger_distance_cm"] = 17
        learning["draft_settings"]["neutral_margin_cm"] = 5

        self.assertTrue(self.core.finish_learning_session(learning, settings))
        self.assertEqual(settings["trigger_distance_cm"], 17)
        self.assertEqual(settings["neutral_margin_cm"], 5)
        self.assertFalse(learning["active"])

        self.core.begin_learning_session(learning, settings, 2.0)
        learning["draft_settings"]["trigger_distance_cm"] = 29
        self.assertTrue(self.core.cancel_learning_session(learning))
        self.assertEqual(settings["trigger_distance_cm"], 17)
        self.assertFalse(learning["active"])

    def test_calibration_resets_examples_but_remains_in_draft(self):
        settings = self.core.default_settings()
        learning = self.core.default_learning_state()
        self.core.begin_learning_session(learning, settings, 1.0)
        learning["event_count"] = 2
        learning["results"] = [{"trigger_distance_cm": 10}]
        calibrated = settings.copy()
        calibrated["base_distance_1_cm"] = 123
        calibrated["base_distance_2_cm"] = 145

        self.core.reset_learning_after_calibration(learning, calibrated)

        self.assertEqual(learning["event_count"], 0)
        self.assertEqual(learning["results"], [])
        self.assertEqual(learning["draft_settings"]["base_distance_1_cm"], 123)
        self.assertIsNone(settings["base_distance_1_cm"])

    def test_learning_results_use_median_sensitivity_and_conservative_timing(self):
        settings = self.core.default_settings()
        results = [
            {"trigger_distance_cm": 10, "neutral_margin_cm": 3, "timeout_ms": 1200, "cooldown_ms": 2200, "sensor_order": "A/B"},
            {"trigger_distance_cm": 16, "neutral_margin_cm": 5, "timeout_ms": 1800, "cooldown_ms": 2600, "sensor_order": "A/B"},
            {"trigger_distance_cm": 40, "neutral_margin_cm": 9, "timeout_ms": 1400, "cooldown_ms": 2100, "sensor_order": "B/A"},
        ]

        combined = self.core.combine_learning_results(results, settings)

        self.assertEqual(combined["trigger_distance_cm"], 16)
        self.assertEqual(combined["neutral_margin_cm"], 9)
        self.assertEqual(combined["timeout_ms"], 1800)
        self.assertEqual(combined["cooldown_ms"], 2600)
        self.assertEqual(combined["sensor_order"], "A/B")

    def trigger_settings(self, sensor_order=None):
        settings = self.core.default_settings()
        settings.update({
            "trigger_distance_cm": 20,
            "neutral_margin_cm": 8,
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
            trigger_threshold_1 = settings["base_distance_1_cm"] - settings["trigger_distance_cm"]
            trigger_threshold_2 = settings["base_distance_2_cm"] - settings["trigger_distance_cm"]
            neutral_threshold_1 = settings["base_distance_1_cm"] - settings["neutral_margin_cm"]
            neutral_threshold_2 = settings["base_distance_2_cm"] - settings["neutral_margin_cm"]
            sensor_a, sensor_b = self.core.logical_sensor_values(settings, filtered_1, filtered_2)
            trigger_threshold_a, trigger_threshold_b = self.core.logical_sensor_values(settings, trigger_threshold_1, trigger_threshold_2)
            neutral_threshold_a, neutral_threshold_b = self.core.logical_sensor_values(settings, neutral_threshold_1, neutral_threshold_2)
            state, event = self.core.process_counter_sample(
                settings,
                state,
                now,
                sensor_a,
                sensor_b,
                trigger_threshold_a,
                trigger_threshold_b,
                neutral_threshold_a,
                neutral_threshold_b,
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
            (0.36, 70, 70),
            (0.6, 100, 100),
        ])

        self.assertEqual(sum(event["counted"] for event in events), 1)
        self.assertEqual(state["last_counted_at"], 0.36)
        self.assertIsNone(state["sensor1_triggered_at"])

    def test_wrong_direction_does_not_count_when_b_is_already_blocked(self):
        events, state = self.run_trigger_stream([
            (0.0, 100, 100),
            (0.1, 100, 70),
            (0.2, 70, 70),
            (0.3, 70, 70),
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

    def test_sustained_occupancy_with_noisy_sensor_b_does_not_keep_incrementing(self):
        settings = self.trigger_settings()
        settings["cooldown_ms"] = 250
        events, state = self.run_trigger_stream(
            [
                (0.0, 70, 70),
                (0.2, 70, 100),
                (0.3, 70, 70),
                (0.6, 70, 70),
                (0.7, 70, 100),
                (0.8, 70, 70),
                (1.1, 70, 70),
                (1.2, 70, 100),
                (1.3, 70, 70),
                (1.6, 70, 70),
                (1.7, 70, 100),
                (1.8, 70, 70),
            ],
            settings=settings,
        )

        counted_events = sum(event["counted"] for event in events)
        self.assertEqual(counted_events, 0, f"sustained occupancy produced {counted_events} counts")
        self.assertIsNone(state["last_counted_at"])

    def test_trigger_distance_controls_how_far_sensor_must_drop(self):
        strict_settings = self.trigger_settings()
        strict_settings["trigger_distance_cm"] = 20
        strict_events, strict_state = self.run_trigger_stream(
            [
                (0.0, 100, 100),
                (0.1, 85, 100),
                (0.2, 85, 70),
                (0.26, 85, 70),
            ],
            settings=strict_settings,
        )

        sensitive_settings = self.trigger_settings()
        sensitive_settings["trigger_distance_cm"] = 10
        sensitive_events, sensitive_state = self.run_trigger_stream(
            [
                (0.0, 100, 100),
                (0.1, 85, 100),
                (0.2, 85, 85),
                (0.26, 85, 85),
            ],
            settings=sensitive_settings,
        )

        self.assertEqual(sum(event["counted"] for event in strict_events), 0)
        self.assertIsNone(strict_state["last_counted_at"])
        self.assertEqual(sum(event["counted"] for event in sensitive_events), 1)
        self.assertEqual(sensitive_state["last_counted_at"], 0.26)

    def test_neutral_margin_requires_full_neutral_before_rearming(self):
        settings = self.trigger_settings()
        settings["cooldown_ms"] = 100
        events, state = self.run_trigger_stream(
            [
                (0.0, 100, 100),
                (0.1, 70, 100),
                (0.2, 70, 70),
                (0.26, 70, 70),
                (0.4, 90, 90),
                (0.8, 90, 90),
                (0.9, 70, 100),
                (1.0, 70, 70),
                (1.3, 100, 100),
                (1.6, 100, 100),
                (1.7, 70, 100),
                (1.8, 70, 70),
                (1.86, 70, 70),
            ],
            settings=settings,
        )

        self.assertEqual(sum(event["counted"] for event in events), 2)
        self.assertFalse(any(event["counted"] for event in events[4:8]))
        self.assertTrue(events[9]["rearmed"])
        self.assertEqual(state["last_counted_at"], 1.86)

    def test_larger_neutral_margin_rearms_when_sensors_are_near_baseline(self):
        settings = self.trigger_settings()
        settings["cooldown_ms"] = 100
        settings["neutral_margin_cm"] = 20
        events, state = self.run_trigger_stream(
            [
                (0.0, 100, 100),
                (0.1, 70, 100),
                (0.2, 70, 70),
                (0.26, 70, 70),
                (0.4, 90, 90),
                (0.7, 90, 90),
                (0.8, 70, 100),
                (0.9, 70, 70),
                (0.96, 70, 70),
            ],
            settings=settings,
        )

        self.assertEqual(sum(event["counted"] for event in events), 2)
        self.assertTrue(events[5]["rearmed"])
        self.assertEqual(state["last_counted_at"], 0.96)

    def test_sensor_b_must_stay_triggered_through_debounce_window(self):
        events, state = self.run_trigger_stream([
            (0.0, 100, 100),
            (0.1, 70, 100),
            (0.2, 70, 70),
            (0.23, 70, 100),
            (0.4, 70, 70),
            (0.46, 70, 70),
        ])

        self.assertFalse(events[2]["counted"])
        self.assertEqual(sum(event["counted"] for event in events), 1)
        self.assertEqual(state["last_counted_at"], 0.46)

    def test_sensor_b_must_be_neutral_after_sensor_a_before_counting(self):
        events, state = self.run_trigger_stream(
            [
                (0.2, 70, 70),
                (0.3, 70, 70),
                (0.5, 70, 70),
                (0.7, 70, 70),
                (1.2, 70, 70),
            ],
            initial_state=self.core.default_trigger_state(sensor1_triggered_at=0.0),
        )

        self.assertEqual(sum(event["counted"] for event in events), 0)
        self.assertTrue(any(event["timed_out"] for event in events))
        self.assertIsNone(state["last_counted_at"])

    def test_sensor_b_must_trigger_before_timeout(self):
        events, state = self.run_trigger_stream([
            (0.0, 100, 100),
            (0.1, 70, 100),
            (1.3, 70, 100),
            (1.4, 70, 70),
            (1.46, 70, 70),
        ])

        self.assertEqual(sum(event["counted"] for event in events), 0)
        self.assertTrue(any(event["timed_out"] for event in events))
        self.assertIsNone(state["last_counted_at"])

    def test_cooldown_suppresses_repeated_counts_until_it_expires(self):
        events, state = self.run_trigger_stream([
            (0.0, 100, 100),
            (0.1, 70, 100),
            (0.2, 70, 70),
            (0.26, 70, 70),
            (0.4, 100, 100),
            (0.8, 70, 100),
            (0.9, 70, 70),
            (2.3, 100, 100),
            (2.6, 100, 100),
            (2.7, 70, 100),
            (2.8, 70, 70),
            (2.86, 70, 70),
        ])

        self.assertEqual(sum(event["counted"] for event in events), 2)
        self.assertTrue(any(event["cooldown_active"] for event in events))
        self.assertEqual(state["last_counted_at"], 2.86)

    def test_saved_ba_order_counts_physical_sensor_2_then_sensor_1(self):
        events, state = self.run_trigger_stream(
            [
                (0.0, 100, 100),
                (0.1, 100, 70),
                (0.3, 70, 70),
                (0.36, 70, 70),
            ],
            settings=self.trigger_settings(sensor_order=self.core.SENSOR_ORDER_BA),
        )

        self.assertEqual(sum(event["counted"] for event in events), 1)
        self.assertEqual(state["last_counted_at"], 0.36)

    def test_ignored_high_reading_does_not_replace_last_valid_distance(self):
        events, _ = self.run_trigger_stream([
            (0.0, 100, 100),
            (0.1, 70, 130),
            (0.2, 70, 70),
            (0.26, 70, 70),
        ])

        self.assertTrue(events[1]["ignored_2"])
        self.assertFalse(events[1]["counted"])
        self.assertTrue(events[3]["counted"])


if __name__ == "__main__":
    unittest.main()
