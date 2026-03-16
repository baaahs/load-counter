"""Minimal graphics helpers for the rgbmatrix emulator.

Provides a `Font` class with `LoadFont(path)` (best-effort), a `Color` factory,
and `DrawText(canvas, font, x, y, color, text)` which renders text onto a
Canvas produced by the emulator.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    from PIL import ImageDraw, ImageFont
except Exception as e:
    raise ImportError("rgbmatrix graphics requires Pillow. Install with: pip install pillow") from e


@dataclass
class Color:
    r: int
    g: int
    b: int


class Font:
    def __init__(self):
        self.pil_font: Optional[ImageFont.ImageFont] = None
        self.size = 10

    def LoadFont(self, path: str):
        # Best-effort: if a TTF is provided, load it; otherwise guess size from filename
        try:
            if path.lower().endswith((".ttf", ".otf")):
                size = _guess_size_from_name(path) or 12
                self.pil_font = ImageFont.truetype(path, size)
                self.size = size
                return
        except Exception:
            pass

        # For BDF/other fonts, use guessed size with load_default
        size = _guess_size_from_name(path) or 10
        self.size = size
        try:
            self.pil_font = ImageFont.load_default(size=size)
        except TypeError:
            self.pil_font = ImageFont.load_default()


def _guess_size_from_name(path: str) -> int | None:
    import re

    m = re.findall(r"(\d{1,3})", path)
    if m:
        # pick largest number as size
        return int(m[-1])
    return None


def TextWidth(font: Font, text: str) -> int:
    """Return the pixel width of text rendered with the given font."""
    w, _ = TextSize(font, text)
    return w


def TextSize(font: Font, text: str):
    """Return (width, height) of text rendered with the given font."""
    from PIL import ImageFont

    pil_font = font.pil_font if (font and getattr(font, "pil_font", None)) else ImageFont.load_default()
    from PIL import ImageDraw, Image
    tmp = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(tmp)
    bbox = draw.textbbox((0, 0), text, font=pil_font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def DrawText(canvas, font: Font, x: int, y: int, color: Color, text: str):
    """Draw text onto the emulator canvas.

    The `y` value is treated as a baseline-like coordinate to mimic the original API.
    """
    from PIL import ImageDraw

    if not hasattr(canvas, "img"):
        return

    draw = ImageDraw.Draw(canvas.img)
    pil_font = font.pil_font if (font and getattr(font, "pil_font", None)) else ImageFont.load_default()
    # compute height and adjust so `y` works like baseline
    bbox = draw.textbbox((0, 0), text, font=pil_font)
    h = bbox[3] - bbox[1]
    top = max(0, y - h)
    draw.text((x, top), text, fill=(color.r, color.g, color.b), font=pil_font)
