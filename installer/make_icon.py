"""Генерация иконки продукта GZP.

Не зависит от внутренних функций branding.py — CI собирает ico до
PyInstaller, и падение здесь раньше останавливало весь Windows-job.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BG = (8, 7, 6)
GOLD_DEEP = (122, 86, 28)
GOLD = (212, 162, 74)
GOLD_LIGHT = (255, 224, 160)
SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in (
        "C:/Windows/Fonts/georgiab.ttf",
        "C:/Windows/Fonts/timesbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def build_icon(out_path: Path) -> Path:
    size = 256
    img = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [8, 8, size - 9, size - 9],
        radius=48,
        fill=(14, 12, 10),
        outline=GOLD_DEEP,
        width=4,
    )

    font = _font(78)
    text = "GZP"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) // 2 - bbox[0]
    y = (size - th) // 2 - bbox[1] - 4

    glow = Image.new("L", (size, size), 0)
    ImageDraw.Draw(glow).text((x, y), text, font=font, fill=180)
    glow = glow.filter(ImageFilter.GaussianBlur(10))
    warm = Image.new("RGB", (size, size), GOLD)
    img.paste(Image.composite(warm, img, glow), (0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((x, y), text, font=font, fill=GOLD_LIGHT)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="ICO", sizes=SIZES)
    return out_path


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("assets/gzp.ico")
    print(f"icon written: {build_icon(target)}")
