"""Генерация иконки продукта GZP из фирменного стиля.

Запускается в CI перед сборкой инсталлятора: assets/gzp.ico строится из того же
латунного градиента, что и загрузочный экран, — стиль остаётся единым.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw  # noqa: E402

from gzp_core import branding  # noqa: E402

SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]


def build_icon(out_path: Path) -> Path:
    size = 256
    img = Image.new("RGB", (size, size), branding.BG_DEEP)
    draw = ImageDraw.Draw(img)

    # Плашка со скруглением и тонкой золотой рамкой.
    draw.rounded_rectangle([6, 6, size - 7, size - 7], radius=46, fill=(14, 15, 18),
                           outline=branding.GOLD_DEEP, width=3)
    # Монограм тем же латунным градиентом, что и на загрузочном экране.
    branding.draw_gold_text(img, (size // 2, size // 2 - 6), "GZP",
                            branding.serif(88), shimmer=0.45, glow=True)
    img.save(out_path, format="ICO", sizes=SIZES)
    return out_path


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("assets/gzp.ico")
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"icon written: {build_icon(target)}")
