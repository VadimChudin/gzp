"""Поиск значимых фитилей и измерение реакции после них.

Реализует ТЗ §4-§12, §26-§29.

Главные требования ТЗ, которые здесь соблюдены буквально:
  • каждый фитиль — это ОБЛАСТЬ [outer..inner], а не одна цена (§10, §11);
  • не каждый фитиль является зоной — только кандидатом (§5, §29);
  • значимость считается относительно волатильности и самой свечи (§6);
  • важно, что произошло ПОСЛЕ фитиля (§7, §8, §27, §28);
  • реакция измеряется только по данным, доступным на момент анализа (§45).
"""

from __future__ import annotations

from .config import Config
from .indicators import atr_at, prev_local_extreme
from .models import Candle, Direction, Evidence, EvidenceKind, Reaction


def _wick_significance(
    wick: float,
    body: float,
    rng: float,
    atr: float,
    min_atr: float,
    min_body_ratio: float,
    min_range_ratio: float,
) -> float:
    """0.0 — фитиль незначим; >0 — во сколько раз он перекрывает минимум.

    ТЗ §6: смотрим три характеристики одновременно, а не только длину в пунктах.
    """
    if wick <= 0 or rng <= 0 or atr <= 0:
        return 0.0

    atr_ratio = wick / atr
    range_ratio = wick / rng
    # Свеча без тела (доджи) — тело считаем минимальным, чтобы не делить на ноль.
    body_ratio = wick / body if body > 1e-9 else wick / (rng * 0.1 + 1e-9)

    if atr_ratio < min_atr:
        return 0.0
    if range_ratio < min_range_ratio:
        return 0.0
    if body_ratio < min_body_ratio:
        return 0.0

    # Значимость — насколько фитиль перекрывает минимальные требования.
    return round(min(atr_ratio / min_atr, 3.0), 4)


def measure_reaction(
    candles: list[Candle],
    index: int,
    direction: Direction,
    atr: float,
    horizon: int,
    now_index: int | None = None,
) -> Reaction:
    """Импульс от области фитиля в противоположную сторону (ТЗ §8, §27, §28).

    now_index ограничивает обзор: заглядывать за текущий момент нельзя (ТЗ §45).
    """
    if atr <= 0:
        return Reaction()

    last = len(candles) - 1 if now_index is None else min(now_index, len(candles) - 1)
    end = min(last, index + horizon)
    if end <= index:
        return Reaction()

    forward = candles[index + 1 : end + 1]
    if not forward:
        return Reaction()

    src = candles[index]
    if direction is Direction.LOWER:
        # Нижняя область отвергнута: цена должна уйти ВВЕРХ от минимума.
        extreme = max(c.high for c in forward)
        displacement = extreme - src.low
        prev_ext = prev_local_extreme(candles, index, horizon, upper=True)
        broke = prev_ext is not None and extreme > prev_ext
        returned = any(c.close > src.body_bottom for c in forward)
    else:
        extreme = min(c.low for c in forward)
        displacement = src.high - extreme
        prev_ext = prev_local_extreme(candles, index, horizon, upper=False)
        broke = prev_ext is not None and extreme < prev_ext
        returned = any(c.close < src.body_top for c in forward)

    displacement_atr = max(displacement, 0.0) / atr
    return Reaction(
        displacement_atr=round(displacement_atr, 4),
        broke_local_extreme=bool(broke),
        returned_to_body=bool(returned),
    )


def find_wick_events(
    candles: list[Candle],
    cfg: Config,
    timeframe: str,
    now_index: int | None = None,
    lookback: int | None = None,
) -> list[Evidence]:
    """Значимые фитили в актуальном окне истории до now_index включительно.

    lookback ограничивает глубину поиска: по ТЗ §36 зона должна находиться
    в актуальной исторической области, иначе подтверждения копятся бесконечно.
    Возвращает Evidence с областью фитиля, а не с одной ценой (ТЗ §10, §11).
    """
    if timeframe == "H4":
        min_atr = cfg.h4_wick_min_atr
        min_body = cfg.h4_wick_min_body_ratio
        min_range = cfg.h4_wick_min_range_ratio
        horizon = cfg.reaction_horizon_h4
        kind = EvidenceKind.H4_WICK
    else:
        min_atr = cfg.h1_wick_min_atr
        min_body = cfg.h1_wick_min_body_ratio
        min_range = cfg.h1_wick_min_range_ratio
        horizon = cfg.reaction_horizon_h1
        kind = EvidenceKind.H1_WICK

    last = len(candles) - 1 if now_index is None else min(now_index, len(candles) - 1)
    window = lookback if lookback is not None else (
        cfg.h4_evidence_bars if timeframe == "H4" else cfg.h1_evidence_bars
    )
    first = max(cfg.atr_period, last - window + 1)
    events: list[Evidence] = []

    for i in range(first, last + 1):
        c = candles[i]
        atr = atr_at(candles, i, cfg.atr_period)

        for direction in (Direction.LOWER, Direction.UPPER):
            wick = c.lower_wick if direction is Direction.LOWER else c.upper_wick
            sig = _wick_significance(
                wick, c.body, c.range, atr, min_atr, min_body, min_range
            )
            if sig <= 0:
                continue

            reaction = measure_reaction(
                candles, i, direction, atr, horizon, now_index=last
            )
            # ТЗ §7: большой фитиль без последующего движения менее интересен.
            if reaction.displacement_atr < cfg.reaction_min_atr:
                weight_hint = sig * 0.5
            else:
                weight_hint = sig

            if direction is Direction.LOWER:
                outer, inner = c.low, c.body_bottom
            else:
                outer, inner = c.high, c.body_top

            events.append(
                Evidence(
                    kind=kind,
                    direction=direction,
                    outer=outer,
                    inner=inner,
                    # Характерная цена — экстремум фитиля: именно там произошло
                    # отвержение (ТЗ §11).
                    price=outer,
                    ts=c.ts,
                    timeframe=timeframe,
                    event_key=f"{timeframe}:{c.ts.isoformat()}:{direction.value}",
                    weight_hint=round(weight_hint, 4),
                    reaction=reaction,
                )
            )

    return events
