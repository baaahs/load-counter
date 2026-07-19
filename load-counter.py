import json
import math
import os
import random
import time
from datetime import datetime

from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

import adafruit_us100
import serial

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_THRESHOLD = 40  # cm
DEFAULT_TIMEOUT_MS = 20_000
DEFAULT_COOLDOWN_MS = 10_000
DEFAULT_BRIGHTNESS_PERCENT = 100
WIDTH = 64
HEIGHT = 32
COUNT_TOP = 10
FOUNTAIN_Y_OFFSET = 0
COUNTER_STATE_DIR = "/var/lib/loadcounter"
COUNTER_STATE_PATH = os.path.join(COUNTER_STATE_DIR, "counter-state.txt")
SETTINGS_STATE_PATH = os.path.join(COUNTER_STATE_DIR, "settings.json")
EVENT_LOG_PATH = os.path.join(COUNTER_STATE_DIR, "events.jsonl")
COMMAND_STATE_DIR = "/var/tmp/loadcounter"
KEYBOARD_COMMAND_PATH = os.path.join(COMMAND_STATE_DIR, "keyboard-command.json")
LEARNING_STATE_PATH = os.path.join(COMMAND_STATE_DIR, "learning-state.json")
PRIOR_COUNTER_STATE_PATH = "/var/tmp/loadcounter/counter-state.txt"
LEGACY_COUNTER_STATE_PATH = os.path.join(BASE_DIR, "counter-state.txt")

FOUNTAIN_STAGGER = 3
FOUNTAIN_FRAME_DELAY = 0.029
BOOT_HOLD_SECONDS = 1.0
BOOT_BACKGROUND = (0, 0, 0)
BOOT_FADE_STEPS = 8
BOOT_FADE_FRAME_DELAY = 0.05
DEFAULT_DEBUG_MODE = False
STATUS_MESSAGE_SECONDS = 2.0
COUNT_TRIGGER_FLASH_SECONDS = 1.0
MIN_THRESHOLD = 5
MAX_THRESHOLD = 300
MIN_TIMEOUT_MS = 100
MAX_TIMEOUT_MS = 120_000
MIN_COOLDOWN_MS = 0
MAX_COOLDOWN_MS = 120_000
MIN_BRIGHTNESS_PERCENT = 1
MAX_BRIGHTNESS_PERCENT = 100
MAX_COUNTER = 999999
CALIBRATION_SECONDS = 10.0
LEARNING_COUNTDOWN_SECONDS = 10.0
LEARNING_EVENT_EARLY_SECONDS = 1.5
LEARNING_EVENT_LATE_SECONDS = 2.0
LEARNING_MIN_DROP_CM = 3.0
LEARNING_THRESHOLD_MARGIN_CM = 2.0
LEARNING_TIMEOUT_MARGIN_SECONDS = 1.0
LEARNING_COOLDOWN_MARGIN_SECONDS = 1.5
IGNORE_MARGIN_CM = 1
CALIBRATION_CLUSTER_SPAN_CM = 5
BDF_GLYPHS = {}
SENSOR_ORDER_AB = "A/B"
SENSOR_ORDER_BA = "B/A"
BOOT_TONE_MAP = {
    " ": (0, 0, 0),
    ".": (16, 16, 16),
    ":": (64, 64, 64),
    "-": (112, 112, 112),
    "=": (168, 168, 168),
    "#": (232, 232, 232),
}
COUNT_RAINBOW_STOPS = [
    (255, 40, 40),
    (255, 140, 0),
    (255, 235, 0),
    (50, 220, 80),
    (0, 185, 255),
    (90, 100, 255),
    (190, 70, 255),
]
BOOT_LOGO_ROWS = [
    "      :::....:::      :::....:::      ",
    "    :::.........::  ::.........:::    ",
    "   ::.............::.............::   ",
    "  :................................:  ",
    " ::................................:: ",
    " :..=####=..................=####=..: ",
    ":...:-####..................####-:...:",
    ":.....:-##..................##-:.....:",
    ":...........::..........::...........:",
    "...........:=#=........=#=:...........",
    "...........:=.##::::::##.=:...........",
    "...........:=-##########-=:...........",
    "............=############=............",
    ":...........=############=...........:",
    ":...........=############=...........:",
    " :..........-=##########=-..........: ",
    " :..........:=##########=:..........: ",
    "  :..........=##########=..........:  ",
    "  :..........-=########=-..........:  ",
    "   :.........:=########=:.........:   ",
    "    :.........=########=.........:    ",
    "     :........-=######=-........:     ",
    "     ::.......:=######=:.......::     ",
    "       ........=#=##=#=........       ",
    "        :......=##--##=......:        ",
    "         :.....-=####=-.....:         ",
    "          :.....=----=.....:          ",
    "            :...:====:...:            ",
    "            ::..........::            ",
    "              ::......::              ",
    "                :....:                ",
    "                  ..                  ",
]

MENU_ITEMS = [
    {"id": "calibrate", "label": "CAL", "type": "action"},
    {"id": "counter_value", "label": "COUNT", "type": "int", "step": 1, "minimum": 0, "maximum": MAX_COUNTER},
    {"id": "threshold_cm", "label": "THRESH (cm)", "type": "int", "step": 1, "minimum": MIN_THRESHOLD, "maximum": MAX_THRESHOLD},
    {"id": "timeout_ms", "label": "TIME (s)", "type": "float", "step": 100, "minimum": MIN_TIMEOUT_MS, "maximum": MAX_TIMEOUT_MS},
    {"id": "cooldown_ms", "label": "COOLDWN (s)", "type": "float", "step": 100, "minimum": MIN_COOLDOWN_MS, "maximum": MAX_COOLDOWN_MS},
    {"id": "brightness_percent", "label": "BRIGHT", "type": "int", "step": 5, "minimum": MIN_BRIGHTNESS_PERCENT, "maximum": MAX_BRIGHTNESS_PERCENT},
    {"id": "sensor_order", "label": "SENSORS", "type": "order"},
    {"id": "debug_mode", "label": "DEBUG", "type": "bool"},
    {"id": "play_animation", "label": "PLAY", "type": "action"},
    {"id": "reset_defaults", "label": "RESET", "type": "action"},
    {"id": "save_exit", "label": "EXIT", "type": "action"},
]


def text_width(font, text):
    return sum(font.CharacterWidth(ord(char)) for char in text)


def fill_ellipse(canvas, cx, cy, rx, ry, color):
    if rx <= 0 or ry <= 0:
        return

    rr_x = rx * rx
    rr_y = ry * ry
    rxy = rr_x * rr_y
    for y in range(max(0, cy - ry), min(HEIGHT, cy + ry + 1)):
        dy = y - cy
        dy_term = dy * dy * rr_x
        for x in range(max(0, cx - rx), min(WIDTH, cx + rx + 1)):
            dx = x - cx
            if dx * dx * rr_y + dy_term <= rxy:
                canvas.SetPixel(x, y, *color)


def fill_circle(canvas, cx, cy, radius, color):
    fill_ellipse(canvas, cx, cy, radius, radius, color)


def fill_triangle(canvas, p1, p2, p3, color):
    points = sorted([p1, p2, p3], key=lambda point: point[1])
    min_y = max(0, points[0][1])
    max_y = min(HEIGHT - 1, points[2][1])

    def edge_intersection(a, b, y):
        if a[1] == b[1]:
            return [a[0], b[0]]
        if y < min(a[1], b[1]) or y > max(a[1], b[1]):
            return []
        t = (y - a[1]) / (b[1] - a[1])
        return [a[0] + t * (b[0] - a[0])]

    for y in range(min_y, max_y + 1):
        xs = []
        xs.extend(edge_intersection(points[0], points[1], y))
        xs.extend(edge_intersection(points[1], points[2], y))
        xs.extend(edge_intersection(points[0], points[2], y))
        if len(xs) < 2:
            continue
        x1 = max(0, math.floor(min(xs)))
        x2 = min(WIDTH - 1, math.ceil(max(xs)))
        for x in range(x1, x2 + 1):
            canvas.SetPixel(x, y, *color)


def fill_face(canvas, cx, top_y, height, top_width, bottom_width, color):
    if height <= 0:
        return

    for row in range(height):
        t = row / max(1, height - 1)
        width = round(top_width + (bottom_width - top_width) * t)
        y = top_y + row
        if 0 <= y < HEIGHT:
            start_x = max(0, cx - width // 2)
            end_x = min(WIDTH - 1, cx + width // 2)
            for x in range(start_x, end_x + 1):
                canvas.SetPixel(x, y, *color)


def scale_color(color, factor):
    return tuple(int(channel * factor) for channel in color)


def mix_color(start_color, end_color, amount):
    return tuple(round(start + (end - start) * amount) for start, end in zip(start_color, end_color))


def rainbow_color_for_y(pixel_y, top_y, bottom_y, brightness=1.0):
    if bottom_y <= top_y:
        return scale_color(COUNT_RAINBOW_STOPS[0], brightness)

    position = (pixel_y - top_y) / (bottom_y - top_y)
    scaled = max(0.0, min(1.0, position)) * (len(COUNT_RAINBOW_STOPS) - 1)
    stop_index = min(len(COUNT_RAINBOW_STOPS) - 2, int(scaled))
    amount = scaled - stop_index
    return scale_color(mix_color(COUNT_RAINBOW_STOPS[stop_index], COUNT_RAINBOW_STOPS[stop_index + 1], amount), brightness)


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def normalize_sensor_order(sensor_order):
    if sensor_order == SENSOR_ORDER_BA:
        return SENSOR_ORDER_BA
    return SENSOR_ORDER_AB


def sensor_pair_values(sensor_order, sensor1_value, sensor2_value):
    if normalize_sensor_order(sensor_order) == SENSOR_ORDER_BA:
        return sensor2_value, sensor1_value
    return sensor1_value, sensor2_value


def logical_sensor_values(settings, sensor1_value, sensor2_value):
    return sensor_pair_values(settings.get("sensor_order", SENSOR_ORDER_AB), sensor1_value, sensor2_value)


def toggle_sensor_order(sensor_order):
    return SENSOR_ORDER_AB if normalize_sensor_order(sensor_order) == SENSOR_ORDER_BA else SENSOR_ORDER_BA


def default_settings():
    return {
        "threshold_cm": DEFAULT_THRESHOLD,
        "timeout_ms": DEFAULT_TIMEOUT_MS,
        "cooldown_ms": DEFAULT_COOLDOWN_MS,
        "brightness_percent": DEFAULT_BRIGHTNESS_PERCENT,
        "debug_mode": DEFAULT_DEBUG_MODE,
        "sensor_order": SENSOR_ORDER_AB,
        "base_distance_1_cm": None,
        "base_distance_2_cm": None,
    }


def sanitize_settings(raw_settings):
    settings = default_settings()
    if not isinstance(raw_settings, dict):
        return settings

    try:
        settings["threshold_cm"] = clamp(int(raw_settings.get("threshold_cm", DEFAULT_THRESHOLD)), MIN_THRESHOLD, MAX_THRESHOLD)
    except (TypeError, ValueError):
        pass

    try:
        if "timeout_ms" in raw_settings:
            timeout_ms = int(float(raw_settings.get("timeout_ms", DEFAULT_TIMEOUT_MS)))
        else:
            timeout_ms = round(float(raw_settings.get("timeout_s", DEFAULT_TIMEOUT_MS / 1000)) * 1000)
        settings["timeout_ms"] = clamp(timeout_ms, MIN_TIMEOUT_MS, MAX_TIMEOUT_MS)
    except (TypeError, ValueError):
        pass

    try:
        if "cooldown_ms" in raw_settings:
            cooldown_ms = int(float(raw_settings.get("cooldown_ms", DEFAULT_COOLDOWN_MS)))
        else:
            cooldown_ms = round(float(raw_settings.get("cooldown_s", DEFAULT_COOLDOWN_MS / 1000)) * 1000)
        settings["cooldown_ms"] = clamp(cooldown_ms, MIN_COOLDOWN_MS, MAX_COOLDOWN_MS)
    except (TypeError, ValueError):
        pass

    try:
        settings["brightness_percent"] = clamp(
            int(float(raw_settings.get("brightness_percent", DEFAULT_BRIGHTNESS_PERCENT))),
            MIN_BRIGHTNESS_PERCENT,
            MAX_BRIGHTNESS_PERCENT,
        )
    except (TypeError, ValueError):
        pass

    settings["debug_mode"] = bool(raw_settings.get("debug_mode", DEFAULT_DEBUG_MODE))
    settings["sensor_order"] = normalize_sensor_order(raw_settings.get("sensor_order", SENSOR_ORDER_AB))
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


def load_settings(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return sanitize_settings(json.load(handle))
    except FileNotFoundError:
        return default_settings()
    except (OSError, ValueError, TypeError) as exc:
        print(f"Failed to load settings from {path}: {exc}", flush=True)
        return default_settings()


def save_settings(path, settings):
    temp_path = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(sanitize_settings(settings), handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except OSError as exc:
        print(f"Failed to save settings to {path}: {exc}", flush=True)


def apply_matrix_brightness(matrix, settings, current_brightness_percent):
    brightness_percent = settings["brightness_percent"]
    if brightness_percent == current_brightness_percent:
        return current_brightness_percent

    try:
        matrix.brightness = brightness_percent
    except Exception as attr_exc:
        set_brightness = getattr(matrix, "SetBrightness", None)
        if set_brightness is None:
            print(f"Failed to set matrix brightness to {brightness_percent}%: {attr_exc}", flush=True)
        else:
            try:
                set_brightness(brightness_percent)
            except Exception as method_exc:
                print(f"Failed to set matrix brightness to {brightness_percent}%: {method_exc}", flush=True)
            else:
                print(f"Display brightness set to {brightness_percent}%", flush=True)
    else:
        print(f"Display brightness set to {brightness_percent}%", flush=True)

    return brightness_percent


def load_keyboard_command(path, last_command_id):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return None, last_command_id
    except (OSError, ValueError, TypeError) as exc:
        print(f"Failed to load keyboard command from {path}: {exc}", flush=True)
        return None, last_command_id

    if not isinstance(payload, dict):
        return None, last_command_id

    command_id = str(payload.get("id", ""))
    command = payload.get("command")
    if not command_id or command_id == last_command_id or not isinstance(command, str):
        return None, last_command_id

    return command, command_id


def clear_keyboard_command(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        return
    except OSError as exc:
        print(f"Failed to clear keyboard command file {path}: {exc}", flush=True)


def set_status_message(message):
    return message, time.time() + STATUS_MESSAGE_SECONDS


def draw_status_overlay(canvas, debug_font, message):
    if not message:
        return

    baseline_y = HEIGHT - 8
    status_color = graphics.Color(255, 180, 80)
    status_width = text_width(debug_font, message)
    status_x = max(0, (WIDTH - status_width) // 2)
    graphics.DrawText(canvas, debug_font, status_x, baseline_y, status_color, message)


def draw_counter_label(canvas, font, debug_font, message, brightness=1.0, is_status=False):
    label_font = font
    baseline_y = 8
    if text_width(label_font, message) > WIDTH:
        label_font = debug_font
        baseline_y = 7

    base_color = (255, 180, 80) if is_status else (180, 180, 255)
    label_color = graphics.Color(*scale_color(base_color, brightness))
    label_width = text_width(label_font, message)
    graphics.DrawText(canvas, label_font, max(0, (WIDTH - label_width) // 2), baseline_y, label_color, message)


def draw_debug_overlay(canvas, debug_font, distance1, distance2, debug_mode, distance1_ignored=False, distance2_ignored=False):
    if not debug_mode or distance1 is None or distance2 is None:
        return

    baseline_y = HEIGHT
    sensor_a_value = max(0, min(9999, round(distance1)))
    sensor_b_value = max(0, min(9999, round(distance2)))
    sensor_a_text = f"A:{sensor_a_value:>4}"
    sensor_b_text = f"B:{sensor_b_value:>4}"
    debug_color = graphics.Color(96, 255, 96)
    ignored_color = graphics.Color(120, 120, 120)
    sensor_b_x = WIDTH - text_width(debug_font, "B:0000")

    graphics.DrawText(canvas, debug_font, 0, baseline_y, ignored_color if distance1_ignored else debug_color, sensor_a_text)
    graphics.DrawText(canvas, debug_font, sensor_b_x, baseline_y, ignored_color if distance2_ignored else debug_color, sensor_b_text)


def draw_footer_overlay(
    canvas,
    debug_font,
    distance1,
    distance2,
    debug_mode,
    status_message,
    distance1_ignored=False,
    distance2_ignored=False,
):
    draw_debug_overlay(
        canvas,
        debug_font,
        distance1,
        distance2,
        debug_mode,
        distance1_ignored=distance1_ignored,
        distance2_ignored=distance2_ignored,
    )


def filtered_average(samples):
    valid = sorted(sample for sample in samples if 2 <= sample <= 800)
    if not valid:
        return None

    median = valid[len(valid) // 2]
    tolerance = max(20, int(median * 0.2))
    filtered = [sample for sample in valid if abs(sample - median) <= tolerance]
    working = filtered or valid

    trim = min(len(working) // 5, max(0, len(working) - 3))
    if trim > 0:
        working = working[trim:-trim]

    return round(sum(working) / len(working))


def filtered_max(samples):
    valid = sorted(float(sample) for sample in samples if 2 <= sample <= 3000)
    if not valid:
        return None

    rounded = [round(sample) for sample in valid]
    cluster_counts = {}
    for sample in rounded:
        for start in range(sample - CALIBRATION_CLUSTER_SPAN_CM, sample + 1):
            cluster_counts[start] = cluster_counts.get(start, 0) + 1

    best_start, _ = max(cluster_counts.items(), key=lambda item: (item[1], -abs(item[0] - round(valid[len(valid) // 2]))))
    best_end = best_start + CALIBRATION_CLUSTER_SPAN_CM
    stable = [sample for sample in valid if best_start <= sample <= best_end]
    working = stable or valid
    return max(working)


def reading_is_ignored(distance, baseline):
    return distance is not None and baseline is not None and distance > baseline + IGNORE_MARGIN_CM


def effective_distance(distance, baseline, last_valid_distance):
    if distance is None:
        return None, False, last_valid_distance

    if reading_is_ignored(distance, baseline):
        return last_valid_distance, True, last_valid_distance

    return distance, False, distance


def calibrate_base_distances(us100_1, us100_2, duration_seconds=CALIBRATION_SECONDS, progress_callback=None):
    samples_1 = []
    samples_2 = []
    started_at = time.time()
    deadline = started_at + duration_seconds

    while time.time() < deadline:
        samples_1.append(us100_1.distance)
        samples_2.append(us100_2.distance)
        base_1 = filtered_max(samples_1)
        base_2 = filtered_max(samples_2)
        if progress_callback is not None:
            progress_callback(
                {
                    "remaining_seconds": max(0.0, deadline - time.time()),
                    "current_1": samples_1[-1],
                    "current_2": samples_2[-1],
                    "calibrated_1": base_1,
                    "calibrated_2": base_2,
                }
            )
        time.sleep(0.05)

    return filtered_max(samples_1), filtered_max(samples_2)


def render_calibrating_display(canvas, debug_font, progress=None, sensor_order=SENSOR_ORDER_AB):
    canvas.Clear()
    color = graphics.Color(255, 180, 80)
    value_color = graphics.Color(96, 255, 96)
    remaining_seconds = CALIBRATION_SECONDS if progress is None else max(0, math.ceil(progress["remaining_seconds"]))
    message = f"CALIBRATING ({remaining_seconds})"
    text_x = max(0, (WIDTH - text_width(debug_font, message)) // 2)
    graphics.DrawText(canvas, debug_font, text_x, 5, color, message)

    if progress is None:
        graphics.DrawText(canvas, debug_font, 0, 13, value_color, "A   0")
        graphics.DrawText(canvas, debug_font, 32, 13, value_color, "B   0")
        return

    current_a, current_b = sensor_pair_values(sensor_order, progress["current_1"], progress["current_2"])
    calibrated_a_value, calibrated_b_value = sensor_pair_values(
        sensor_order,
        progress["calibrated_1"],
        progress["calibrated_2"],
    )
    current_a = f"A{max(0, min(9999, round(current_a))):>4}"
    current_b = f"B{max(0, min(9999, round(current_b))):>4}"
    calibrated_a = f"C{round(calibrated_a_value):>4}" if calibrated_a_value is not None else "C  --"
    calibrated_b = f"C{round(calibrated_b_value):>4}" if calibrated_b_value is not None else "C  --"
    limit_a = f"I>{round(calibrated_a_value + IGNORE_MARGIN_CM):>4}" if calibrated_a_value is not None else "I> --"
    limit_b = f"I>{round(calibrated_b_value + IGNORE_MARGIN_CM):>4}" if calibrated_b_value is not None else "I> --"

    graphics.DrawText(canvas, debug_font, 0, 12, value_color, current_a)
    graphics.DrawText(canvas, debug_font, 32, 12, value_color, current_b)
    graphics.DrawText(canvas, debug_font, 0, 18, value_color, calibrated_a)
    graphics.DrawText(canvas, debug_font, 32, 18, value_color, calibrated_b)
    graphics.DrawText(canvas, debug_font, 0, 24, color, limit_a)
    graphics.DrawText(canvas, debug_font, 32, 24, color, limit_b)


def default_learning_state():
    return {
        "active": False,
        "round": 0,
        "started_at": None,
        "event_at": None,
        "phase": "idle",
        "status": "Idle",
        "samples": [],
        "last_result": None,
    }


def begin_learning_round(learning, now):
    previous_result = learning.get("last_result")
    learning.update({
        "active": True,
        "round": int(learning.get("round") or 0) + 1,
        "started_at": now,
        "event_at": now + LEARNING_COUNTDOWN_SECONDS,
        "phase": "countdown",
        "status": "Countdown",
        "samples": [],
        "last_result": previous_result,
    })
    return learning


def stop_learning(learning):
    last_result = learning.get("last_result")
    learning.update(default_learning_state())
    learning["last_result"] = last_result
    return learning


def valid_learning_value(value):
    return value is not None and 2 <= value <= 800


def learning_values(samples, key, start_at=None, end_at=None):
    values = []
    for sample in samples:
        if start_at is not None and sample["t"] < start_at:
            continue
        if end_at is not None and sample["t"] > end_at:
            continue
        value = sample.get(key)
        if valid_learning_value(value):
            values.append(float(value))
    return values


def learning_crossing_time(samples, key, baseline, drop, event_at):
    crossing_level = baseline - max(LEARNING_MIN_DROP_CM, drop * 0.45)
    for sample in sorted(samples, key=lambda item: item["t"]):
        if sample["t"] < event_at - LEARNING_EVENT_EARLY_SECONDS:
            continue
        if sample["t"] > event_at + LEARNING_EVENT_LATE_SECONDS:
            break
        value = sample.get(key)
        if valid_learning_value(value) and value <= crossing_level:
            return sample["t"]
    return None


def analyze_learning_round(learning, settings):
    samples = learning.get("samples") or []
    event_at = learning.get("event_at")
    if event_at is None:
        return None, "NO EVENT"

    window_start = event_at - LEARNING_EVENT_EARLY_SECONDS
    window_end = event_at + LEARNING_EVENT_LATE_SECONDS
    pre_end = event_at - LEARNING_EVENT_EARLY_SECONDS

    pre_1 = learning_values(samples, "d1", end_at=pre_end)
    pre_2 = learning_values(samples, "d2", end_at=pre_end)
    window_1 = learning_values(samples, "d1", start_at=window_start, end_at=window_end)
    window_2 = learning_values(samples, "d2", start_at=window_start, end_at=window_end)

    baseline_1 = filtered_max(pre_1) or settings.get("base_distance_1_cm")
    baseline_2 = filtered_max(pre_2) or settings.get("base_distance_2_cm")
    if baseline_1 is None or baseline_2 is None or not window_1 or not window_2:
        return None, "NO DATA"

    min_1 = min(window_1)
    min_2 = min(window_2)
    drop_1 = max(0.0, float(baseline_1) - min_1)
    drop_2 = max(0.0, float(baseline_2) - min_2)
    min_drop = min(drop_1, drop_2)
    if min_drop < LEARNING_MIN_DROP_CM:
        return None, "NO DROP"

    cross_1 = learning_crossing_time(samples, "d1", float(baseline_1), drop_1, event_at)
    cross_2 = learning_crossing_time(samples, "d2", float(baseline_2), drop_2, event_at)
    if cross_1 is None or cross_2 is None:
        return None, "PARTIAL"

    learned_order = SENSOR_ORDER_AB if cross_1 <= cross_2 else SENSOR_ORDER_BA
    first_cross = min(cross_1, cross_2)
    second_cross = max(cross_1, cross_2)
    delay_seconds = second_cross - first_cross

    pre_noise_1 = max([max(0.0, float(baseline_1) - value) for value in pre_1] or [0.0])
    pre_noise_2 = max([max(0.0, float(baseline_2) - value) for value in pre_2] or [0.0])
    noise_floor = max(pre_noise_1, pre_noise_2) + LEARNING_THRESHOLD_MARGIN_CM
    event_ceiling = min_drop - LEARNING_THRESHOLD_MARGIN_CM
    if event_ceiling >= noise_floor:
        threshold_cm = round((noise_floor + event_ceiling) / 2)
    else:
        threshold_cm = round(min_drop * 0.6)
    threshold_cm = clamp(threshold_cm, MIN_THRESHOLD, MAX_THRESHOLD)

    low_level_1 = float(baseline_1) - threshold_cm
    low_level_2 = float(baseline_2) - threshold_cm
    low_samples = [
        sample["t"]
        for sample in samples
        if window_start <= sample["t"] <= window_end
        and (
            (valid_learning_value(sample.get("d1")) and sample["d1"] <= low_level_1)
            or (valid_learning_value(sample.get("d2")) and sample["d2"] <= low_level_2)
        )
    ]
    event_duration_seconds = max(0.0, (max(low_samples) - first_cross) if low_samples else delay_seconds)

    timeout_ms = clamp(
        round((delay_seconds + LEARNING_TIMEOUT_MARGIN_SECONDS) * 1000),
        max(MIN_TIMEOUT_MS, 500),
        MAX_TIMEOUT_MS,
    )
    cooldown_ms = clamp(
        round((event_duration_seconds + LEARNING_COOLDOWN_MARGIN_SECONDS) * 1000),
        max(MIN_COOLDOWN_MS, 1000),
        MAX_COOLDOWN_MS,
    )

    return {
        "round": learning.get("round") or 0,
        "sensor_order": learned_order,
        "threshold_cm": threshold_cm,
        "timeout_ms": timeout_ms,
        "cooldown_ms": cooldown_ms,
        "base_distance_1_cm": round(baseline_1),
        "base_distance_2_cm": round(baseline_2),
        "drop_1_cm": round(drop_1, 1),
        "drop_2_cm": round(drop_2, 1),
        "delay_seconds": round(delay_seconds, 2),
        "duration_seconds": round(event_duration_seconds, 2),
    }, "LEARN OK"


def update_learning(learning, settings, now, raw_distance1, raw_distance2):
    if not learning.get("active"):
        return False, None

    learning["samples"].append({
        "t": now,
        "d1": raw_distance1,
        "d2": raw_distance2,
    })

    event_at = learning["event_at"]
    if now < event_at:
        learning["phase"] = "countdown"
        learning["status"] = "Countdown"
        return False, None

    if now < event_at + LEARNING_EVENT_LATE_SECONDS:
        learning["phase"] = "watching"
        learning["status"] = "Watch now"
        return False, None

    result, status = analyze_learning_round(learning, settings)
    learning["last_result"] = result
    if result is not None:
        settings["threshold_cm"] = result["threshold_cm"]
        settings["timeout_ms"] = result["timeout_ms"]
        settings["cooldown_ms"] = result["cooldown_ms"]
        settings["sensor_order"] = result["sensor_order"]
        settings["base_distance_1_cm"] = result["base_distance_1_cm"]
        settings["base_distance_2_cm"] = result["base_distance_2_cm"]
        save_settings(SETTINGS_STATE_PATH, settings)
        log_event("learning_round", source="learn_mode", learned=result)
        print(f"Learning round updated settings: {result}", flush=True)
    else:
        print(f"Learning round did not update settings: {status}", flush=True)

    learning["status"] = status
    begin_learning_round(learning, now)
    return result is not None, status


def learning_payload(learning, now):
    active = bool(learning.get("active"))
    event_at = learning.get("event_at") if active else None
    countdown = max(0, math.ceil(event_at - now)) if event_at is not None else 0
    last_result = learning.get("last_result") or {}
    return {
        "active": active,
        "round": int(learning.get("round") or 0),
        "phase": learning.get("phase") or ("countdown" if active else "idle"),
        "status": learning.get("status") or ("Countdown" if active else "Idle"),
        "countdown_seconds": countdown,
        "learned_threshold_cm": last_result.get("threshold_cm"),
        "learned_timeout_ms": last_result.get("timeout_ms"),
        "learned_cooldown_ms": last_result.get("cooldown_ms"),
        "learned_sensor_order": last_result.get("sensor_order"),
    }


def publish_learning_state(path, learning, now, last_payload_text):
    payload_text = json.dumps(learning_payload(learning, now), separators=(",", ":"), sort_keys=True)
    if payload_text == last_payload_text:
        return last_payload_text

    temp_path = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(temp_path, "w", encoding="utf-8") as handle:
            handle.write(payload_text)
            handle.write("\n")
        os.replace(temp_path, path)
        return payload_text
    except OSError as exc:
        print(f"Failed to publish learning state {path}: {exc}", flush=True)
        return last_payload_text


def render_learning_display(canvas, font, big_font, debug_font, learning, now, distance1, distance2):
    canvas.Clear()
    payload = learning_payload(learning, now)
    label = f"LEARN {payload['round']}"
    draw_counter_label(canvas, font, debug_font, label, is_status=True)

    number = str(payload["countdown_seconds"])
    count_width = text_width(big_font, number)
    draw_count_pixels(
        canvas,
        count_text_pixels(big_font, number, (WIDTH - count_width) // 2, count_baseline(big_font)),
    )

    value_color = graphics.Color(96, 255, 96)
    status_color = graphics.Color(255, 180, 80)
    sensor_a = f"A{max(0, min(9999, round(distance1))):>4}" if distance1 is not None else "A----"
    sensor_b = f"B{max(0, min(9999, round(distance2))):>4}" if distance2 is not None else "B----"
    status = "NOW" if payload["phase"] == "watching" else "RDY"
    if payload["status"] not in ("Countdown", "Watch now"):
        status = payload["status"][:3].upper()

    graphics.DrawText(canvas, debug_font, 0, HEIGHT - 1, value_color, sensor_a)
    graphics.DrawText(canvas, debug_font, 24, HEIGHT - 1, value_color, sensor_b)
    graphics.DrawText(canvas, debug_font, WIDTH - text_width(debug_font, status), HEIGHT - 1, status_color, status)


def format_timeout_seconds(timeout_ms):
    return f"{timeout_ms / 1000:.1f}"


def calibration_value_text(draft_settings):
    base_1 = draft_settings.get("base_distance_1_cm")
    base_2 = draft_settings.get("base_distance_2_cm")
    if base_1 is None or base_2 is None:
        return "--/--"
    base_a, base_b = logical_sensor_values(draft_settings, base_1, base_2)
    return f"A{round(base_a)} B{round(base_b)}"


def menu_value_text(item, draft_settings, draft_counter):
    item_id = item["id"]
    if item_id == "counter_value":
        return str(draft_counter)
    if item_id == "threshold_cm":
        return str(draft_settings["threshold_cm"])
    if item_id == "timeout_ms":
        return format_timeout_seconds(draft_settings["timeout_ms"])
    if item_id == "cooldown_ms":
        return format_timeout_seconds(draft_settings["cooldown_ms"])
    if item_id == "brightness_percent":
        return f"{draft_settings['brightness_percent']}%"
    if item_id == "sensor_order":
        return draft_settings["sensor_order"]
    if item_id == "debug_mode":
        return "ON" if draft_settings["debug_mode"] else "OFF"
    if item_id == "play_animation":
        return "GO"
    if item_id == "calibrate":
        return calibration_value_text(draft_settings)
    if item_id == "reset_defaults":
        return "DEF"
    if item_id == "save_exit":
        return "SAVE"
    return ""


def trigger_status_text(sensor1_triggered_at, last_counted_at, now, cooldown_active=False):
    if last_counted_at is not None and now - last_counted_at <= COUNT_TRIGGER_FLASH_SECONDS:
        return "CNT"
    if cooldown_active:
        return "CLD"
    if sensor1_triggered_at is not None:
        return "ARM"
    return "IDL"


def has_unsaved_menu_changes(settings, draft_settings, counter, draft_counter):
    return sanitize_settings(draft_settings) != sanitize_settings(settings) or draft_counter != counter


def render_save_changes_dialog(canvas, debug_font):
    canvas.Clear()
    overlay_color = graphics.Color(255, 180, 80)
    prompt = "SAVE CHANGES"
    choices = "Y / N"
    prompt_x = max(0, (WIDTH - text_width(debug_font, prompt)) // 2)
    choices_x = max(0, (WIDTH - text_width(debug_font, choices)) // 2)
    graphics.DrawText(canvas, debug_font, prompt_x, 13, overlay_color, prompt)
    graphics.DrawText(canvas, debug_font, choices_x, 21, overlay_color, choices)


def render_menu_display(
    canvas,
    debug_font,
    draft_settings,
    draft_counter,
    selected_index,
    edit_mode,
    input_buffer,
    confirm_exit_unsaved,
    distance1,
    distance2,
    distance1_ignored,
    distance2_ignored,
    sensor1_triggered_at,
    last_counted_at,
    cooldown_active,
):
    canvas.Clear()
    if confirm_exit_unsaved:
        render_save_changes_dialog(canvas, debug_font)
        return

    normal_label = graphics.Color(120, 120, 180)
    selected_label = graphics.Color(255, 220, 100)
    normal_value = graphics.Color(220, 220, 220)
    editing_value = graphics.Color(120, 255, 120)
    action_value = graphics.Color(180, 220, 255)
    visible_rows = 5
    start_index = min(max(0, selected_index - visible_rows + 1), max(0, len(MENU_ITEMS) - visible_rows))

    for row_index in range(visible_rows):
        index = start_index + row_index
        if index >= len(MENU_ITEMS):
            break

        item = MENU_ITEMS[index]
        baseline_y = 5 + row_index * 5
        marker = ">" if index == selected_index else " "
        label_color = selected_label if index == selected_index else normal_label
        value_color = normal_value
        if item["type"] == "action":
            value_color = action_value
        if index == selected_index and edit_mode:
            value_color = editing_value

        label = f"{marker}{item['label']}"
        value = menu_value_text(item, draft_settings, draft_counter)
        if index == selected_index and edit_mode and item["type"] in ("int", "float") and input_buffer is not None:
            value = f"{input_buffer}_"
        value_x = WIDTH - text_width(debug_font, value)

        graphics.DrawText(canvas, debug_font, 0, baseline_y, label_color, label)
        graphics.DrawText(canvas, debug_font, value_x, baseline_y, value_color, value)

    if distance1 is not None:
        sensor_a = f"A{max(0, min(9999, round(distance1))):>4}"
    else:
        sensor_a = "A----"
    if distance2 is not None:
        sensor_b = f"B{max(0, min(9999, round(distance2))):>4}"
    else:
        sensor_b = "B----"
    status_text = trigger_status_text(sensor1_triggered_at, last_counted_at, time.time(), cooldown_active=cooldown_active)
    bottom_color = graphics.Color(96, 255, 96)
    ignored_color = graphics.Color(120, 120, 120)
    status_color = graphics.Color(255, 180, 80) if status_text == "CNT" else graphics.Color(180, 180, 255)

    graphics.DrawText(canvas, debug_font, 0, HEIGHT - 1, ignored_color if distance1_ignored else bottom_color, sensor_a)
    graphics.DrawText(canvas, debug_font, 24, HEIGHT - 1, ignored_color if distance2_ignored else bottom_color, sensor_b)
    graphics.DrawText(canvas, debug_font, WIDTH - text_width(debug_font, status_text), HEIGHT - 1, status_color, status_text)

def render_boot_screen(canvas, brightness=1.0):
    background = scale_color(BOOT_BACKGROUND, brightness)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            canvas.SetPixel(x, y, *background)
    x_offset = (WIDTH - len(BOOT_LOGO_ROWS[0])) // 2
    for y, row in enumerate(BOOT_LOGO_ROWS):
        for x, pixel in enumerate(row):
            canvas.SetPixel(x + x_offset, y, *scale_color(BOOT_TONE_MAP[pixel], brightness))


def boot_screen(matrix, canvas, font, big_font):
    canvas.Clear()
    render_boot_screen(canvas)
    canvas = matrix.SwapOnVSync(canvas)
    time.sleep(BOOT_HOLD_SECONDS)
    return canvas


def load_counter(path, legacy_path=None):
    last_error = None
    paths = [path]
    if legacy_path and legacy_path != path:
        paths.append(legacy_path)

    for candidate in paths:
        for _ in range(3):
            try:
                with open(candidate, "r", encoding="utf-8") as handle:
                    raw = handle.read().strip()
                if raw:
                    return max(0, int(raw))
                time.sleep(0.05)
            except FileNotFoundError:
                break
            except (OSError, ValueError) as exc:
                last_error = exc
                time.sleep(0.05)

    if last_error is not None:
        print(f"Failed to load counter from {path}: {last_error}", flush=True)
    return 0


def save_counter(path, value):
    temp_path = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(temp_path, "w", encoding="utf-8") as handle:
            handle.write(f"{value}\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except OSError as exc:
        print(f"Failed to save counter to {path}: {exc}", flush=True)


def log_event(event_name, old_count=None, new_count=None, **details):
    now = datetime.now().astimezone()
    payload = {
        "timestamp": now.isoformat(timespec="seconds"),
        "event": event_name,
        "old_count": old_count,
        "new_count": new_count,
    }
    if details:
        payload["details"] = details

    try:
        os.makedirs(os.path.dirname(EVENT_LOG_PATH), exist_ok=True)
        with open(EVENT_LOG_PATH, "a", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        print(f"Logged event {event_name} to {EVENT_LOG_PATH}", flush=True)
    except OSError as exc:
        print(f"Failed to append event log {EVENT_LOG_PATH}: {exc}", flush=True)


def ensure_counter_state_file(path, value):
    if not os.path.exists(path):
        save_counter(path, value)


def count_baseline(big_font):
    return COUNT_TOP + big_font.baseline


def load_bdf_glyphs(path):
    glyphs = {}
    encoding = None
    dwidth = 0
    bbx = None
    in_bitmap = False
    bitmap_rows = []

    with open(path, "r", encoding="latin-1") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line.startswith("ENCODING"):
                encoding = int(line.split()[1])
            elif line.startswith("DWIDTH"):
                dwidth = int(line.split()[1])
            elif line.startswith("BBX"):
                parts = line.split()
                bbx = (int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]))
            elif line == "BITMAP":
                in_bitmap = True
                bitmap_rows = []
            elif line == "ENDCHAR":
                if encoding is not None and bbx is not None and encoding >= 0:
                    glyphs[encoding] = {
                        "dwidth": dwidth,
                        "w": bbx[0],
                        "h": bbx[1],
                        "xoff": bbx[2],
                        "yoff": bbx[3],
                        "rows": bitmap_rows[:],
                    }
                encoding = None
                bbx = None
                in_bitmap = False
                bitmap_rows = []
            elif in_bitmap:
                bitmap_rows.append(int(line, 16))

    return glyphs


def text_pixel_positions(glyphs, text, origin_x, baseline_y, fallback_width):
    pixels = set()
    cursor_x = origin_x

    for char in text:
        glyph = glyphs.get(ord(char))
        if glyph is None:
            cursor_x += fallback_width
            continue

        total_bits = ((glyph["w"] + 7) // 8) * 8
        for row_index, row_value in enumerate(glyph["rows"]):
            pixel_y = baseline_y - glyph["yoff"] - glyph["h"] + 1 + row_index
            for bit_index in range(glyph["w"]):
                if row_value & (1 << (total_bits - 1 - bit_index)):
                    pixel_x = cursor_x + glyph["xoff"] + bit_index
                    if 0 <= pixel_x < WIDTH and 0 <= pixel_y < HEIGHT:
                        pixels.add((pixel_x, pixel_y))

        cursor_x += glyph["dwidth"]

    return pixels


def count_text_pixels(big_font, text, origin_x, baseline_y):
    fallback_width = big_font.CharacterWidth(ord("0"))
    return text_pixel_positions(BDF_GLYPHS, text, origin_x, baseline_y, fallback_width)


def count_pixel_colors(pixels, brightness=1.0):
    if not pixels:
        return {}

    top_y = min(py for _, py in pixels)
    bottom_y = max(py for _, py in pixels)
    return {
        (px, py): rainbow_color_for_y(py, top_y, bottom_y, brightness)
        for px, py in pixels
    }


def draw_count_pixels(canvas, pixels, brightness=1.0):
    for (px, py), color in count_pixel_colors(pixels, brightness).items():
        canvas.SetPixel(px, py, *color)


def draw_counter_display(
    matrix,
    canvas,
    font,
    big_font,
    debug_font,
    counter,
    distance1=None,
    distance2=None,
    distance1_ignored=False,
    distance2_ignored=False,
    debug_mode=False,
    status_message=None,
):
    canvas.Clear()
    render_counter_display(
        canvas,
        font,
        big_font,
        debug_font,
        counter,
        distance1=distance1,
        distance2=distance2,
        distance1_ignored=distance1_ignored,
        distance2_ignored=distance2_ignored,
        debug_mode=debug_mode,
        status_message=status_message,
    )
    return matrix.SwapOnVSync(canvas)


def render_counter_display(
    canvas,
    font,
    big_font,
    debug_font,
    counter,
    label_brightness=1.0,
    count_brightness=1.0,
    distance1=None,
    distance2=None,
    distance1_ignored=False,
    distance2_ignored=False,
    debug_mode=False,
    status_message=None,
):
    label = status_message or "LOAD COUNT"
    draw_counter_label(canvas, font, debug_font, label, brightness=label_brightness, is_status=status_message is not None)

    num = str(counter)
    count_width = text_width(big_font, num)
    num_y = count_baseline(big_font)
    draw_count_pixels(
        canvas,
        count_text_pixels(big_font, num, (WIDTH - count_width) // 2, num_y),
        brightness=count_brightness,
    )
    draw_footer_overlay(
        canvas,
        debug_font,
        distance1,
        distance2,
        debug_mode,
        status_message,
        distance1_ignored=distance1_ignored,
        distance2_ignored=distance2_ignored,
    )


def fade_boot_to_counter(
    matrix,
    canvas,
    font,
    big_font,
    debug_font,
    counter,
    distance1=None,
    distance2=None,
    distance1_ignored=False,
    distance2_ignored=False,
    debug_mode=False,
    status_message=None,
):
    for step in range(BOOT_FADE_STEPS, -1, -1):
        canvas.Clear()
        render_boot_screen(canvas, step / BOOT_FADE_STEPS)
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(BOOT_FADE_FRAME_DELAY)

    for step in range(0, BOOT_FADE_STEPS + 1):
        canvas.Clear()
        render_counter_display(
            canvas,
            font,
            big_font,
            debug_font,
            counter,
            label_brightness=step / BOOT_FADE_STEPS,
            count_brightness=step / BOOT_FADE_STEPS,
            distance1=distance1,
            distance2=distance2,
            distance1_ignored=distance1_ignored,
            distance2_ignored=distance2_ignored,
            debug_mode=debug_mode,
            status_message=status_message,
        )
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(BOOT_FADE_FRAME_DELAY)

    return canvas


def fountain(
    matrix,
    canvas,
    font,
    big_font,
    debug_font,
    old_count,
    new_count,
    distance1=None,
    distance2=None,
    debug_mode=False,
    status_message=None,
):
    label = "LOAD COUNT"
    label_width = text_width(font, label)

    old_text = str(old_count)
    new_text = str(new_count)
    old_width = text_width(big_font, old_text)
    new_width = text_width(big_font, new_text)
    old_x = (WIDTH - old_width) // 2
    new_x = (WIDTH - new_width) // 2
    new_y = count_baseline(big_font) + FOUNTAIN_Y_OFFSET

    old_pixels = count_text_pixels(big_font, old_text, old_x, new_y)
    new_pixels = count_text_pixels(big_font, new_text, new_x, new_y)
    old_pixel_colors = count_pixel_colors(old_pixels)
    new_pixel_colors = count_pixel_colors(new_pixels)
    written_pixels = set()
    swept_pixels = set()

    y_positions = list(range(6, HEIGHT - 2))
    random.shuffle(y_positions)
    swimmers = []
    for index, sy in enumerate(y_positions):
        swimmers.append({
            "hx": -14.0,
            "hy": float(sy),
            "vx": random.uniform(2.2, 3.2),
            "amp": random.uniform(0.7, 1.5),
            "freq": random.uniform(0.45, 0.75),
            "phase": random.uniform(0, 2 * math.pi),
            "launch": index * FOUNTAIN_STAGGER,
            "tail_len": random.randint(7, 12),
        })

    total_frames = swimmers[-1]["launch"] + int(WIDTH / 1.3) + 20

    for frame in range(total_frames):
        canvas.Clear()
        graphics.DrawText(canvas, font, (WIDTH - label_width) // 2, 8, graphics.Color(180, 180, 255), label)

        for px, py in old_pixels:
            if (px, py) not in swept_pixels:
                canvas.SetPixel(px, py, *old_pixel_colors[(px, py)])
        for px, py in new_pixels:
            if (px, py) in written_pixels:
                canvas.SetPixel(px, py, *new_pixel_colors[(px, py)])

        for sp in swimmers:
            if frame < sp["launch"]:
                continue

            sp["hx"] += sp["vx"]
            hx = sp["hx"]
            hy = sp["hy"]
            phase = sp["phase"] + (frame - sp["launch"]) * 0.4
            col_start = max(0, int(hx - sp["vx"]))
            col_end = min(WIDTH - 1, int(hx))

            for col in range(col_start, col_end + 1):
                for dy in range(-2, 3):
                    swept_pixels.add((col, int(hy) + dy))
                for py in range(max(0, int(hy) - 2), min(HEIGHT, int(hy) + 3)):
                    if (col, py) in new_pixels:
                        written_pixels.add((col, py))

            for dx, dy in [(0, 0), (1, 0), (-1, 0), (0, -1), (0, 1)]:
                hpx = int(round(hx)) + dx
                hpy = int(round(hy)) + dy
                if 0 <= hpx < WIDTH and 0 <= hpy < HEIGHT:
                    canvas.SetPixel(hpx, hpy, 255, 255, 230)

            tail_len = sp["tail_len"]
            for i in range(1, tail_len + 1):
                tx = int(round(hx)) - i - 1
                ty = int(round(hy + sp["amp"] * math.sin(phase + i * sp["freq"])))
                if 0 <= tx < WIDTH and 0 <= ty < HEIGHT:
                    fade = (tail_len - i + 1) / tail_len
                    canvas.SetPixel(tx, ty, int(220 * fade), int(220 * fade), int(140 * fade))

        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(FOUNTAIN_FRAME_DELAY)

    return draw_counter_display(
        matrix,
        canvas,
        font,
        big_font,
        debug_font,
        new_count,
        distance1=distance1,
        distance2=distance2,
        debug_mode=debug_mode,
        status_message=status_message,
    )


def default_trigger_state(sensor1_triggered_at=None, sensor2_ready_after_sensor1=False, last_counted_at=None):
    return {
        "sensor1_triggered_at": sensor1_triggered_at,
        "sensor2_ready_after_sensor1": sensor2_ready_after_sensor1,
        "last_counted_at": last_counted_at,
    }


def process_counter_sample(settings, trigger_state, now, sensor_a_distance, sensor_b_distance, sensor_a_threshold, sensor_b_threshold):
    state = default_trigger_state(
        sensor1_triggered_at=trigger_state.get("sensor1_triggered_at"),
        sensor2_ready_after_sensor1=bool(trigger_state.get("sensor2_ready_after_sensor1")),
        last_counted_at=trigger_state.get("last_counted_at"),
    )
    event = {
        "counted": False,
        "cooldown_active": False,
        "sensor_a_started": False,
        "timed_out": False,
    }

    cooldown_active = (
        state["last_counted_at"] is not None
        and now - state["last_counted_at"] < settings["cooldown_ms"] / 1000.0
    )
    event["cooldown_active"] = cooldown_active

    if cooldown_active:
        state["sensor1_triggered_at"] = None
        state["sensor2_ready_after_sensor1"] = False
        return state, event

    if sensor_a_distance is not None and sensor_a_distance < sensor_a_threshold:
        if state["sensor1_triggered_at"] is None:
            state["sensor1_triggered_at"] = now
            state["sensor2_ready_after_sensor1"] = sensor_b_distance is not None and sensor_b_distance >= sensor_b_threshold
            event["sensor_a_started"] = True

    if state["sensor1_triggered_at"] is not None:
        if not state["sensor2_ready_after_sensor1"] and sensor_b_distance is not None and sensor_b_distance >= sensor_b_threshold:
            state["sensor2_ready_after_sensor1"] = True

        if now - state["sensor1_triggered_at"] > settings["timeout_ms"] / 1000.0:
            state["sensor1_triggered_at"] = None
            state["sensor2_ready_after_sensor1"] = False
            event["timed_out"] = True
        elif state["sensor2_ready_after_sensor1"] and sensor_b_distance is not None and sensor_b_distance < sensor_b_threshold:
            state["last_counted_at"] = now
            state["sensor1_triggered_at"] = None
            state["sensor2_ready_after_sensor1"] = False
            event["counted"] = True

    return state, event


def apply_command(command, settings, counter):
    updated_counter = counter
    settings_changed = False
    counter_changed = False
    status_message = None

    if command == "threshold_up":
        settings["threshold_cm"] = clamp(settings["threshold_cm"] + 1, MIN_THRESHOLD, MAX_THRESHOLD)
        settings_changed = True
        status_message = f"THR {settings['threshold_cm']}"
    elif command == "threshold_down":
        settings["threshold_cm"] = clamp(settings["threshold_cm"] - 1, MIN_THRESHOLD, MAX_THRESHOLD)
        settings_changed = True
        status_message = f"THR {settings['threshold_cm']}"
    elif command == "debug_toggle":
        settings["debug_mode"] = not settings["debug_mode"]
        settings_changed = True
        status_message = None
    elif command == "count_reset":
        updated_counter = 0
        counter_changed = True
        status_message = "COUNT RESET"

    return updated_counter, settings_changed, counter_changed, status_message


def parse_direct_int(command, keys, minimum, maximum):
    command_lower = command.lower()
    for key in keys:
        prefix = f"{key}:"
        if command_lower.startswith(prefix):
            raw_value = command.split(":", 1)[1]
            try:
                return clamp(int(float(raw_value)), minimum, maximum)
            except (TypeError, ValueError):
                return None
    return None


def parse_direct_bool(command, keys):
    command_lower = command.lower()
    for key in keys:
        prefix = f"{key}:"
        if command_lower.startswith(prefix):
            value = command.split(":", 1)[1].strip().lower()
            if value in ("1", "true", "yes", "on"):
                return True
            if value in ("0", "false", "no", "off"):
                return False
            return None
    return None


def parse_direct_sensor_order(command):
    command_lower = command.lower()
    if not (command_lower.startswith("sensor_order:") or command_lower.startswith("sensors:")):
        return None
    value = command.split(":", 1)[1].strip().upper().replace(" ", "")
    if value in ("A/B", "AB"):
        return SENSOR_ORDER_AB
    if value in ("B/A", "BA"):
        return SENSOR_ORDER_BA
    return None


def run_calibration(settings, matrix, offscreen_canvas, debug_font, us100_1, us100_2):
    def update_calibration_display(progress):
        nonlocal offscreen_canvas
        render_calibrating_display(
            offscreen_canvas,
            debug_font,
            progress,
            sensor_order=settings["sensor_order"],
        )
        offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)

    render_calibrating_display(
        offscreen_canvas,
        debug_font,
        {
            "remaining_seconds": CALIBRATION_SECONDS,
            "current_1": 0,
            "current_2": 0,
            "calibrated_1": None,
            "calibrated_2": None,
        },
        sensor_order=settings["sensor_order"],
    )
    offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
    base_1, base_2 = calibrate_base_distances(
        us100_1,
        us100_2,
        duration_seconds=CALIBRATION_SECONDS,
        progress_callback=update_calibration_display,
    )
    if base_1 is None or base_2 is None:
        return settings, offscreen_canvas, False

    settings["base_distance_1_cm"] = base_1
    settings["base_distance_2_cm"] = base_2
    save_settings(SETTINGS_STATE_PATH, settings)
    print(f"Calibrated base distances to {base_1}cm/{base_2}cm", flush=True)
    return settings, offscreen_canvas, True


def apply_direct_setting_command(command, target_settings):
    threshold_cm = parse_direct_int(command, ("threshold", "threshold_cm"), MIN_THRESHOLD, MAX_THRESHOLD)
    if threshold_cm is not None:
        target_settings["threshold_cm"] = threshold_cm
        return True, True, f"THR {target_settings['threshold_cm']}"

    timeout_ms = parse_direct_int(command, ("timeout_ms",), MIN_TIMEOUT_MS, MAX_TIMEOUT_MS)
    if timeout_ms is not None:
        target_settings["timeout_ms"] = timeout_ms
        return True, True, f"TIME {format_timeout_seconds(target_settings['timeout_ms'])}"

    timeout_s = parse_direct_int(command, ("timeout", "timeout_s"), 1, MAX_TIMEOUT_MS // 1000)
    if timeout_s is not None:
        target_settings["timeout_ms"] = clamp(timeout_s * 1000, MIN_TIMEOUT_MS, MAX_TIMEOUT_MS)
        return True, True, f"TIME {format_timeout_seconds(target_settings['timeout_ms'])}"

    cooldown_ms = parse_direct_int(command, ("cooldown_ms",), MIN_COOLDOWN_MS, MAX_COOLDOWN_MS)
    if cooldown_ms is not None:
        target_settings["cooldown_ms"] = cooldown_ms
        return True, True, f"CLD {format_timeout_seconds(target_settings['cooldown_ms'])}"

    cooldown_s = parse_direct_int(command, ("cooldown", "cooldown_s"), 0, MAX_COOLDOWN_MS // 1000)
    if cooldown_s is not None:
        target_settings["cooldown_ms"] = clamp(cooldown_s * 1000, MIN_COOLDOWN_MS, MAX_COOLDOWN_MS)
        return True, True, f"CLD {format_timeout_seconds(target_settings['cooldown_ms'])}"

    debug_mode = parse_direct_bool(command, ("debug", "debug_mode"))
    if debug_mode is not None:
        target_settings["debug_mode"] = debug_mode
        return True, True, "DBG ON" if debug_mode else "DBG OFF"

    sensor_order = parse_direct_sensor_order(command)
    if sensor_order is not None:
        target_settings["sensor_order"] = sensor_order
        return True, True, f"SENS {target_settings['sensor_order']}"

    if command == "brightness_up":
        target_settings["brightness_percent"] = clamp(
            target_settings["brightness_percent"] + 5,
            MIN_BRIGHTNESS_PERCENT,
            MAX_BRIGHTNESS_PERCENT,
        )
        return True, True, f"BRI {target_settings['brightness_percent']}%"

    if command == "brightness_down":
        target_settings["brightness_percent"] = clamp(
            target_settings["brightness_percent"] - 5,
            MIN_BRIGHTNESS_PERCENT,
            MAX_BRIGHTNESS_PERCENT,
        )
        return True, True, f"BRI {target_settings['brightness_percent']}%"

    if command.startswith("brightness:"):
        try:
            brightness_percent = int(float(command.split(":", 1)[1]))
        except ValueError:
            return True, False, "BRI ?"
        target_settings["brightness_percent"] = clamp(
            brightness_percent,
            MIN_BRIGHTNESS_PERCENT,
            MAX_BRIGHTNESS_PERCENT,
        )
        return True, True, f"BRI {target_settings['brightness_percent']}%"

    if command == "sensor_order_toggle":
        target_settings["sensor_order"] = toggle_sensor_order(target_settings["sensor_order"])
        return True, True, f"SENS {target_settings['sensor_order']}"

    return False, False, None


def adjust_menu_setting(item, draft_settings, draft_counter, direction):
    if item["id"] == "counter_value":
        value = draft_counter + item["step"] * direction
        return clamp(value, item["minimum"], item["maximum"])

    if item["type"] == "bool":
        draft_settings[item["id"]] = not draft_settings[item["id"]]
        return draft_counter

    if item["type"] == "order":
        draft_settings[item["id"]] = toggle_sensor_order(draft_settings[item["id"]])
        return draft_counter

    value = draft_settings[item["id"]] + item["step"] * direction
    draft_settings[item["id"]] = clamp(value, item["minimum"], item["maximum"])
    return draft_counter


def commit_menu_input(item, draft_settings, draft_counter, input_buffer):
    if item["type"] not in ("int", "float") or input_buffer is None or input_buffer == "":
        return draft_counter

    if item["type"] == "float":
        value = clamp(round(float(input_buffer) * 1000), item["minimum"], item["maximum"])
    else:
        value = clamp(int(input_buffer), item["minimum"], item["maximum"])
    if item["id"] == "counter_value":
        return value

    draft_settings[item["id"]] = value
    return draft_counter


def save_menu_changes(draft_settings, draft_counter, current_counter):
    counter_value = draft_counter
    save_counter(COUNTER_STATE_PATH, counter_value)
    saved_settings = sanitize_settings(draft_settings)
    save_settings(SETTINGS_STATE_PATH, saved_settings)
    if counter_value != current_counter:
        log_event(
            "manual_number_changed",
            old_count=current_counter,
            new_count=counter_value,
            source="debug_menu",
        )
    print(f"Updated settings={saved_settings} counter={counter_value}", flush=True)
    return saved_settings, counter_value


def reset_counter_with_log(current_counter, source):
    save_counter(COUNTER_STATE_PATH, 0)
    log_event(
        "counter_reset",
        old_count=current_counter,
        new_count=0,
        source=source,
    )
    print("Counter reset from keyboard", flush=True)
    return 0


uart1 = serial.Serial("/dev/ttyUSB0", baudrate=9600, timeout=1)
uart2 = serial.Serial("/dev/ttyUSB1", baudrate=9600, timeout=1)

us100_1 = adafruit_us100.US100(uart1)
us100_2 = adafruit_us100.US100(uart2)

settings = load_settings(SETTINGS_STATE_PATH)
if settings["debug_mode"]:
    settings["debug_mode"] = False
save_settings(SETTINGS_STATE_PATH, settings)

options = RGBMatrixOptions()
options.rows = 32
options.cols = 64
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = "adafruit-hat"
options.brightness = settings["brightness_percent"]

font = graphics.Font()
font.LoadFont(os.path.join(BASE_DIR, "fonts/6x12.bdf"))
big_font = graphics.Font()
big_font.LoadFont(os.path.join(BASE_DIR, "fonts/10x20.bdf"))
debug_font = graphics.Font()
debug_font.LoadFont(os.path.join(BASE_DIR, "fonts/4x6.bdf"))
BDF_GLYPHS = load_bdf_glyphs(os.path.join(BASE_DIR, "fonts/10x20.bdf"))
matrix = RGBMatrix(options=options)
offscreen_canvas = matrix.CreateFrameCanvas()
current_brightness_percent = None
current_brightness_percent = apply_matrix_brightness(matrix, settings, current_brightness_percent)

counter = load_counter(COUNTER_STATE_PATH, PRIOR_COUNTER_STATE_PATH)
if counter == 0:
    counter = load_counter(COUNTER_STATE_PATH, LEGACY_COUNTER_STATE_PATH)
ensure_counter_state_file(COUNTER_STATE_PATH, counter)
clear_keyboard_command(KEYBOARD_COMMAND_PATH)
print(f"Loaded counter={counter} from {COUNTER_STATE_PATH}", flush=True)
print(f"Loaded settings={settings} from {SETTINGS_STATE_PATH}", flush=True)
sensor1_triggered_at = None
sensor2_ready_after_sensor1 = False
distance1 = None
distance2 = None
distance1_ignored = False
distance2_ignored = False
last_valid_distance1 = None
last_valid_distance2 = None
last_command_id = None
status_message = None
status_expires_at = 0.0
last_counted_at = None
menu_open = False
menu_edit_mode = False
menu_index = 0
menu_input_buffer = None
menu_input_replace = False
menu_confirm_exit_unsaved = False
learning = default_learning_state()
last_learning_state_json = None
draft_settings = sanitize_settings(settings)
draft_counter = counter
offscreen_canvas = boot_screen(matrix, offscreen_canvas, font, big_font)
if settings["base_distance_1_cm"] is None or settings["base_distance_2_cm"] is None:
    settings["base_distance_1_cm"] = round(us100_1.distance)
    settings["base_distance_2_cm"] = round(us100_2.distance)
    save_settings(SETTINGS_STATE_PATH, settings)
    print(
        f"Initialized base distances to {settings['base_distance_1_cm']}cm/{settings['base_distance_2_cm']}cm",
        flush=True,
    )
    draft_settings = sanitize_settings(settings)
offscreen_canvas = fade_boot_to_counter(
    matrix,
    offscreen_canvas,
    font,
    big_font,
    debug_font,
    counter,
    debug_mode=settings["debug_mode"],
)
offscreen_canvas = draw_counter_display(
    matrix,
    offscreen_canvas,
    font,
    big_font,
    debug_font,
    counter,
    debug_mode=settings["debug_mode"],
)

while True:
    now = time.time()
    if status_message and now >= status_expires_at:
        status_message = None

    active_settings = draft_settings if menu_open else settings
    command, last_command_id = load_keyboard_command(KEYBOARD_COMMAND_PATH, last_command_id)
    if command is not None:
        handled_direct_command = False
        direct_settings_changed = False
        direct_status = None
        direct_opened_menu = False

        direct_counter = parse_direct_int(command, ("counter", "count"), 0, MAX_COUNTER)
        if direct_counter is not None:
            handled_direct_command = True
            old_counter = counter
            counter = direct_counter
            save_counter(COUNTER_STATE_PATH, counter)
            if counter != old_counter:
                log_event(
                    "manual_number_changed",
                    old_count=old_counter,
                    new_count=counter,
                    source="iphone",
                )
            sensor1_triggered_at = None
            sensor2_ready_after_sensor1 = False
            last_counted_at = None
            direct_status = f"COUNT {counter}"
        elif command == "reset_defaults":
            handled_direct_command = True
            base_1 = settings["base_distance_1_cm"]
            base_2 = settings["base_distance_2_cm"]
            settings = default_settings()
            settings["base_distance_1_cm"] = base_1
            settings["base_distance_2_cm"] = base_2
            direct_settings_changed = True
            direct_status = "DEFAULTS"
        elif command == "calibrate":
            handled_direct_command = True
            settings, offscreen_canvas, calibrated = run_calibration(
                settings,
                matrix,
                offscreen_canvas,
                debug_font,
                us100_1,
                us100_2,
            )
            direct_settings_changed = calibrated
            direct_status = "CAL OK" if calibrated else "CAL FAIL"
        elif command == "play_animation":
            handled_direct_command = True
            preview_count = min(counter + 1, MAX_COUNTER)
            preview_distance1, preview_distance2 = logical_sensor_values(settings, distance1, distance2)
            offscreen_canvas = fountain(
                matrix,
                offscreen_canvas,
                font,
                big_font,
                debug_font,
                counter,
                preview_count,
                distance1=preview_distance1,
                distance2=preview_distance2,
                debug_mode=False,
                status_message=None,
            )
            direct_status = "PLAY"
        elif command == "menu_open":
            handled_direct_command = True
            direct_opened_menu = True
            menu_open = True
            menu_edit_mode = False
            menu_index = 0
            menu_input_buffer = None
            menu_input_replace = False
            menu_confirm_exit_unsaved = False
            draft_settings = sanitize_settings(settings)
            draft_counter = counter
        elif command == "menu_cancel":
            handled_direct_command = True
            menu_open = False
            menu_edit_mode = False
            menu_index = 0
            menu_input_buffer = None
            menu_input_replace = False
            menu_confirm_exit_unsaved = False
            draft_settings = sanitize_settings(settings)
            draft_counter = counter
            direct_status = "CANCEL"
        elif command == "learn_start":
            handled_direct_command = True
            menu_open = False
            menu_edit_mode = False
            menu_index = 0
            menu_input_buffer = None
            menu_input_replace = False
            menu_confirm_exit_unsaved = False
            draft_settings = sanitize_settings(settings)
            draft_counter = counter
            sensor1_triggered_at = None
            sensor2_ready_after_sensor1 = False
            last_counted_at = None
            begin_learning_round(learning, now)
            direct_status = "LEARN"
        elif command == "learn_stop":
            handled_direct_command = True
            stop_learning(learning)
            sensor1_triggered_at = None
            sensor2_ready_after_sensor1 = False
            last_counted_at = None
            direct_status = "LEARN OFF"
        else:
            handled_direct_command, direct_settings_changed, direct_status = apply_direct_setting_command(command, settings)

        if handled_direct_command:
            if direct_status:
                status_message, status_expires_at = set_status_message(direct_status)
            if direct_settings_changed:
                settings = sanitize_settings(settings)
                save_settings(SETTINGS_STATE_PATH, settings)
                print(f"Updated settings={settings}", flush=True)
            if not direct_opened_menu:
                menu_open = False
                menu_edit_mode = False
                menu_input_buffer = None
                menu_input_replace = False
                menu_confirm_exit_unsaved = False
                draft_settings = sanitize_settings(settings)
                draft_counter = counter
            command = None

    if command is not None:
        if menu_open:
            selected_item = MENU_ITEMS[menu_index]
            if menu_confirm_exit_unsaved:
                if command == "yes":
                    settings, counter = save_menu_changes(draft_settings, draft_counter, counter)
                    menu_open = False
                    menu_edit_mode = False
                    menu_input_buffer = None
                    menu_input_replace = False
                    menu_confirm_exit_unsaved = False
                    status_message = None
                elif command in ("no", "esc"):
                    draft_settings = sanitize_settings(settings)
                    draft_counter = counter
                    menu_open = False
                    menu_edit_mode = False
                    menu_input_buffer = None
                    menu_input_replace = False
                    menu_confirm_exit_unsaved = False
                    status_message = None
            elif command == "enter":
                if selected_item["type"] == "action":
                    if selected_item["id"] == "calibrate":
                        def update_calibration_display(progress):
                            global offscreen_canvas
                            render_calibrating_display(
                                offscreen_canvas,
                                debug_font,
                                progress,
                                sensor_order=draft_settings["sensor_order"],
                            )
                            offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)

                        render_calibrating_display(
                            offscreen_canvas,
                            debug_font,
                            {
                                "remaining_seconds": CALIBRATION_SECONDS,
                                "current_1": 0,
                                "current_2": 0,
                                "calibrated_1": None,
                                "calibrated_2": None,
                            },
                            sensor_order=draft_settings["sensor_order"],
                        )
                        offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
                        base_1, base_2 = calibrate_base_distances(
                            us100_1,
                            us100_2,
                            duration_seconds=CALIBRATION_SECONDS,
                            progress_callback=update_calibration_display,
                        )
                        if base_1 is not None and base_2 is not None:
                            draft_settings["base_distance_1_cm"] = base_1
                            draft_settings["base_distance_2_cm"] = base_2
                            settings["base_distance_1_cm"] = base_1
                            settings["base_distance_2_cm"] = base_2
                            save_settings(SETTINGS_STATE_PATH, settings)
                            print(f"Calibrated base distances to {base_1}cm/{base_2}cm", flush=True)
                        menu_edit_mode = False
                        menu_input_buffer = None
                        menu_input_replace = False
                    elif selected_item["id"] == "play_animation":
                        preview_count = min(draft_counter + 1, MAX_COUNTER)
                        preview_distance1, preview_distance2 = logical_sensor_values(draft_settings, distance1, distance2)
                        offscreen_canvas = fountain(
                            matrix,
                            offscreen_canvas,
                            font,
                            big_font,
                            debug_font,
                            draft_counter,
                            preview_count,
                            distance1=preview_distance1,
                            distance2=preview_distance2,
                            debug_mode=False,
                            status_message=None,
                        )
                        draft_counter = preview_count
                        menu_edit_mode = False
                        menu_input_buffer = None
                        menu_input_replace = False
                    elif selected_item["id"] == "reset_defaults":
                        base_1 = draft_settings["base_distance_1_cm"]
                        base_2 = draft_settings["base_distance_2_cm"]
                        draft_settings = default_settings()
                        draft_settings["base_distance_1_cm"] = base_1
                        draft_settings["base_distance_2_cm"] = base_2
                        draft_counter = counter
                        menu_edit_mode = False
                        menu_input_buffer = None
                        menu_input_replace = False
                    elif selected_item["id"] == "save_exit":
                        settings, counter = save_menu_changes(draft_settings, draft_counter, counter)
                        menu_open = False
                        menu_edit_mode = False
                        menu_input_buffer = None
                        menu_input_replace = False
                        menu_confirm_exit_unsaved = False
                        status_message = None
                elif selected_item["type"] in ("bool", "order"):
                    draft_counter = adjust_menu_setting(selected_item, draft_settings, draft_counter, 1)
                    menu_edit_mode = False
                    menu_input_buffer = None
                    menu_input_replace = False
                else:
                    if menu_edit_mode:
                        draft_counter = commit_menu_input(selected_item, draft_settings, draft_counter, menu_input_buffer)
                        menu_input_buffer = None
                        menu_input_replace = False
                    else:
                        if selected_item["id"] == "counter_value":
                            menu_input_buffer = str(draft_counter)
                        elif selected_item["id"] in ("timeout_ms", "cooldown_ms"):
                            menu_input_buffer = format_timeout_seconds(draft_settings["timeout_ms"])
                            if selected_item["id"] == "cooldown_ms":
                                menu_input_buffer = format_timeout_seconds(draft_settings["cooldown_ms"])
                        else:
                            menu_input_buffer = str(draft_settings[selected_item["id"]])
                        menu_input_replace = True
                    menu_edit_mode = not menu_edit_mode
            elif command == "up":
                if menu_edit_mode:
                    draft_counter = commit_menu_input(selected_item, draft_settings, draft_counter, menu_input_buffer)
                    menu_input_buffer = None
                    menu_input_replace = False
                    draft_counter = adjust_menu_setting(selected_item, draft_settings, draft_counter, 1)
                else:
                    menu_index = (menu_index - 1) % len(MENU_ITEMS)
            elif command == "down":
                if menu_edit_mode:
                    draft_counter = commit_menu_input(selected_item, draft_settings, draft_counter, menu_input_buffer)
                    menu_input_buffer = None
                    menu_input_replace = False
                    draft_counter = adjust_menu_setting(selected_item, draft_settings, draft_counter, -1)
                else:
                    menu_index = (menu_index + 1) % len(MENU_ITEMS)
            elif command == "left" and menu_edit_mode:
                draft_counter = commit_menu_input(selected_item, draft_settings, draft_counter, menu_input_buffer)
                menu_input_buffer = None
                menu_input_replace = False
                draft_counter = adjust_menu_setting(selected_item, draft_settings, draft_counter, -1)
            elif command == "right" and menu_edit_mode:
                draft_counter = commit_menu_input(selected_item, draft_settings, draft_counter, menu_input_buffer)
                menu_input_buffer = None
                menu_input_replace = False
                draft_counter = adjust_menu_setting(selected_item, draft_settings, draft_counter, 1)
            elif command.startswith("digit:") and menu_edit_mode and selected_item["type"] in ("int", "float"):
                digit = command.split(":", 1)[1]
                if menu_input_replace:
                    menu_input_buffer = digit
                    menu_input_replace = False
                else:
                    menu_input_buffer = (menu_input_buffer or "") + digit
            elif command == "dot" and menu_edit_mode and selected_item["type"] == "float":
                if menu_input_replace:
                    menu_input_buffer = "0."
                    menu_input_replace = False
                elif "." not in (menu_input_buffer or ""):
                    menu_input_buffer = f"{menu_input_buffer or '0'}."
            elif command == "backspace" and menu_edit_mode and selected_item["type"] in ("int", "float"):
                if menu_input_replace:
                    menu_input_buffer = ""
                    menu_input_replace = False
                else:
                    menu_input_buffer = (menu_input_buffer or "")[:-1]
            elif command == "space":
                draft_settings["debug_mode"] = not draft_settings["debug_mode"]
                menu_edit_mode = False
                menu_input_buffer = None
                menu_input_replace = False
            elif command == "esc":
                if menu_edit_mode:
                    draft_counter = commit_menu_input(selected_item, draft_settings, draft_counter, menu_input_buffer)
                menu_edit_mode = False
                menu_input_buffer = None
                menu_input_replace = False
                if has_unsaved_menu_changes(settings, draft_settings, counter, draft_counter):
                    menu_confirm_exit_unsaved = True
                else:
                    menu_open = False
                    menu_confirm_exit_unsaved = False
            elif command == "count_reset":
                counter = reset_counter_with_log(counter, "debug_menu")
                sensor1_triggered_at = None
                sensor2_ready_after_sensor1 = False
                last_counted_at = None
        else:
            if command == "enter":
                menu_open = True
                menu_edit_mode = False
                menu_index = 0
                menu_input_buffer = None
                menu_input_replace = False
                menu_confirm_exit_unsaved = False
                draft_settings = sanitize_settings(settings)
                draft_counter = counter
            elif command == "space":
                updated_counter, settings_changed, counter_changed, key_status = apply_command("debug_toggle", settings, counter)
                if key_status:
                    status_message, status_expires_at = set_status_message(key_status)
                if settings_changed:
                    save_settings(SETTINGS_STATE_PATH, settings)
                    print(f"Updated settings={settings}", flush=True)
                if counter_changed:
                    old_counter = counter
                    counter = updated_counter
                    save_counter(COUNTER_STATE_PATH, counter)
                    log_event("counter_reset", old_count=old_counter, new_count=updated_counter, source="keyboard")
                    sensor1_triggered_at = None
                    sensor2_ready_after_sensor1 = False
                    print("Counter reset from keyboard", flush=True)
            elif command == "count_reset":
                counter = reset_counter_with_log(counter, "keyboard")
                sensor1_triggered_at = None
                sensor2_ready_after_sensor1 = False
                last_counted_at = None

    active_settings = draft_settings if menu_open else settings
    current_brightness_percent = apply_matrix_brightness(matrix, active_settings, current_brightness_percent)

    raw_distance1 = us100_1.distance
    raw_distance2 = us100_2.distance
    baseline_1 = active_settings["base_distance_1_cm"]
    baseline_2 = active_settings["base_distance_2_cm"]
    filtered_distance1, distance1_ignored, last_valid_distance1 = effective_distance(raw_distance1, baseline_1, last_valid_distance1)
    filtered_distance2, distance2_ignored, last_valid_distance2 = effective_distance(raw_distance2, baseline_2, last_valid_distance2)
    distance1 = raw_distance1
    distance2 = raw_distance2
    display_distance1, display_distance2 = logical_sensor_values(active_settings, distance1, distance2)
    display_distance1_ignored, display_distance2_ignored = logical_sensor_values(
        active_settings,
        distance1_ignored,
        distance2_ignored,
    )

    base_1 = active_settings["base_distance_1_cm"] if active_settings["base_distance_1_cm"] is not None else round(filtered_distance1 or raw_distance1)
    base_2 = active_settings["base_distance_2_cm"] if active_settings["base_distance_2_cm"] is not None else round(filtered_distance2 or raw_distance2)
    threshold_1 = max(1, base_1 - active_settings["threshold_cm"])
    threshold_2 = max(1, base_2 - active_settings["threshold_cm"])
    trigger_distance1, trigger_distance2 = logical_sensor_values(active_settings, filtered_distance1, filtered_distance2)
    trigger_threshold1, trigger_threshold2 = logical_sensor_values(active_settings, threshold_1, threshold_2)
    cooldown_active = (
        last_counted_at is not None
        and now - last_counted_at < active_settings["cooldown_ms"] / 1000.0
    )

    learning_active = bool(learning.get("active"))
    if learning_active:
        _, learn_status = update_learning(learning, settings, now, raw_distance1, raw_distance2)
        if learn_status:
            status_message, status_expires_at = set_status_message(learn_status)
        sensor1_triggered_at = None
        sensor2_ready_after_sensor1 = False
        last_counted_at = None
        active_settings = draft_settings if menu_open else settings
        display_distance1, display_distance2 = logical_sensor_values(active_settings, distance1, distance2)
        display_distance1_ignored, display_distance2_ignored = logical_sensor_values(
            active_settings,
            distance1_ignored,
            distance2_ignored,
        )
        cooldown_active = False
    else:
        trigger_state, trigger_event = process_counter_sample(
            active_settings,
            default_trigger_state(sensor1_triggered_at, sensor2_ready_after_sensor1, last_counted_at),
            now,
            trigger_distance1,
            trigger_distance2,
            trigger_threshold1,
            trigger_threshold2,
        )
        sensor1_triggered_at = trigger_state["sensor1_triggered_at"]
        sensor2_ready_after_sensor1 = trigger_state["sensor2_ready_after_sensor1"]
        last_counted_at = trigger_state["last_counted_at"]
        cooldown_active = trigger_event["cooldown_active"]

        if trigger_event["sensor_a_started"]:
            print(f"Sensor A triggered: {trigger_distance1} cm", flush=True)
        if trigger_event["timed_out"]:
            print(f"Timeout - sensor B did not trigger within {active_settings['timeout_ms']}ms", flush=True)
        if trigger_event["counted"]:
            old_count = counter
            counter += 1
            save_counter(COUNTER_STATE_PATH, counter)
            log_event(
                "counter_triggered",
                old_count=old_count,
                new_count=counter,
                direction="a_to_b",
                sensor_order=active_settings["sensor_order"],
                sensor_a_distance_cm=trigger_distance1,
                sensor_b_distance_cm=trigger_distance2,
                sensor_a_threshold_cm=trigger_threshold1,
                sensor_b_threshold_cm=trigger_threshold2,
                raw_sensor_1_distance_cm=distance1,
                raw_sensor_2_distance_cm=distance2,
            )
            print(f"Count! #{counter} (A->B)", flush=True)
            sensor1_triggered_at = None
            sensor2_ready_after_sensor1 = False
            if not menu_open:
                offscreen_canvas = fountain(
                    matrix,
                    offscreen_canvas,
                    font,
                    big_font,
                    debug_font,
                    old_count,
                    counter,
                    distance1=display_distance1,
                    distance2=display_distance2,
                    debug_mode=active_settings["debug_mode"],
                    status_message=status_message,
                )

    print(
        f"d1={distance1:.0f}cm{' ignored' if distance1_ignored else ''} "
        f"d2={distance2:.0f}cm{' ignored' if distance2_ignored else ''} count={counter}",
        flush=True,
    )
    last_learning_state_json = publish_learning_state(
        LEARNING_STATE_PATH,
        learning,
        time.time(),
        last_learning_state_json,
    )

    if menu_open:
        render_menu_display(
            offscreen_canvas,
            debug_font,
            draft_settings,
            draft_counter,
            menu_index,
            menu_edit_mode,
            menu_input_buffer,
            menu_confirm_exit_unsaved,
            display_distance1,
            display_distance2,
            display_distance1_ignored,
            display_distance2_ignored,
            sensor1_triggered_at,
            last_counted_at,
            cooldown_active,
        )
        offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
    elif learning.get("active"):
        render_learning_display(
            offscreen_canvas,
            font,
            big_font,
            debug_font,
            learning,
            time.time(),
            display_distance1,
            display_distance2,
        )
        offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
    else:
        offscreen_canvas = draw_counter_display(
            matrix,
            offscreen_canvas,
            font,
            big_font,
            debug_font,
            counter,
            distance1=display_distance1,
            distance2=display_distance2,
            distance1_ignored=display_distance1_ignored,
            distance2_ignored=display_distance2_ignored,
            debug_mode=active_settings["debug_mode"],
            status_message=status_message,
        )
