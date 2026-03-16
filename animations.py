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


def draw_counter_display(matrix, canvas, font, big_font, counter):
    """Draw 'LOAD COUNT' label centered at top, counter centered below."""
    W = getattr(matrix, "cols", canvas.width)
    H = getattr(matrix, "rows", canvas.height)

    canvas.Clear()

    label_color = graphics.Color(180, 180, 255)
    count_color = graphics.Color(255, 255, 0)

    label = "LOAD COUNT"
    lw = graphics.TextWidth(font, label)
    graphics.DrawText(canvas, font, (W - lw) // 2, 6, label_color, label)

    # center number vertically in the space below the label (rows 7–H)
    num = str(counter)
    nw, nh = graphics.TextSize(big_font, num)
    label_bottom = 7
    num_top = label_bottom + (H - label_bottom - nh) // 2 - 3
    graphics.DrawText(canvas, big_font, (W - nw) // 2, num_top + nh, count_color, num)

    return matrix.SwapOnVSync(canvas)
