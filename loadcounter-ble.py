#!/usr/bin/env python3
import asyncio
import json
import os
import signal
import subprocess
import time

from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType, PropertyAccess
from dbus_next.errors import DBusError
from dbus_next.service import ServiceInterface, dbus_property, method


BLUEZ_SERVICE_NAME = "org.bluez"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
LE_ADVERTISEMENT_IFACE = "org.bluez.LEAdvertisement1"

APP_PATH = "/com/loadcounter/ble"
SERVICE_PATH = f"{APP_PATH}/service0"
COMMAND_CHARACTERISTIC_PATH = f"{SERVICE_PATH}/char0"
STATUS_CHARACTERISTIC_PATH = f"{SERVICE_PATH}/char1"
ADVERTISEMENT_PATH = f"{APP_PATH}/advertisement0"

LOADCOUNTER_SERVICE_UUID = "8fd2f4f8-a7b2-4b2d-a59f-4b2c64850a95"
COMMAND_CHARACTERISTIC_UUID = "8fd2f4f9-a7b2-4b2d-a59f-4b2c64850a95"
STATUS_CHARACTERISTIC_UUID = "8fd2f4fa-a7b2-4b2d-a59f-4b2c64850a95"

COMMAND_STATE_DIR = "/var/tmp/loadcounter"
KEYBOARD_COMMAND_PATH = os.path.join(COMMAND_STATE_DIR, "keyboard-command.json")
LEARNING_STATE_PATH = os.path.join(COMMAND_STATE_DIR, "learning-state.json")
COUNTER_STATE_DIR = "/var/lib/loadcounter"
COUNTER_STATE_PATH = os.path.join(COUNTER_STATE_DIR, "counter-state.txt")
SETTINGS_STATE_PATH = os.path.join(COUNTER_STATE_DIR, "settings.json")
DEVICE_NAME = "LoadCounter"
LOADCOUNTER_PROGRAM_SERVICE = "loadcounter.service"

MIN_TRIGGER_DISTANCE = 5
MAX_TRIGGER_DISTANCE = 300
MIN_NEUTRAL_MARGIN = 0
MAX_NEUTRAL_MARGIN = 300
MIN_TIMEOUT_MS = 100
MAX_TIMEOUT_MS = 120_000
MIN_COOLDOWN_MS = 0
MAX_COOLDOWN_MS = 120_000
MIN_BRIGHTNESS_PERCENT = 1
MAX_BRIGHTNESS_PERCENT = 100
MAX_COUNTER = 999999
SENSOR_ORDER_AB = "A/B"
SENSOR_ORDER_BA = "B/A"

KEYBOARD_COMMANDS = {
    "enter",
    "esc",
    "space",
    "up",
    "down",
    "left",
    "right",
    "backspace",
    "dot",
    "count_reset",
    "yes",
    "no",
    "calibrate",
    "play_animation",
    "reset_defaults",
    "menu_open",
    "menu_cancel",
    "learn_start",
    "learn_stop",
}

SERVICE_COMMANDS = {
    "loadcounter_start",
    "loadcounter_stop",
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


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def int_value(raw_value, minimum, maximum, label):
    try:
        return clamp(int(float(raw_value)), minimum, maximum)
    except ValueError as exc:
        raise ValueError(f"invalid {label} value: {raw_value}") from exc


def milliseconds_value(raw_value, minimum, maximum, label):
    try:
        return clamp(round(float(raw_value) * 1000), minimum, maximum)
    except ValueError as exc:
        raise ValueError(f"invalid {label} value: {raw_value}") from exc


def bool_value(raw_value, label):
    value = raw_value.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"invalid {label} value: {raw_value}")


def normalize_sensor_order(raw_value):
    value = raw_value.strip().upper().replace(" ", "")
    if value in ("A/B", "AB"):
        return SENSOR_ORDER_AB
    if value in ("B/A", "BA"):
        return SENSOR_ORDER_BA
    raise ValueError(f"invalid sensor order: {raw_value}")


def load_counter():
    try:
        with open(COUNTER_STATE_PATH, "r", encoding="utf-8") as handle:
            return clamp(int(handle.read().strip() or "0"), 0, MAX_COUNTER)
    except (FileNotFoundError, OSError, ValueError):
        return 0


def load_settings():
    defaults = {
        "trigger_distance_cm": 40,
        "neutral_margin_cm": 8,
        "timeout_ms": 20_000,
        "cooldown_ms": 10_000,
        "brightness_percent": 100,
        "debug_mode": False,
        "sensor_order": SENSOR_ORDER_AB,
        "base_distance_1_cm": None,
        "base_distance_2_cm": None,
    }
    try:
        with open(SETTINGS_STATE_PATH, "r", encoding="utf-8") as handle:
            raw_settings = json.load(handle)
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return defaults
    if not isinstance(raw_settings, dict):
        return defaults

    settings = defaults.copy()
    for key, minimum, maximum in (
        ("trigger_distance_cm", MIN_TRIGGER_DISTANCE, MAX_TRIGGER_DISTANCE),
        ("neutral_margin_cm", MIN_NEUTRAL_MARGIN, MAX_NEUTRAL_MARGIN),
        ("timeout_ms", MIN_TIMEOUT_MS, MAX_TIMEOUT_MS),
        ("cooldown_ms", MIN_COOLDOWN_MS, MAX_COOLDOWN_MS),
        ("brightness_percent", MIN_BRIGHTNESS_PERCENT, MAX_BRIGHTNESS_PERCENT),
    ):
        try:
            raw_value = raw_settings.get(key, settings[key])
            if key == "trigger_distance_cm":
                raw_value = raw_settings.get("trigger_distance_cm", raw_settings.get("threshold_cm", settings[key]))
            settings[key] = clamp(int(float(raw_value)), minimum, maximum)
        except (TypeError, ValueError):
            pass
    settings["debug_mode"] = bool(raw_settings.get("debug_mode", settings["debug_mode"]))
    try:
        settings["sensor_order"] = normalize_sensor_order(str(raw_settings.get("sensor_order", settings["sensor_order"])))
    except ValueError:
        settings["sensor_order"] = SENSOR_ORDER_AB
    for key in ("base_distance_1_cm", "base_distance_2_cm"):
        raw_value = raw_settings.get(key)
        if raw_value is None:
            settings[key] = None
            continue
        try:
            settings[key] = max(1, int(raw_value))
        except (TypeError, ValueError):
            settings[key] = None
    return settings


def normalize_command(command_text):
    command = command_text.strip().lower()
    if not command:
        raise ValueError("empty command")
    if command == "open_menu":
        return "menu_open"
    if command in ("close_menu", "cancel_menu"):
        return "menu_cancel"
    if command in ("learn", "start_learning", "learning_start"):
        return "learn_start"
    if command in ("stop_learning", "learning_stop"):
        return "learn_stop"
    if command in ("loadcounter_on", "load_counter_on", "program_on", "counter_on"):
        return "loadcounter_start"
    if command in ("loadcounter_off", "load_counter_off", "program_off", "counter_off"):
        return "loadcounter_stop"
    if command in KEYBOARD_COMMANDS:
        return command
    if command in SERVICE_COMMANDS:
        return command
    if command.isdigit() and len(command) == 1:
        return f"digit:{command}"
    if command.startswith("digit:") and command[6:].isdigit() and len(command[6:]) == 1:
        return command
    if command in ("reset", "counter_reset"):
        return "count_reset"
    if command in ("brightness_up", "brightness_down", "sensor_order_toggle"):
        return command
    if command.startswith("brightness:"):
        raw_percent = command.split(":", 1)[1]
        percent = int_value(raw_percent, MIN_BRIGHTNESS_PERCENT, MAX_BRIGHTNESS_PERCENT, "brightness")
        return f"brightness:{percent}"
    if command.startswith("counter:") or command.startswith("count:"):
        raw_count = command.split(":", 1)[1]
        return f"counter:{int_value(raw_count, 0, MAX_COUNTER, 'counter')}"
    if command.startswith(("trigger_distance:", "trigger_distance_cm:", "threshold:", "threshold_cm:")):
        raw_distance = command.split(":", 1)[1]
        trigger_distance = int_value(raw_distance, MIN_TRIGGER_DISTANCE, MAX_TRIGGER_DISTANCE, "trigger distance")
        return f"trigger_distance_cm:{trigger_distance}"
    if command.startswith(("neutral_margin:", "neutral_margin_cm:")):
        raw_margin = command.split(":", 1)[1]
        neutral_margin = int_value(raw_margin, MIN_NEUTRAL_MARGIN, MAX_NEUTRAL_MARGIN, "neutral margin")
        return f"neutral_margin_cm:{neutral_margin}"
    if command.startswith("timeout_ms:"):
        raw_timeout = command.split(":", 1)[1]
        timeout_ms = int_value(raw_timeout, MIN_TIMEOUT_MS, MAX_TIMEOUT_MS, "timeout")
        return f"timeout_ms:{timeout_ms}"
    if command.startswith("timeout:") or command.startswith("timeout_s:"):
        raw_timeout = command.split(":", 1)[1]
        timeout_ms = milliseconds_value(raw_timeout, MIN_TIMEOUT_MS, MAX_TIMEOUT_MS, "timeout")
        return f"timeout_ms:{timeout_ms}"
    if command.startswith("cooldown_ms:"):
        raw_cooldown = command.split(":", 1)[1]
        cooldown_ms = int_value(raw_cooldown, MIN_COOLDOWN_MS, MAX_COOLDOWN_MS, "cooldown")
        return f"cooldown_ms:{cooldown_ms}"
    if command.startswith("cooldown:") or command.startswith("cooldown_s:"):
        raw_cooldown = command.split(":", 1)[1]
        cooldown_ms = milliseconds_value(raw_cooldown, MIN_COOLDOWN_MS, MAX_COOLDOWN_MS, "cooldown")
        return f"cooldown_ms:{cooldown_ms}"
    if command.startswith("sensor_order:") or command.startswith("sensors:"):
        raw_order = command.split(":", 1)[1]
        return f"sensor_order:{normalize_sensor_order(raw_order)}"
    if command.startswith("debug:") or command.startswith("debug_mode:"):
        raw_debug = command.split(":", 1)[1]
        return f"debug:{1 if bool_value(raw_debug, 'debug') else 0}"
    raise ValueError(f"unknown command: {command_text}")


def systemctl_service(action, service_name):
    result = subprocess.run(
        ["systemctl", action, service_name],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(details or f"systemctl {action} {service_name} failed")


def service_is_active(service_name):
    result = subprocess.run(
        ["systemctl", "is-active", "--quiet", service_name],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
    )
    return result.returncode == 0


def service_status(service_name):
    result = subprocess.run(
        ["systemctl", "is-active", service_name],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    status = (result.stdout or "").strip()
    return status or "unknown"


def save_idle_learning_state():
    payload = default_learning_state()
    temp_path = f"{LEARNING_STATE_PATH}.tmp"
    os.makedirs(COMMAND_STATE_DIR, exist_ok=True)
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
        handle.write("\n")
    os.replace(temp_path, LEARNING_STATE_PATH)


def default_learning_state():
    return {
        "active": False,
        "round": 0,
        "phase": "idle",
        "status": "Idle",
        "countdown_seconds": 0,
        "learned_trigger_distance_cm": None,
        "learned_timeout_ms": None,
        "learned_cooldown_ms": None,
        "learned_sensor_order": None,
    }


def apply_service_command(command):
    if command == "loadcounter_start":
        systemctl_service("start", LOADCOUNTER_PROGRAM_SERVICE)
        return
    if command == "loadcounter_stop":
        save_idle_learning_state()
        clear_command_files()
        systemctl_service("stop", LOADCOUNTER_PROGRAM_SERVICE)
        return
    raise ValueError(f"unsupported service command: {command}")


def clear_command_files():
    for path in (
        KEYBOARD_COMMAND_PATH,
        f"{KEYBOARD_COMMAND_PATH}.tmp",
    ):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def load_learning_state():
    defaults = default_learning_state()
    try:
        with open(LEARNING_STATE_PATH, "r", encoding="utf-8") as handle:
            raw_state = json.load(handle)
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return defaults
    if not isinstance(raw_state, dict):
        return defaults

    learning = defaults.copy()
    for key in learning:
        if key in raw_state:
            learning[key] = raw_state[key]
    learning["active"] = bool(learning["active"])
    for key in ("round", "countdown_seconds"):
        try:
            learning[key] = max(0, int(learning[key]))
        except (TypeError, ValueError):
            learning[key] = defaults[key]
    if raw_state.get("learned_trigger_distance_cm") is None and "learned_threshold_cm" in raw_state:
        learning["learned_trigger_distance_cm"] = raw_state["learned_threshold_cm"]
    for key in ("learned_trigger_distance_cm", "learned_timeout_ms", "learned_cooldown_ms"):
        if learning[key] is None:
            continue
        try:
            learning[key] = int(learning[key])
        except (TypeError, ValueError):
            learning[key] = None
    if learning["learned_sensor_order"] not in (SENSOR_ORDER_AB, SENSOR_ORDER_BA):
        learning["learned_sensor_order"] = None
    learning["phase"] = str(learning["phase"])
    learning["status"] = str(learning["status"])
    return learning


def bytes_for_text(text):
    return text.encode("utf-8")


def state_payload(status_text):
    program_status = service_status(LOADCOUNTER_PROGRAM_SERVICE)
    program_active = program_status == "active"
    return {
        "status": status_text,
        "program": {
            "active": program_active,
            "status": program_status,
        },
        "counter": load_counter(),
        "settings": load_settings(),
        "learning": load_learning_state() if program_active else default_learning_state(),
        "updated_at": time.time(),
    }


class Application(ServiceInterface):
    def __init__(self):
        super().__init__(DBUS_OM_IFACE)
        self.objects = []

    def add(self, obj):
        self.objects.append(obj)

    @method()
    def GetManagedObjects(self) -> "a{oa{sa{sv}}}":
        managed = {}
        for obj in self.objects:
            managed[obj.path] = obj.get_properties()
        return managed


class LoadCounterService(ServiceInterface):
    def __init__(self):
        super().__init__(GATT_SERVICE_IFACE)
        self.path = SERVICE_PATH

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return LOADCOUNTER_SERVICE_UUID

    @dbus_property(access=PropertyAccess.READ)
    def Primary(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def Includes(self) -> "ao":
        return []

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                "UUID": Variant("s", self.UUID),
                "Primary": Variant("b", self.Primary),
                "Includes": Variant("ao", self.Includes),
            }
        }


class CommandCharacteristic(ServiceInterface):
    def __init__(self, status):
        super().__init__(GATT_CHRC_IFACE)
        self.path = COMMAND_CHARACTERISTIC_PATH
        self.status = status

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return COMMAND_CHARACTERISTIC_UUID

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> "o":
        return SERVICE_PATH

    @dbus_property(access=PropertyAccess.READ)
    def Flags(self) -> "as":
        return ["write", "write-without-response"]

    @method()
    def WriteValue(self, value: "ay", options: "a{sv}") -> "":
        try:
            text = bytes(value).decode("utf-8")
            command = normalize_command(text)
            if command in SERVICE_COMMANDS:
                apply_service_command(command)
            else:
                write_command(command)
        except Exception as exc:
            self.status.set_text(f"error: {exc}")
            print(f"Rejected BLE command {list(value)!r}: {exc}", flush=True)
            raise DBusError("org.bluez.Error.Failed", str(exc)) from exc

        self.status.set_text(f"ok: {command}")
        print(f"Wrote BLE command: {command}", flush=True)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                "UUID": Variant("s", self.UUID),
                "Service": Variant("o", self.Service),
                "Flags": Variant("as", self.Flags),
            }
        }


class StatusCharacteristic(ServiceInterface):
    def __init__(self):
        super().__init__(GATT_CHRC_IFACE)
        self.path = STATUS_CHARACTERISTIC_PATH
        self.text = "ready"

    def set_text(self, text):
        self.text = text

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return STATUS_CHARACTERISTIC_UUID

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> "o":
        return SERVICE_PATH

    @dbus_property(access=PropertyAccess.READ)
    def Flags(self) -> "as":
        return ["read"]

    @method()
    def ReadValue(self, options: "a{sv}") -> "ay":
        return bytes_for_text(json.dumps(state_payload(self.text), separators=(",", ":"), sort_keys=True))

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                "UUID": Variant("s", self.UUID),
                "Service": Variant("o", self.Service),
                "Flags": Variant("as", self.Flags),
            }
        }


class Advertisement(ServiceInterface):
    def __init__(self):
        super().__init__(LE_ADVERTISEMENT_IFACE)
        self.path = ADVERTISEMENT_PATH

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> "s":
        return "peripheral"

    @dbus_property(access=PropertyAccess.READ)
    def ServiceUUIDs(self) -> "as":
        return [LOADCOUNTER_SERVICE_UUID]

    @dbus_property(access=PropertyAccess.READ)
    def LocalName(self) -> "s":
        return DEVICE_NAME

    @dbus_property(access=PropertyAccess.READ)
    def Includes(self) -> "as":
        return ["tx-power"]

    @method()
    def Release(self) -> "":
        print("BLE advertisement released", flush=True)


async def get_bluez_object_manager(bus):
    introspection = await bus.introspect(BLUEZ_SERVICE_NAME, "/")
    bluez = bus.get_proxy_object(BLUEZ_SERVICE_NAME, "/", introspection)
    return bluez.get_interface(DBUS_OM_IFACE)


async def find_adapter(bus):
    manager = await get_bluez_object_manager(bus)
    objects = await manager.call_get_managed_objects()
    for path, interfaces in objects.items():
        if GATT_MANAGER_IFACE in interfaces and LE_ADVERTISING_MANAGER_IFACE in interfaces:
            return path
    raise RuntimeError("No Bluetooth adapter with GATT and LE advertising support found")


async def get_interface(bus, path, interface_name):
    introspection = await bus.introspect(BLUEZ_SERVICE_NAME, path)
    proxy = bus.get_proxy_object(BLUEZ_SERVICE_NAME, path, introspection)
    return proxy.get_interface(interface_name)


async def set_adapter_powered(bus, adapter_path):
    properties = await get_interface(bus, adapter_path, "org.freedesktop.DBus.Properties")
    await properties.call_set("org.bluez.Adapter1", "Powered", Variant("b", True))


async def main():
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    adapter_path = await find_adapter(bus)
    await set_adapter_powered(bus, adapter_path)

    app = Application()
    service = LoadCounterService()
    status = StatusCharacteristic()
    command = CommandCharacteristic(status)
    advertisement = Advertisement()

    for obj in (service, command, status):
        app.add(obj)

    bus.export(APP_PATH, app)
    bus.export(service.path, service)
    bus.export(command.path, command)
    bus.export(status.path, status)
    bus.export(advertisement.path, advertisement)

    gatt_manager = await get_interface(bus, adapter_path, GATT_MANAGER_IFACE)
    advertising_manager = await get_interface(bus, adapter_path, LE_ADVERTISING_MANAGER_IFACE)

    await gatt_manager.call_register_application(APP_PATH, {})
    await advertising_manager.call_register_advertisement(ADVERTISEMENT_PATH, {})
    print(f"Advertising {DEVICE_NAME} BLE control service on {adapter_path}", flush=True)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        await stop_event.wait()
    finally:
        try:
            await advertising_manager.call_unregister_advertisement(ADVERTISEMENT_PATH)
        except Exception as exc:
            print(f"Failed to unregister advertisement: {exc}", flush=True)
        try:
            await gatt_manager.call_unregister_application(APP_PATH)
        except Exception as exc:
            print(f"Failed to unregister GATT application: {exc}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
