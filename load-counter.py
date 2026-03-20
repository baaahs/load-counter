import math
import os
import random
import time

from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

import adafruit_us100
import serial

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

THRESHOLD = 40  # cm
TIMEOUT = 20  # seconds
WIDTH = 64
HEIGHT = 32
COUNT_TOP = 11
FOUNTAIN_Y_OFFSET = -1
COUNTER_STATE_DIR = "/var/lib/loadcounter"
COUNTER_STATE_PATH = os.path.join(COUNTER_STATE_DIR, "counter-state.txt")
PRIOR_COUNTER_STATE_PATH = "/var/tmp/loadcounter/counter-state.txt"
LEGACY_COUNTER_STATE_PATH = os.path.join(BASE_DIR, "counter-state.txt")

FOUNTAIN_STAGGER = 3
FOUNTAIN_FRAME_DELAY = 0.029
BOOT_HOLD_SECONDS = 2.2
BDF_GLYPHS = {}


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


def boot_screen(matrix, canvas, font, big_font):
    canvas.Clear()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            canvas.SetPixel(x, y, 0, 0, 0)

    text = "baaahs"
    shadow_color = graphics.Color(70, 70, 70)
    text_color = graphics.Color(255, 255, 255)
    text_width_px = text_width(big_font, text)
    text_x = (WIDTH - text_width_px) // 2
    baseline_y = 23

    graphics.DrawText(canvas, big_font, text_x + 1, baseline_y + 1, shadow_color, text)
    graphics.DrawText(canvas, big_font, text_x, baseline_y, text_color, text)

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


def draw_counter_display(matrix, canvas, font, big_font, counter):
    canvas.Clear()

    label = "LOAD COUNT"
    label_color = graphics.Color(180, 180, 255)
    count_color = graphics.Color(255, 255, 0)

    label_width = text_width(font, label)
    graphics.DrawText(canvas, font, (WIDTH - label_width) // 2, 8, label_color, label)

    num = str(counter)
    count_width = text_width(big_font, num)
    num_y = count_baseline(big_font)
    graphics.DrawText(canvas, big_font, (WIDTH - count_width) // 2, num_y, count_color, num)

    return matrix.SwapOnVSync(canvas)


def fountain(matrix, canvas, font, big_font, old_count, new_count):
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

    return draw_counter_display(matrix, canvas, font, big_font, new_count)


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
BDF_GLYPHS = load_bdf_glyphs(os.path.join(BASE_DIR, "fonts/10x20.bdf"))
matrix = RGBMatrix(options=options)
offscreen_canvas = matrix.CreateFrameCanvas()

counter = load_counter(COUNTER_STATE_PATH, PRIOR_COUNTER_STATE_PATH)
if counter == 0:
    counter = load_counter(COUNTER_STATE_PATH, LEGACY_COUNTER_STATE_PATH)
ensure_counter_state_file(COUNTER_STATE_PATH, counter)
print(f"Loaded counter={counter} from {COUNTER_STATE_PATH}", flush=True)
sensor1_triggered_at = None
offscreen_canvas = boot_screen(matrix, offscreen_canvas, font, big_font)
offscreen_canvas = draw_counter_display(matrix, offscreen_canvas, font, big_font, counter)

while True:
    distance1 = us100_1.distance
    distance2 = us100_2.distance

    if distance1 < THRESHOLD:
        if sensor1_triggered_at is None:
            sensor1_triggered_at = time.time()
            print(f"Sensor 1 triggered: {distance1} cm", flush=True)

    if sensor1_triggered_at is not None:
        if time.time() - sensor1_triggered_at > TIMEOUT:
            print(f"Timeout - sensor 2 did not trigger within {TIMEOUT}s", flush=True)
            sensor1_triggered_at = None
        elif distance2 < THRESHOLD:
            old_count = counter
            counter += 1
            save_counter(COUNTER_STATE_PATH, counter)
            print(f"Count! #{counter} (sensor1->sensor2)", flush=True)
            sensor1_triggered_at = None
            offscreen_canvas = fountain(matrix, offscreen_canvas, font, big_font, old_count, counter)

    print(f"d1={distance1:.0f}cm d2={distance2:.0f}cm count={counter}", flush=True)
    offscreen_canvas = draw_counter_display(matrix, offscreen_canvas, font, big_font, counter)
