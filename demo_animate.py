"""Demo script to run animations on the local rgbmatrix emulator.

Uses the local `rgbmatrix` emulator package and `animations.fountain` to
exercise the animation without any hardware attached.
"""
import threading
import time
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from animations import fountain, draw_counter_display


def animate(m):
    canvas = m.CreateFrameCanvas()

    # load fonts (best-effort)
    small = graphics.Font()
    small.LoadFont("fonts/5x7.bdf")
    big = graphics.Font()
    big.LoadFont("fonts/10x20.bdf")

    counter = 0

    try:
        while True:
            canvas = draw_counter_display(m, canvas, small, big, counter)
            time.sleep(0.6)
            canvas = fountain(m, canvas, small, big, counter, counter + 1)
            counter += 1
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
