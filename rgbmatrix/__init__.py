"""Lightweight rgbmatrix emulator for local development.

Provides: RGBMatrixOptions, RGBMatrix, and CreateFrameCanvas/SwapOnVSync APIs.

Displays a scaled window using Pillow + Tkinter. If Pillow isn't installed,
the module raises an informative error on import.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
try:
    from PIL import Image, ImageTk
    import tkinter as tk
except Exception as e:
    raise ImportError("rgbmatrix emulator requires Pillow and Tkinter. Install Pillow: pip install pillow") from e

from . import graphics


@dataclass
class RGBMatrixOptions:
    rows: int = 32
    cols: int = 64
    chain_length: int = 1
    parallel: int = 1
    hardware_mapping: str | None = None


class Canvas:
    def __init__(self, width, height):
        from PIL import Image, ImageDraw

        self.width = width
        self.height = height
        self.img = Image.new("RGB", (width, height), (0, 0, 0))
        self._draw = Image.new("RGB", (width, height), (0, 0, 0))

    def SetPixel(self, x, y, r, g, b):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.img.putpixel((x, y), (int(r) & 255, int(g) & 255, int(b) & 255))

    def Clear(self):
        from PIL import Image

        self.img = Image.new("RGB", (self.width, self.height), (0, 0, 0))


class RGBMatrix:
    """Must be created from the main thread (macOS AppKit requirement)."""

    def __init__(self, options: RGBMatrixOptions | None = None, scale: int = 10):
        if options is None:
            options = RGBMatrixOptions()
        self.options = options
        self.rows = options.rows
        self.cols = options.cols
        self.scale = scale
        self._queue: list = []
        self._lock = threading.Lock()

        w = self.cols * self.scale
        h = self.rows * self.scale

        self.root = tk.Tk()
        self.root.title("RGBMatrix Emulator")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.root.quit)
        self._tk_canvas = tk.Canvas(self.root, width=w, height=h, bg="black", highlightthickness=0)
        self._tk_canvas.pack()
        self._photo = None
        self._poll()

    def _poll(self):
        with self._lock:
            if self._queue:
                img = self._queue.pop(0)
                self._photo = ImageTk.PhotoImage(img, master=self.root)
                self._tk_canvas.delete("all")
                self._tk_canvas.create_image(0, 0, anchor="nw", image=self._photo)
                self._tk_canvas.image = self._photo
        self.root.after(20, self._poll)

    def CreateFrameCanvas(self):
        return Canvas(self.cols, self.rows)

    def SwapOnVSync(self, canvas: Canvas):
        # scale the small matrix image and enqueue for display
        img = canvas.img.resize(
            (self.cols * self.scale, self.rows * self.scale), resample=Image.NEAREST
        )
        with self._lock:
            self._queue.append(img)
        return Canvas(self.cols, self.rows)

    def run(self):
        """Start the Tk main loop. Must be called from the main thread."""
        self.root.mainloop()


# Expose graphics helpers under the package as in the original lib
Font = graphics.Font
Color = graphics.Color
DrawText = graphics.DrawText

__all__ = ["RGBMatrixOptions", "RGBMatrix", "Font", "Color", "DrawText", "graphics"]
