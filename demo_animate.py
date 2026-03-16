"""Demo script to run animations on the local rgbmatrix emulator.

Uses the local `rgbmatrix` emulator package and `animations.splash` to
exercise the animation without any hardware attached.
"""
import threading
import time
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from animations import splash, draw_counter_display


def animate(m):
    canvas = m.CreateFrameCanvas()

    # load fonts (best-effort)
    small = graphics.Font()
    small.LoadFont("fonts/6x12.bdf")
    big = graphics.Font()
    big.LoadFont("fonts/9x18.bdf")

    try:
        while True:
            for counter in (37, 38):
                canvas = draw_counter_display(m, canvas, small, big, 123, 456, counter)
                time.sleep(0.6)
                canvas = splash(m, canvas, big, counter + 1)
                time.sleep(0.2)
    except KeyboardInterrupt:
        print("Demo stopped")


def main():
    opts = RGBMatrixOptions(rows=32, cols=64)
    # scale controls how big the preview window is on your Mac
    m = RGBMatrix(opts, scale=8)

    t = threading.Thread(target=animate, args=(m,), daemon=True)
    t.start()

    # Tk mainloop must run on the main thread (macOS requirement)
    m.run()


if __name__ == "__main__":
    main()
