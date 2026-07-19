import importlib.util
import unittest


def load_remote_module():
    spec = importlib.util.spec_from_file_location("loadcounter_remote", "loadcounter-remote.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LoadCounterRemoteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.remote = load_remote_module()

    def test_normalize_command_maps_keyboard_aliases(self):
        cases = {
            "return": "enter",
            "escape": "esc",
            "debug": "space",
            ".": "dot",
            "7": "digit:7",
            "learn": "learn_start",
            "stop_learning": "learn_stop",
            "cancel": "menu_cancel",
        }

        for raw_command, normalized in cases.items():
            with self.subTest(raw_command=raw_command):
                self.assertEqual(self.remote.normalize_command(raw_command), normalized)

    def test_normalize_command_rejects_service_power_commands(self):
        with self.assertRaises(ValueError):
            self.remote.normalize_command("loadcounter_off")

    def test_key_to_command_maps_common_keys(self):
        self.assertEqual(self.remote.key_to_command(ord("d")), ("space", False))
        self.assertEqual(self.remote.key_to_command(ord("r")), ("count_reset", False))
        self.assertEqual(self.remote.key_to_command(ord("5")), ("digit:5", False))
        self.assertEqual(self.remote.key_to_command(3), (None, True))


if __name__ == "__main__":
    unittest.main()
