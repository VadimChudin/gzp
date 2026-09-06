"""Визуальный язык GZP.

Загрузочный экран строится из вашего референса (золотая сфера, орбиты,
свечи) и поверх него рисуется ЖИВОЙ прогресс-бар: заполнение едет слева
направо, голова бара светится, по орбитам бегут бусины.

Unlock-экран — та же палитра, без сферы: панель Secure Access.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# ── Палитра ──────────────────────────────────────────────────────────────────

BG_DEEP = (0, 0, 0)
GOLD = (212, 162, 74)
GOLD_LIGHT = (255, 224, 160)
GOLD_DEEP = (122, 86, 28)
TEXT_DIM = (168, 156, 132)
TEXT_SOFT = (232, 220, 196)
HAIRLINE = (96, 74, 40)
DANGER = (196, 84, 74)

# Соотношение референса 1536×1024.
WIDTH, HEIGHT = 960, 640

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
_REF_CANDIDATES = (
    _ASSETS / "splash_reference_1.png",
    _ASSETS / "splash_reference_2.png",
)

_SERIF_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "C:/Windows/Fonts/georgiab.ttf",
    "C:/Windows/Fonts/timesbd.ttf",
]
_SANS_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]
_MONO_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "C:/Windows/Fonts/consola.ttf",
]


def _font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def serif(size: int) -> ImageFont.FreeTypeFont:
    return _font(_SERIF_CANDIDATES, size)


def sans(size: int) -> ImageFont.FreeTypeFont:
    return _font(_SANS_CANDIDATES, size)


def mono(size: int) -> ImageFont.FreeTypeFont:
    return _font(_MONO_CANDIDATES, size)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], f: float) -> tuple[int, int, int]:
    f = max(0.0, min(1.0, f))
    return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))  # type: ignore[return-value]


# ── Референс ─────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _base_art(size: tuple[int, int]) -> Image.Image:
    """Референс сферы, подогнанный под окно. Кэш — кадры идут 30 раз в секунду."""
    w, h = size
    for path in _REF_CANDIDATES:
        if path.exists():
            src = Image.open(path).convert("RGB")
            # cover: заполняем окно без полей, лишнее обрезаем по центру.
            scale = max(w / src.width, h / src.height)
            nw, nh = int(src.width * scale), int(src.height * scale)
            src = src.resize((nw, nh), Image.LANCZOS)
            left, top = (nw - w) // 2, (nh - h) // 2
            return src.crop((left, top, left + w, top + h))
    return Image.new("RGB", size, BG_DEEP)


def _vignette(img: Image.Image, strength: float = 0.55) -> Image.Image:
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([-w * 0.05, -h * 0.12, w * 1.05, h * 1.12], fill=int(255 * (1 - strength)))
    mask = mask.filter(ImageFilter.GaussianBlur(90))
    black = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(img, black, mask.point(lambda v: 255 - v))


# ── Прогресс-бар ─────────────────────────────────────────────────────────────


def _bar_geometry(w: int, h: int) -> tuple[int, int, int, int]:
    """Капсула бара внутри сферы — те же пропорции, что на референсе.

    На исходнике 1536×1024 заполнение сидело около y=609..621, x=553..980.
    """
    bar_w = int(w * 0.28)
    bar_h = max(10, int(h * 0.018))
    x = (w - bar_w) // 2
    y = int(h * 0.598)
    return x, y, bar_w, bar_h


def _cover_static_bar(img: Image.Image) -> Image.Image:
    """Гасим только неподвижный бар на референсе — сферу и LOADING не трогаем."""
    w, h = img.size
    x, y, bw, bh = _bar_geometry(w, h)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rounded_rectangle(
        [x - 2, y - 2, x + bw + 2, y + bh + 2],
        radius=(bh + 4) // 2,
        fill=(10, 8, 6, 235),
    )
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def draw_progress(img: Image.Image, progress: float, t: float) -> None:
    """Живой золотой бар: заполнение едет, голова пульсирует."""
    progress = max(0.0, min(1.0, progress))
    w, h = img.size
    x, y, bw, bh = _bar_geometry(w, h)
    radius = bh // 2

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # Дорожка.
    d.rounded_rectangle([x, y, x + bw, y + bh], radius=radius, outline=(90, 70, 36, 220), width=1)
    d.rounded_rectangle(
        [x + 1, y + 1, x + bw - 1, y + bh - 1],
        radius=max(1, radius - 1),
        fill=(18, 14, 8, 210),
    )

    filled = max(int(bw * progress), bh if progress > 0 else 0)
    if filled > 0:
        cap = Image.new("RGBA", (filled, bh), (0, 0, 0, 0))
        cd = ImageDraw.Draw(cap)
        for px in range(filled):
            k = px / max(filled - 1, 1)
            # Тёплый градиент + бегущий блик.
            shimmer = 0.5 + 0.5 * math.sin((k * 6.0) - t * 6.0)
            col = _mix(GOLD_DEEP, GOLD_LIGHT, 0.25 + 0.55 * k + 0.2 * shimmer)
            cd.line([(px, 0), (px, bh)], fill=(*col, 255))
        mask = Image.new("L", (filled, bh), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, filled - 1, bh - 1], radius=radius, fill=255)
        overlay.paste(cap, (x, y), mask)

        # Светящаяся голова бара.
        head_x = x + filled
        head_y = y + bh // 2
        pulse = 0.65 + 0.35 * (0.5 + 0.5 * math.sin(t * 7.0))
        glow = Image.new("L", (w, h), 0)
        gd = ImageDraw.Draw(glow)
        r = int(22 * pulse)
        gd.ellipse([head_x - r, head_y - r // 2, head_x + r, head_y + r // 2], fill=int(180 * pulse))
        glow = glow.filter(ImageFilter.GaussianBlur(8))
        warm = Image.new("RGBA", (w, h), (*GOLD_LIGHT, 0))
        warm.putalpha(glow)
        overlay = Image.alpha_composite(overlay, warm)

    composed = Image.alpha_composite(img.convert("RGBA"), overlay)
    img.paste(composed.convert("RGB"))


# ── Орбитальные бусины ───────────────────────────────────────────────────────


def draw_orbit_beads(img: Image.Image, t: float) -> None:
    """Бусины бегут по эллипсам вокруг сферы — как на референсе, но живые."""
    w, h = img.size
    cx, cy = w * 0.50, h * 0.46
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    orbits = (
        (w * 0.34, h * 0.16, 0.55, 3),
        (w * 0.40, h * 0.22, -0.38, 2),
        (w * 0.28, h * 0.12, 0.90, 2),
    )
    for rx, ry, speed, count in orbits:
        for i in range(count):
            ang = t * speed + i * (math.tau / count)
            x = cx + rx * math.cos(ang)
            y = cy + ry * math.sin(ang)
            r = 3.4 + 1.6 * math.sin(ang * 2 + i)
            d.ellipse([x - r, y - r, x + r, y + r], fill=(*GOLD_LIGHT, 230))
            d.ellipse([x - r * 2.6, y - r * 2.6, x + r * 2.6, y + r * 2.6], fill=(*GOLD, 40))

    overlay = overlay.filter(ImageFilter.GaussianBlur(0.6))
    composed = Image.alpha_composite(img.convert("RGBA"), overlay)
    img.paste(composed.convert("RGB"))


# ── Таблица версии ───────────────────────────────────────────────────────────


def draw_version_footer(img: Image.Image, rows: list[tuple[str, str]]) -> None:
    """Одна строка версии в нижнем баннере референса, без таблицы поверх сферы."""
    data = {k.upper(): v for k, v in rows}
    line = f"{data.get('PRODUCT', 'GZP')}   v{data.get('VERSION', '')}   {data.get('RELEASE', '')}"
    w, h = img.size
    draw = ImageDraw.Draw(img)
    draw.text((w // 2, int(h * 0.905)), line, font=sans(11), fill=TEXT_DIM, anchor="mm")


# ── Кадры ────────────────────────────────────────────────────────────────────


def render_splash_frame(
    rows: list[tuple[str, str]],
    progress: float,
    status: str,
    t: float,
    size: tuple[int, int] = (WIDTH, HEIGHT),
) -> Image.Image:
    """Один кадр: ваш референс + живой бар. Без таблицы и лишнего LOADING."""
    img = _base_art(size).copy()
    img = _cover_static_bar(img)
    draw_progress(img, progress, t)
    draw_version_footer(img, rows)
    return img


def render_unlock_frame(
    footer: str,
    masked_len: int,
    t: float,
    error: str | None = None,
    focus: bool = True,
    size: tuple[int, int] = (WIDTH, HEIGHT),
) -> Image.Image:
    """Экран пароля в той же золотой палитре."""
    w, h = size
    base = _base_art(size).copy()
    # Сильно затемняем сферу — она остаётся атмосферой, не конкурирует с формой.
    dark = ImageEnhance.Brightness(base).enhance(0.22)
    img = _vignette(dark, 0.7)
    draw = ImageDraw.Draw(img)

    panel = [int(w * 0.26), int(h * 0.16), int(w * 0.74), int(h * 0.84)]
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(panel, radius=22, fill=(8, 7, 6, 210), outline=(120, 92, 42, 200), width=1)
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Монограм.
    draw.text((w // 2, panel[1] + 46), "АЛГО", font=sans(12), fill=TEXT_DIM, anchor="mm")
    draw.text((w // 2, panel[1] + 92), "GZP", font=serif(54), fill=GOLD_LIGHT, anchor="mm")
    draw.text(
        (w // 2, panel[1] + 138),
        "S E C U R E   A C C E S S",
        font=sans(11),
        fill=TEXT_DIM,
        anchor="mm",
    )

    field = [panel[0] + 40, panel[1] + 180, panel[2] - 40, panel[1] + 226]
    draw.rounded_rectangle(field, radius=10, fill=(16, 14, 12), outline=(70, 58, 36))
    underline = GOLD if focus else (72, 66, 52)
    draw.line([(field[0] + 12, field[3] + 3), (field[2] - 12, field[3] + 3)], fill=underline, width=2)
    dots = "\u2022" * masked_len
    draw.text((field[0] + 18, (field[1] + field[3]) // 2), dots, font=mono(18), fill=TEXT_SOFT, anchor="lm")
    if focus and (t % 1.0) < 0.5:
        caret_x = field[0] + 22 + int(draw.textlength(dots, font=mono(18)))
        draw.line([(caret_x, field[1] + 14), (caret_x, field[3] - 14)], fill=GOLD_LIGHT, width=2)

    button = [panel[0] + 40, field[3] + 28, panel[2] - 40, field[3] + 78]
    bw, bh = button[2] - button[0], button[3] - button[1]
    grad = Image.new("RGB", (bw, bh))
    gd = ImageDraw.Draw(grad)
    for px in range(bw):
        gd.line([(px, 0), (px, bh)], fill=_mix(GOLD_DEEP, GOLD_LIGHT, (px / max(bw, 1)) ** 0.8))
    mask = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, bw - 1, bh - 1], radius=10, fill=255)
    img.paste(grad, (button[0], button[1]), mask)
    draw = ImageDraw.Draw(img)
    draw.text(
        ((button[0] + button[2]) // 2, (button[1] + button[3]) // 2),
        "U N L O C K",
        font=sans(14),
        fill=(26, 22, 12),
        anchor="mm",
    )

    if error:
        draw.text((w // 2, button[3] + 24), error, font=sans(12), fill=DANGER, anchor="mm")

    draw.text((w // 2, panel[3] - 28), footer, font=mono(11), fill=TEXT_DIM, anchor="mm")
    return img
