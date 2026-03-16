import math
import time
from rgbmatrix import graphics


SPLASH_FRAMES = 14
SPLASH_RING_WIDTH = 6
SPLASH_FRAME_DELAY = 0.035


def splash(matrix, canvas, font, count):
    """Expanding white ring with the new count shown in the center.

    Kept API compatible with the original `load-counter.py` splash(matrix, canvas, font, count).
    """
    WIDTH = getattr(matrix, "cols", canvas.width)
    HEIGHT = getattr(matrix, "rows", canvas.height)
    CX, CY = WIDTH // 2, HEIGHT // 2
    MAX_RADIUS = math.sqrt(CX ** 2 + CY ** 2)

    for frame in range(SPLASH_FRAMES):
        t = frame / (SPLASH_FRAMES - 1)  # 0.0 → 1.0
        radius = t * MAX_RADIUS * 1.3
        brightness = 1.0 - t * 0.7  # fade as it expands

        canvas.Clear()

        # Draw ring: only pixels near the ring edge light up
        for y in range(HEIGHT):
            for x in range(WIDTH):
                dist = math.sqrt((x - CX) ** 2 + (y - CY) ** 2)
                diff = abs(dist - radius)
                if diff < SPLASH_RING_WIDTH:
                    intensity = (1.0 - diff / SPLASH_RING_WIDTH) * brightness
                    v = int(255 * intensity)
                    canvas.SetPixel(x, y, v, v, v)

        # Draw counter text on top
        color = graphics.Color(255, 255, 0)
        text = str(count)
        # Use DrawText from graphics module; position roughly centered
        text_width = len(text) * 9
        text_x = (WIDTH - text_width) // 2
        graphics.DrawText(canvas, font, text_x, HEIGHT - 8, color, text)

        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(SPLASH_FRAME_DELAY)

    return canvas


def draw_counter_display(matrix, canvas, font, big_font, distance1, distance2, counter):
    """Draw the main counter and distance readout and swap the canvas.

    Convenience helper for demos and for keeping UI code in one place.
    """
    canvas.Clear()
    text_color = graphics.Color(255, 255, 0)
    dim_color = graphics.Color(80, 80, 0)
    graphics.DrawText(canvas, font, 0, 10, dim_color, f"{distance1:.0f}  {distance2:.0f}")
    graphics.DrawText(canvas, big_font, 0, matrix.rows - 2, text_color, str(counter))
    return matrix.SwapOnVSync(canvas)
