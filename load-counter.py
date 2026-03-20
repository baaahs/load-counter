import math
import os
import random
import sys
import time

from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

import adafruit_us100
import serial

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

THRESHOLD = 40  # cm
TIMEOUT = 20  # seconds
WIDTH = 64
HEIGHT = 32
CX, CY = WIDTH // 2, HEIGHT // 2
MAX_RADIUS = math.sqrt(CX ** 2 + CY ** 2)

FOUNTAIN_STAGGER = 3
FOUNTAIN_FRAME_DELAY = 0.022


def text_width(font, text):
    return sum(font.CharacterWidth(ord(char)) for char in text)


def draw_counter_display(matrix, canvas, font, big_font, counter):
    canvas.Clear()

    label = "LOAD COUNT"
    label_color = graphics.Color(180, 180, 255)
    count_color = graphics.Color(255, 255, 0)

    label_width = text_width(font, label)
    graphics.DrawText(canvas, font, (WIDTH - label_width) // 2, 8, label_color, label)

    num = str(counter)
    count_width = text_width(big_font, num)
    num_y = 30
    graphics.DrawText(canvas, big_font, (WIDTH - count_width) // 2, num_y, count_color, num)

    return matrix.SwapOnVSync(canvas)


def fountain(matrix, canvas, font, big_font, old_count, new_count):
    label = "LOAD COUNT"
    label_width = text_width(font, label)

    new_text = str(new_count)
    new_width = text_width(big_font, new_text)
    new_x = (WIDTH - new_width) // 2
    new_y = 30

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
        graphics.DrawText(canvas, big_font, new_x, new_y, graphics.Color(255, 255, 0), new_text)

        for sp in swimmers:
            if frame < sp["launch"]:
                continue

            sp["hx"] += sp["vx"]
            hx = sp["hx"]
            hy = sp["hy"]
            phase = sp["phase"] + (frame - sp["launch"]) * 0.4

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
big_font.LoadFont(os.path.join(BASE_DIR, "fonts/9x18.bdf"))
matrix = RGBMatrix(options=options)
offscreen_canvas = matrix.CreateFrameCanvas()

counter = 0
sensor1_triggered_at = None
offscreen_canvas = draw_counter_display(matrix, offscreen_canvas, font, big_font, counter)

while True:
    distance1 = us100_1.distance
    distance2 = us100_2.distance

    if distance1 < THRESHOLD:
        if sensor1_triggered_at is None:
            sensor1_triggered_at = time.time()
            print(f"Sensor 1 triggered: {distance1} cm")

    if sensor1_triggered_at is not None:
        if time.time() - sensor1_triggered_at > TIMEOUT:
            print(f"Timeout - sensor 2 did not trigger within {TIMEOUT}s")
            sensor1_triggered_at = None
        elif distance2 < THRESHOLD:
            old_count = counter
            counter += 1
            print(f"Count! #{counter} (sensor1->sensor2)")
            sensor1_triggered_at = None
            offscreen_canvas = fountain(matrix, offscreen_canvas, font, big_font, old_count, counter)

    print(f"d1={distance1:.0f}cm d2={distance2:.0f}cm count={counter}")
    offscreen_canvas = draw_counter_display(matrix, offscreen_canvas, font, big_font, counter)
