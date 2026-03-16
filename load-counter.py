import math
import time
import sys

from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

import serial
import adafruit_us100

uart1 = serial.Serial("/dev/ttyUSB0", baudrate=9600, timeout=1)
uart2 = serial.Serial("/dev/ttyUSB1", baudrate=9600, timeout=1)

us100_1 = adafruit_us100.US100(uart1)
us100_2 = adafruit_us100.US100(uart2)

options = RGBMatrixOptions()
options.rows = 32
options.cols = 64
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = 'adafruit-hat'

matrix = RGBMatrix(options=options)
offscreen_canvas = matrix.CreateFrameCanvas()
font = graphics.Font()
font.LoadFont("fonts/6x12.bdf")
big_font = graphics.Font()
big_font.LoadFont("fonts/9x18.bdf")

# animation helpers are extracted to animations.py
from animations import splash


counter = 0
sensor1_triggered_at = None

while True:
    distance1 = us100_1.distance
    distance2 = us100_2.distance

    # State machine: sensor 1 triggers, then sensor 2 confirms within TIMEOUT
    if distance1 < THRESHOLD:
        if sensor1_triggered_at is None:
            sensor1_triggered_at = time.time()
            print(f"Sensor 1 triggered: {distance1} cm")

    if sensor1_triggered_at is not None:
        if time.time() - sensor1_triggered_at > TIMEOUT:
            print(f"Timeout — sensor 2 did not trigger within {TIMEOUT}s")
            sensor1_triggered_at = None
        elif distance2 < THRESHOLD:
            counter += 1
            print(f"Count! #{counter} (sensor1→sensor2)")
            sensor1_triggered_at = None
            offscreen_canvas = splash(matrix, offscreen_canvas, big_font, counter)
            continue

    print(f"d1={distance1:.0f}cm d2={distance2:.0f}cm count={counter}")

    # Display counter on matrix
    offscreen_canvas.Clear()
    text_color = graphics.Color(255, 255, 0)
    dim_color = graphics.Color(80, 80, 0)
    graphics.DrawText(offscreen_canvas, font, 0, 10, dim_color, f"{distance1:.0f}  {distance2:.0f}")
    graphics.DrawText(offscreen_canvas, big_font, 0, 30, text_color, str(counter))
    offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
