import json
import math
import os
import random
import time

from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

import adafruit_us100
import serial

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_THRESHOLD = 40  # cm
DEFAULT_TIMEOUT_MS = 20_000
WIDTH = 64
HEIGHT = 32
COUNT_TOP = 11
FOUNTAIN_Y_OFFSET = -1
COUNTER_STATE_DIR = "/var/lib/loadcounter"
COUNTER_STATE_PATH = os.path.join(COUNTER_STATE_DIR, "counter-state.txt")
SETTINGS_STATE_PATH = os.path.join(COUNTER_STATE_DIR, "settings.json")
COMMAND_STATE_DIR = "/var/tmp/loadcounter"
KEYBOARD_COMMAND_PATH = os.path.join(COMMAND_STATE_DIR, "keyboard-command.json")
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
BDF_GLYPHS = {}
BOOT_TONE_MAP = {
    " ": (0, 0, 0),
    ".": (16, 16, 16),
    ":": (64, 64, 64),
    "-": (112, 112, 112),
    "=": (168, 168, 168),
    "#": (232, 232, 232),
}
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
    {"id": "counter_value", "label": "COUNT", "type": "int", "step": 1, "minimum": 0, "maximum": 999999},
    {"id": "threshold_cm", "label": "THRESH (cm)", "type": "int", "step": 1, "minimum": MIN_THRESHOLD, "maximum": MAX_THRESHOLD},
    {"id": "timeout_ms", "label": "TIME (s)", "type": "float", "step": 100, "minimum": MIN_TIMEOUT_MS, "maximum": MAX_TIMEOUT_MS},
    {"id": "debug_mode", "label": "DEBUG", "type": "bool"},
    {"id": "calibrate", "label": "CAL", "type": "action"},
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


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def default_settings():
    return {
        "threshold_cm": DEFAULT_THRESHOLD,
        "timeout_ms": DEFAULT_TIMEOUT_MS,
        "debug_mode": DEFAULT_DEBUG_MODE,
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

    settings["debug_mode"] = bool(raw_settings.get("debug_mode", DEFAULT_DEBUG_MODE))
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


def draw_debug_overlay(canvas, debug_font, distance1, distance2, debug_mode):
    if not debug_mode or distance1 is None or distance2 is None:
        return

    baseline_y = HEIGHT
    left_value = max(0, min(9999, round(distance1)))
    right_value = max(0, min(9999, round(distance2)))
    left_text = f"L:{left_value:>4}"
    right_text = f"R:{right_value:>4}"
    debug_color = graphics.Color(96, 255, 96)
    right_x = WIDTH - text_width(debug_font, "R:0000")

    graphics.DrawText(canvas, debug_font, 0, baseline_y, debug_color, left_text)
    graphics.DrawText(canvas, debug_font, right_x, baseline_y, debug_color, right_text)


def draw_footer_overlay(canvas, debug_font, distance1, distance2, debug_mode, status_message):
    if status_message:
        draw_status_overlay(canvas, debug_font, status_message)
        return

    draw_debug_overlay(canvas, debug_font, distance1, distance2, debug_mode)


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


def calibrate_base_distances(us100_1, us100_2, duration_seconds=2.0):
    samples_1 = []
    samples_2 = []
    deadline = time.time() + duration_seconds

    while time.time() < deadline:
        samples_1.append(us100_1.distance)
        samples_2.append(us100_2.distance)
        time.sleep(0.05)

    return filtered_average(samples_1), filtered_average(samples_2)


def render_calibrating_display(canvas, debug_font):
    canvas.Clear()
    color = graphics.Color(255, 180, 80)
    message = "CALIBRATING"
    text_x = max(0, (WIDTH - text_width(debug_font, message)) // 2)
    graphics.DrawText(canvas, debug_font, text_x, 15, color, message)
    graphics.DrawText(canvas, debug_font, 20, 23, color, "2s")


def format_timeout_seconds(timeout_ms):
    return f"{timeout_ms / 1000:.1f}"


def calibration_value_text(draft_settings):
    base_1 = draft_settings.get("base_distance_1_cm")
    base_2 = draft_settings.get("base_distance_2_cm")
    if base_1 is None or base_2 is None:
        return "--/--"
    return f"L{base_1} R{base_2}"


def menu_value_text(item, draft_settings, draft_counter):
    item_id = item["id"]
    if item_id == "counter_value":
        return str(draft_counter)
    if item_id == "threshold_cm":
        return str(draft_settings["threshold_cm"])
    if item_id == "timeout_ms":
        return format_timeout_seconds(draft_settings["timeout_ms"])
    if item_id == "debug_mode":
        return "ON" if draft_settings["debug_mode"] else "OFF"
    if item_id == "calibrate":
        return calibration_value_text(draft_settings)
    if item_id == "reset_defaults":
        return "DEF"
    if item_id == "save_exit":
        return "SAVE"
    return ""


def trigger_status_text(sensor1_triggered_at, last_counted_at, now):
    if last_counted_at is not None and now - last_counted_at <= COUNT_TRIGGER_FLASH_SECONDS:
        return "CNT"
    if sensor1_triggered_at is not None:
        return "ARM"
    return "IDL"


def has_unsaved_menu_changes(settings, draft_settings, counter, draft_counter):
    return sanitize_settings(draft_settings) != sanitize_settings(settings) or draft_counter != counter


def render_save_changes_dialog(canvas, debug_font):
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
    sensor1_triggered_at,
    last_counted_at,
):
    canvas.Clear()
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

    sensor_left = f"L{distance1:.0f}" if distance1 is not None else "L--"
    sensor_right = f"R{distance2:.0f}" if distance2 is not None else "R--"
    status_text = trigger_status_text(sensor1_triggered_at, last_counted_at, time.time())
    bottom_color = graphics.Color(96, 255, 96)
    status_color = graphics.Color(255, 180, 80) if status_text == "CNT" else graphics.Color(180, 180, 255)

    graphics.DrawText(canvas, debug_font, 0, HEIGHT - 1, bottom_color, sensor_left)
    graphics.DrawText(canvas, debug_font, 18, HEIGHT - 1, bottom_color, sensor_right)
    graphics.DrawText(canvas, debug_font, WIDTH - text_width(debug_font, status_text), HEIGHT - 1, status_color, status_text)
    if confirm_exit_unsaved:
        render_save_changes_dialog(canvas, debug_font)


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


def draw_counter_display(
    matrix,
    canvas,
    font,
    big_font,
    debug_font,
    counter,
    distance1=None,
    distance2=None,
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
    debug_mode=False,
    status_message=None,
):
    label = "LOAD COUNT"
    label_color = graphics.Color(*scale_color((180, 180, 255), label_brightness))
    count_color = graphics.Color(*scale_color((255, 255, 0), count_brightness))

    label_width = text_width(font, label)
    graphics.DrawText(canvas, font, (WIDTH - label_width) // 2, 8, label_color, label)

    num = str(counter)
    count_width = text_width(big_font, num)
    num_y = count_baseline(big_font)
    graphics.DrawText(canvas, big_font, (WIDTH - count_width) // 2, num_y, count_color, num)
    draw_footer_overlay(canvas, debug_font, distance1, distance2, debug_mode, status_message)


def fade_boot_to_counter(
    matrix,
    canvas,
    font,
    big_font,
    debug_font,
    counter,
    distance1=None,
    distance2=None,
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
    fallback_width = big_font.CharacterWidth(ord("0"))

    old_pixels = text_pixel_positions(BDF_GLYPHS, old_text, old_x, new_y, fallback_width)
    new_pixels = text_pixel_positions(BDF_GLYPHS, new_text, new_x, new_y, fallback_width)
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
                canvas.SetPixel(px, py, 255, 255, 0)
        for px, py in new_pixels:
            if (px, py) in written_pixels:
                canvas.SetPixel(px, py, 255, 255, 0)

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


def adjust_menu_setting(item, draft_settings, draft_counter, direction):
    if item["id"] == "counter_value":
        value = draft_counter + item["step"] * direction
        return clamp(value, item["minimum"], item["maximum"])

    if item["type"] == "bool":
        draft_settings[item["id"]] = not draft_settings[item["id"]]
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


def save_menu_changes(draft_settings, draft_counter):
    counter_value = draft_counter
    save_counter(COUNTER_STATE_PATH, counter_value)
    saved_settings = sanitize_settings(draft_settings)
    save_settings(SETTINGS_STATE_PATH, saved_settings)
    print(f"Updated settings={saved_settings} counter={counter_value}", flush=True)
    return saved_settings, counter_value


uart1 = serial.Serial("/dev/ttyUSB0", baudrate=9600, timeout=1)
uart2 = serial.Serial("/dev/ttyUSB1", baudrate=9600, timeout=1)

us100_1 = adafruit_us100.US100(uart1)
us100_2 = adafruit_us100.US100(uart2)

options = RGBMatrixOptions()
options.rows = 32
options.cols = 64
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = "adafruit-hat"

font = graphics.Font()
font.LoadFont(os.path.join(BASE_DIR, "fonts/6x12.bdf"))
big_font = graphics.Font()
big_font.LoadFont(os.path.join(BASE_DIR, "fonts/10x20.bdf"))
debug_font = graphics.Font()
debug_font.LoadFont(os.path.join(BASE_DIR, "fonts/4x6.bdf"))
BDF_GLYPHS = load_bdf_glyphs(os.path.join(BASE_DIR, "fonts/10x20.bdf"))
matrix = RGBMatrix(options=options)
offscreen_canvas = matrix.CreateFrameCanvas()

counter = load_counter(COUNTER_STATE_PATH, PRIOR_COUNTER_STATE_PATH)
if counter == 0:
    counter = load_counter(COUNTER_STATE_PATH, LEGACY_COUNTER_STATE_PATH)
ensure_counter_state_file(COUNTER_STATE_PATH, counter)
settings = load_settings(SETTINGS_STATE_PATH)
if settings["debug_mode"]:
    settings["debug_mode"] = False
save_settings(SETTINGS_STATE_PATH, settings)
clear_keyboard_command(KEYBOARD_COMMAND_PATH)
print(f"Loaded counter={counter} from {COUNTER_STATE_PATH}", flush=True)
print(f"Loaded settings={settings} from {SETTINGS_STATE_PATH}", flush=True)
sensor1_triggered_at = None
sensor2_ready_after_sensor1 = False
distance1 = None
distance2 = None
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
        if menu_open:
            selected_item = MENU_ITEMS[menu_index]
            if menu_confirm_exit_unsaved:
                if command == "yes":
                    settings, counter = save_menu_changes(draft_settings, draft_counter)
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
                        render_calibrating_display(offscreen_canvas, debug_font)
                        offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
                        base_1, base_2 = calibrate_base_distances(us100_1, us100_2)
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
                        settings, counter = save_menu_changes(draft_settings, draft_counter)
                        menu_open = False
                        menu_edit_mode = False
                        menu_input_buffer = None
                        menu_input_replace = False
                        menu_confirm_exit_unsaved = False
                        status_message = None
                elif selected_item["type"] == "bool":
                    draft_settings[selected_item["id"]] = not draft_settings[selected_item["id"]]
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
                        elif selected_item["id"] == "timeout_ms":
                            menu_input_buffer = format_timeout_seconds(draft_settings["timeout_ms"])
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
                counter = 0
                save_counter(COUNTER_STATE_PATH, counter)
                sensor1_triggered_at = None
                sensor2_ready_after_sensor1 = False
                last_counted_at = None
                print("Counter reset from keyboard", flush=True)
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
                    counter = updated_counter
                    save_counter(COUNTER_STATE_PATH, counter)
                    sensor1_triggered_at = None
                    sensor2_ready_after_sensor1 = False
                    print("Counter reset from keyboard", flush=True)
            elif command == "count_reset":
                counter = 0
                save_counter(COUNTER_STATE_PATH, counter)
                sensor1_triggered_at = None
                sensor2_ready_after_sensor1 = False
                last_counted_at = None
                print("Counter reset from keyboard", flush=True)

    active_settings = draft_settings if menu_open else settings

    distance1 = us100_1.distance
    distance2 = us100_2.distance

    base_1 = active_settings["base_distance_1_cm"] if active_settings["base_distance_1_cm"] is not None else round(distance1)
    base_2 = active_settings["base_distance_2_cm"] if active_settings["base_distance_2_cm"] is not None else round(distance2)
    threshold_1 = max(1, base_1 - active_settings["threshold_cm"])
    threshold_2 = max(1, base_2 - active_settings["threshold_cm"])

    if distance1 < threshold_1:
        if sensor1_triggered_at is None:
            sensor1_triggered_at = time.time()
            sensor2_ready_after_sensor1 = distance2 >= threshold_2
            print(f"Sensor 1 triggered: {distance1} cm", flush=True)

    if sensor1_triggered_at is not None:
        if not sensor2_ready_after_sensor1 and distance2 >= threshold_2:
            sensor2_ready_after_sensor1 = True

        if time.time() - sensor1_triggered_at > active_settings["timeout_ms"] / 1000.0:
            print(f"Timeout - sensor 2 did not trigger within {active_settings['timeout_ms']}ms", flush=True)
            sensor1_triggered_at = None
            sensor2_ready_after_sensor1 = False
        elif sensor2_ready_after_sensor1 and distance2 < threshold_2:
            old_count = counter
            counter += 1
            last_counted_at = time.time()
            save_counter(COUNTER_STATE_PATH, counter)
            print(f"Count! #{counter} (sensor1->sensor2)", flush=True)
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
                    distance1=distance1,
                    distance2=distance2,
                    debug_mode=active_settings["debug_mode"],
                    status_message=status_message,
                )

    print(f"d1={distance1:.0f}cm d2={distance2:.0f}cm count={counter}", flush=True)
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
            distance1,
            distance2,
            sensor1_triggered_at,
            last_counted_at,
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
            distance1=distance1,
            distance2=distance2,
            debug_mode=active_settings["debug_mode"],
            status_message=status_message,
        )
