import glob
import json
import os
import time

from evdev import InputDevice, ecodes

COMMAND_STATE_DIR = "/var/tmp/loadcounter"
KEYBOARD_COMMAND_PATH = os.path.join(COMMAND_STATE_DIR, "keyboard-command.json")

KEY_COMMANDS = {
    ecodes.KEY_SPACE: "space",
    ecodes.KEY_D: "space",
    ecodes.KEY_UP: "up",
    ecodes.KEY_DOWN: "down",
    ecodes.KEY_RIGHT: "right",
    ecodes.KEY_LEFT: "left",
    ecodes.KEY_ENTER: "enter",
    ecodes.KEY_KPENTER: "enter",
    ecodes.KEY_BACKSPACE: "backspace",
    ecodes.KEY_R: "count_reset",
    ecodes.KEY_0: "digit:0",
    ecodes.KEY_1: "digit:1",
    ecodes.KEY_2: "digit:2",
    ecodes.KEY_3: "digit:3",
    ecodes.KEY_4: "digit:4",
    ecodes.KEY_5: "digit:5",
    ecodes.KEY_6: "digit:6",
    ecodes.KEY_7: "digit:7",
    ecodes.KEY_8: "digit:8",
    ecodes.KEY_9: "digit:9",
    ecodes.KEY_KP0: "digit:0",
    ecodes.KEY_KP1: "digit:1",
    ecodes.KEY_KP2: "digit:2",
    ecodes.KEY_KP3: "digit:3",
    ecodes.KEY_KP4: "digit:4",
    ecodes.KEY_KP5: "digit:5",
    ecodes.KEY_KP6: "digit:6",
    ecodes.KEY_KP7: "digit:7",
    ecodes.KEY_KP8: "digit:8",
    ecodes.KEY_KP9: "digit:9",
}


def write_command(command):
    payload = {
        "id": str(time.time_ns()),
        "command": command,
        "created_at": time.time(),
    }
    temp_path = f"{KEYBOARD_COMMAND_PATH}.tmp"
    os.makedirs(COMMAND_STATE_DIR, exist_ok=True)
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, KEYBOARD_COMMAND_PATH)
    print(f"Wrote keyboard command: {command}", flush=True)


def find_keyboard_device():
    print("Scanning input devices for keyboard listener...", flush=True)
    fallback_device = None

    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            device = InputDevice(path)
            capabilities = device.capabilities()
            if ecodes.EV_KEY not in capabilities:
                device.close()
                continue

            key_codes = set(capabilities[ecodes.EV_KEY])
            name = (device.name or "").lower()
            has_space = ecodes.KEY_SPACE in key_codes
            print(f"Keyboard listener saw: {device.path} name={device.name!r} has_space={has_space}", flush=True)

            if has_space and any(term in name for term in ("magic keyboard", "apple", "keyboard")):
                print(f"Using keyboard listener device: {device.path} ({device.name})", flush=True)
                return device

            if has_space and fallback_device is None:
                fallback_device = device
                continue

            device.close()
        except OSError as exc:
            print(f"Failed to inspect {path}: {exc}", flush=True)

    if fallback_device is not None:
        print(f"Using fallback keyboard listener device: {fallback_device.path} ({fallback_device.name})", flush=True)
        return fallback_device

    print("No keyboard device available for listener", flush=True)
    return None


while True:
    device = find_keyboard_device()
    if device is None:
        time.sleep(2.0)
        continue

    try:
        for event in device.read_loop():
            if event.type != ecodes.EV_KEY or event.value != 1:
                continue

            command = KEY_COMMANDS.get(event.code)
            if command is None:
                continue

            write_command(command)
    except OSError as exc:
        print(f"Keyboard listener lost device {device.path}: {exc}", flush=True)
        time.sleep(1.0)
    finally:
        try:
            device.close()
        except OSError:
            pass
