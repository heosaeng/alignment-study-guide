"""Generate PNG icons (192, 512, 180) for the Iliad Study PWA.

Pure PIL — no SVG renderer needed. Matches the visual of icon.svg:
- Rounded-square background, vertical blue gradient
- White "II" centered, Georgia-style serif
- Subtle white underline at the bottom

Run once locally; commit the PNGs.
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import sys

OUT_DIR = Path(__file__).parent

# Sizes we need
SIZES = [192, 512, 180]


def find_serif_font(size: int) -> ImageFont.FreeTypeFont:
    """Return a serif font installed on Windows, falling back gracefully."""
    candidates = [
        r"C:\Windows\Fonts\georgiab.ttf",  # Georgia Bold
        r"C:\Windows\Fonts\timesbd.ttf",   # Times New Roman Bold
        r"C:\Windows\Fonts\georgia.ttf",
        r"C:\Windows\Fonts\times.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def vertical_gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    """Build an RGB vertical gradient image."""
    img = Image.new("RGB", (size, size), top)
    px = img.load()
    for y in range(size):
        t = y / max(1, size - 1)
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        for x in range(size):
            px[x, y] = (r, g, b)
    return img


def rounded_mask(size: int, radius_frac: float = 96 / 512) -> Image.Image:
    """White-on-black L mask with rounded corners."""
    r = int(size * radius_frac)
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
    return mask


def make_icon(size: int) -> Image.Image:
    bg = vertical_gradient(size, (45, 109, 177), (26, 72, 120))
    mask = rounded_mask(size)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(bg, (0, 0), mask)

    draw = ImageDraw.Draw(canvas)

    # "II" text — large, white, centered. Letter spacing negative isn't directly supported,
    # so draw as a single string and accept whatever Georgia gives us.
    font_size = int(size * 320 / 512)
    font = find_serif_font(font_size)
    text = "II"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    # Center horizontally; place slightly above center (icon look)
    x = (size - tw) / 2 - bbox[0]
    y = (size - th) / 2 - bbox[1] - int(size * 0.02)
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))

    # Subtle underline near bottom
    line_w = int(size * 328 / 512)
    line_h = max(2, int(size * 6 / 512))
    line_x = (size - line_w) // 2
    line_y = int(size * 408 / 512)
    underline = Image.new("RGBA", (line_w, line_h), (255, 255, 255, 140))
    canvas.paste(underline, (line_x, line_y), underline)

    return canvas


def main():
    for s in SIZES:
        img = make_icon(s)
        out = OUT_DIR / f"icon-{s}.png"
        img.save(out, "PNG", optimize=True)
        print(f"wrote {out}  ({s}x{s})")


if __name__ == "__main__":
    sys.exit(main())
