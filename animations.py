import math
import time
import random
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


def fountain(matrix, canvas, font, big_font, old_count, new_count):
    """Spermatozoids swim left-to-right; each one writes new number pixels as it passes through."""
    W = getattr(matrix, "cols", canvas.width)
    H = getattr(matrix, "rows", canvas.height)

    label = "LOAD COUNT"
    lw = graphics.TextWidth(font, label)
    label_bottom = 7

    def num_draw_pos(n):
        nw, nh = graphics.TextSize(big_font, str(n))
        num_top = label_bottom + (H - label_bottom - nh) // 2 - 3
        return (W - nw) // 2, num_top + nh

    def render_pixels(n):
        tmp = matrix.CreateFrameCanvas()
        nx, ny = num_draw_pos(n)
        graphics.DrawText(tmp, big_font, nx, ny, graphics.Color(255, 255, 0), str(n))
        pix = tmp.img.load()
        return [(x, y, *pix[x, y]) for y in range(H) for x in range(W) if any(pix[x, y])]

    old_pixels = render_pixels(old_count)
    new_pixels = render_pixels(new_count)

    # One sperm per row, shuffled launch order, staggered
    STAGGER = 3
    y_positions = list(range(5, H - 2))
    random.shuffle(y_positions)
    sperm_list = []
    for i, sy in enumerate(y_positions):
        sperm_list.append({
            'hx': -14.0,
            'hy': float(sy),
            'vx': random.uniform(1.3, 2.0),
            'amp': random.uniform(0.7, 1.5),
            'freq': random.uniform(0.45, 0.75),
            'phase': random.uniform(0, 2 * math.pi),
            'launch': i * STAGGER,
            'tail_len': random.randint(7, 12),
        })

    last_launch = sperm_list[-1]['launch']
    FRAMES = last_launch + int(W / 1.3) + 20
    FRAME_DELAY = 0.022

    # Index new pixels by column for fast per-sperm lookup
    new_by_col = {}
    for px, py, r, g, b in new_pixels:
        new_by_col.setdefault(px, []).append((py, r, g, b))

    written = set()  # (x, y) pixels of new number that have been written

    for frame in range(FRAMES):
        canvas.Clear()

        # Advance sperm; write new number pixels within reach of each sperm's head
        for sp in sperm_list:
            if frame < sp['launch']:
                continue
            sp['hx'] += sp['vx']
            col = int(round(sp['hx']))
            if 0 <= col < W and col in new_by_col:
                for py, r, g, b in new_by_col[col]:
                    if abs(py - sp['hy']) <= 2:
                        written.add((col, py))

        # Draw number: written pixels → new, unwritten → old
        for px, py, r, g, b in new_pixels:
            if (px, py) in written:
                canvas.SetPixel(px, py, r, g, b)
        for px, py, r, g, b in old_pixels:
            if (px, py) not in written:
                canvas.SetPixel(px, py, r, g, b)

        # Draw label
        graphics.DrawText(canvas, font, (W - lw) // 2, 6,
                          graphics.Color(180, 180, 255), label)

        # Draw each active sperm
        for sp in sperm_list:
            if frame < sp['launch']:
                continue
            hx = sp['hx']
            hy = sp['hy']
            t = frame - sp['launch']
            phase = sp['phase'] + t * 0.4

            # Head: small oval
            for dx, dy in [(0, 0), (1, 0), (-1, 0), (0, -1), (0, 1)]:
                hpx, hpy = int(round(hx)) + dx, int(round(hy)) + dy
                if 0 <= hpx < W and 0 <= hpy < H:
                    canvas.SetPixel(hpx, hpy, 255, 255, 230)

            # Tail: sinusoidal wave trailing behind the head
            tail_len = sp['tail_len']
            for i in range(1, tail_len + 1):
                tx = int(round(hx)) - i - 1
                ty = int(round(hy + sp['amp'] * math.sin(phase + i * sp['freq'])))
                if 0 <= tx < W and 0 <= ty < H:
                    fade = (tail_len - i + 1) / tail_len
                    canvas.SetPixel(tx, ty, int(220 * fade), int(220 * fade), int(140 * fade))

        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(FRAME_DELAY)

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
