"""Базовые измерения рынка: ATR и локальные экстремумы.

ТЗ §16 и §28 требуют, чтобы и расстояние объединения, и оценка реакции
измерялись относительно текущей волатильности, а не в фиксированных долларах.
"""

from __future__ import annotations

from .models import Candle


def true_range(prev: Candle, cur: Candle) -> float:
    return max(
        cur.high - cur.low,
        abs(cur.high - prev.close),
        abs(cur.low - prev.close),
    )


def atr_series(candles: list[Candle], period: int) -> list[float]:
    """ATR по Уайлдеру. Возвращает список той же длины, что и candles."""
    out: list[float] = []
    if not candles:
        return out

    trs: list[float] = [candles[0].range]
    for i in range(1, len(candles)):
        trs.append(true_range(candles[i - 1], candles[i]))

    running = 0.0
    for i, tr in enumerate(trs):
        if i < period:
            running += tr
            out.append(running / (i + 1))
        else:
            prev = out[-1]
            out.append((prev * (period - 1) + tr) / period)
    return out


def atr_at(candles: list[Candle], index: int, period: int) -> float:
    """ATR на момент закрытия свечи index — только по данным до неё включительно."""
    if index < 0 or not candles:
        return 0.0
    window = candles[: index + 1]
    series = atr_series(window, period)
    value = series[-1] if series else 0.0
    if value <= 0:
        # Дегенеративный случай (плоские данные): не даём делить на ноль.
        return max(window[-1].range, 1e-9)
    return value


def swing_highs(candles: list[Candle], lookaround: int) -> list[int]:
    """Индексы фрактальных swing high (ТЗ §22)."""
    result = []
    for i in range(lookaround, len(candles) - lookaround):
        pivot = candles[i].high
        if all(candles[j].high <= pivot for j in range(i - lookaround, i)) and all(
            candles[j].high < pivot for j in range(i + 1, i + lookaround + 1)
        ):
            result.append(i)
    return result


def swing_lows(candles: list[Candle], lookaround: int) -> list[int]:
    """Индексы фрактальных swing low (ТЗ §22)."""
    result = []
    for i in range(lookaround, len(candles) - lookaround):
        pivot = candles[i].low
        if all(candles[j].low >= pivot for j in range(i - lookaround, i)) and all(
            candles[j].low > pivot for j in range(i + 1, i + lookaround + 1)
        ):
            result.append(i)
    return result


def prev_local_extreme(candles: list[Candle], index: int, window: int, upper: bool) -> float | None:
    """Ближайший предыдущий локальный экстремум до свечи index."""
    start = max(0, index - window)
    seg = candles[start:index]
    if not seg:
        return None
    return max(c.high for c in seg) if upper else min(c.low for c in seg)
