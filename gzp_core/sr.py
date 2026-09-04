"""Исторические S/R-области как НЕЗАВИСИМЫЙ источник подтверждения.

Реализует ТЗ §21, §22, §58:
  • S/R ищется отдельно от фитилей;
  • S/R сам по себе не создаёт Strong Zone — он только подтверждение;
  • S/R представлен областью, а не одной идеальной ценой.
"""

from __future__ import annotations

from .config import Config
from .indicators import atr_at, swing_highs, swing_lows
from .models import Candle, Direction, Evidence, EvidenceKind, Reaction


def _count_touches(candles: list[Candle], price: float, tol: float, upto: int) -> int:
    """Сколько раз цена касалась области уровня (ТЗ §22)."""
    touches = 0
    for c in candles[: upto + 1]:
        if c.low - tol <= price <= c.high + tol:
            touches += 1
    return touches


def find_sr_areas(
    candles: list[Candle],
    cfg: Config,
    timeframe: str,
    now_index: int | None = None,
) -> list[Evidence]:
    """Области swing-разворотов и многократных касаний до now_index."""
    last = len(candles) - 1 if now_index is None else min(now_index, len(candles) - 1)
    if last < cfg.atr_period + cfg.swing_lookaround * 2:
        return []

    start = max(0, last - cfg.sr_history_bars)
    window = candles[start : last + 1]
    if len(window) < cfg.swing_lookaround * 2 + 2:
        return []

    atr = atr_at(candles, last, cfg.atr_period)
    tol = atr * cfg.sr_touch_atr
    events: list[Evidence] = []

    for idx in swing_lows(window, cfg.swing_lookaround):
        c = window[idx]
        touches = _count_touches(window, c.low, tol, len(window) - 1)
        if touches < cfg.sr_min_touches:
            continue
        events.append(
            Evidence(
                kind=EvidenceKind.SR_AREA,
                direction=Direction.LOWER,
                outer=c.low,
                inner=c.low + tol,
                price=c.low,
                ts=c.ts,
                timeframe=timeframe,
                event_key=f"SR:{timeframe}:{c.ts.isoformat()}:lower",
                weight_hint=min(1.0 + (touches - cfg.sr_min_touches) * 0.25, 2.0),
                reaction=Reaction(),
                touches=touches,
            )
        )

    for idx in swing_highs(window, cfg.swing_lookaround):
        c = window[idx]
        touches = _count_touches(window, c.high, tol, len(window) - 1)
        if touches < cfg.sr_min_touches:
            continue
        events.append(
            Evidence(
                kind=EvidenceKind.SR_AREA,
                direction=Direction.UPPER,
                outer=c.high,
                inner=c.high - tol,
                price=c.high,
                ts=c.ts,
                timeframe=timeframe,
                event_key=f"SR:{timeframe}:{c.ts.isoformat()}:upper",
                weight_hint=min(1.0 + (touches - cfg.sr_min_touches) * 0.25, 2.0),
                reaction=Reaction(),
                touches=touches,
            )
        )

    return events
