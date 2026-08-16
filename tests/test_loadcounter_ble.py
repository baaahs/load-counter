import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock


def load_ble_module():
    sys.modules.setdefault("dbus_next", types.SimpleNamespace(Variant=lambda signature, value: value))
    sys.modules.setdefault(
        "dbus_next.aio",
        types.SimpleNamespace(MessageBus=object),
    )
    sys.modules.setdefault(
        "dbus_next.constants",
        types.SimpleNamespace(BusType=types.SimpleNamespace(SYSTEM="system"), PropertyAccess=types.SimpleNamespace(READ="read")),
    )
    sys.modules.setdefault(
        "dbus_next.errors",
        types.SimpleNamespace(DBusError=RuntimeError),
    )
    sys.modules.setdefault(
        "dbus_next.service",
        types.SimpleNamespace(
            ServiceInterface=object,
            dbus_property=lambda *args, **kwargs: (lambda function: property(function)),
            method=lambda *args, **kwargs: (lambda function: function),
        ),
    )
    spec = importlib.util.spec_from_file_location("loadcounter_ble", "loadcounter-ble.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LoadCounterBleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ble = load_ble_module()

    def test_normalize_command_accepts_direct_settings_and_aliases(self):
        cases = {
            "open_menu": "menu_open",
            "close_menu": "menu_cancel",
            "learn": "learn_start",
            "stop_learning": "learn_end",
            "learning_calibrate": "learn_calibrate",
            "learning_count": "learn_count",
            "cancel_learning": "learn_cancel",
            "counter:42": "counter:42",
            "threshold:999": "trigger_distance_cm:300",
            "trigger_distance_cm:42": "trigger_distance_cm:42",
            "neutral_margin:12": "neutral_margin_cm:12",
            "timeout:1.5": "timeout_ms:1500",
            "cooldown_s:2": "cooldown_ms:2000",
            "brightness:0": "brightness:1",
            "sensors:ba": "sensor_order:B/A",
            "loadcounter_off": "loadcounter_stop",
            "program_on": "loadcounter_start",
        }

        for raw_command, normalized in cases.items():
            with self.subTest(raw_command=raw_command):
                self.assertEqual(self.ble.normalize_command(raw_command), normalized)

    def test_normalize_command_rejects_unknown_commands(self):
        with self.assertRaises(ValueError):
            self.ble.normalize_command("not_a_real_command")

    def test_write_command_is_atomic_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            command_path = os.path.join(temp_dir, "keyboard-command.json")
            with mock.patch.object(self.ble, "COMMAND_STATE_DIR", temp_dir), mock.patch.object(
                self.ble,
                "KEYBOARD_COMMAND_PATH",
                command_path,
            ):
                self.ble.write_command("menu_open")

            with open(command_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)

        self.assertEqual(payload["command"], "menu_open")
        self.assertIn("id", payload)
        self.assertIn("created_at", payload)

    def test_load_learning_state_sanitizes_saved_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            learning_path = os.path.join(temp_dir, "learning-state.json")
            with open(learning_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "active": 1,
                        "event_count": "3",
                        "phase": "ready",
                        "status": "Learn_OK",
                        "trigger_distance_cm": "12",
                        "neutral_margin_cm": "4",
                        "timeout_ms": "1400",
                        "cooldown_ms": "2500",
                        "sensor_order": "B/A",
                        "base_distance_1_cm": "120",
                        "base_distance_2_cm": "140",
                    },
                    handle,
                )

            with mock.patch.object(self.ble, "LEARNING_STATE_PATH", learning_path):
                learning = self.ble.load_learning_state()

        self.assertTrue(learning["active"])
        self.assertEqual(learning["event_count"], 3)
        self.assertEqual(learning["trigger_distance_cm"], 12)
        self.assertEqual(learning["neutral_margin_cm"], 4)
        self.assertEqual(learning["sensor_order"], "B/A")
        self.assertEqual(learning["base_distance_2_cm"], 140)

    def test_state_payload_reports_program_and_hides_learning_when_program_is_stopped(self):
        with mock.patch.object(self.ble, "service_status", return_value="inactive"), mock.patch.object(
            self.ble,
            "load_counter",
            return_value=5,
        ), mock.patch.object(self.ble, "load_settings", return_value={"trigger_distance_cm": 40, "neutral_margin_cm": 8}), mock.patch.object(
            self.ble,
            "load_learning_state",
            return_value={"active": True},
        ):
            payload = self.ble.state_payload("ready")

        self.assertEqual(payload["program"], {"active": False, "status": "inactive"})
        self.assertEqual(payload["counter"], 5)
        self.assertFalse(payload["learning"]["active"])

    def test_apply_service_command_stops_program_without_stopping_ble(self):
        calls = []

        def fake_systemctl(action, service_name):
            calls.append((action, service_name))

        with mock.patch.object(self.ble, "systemctl_service", side_effect=fake_systemctl), mock.patch.object(
            self.ble,
            "save_idle_learning_state",
        ) as save_idle, mock.patch.object(self.ble, "clear_command_files") as clear_commands:
            self.ble.apply_service_command("loadcounter_stop")

        save_idle.assert_called_once_with()
        clear_commands.assert_called_once_with()
        self.assertEqual(calls, [("stop", self.ble.LOADCOUNTER_PROGRAM_SERVICE)])


if __name__ == "__main__":
    unittest.main()
