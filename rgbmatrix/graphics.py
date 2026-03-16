"""Minimal graphics helpers for the rgbmatrix emulator.

Provides a `Font` class with `LoadFont(path)` (best-effort), a `Color` factory,
and `DrawText(canvas, font, x, y, color, text)` which renders text onto a
Canvas produced by the emulator.

BDF fonts are parsed and rendered pixel-for-pixel so text looks sharp,
matching real hardware. TTF fonts fall back to Pillow (anti-aliased).
"""
from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass
class _Glyph:
    dwidth: int          # horizontal advance in pixels
    w: int               # bounding box width
    h: int               # bounding box height
    xoff: int            # x offset from pen origin
    yoff: int            # y offset from baseline (positive = above baseline)
    rows: list = field(default_factory=list)  # list of ints, one per bitmap row


def _parse_bdf(path: str) -> dict:
    """Parse a BDF file and return a dict mapping char code -> _Glyph."""
    glyphs = {}
    with open(path, "r", encoding="latin-1") as f:
        lines = f.readlines()

    encoding = None
    dwidth = 0
    bbx = None
    in_bitmap = False
    bitmap_rows: list[int] = []

    for line in lines:
        line = line.strip()
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
            if encoding is not None and encoding >= 0 and bbx is not None:
                w, h, xoff, yoff = bbx
                glyphs[encoding] = _Glyph(dwidth=dwidth, w=w, h=h,
                                           xoff=xoff, yoff=yoff,
                                           rows=bitmap_rows[:])
            encoding = None
            in_bitmap = False
            bitmap_rows = []
        elif in_bitmap:
            bitmap_rows.append(int(line, 16))

    return glyphs


class Font:
    def __init__(self):
        self._glyphs: dict = {}
        self._default_advance: int = 6
        self.pil_font: Optional[ImageFont.ImageFont] = None
        self.size = 10

    def LoadFont(self, path: str):
        # TTF/OTF: use Pillow (will be anti-aliased but keeps compatibility)
        if path.lower().endswith((".ttf", ".otf")):
            try:
                import re
                m = re.findall(r"(\d{1,3})", path)
                size = int(m[-1]) if m else 12
                self.pil_font = ImageFont.truetype(path, size)
                self.size = size
                return
            except Exception:
                pass

        # BDF: parse bitmap glyphs for pixel-perfect rendering
        if path.lower().endswith(".bdf"):
            try:
                self._glyphs = _parse_bdf(path)
                space = self._glyphs.get(ord(" "))
                self._default_advance = space.dwidth if space else 6
                self.pil_font = None
                return
            except Exception:
                pass

        # Fallback: Pillow default font
        import re
        m = re.findall(r"(\d{1,3})", path)
        size = int(m[-1]) if m else 10
        self.size = size
        try:
            self.pil_font = ImageFont.load_default(size=size)
        except TypeError:
            self.pil_font = ImageFont.load_default()


def TextWidth(font: Font, text: str) -> int:
    """Return the pixel width of text rendered with the given font."""
    w, _ = TextSize(font, text)
    return w


def TextSize(font: Font, text: str):
    """Return (width, height) of text rendered with the given font."""
    if font and font._glyphs:
        total_w = 0
        max_h = 0
        for ch in text:
            g = font._glyphs.get(ord(ch))
            if g:
                total_w += g.dwidth
                max_h = max(max_h, g.h)
            else:
                total_w += font._default_advance
        return total_w, max_h

    from PIL import Image
    pil_font = font.pil_font if (font and getattr(font, "pil_font", None)) else ImageFont.load_default()
    tmp = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(tmp)
    bbox = draw.textbbox((0, 0), text, font=pil_font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def DrawText(canvas, font: Font, x: int, y: int, color: Color, text: str):
    """Draw text onto the emulator canvas.

    `y` is treated as the baseline, matching the real rgbmatrix API.
    BDF fonts are stamped pixel-for-pixel; TTF falls back to Pillow.
    """
    if not hasattr(canvas, "img"):
        return

    if font and font._glyphs:
        cx = x
        total_bits_cache: dict[int, int] = {}
        for ch in text:
            code = ord(ch)
            g = font._glyphs.get(code)
            if g is None:
                cx += font._default_advance
                continue
            total_bits = ((g.w + 7) // 8) * 8
            for row_i, row_val in enumerate(g.rows):
                # In BDF, y increases upward; yoff is baseline-relative bottom of bbox.
                # Row 0 is the top of the glyph.
                cy = y - g.yoff - g.h + 1 + row_i
                for bit_j in range(g.w):
                    if row_val & (1 << (total_bits - 1 - bit_j)):
                        canvas.SetPixel(cx + g.xoff + bit_j, cy,
                                        color.r, color.g, color.b)
            cx += g.dwidth
        return

    # Pillow fallback
    draw = ImageDraw.Draw(canvas.img)
    pil_font = font.pil_font if (font and getattr(font, "pil_font", None)) else ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=pil_font)
    h = bbox[3] - bbox[1]
    top = max(0, y - h)
    draw.text((x, top), text, fill=(color.r, color.g, color.b), font=pil_font)
