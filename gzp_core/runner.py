"""Walk-forward прогон: движок шагает по истории строго последовательно.

Реализует ТЗ §46: исторический режим обязан имитировать реальное время.
Тот же самый код используется и в рантайме, и в проверке на истории —
это гарантирует, что «зона найдена заранее» проверяемо и честно (ТЗ §47).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .config import Config
from .engine import ZoneEngine
from .indicators import atr_at
from .lifecycle import ZoneLifecycle
from .models import Candle, Zone


@dataclass
class WalkForwardResult:
    zones: list[Zone] = field(default_factory=list)
    creations: list[tuple[datetime, str]] = field(default_factory=list)
    bars_processed: int = 0

    @property
    def zone_count(self) -> int:
        return len(self.zones)


def walk_forward(
    h4: list[Candle],
    h1: list[Candle],
    cfg: Config | None = None,
    lower_tf: list[Candle] | None = None,
    warmup: int | None = None,
) -> WalkForwardResult:
    """Прогнать историю бар за баром.

    h4/h1 — история; lower_tf (M5/H1) используется только для жизненного цикла
    уже созданных зон, но НИКОГДА для их создания (ТЗ §60).
    """
    cfg = cfg or Config()
    engine = ZoneEngine(cfg)
    lifecycle = ZoneLifecycle(cfg)
    result = WalkForwardResult()

    warmup = warmup if warmup is not None else cfg.atr_period + 5
    lower = sorted(lower_tf or [], key=lambda c: c.ts)
    lower_pos = 0

    for i in range(warmup, len(h4)):
        now = h4[i].ts
        # На момент now доступны только закрытые свечи — срезы делаем явно.
        created = engine.on_h4_close(h4[: i + 1], h1, now=now)
        result.bars_processed += 1
        for zone in created:
            result.creations.append((now, zone.id))

        # Проигрываем младший ТФ до текущего момента: цена приходит в зоны,
        # которые уже были зафиксированы РАНЬШЕ (ТЗ §45, §69).
        atr = atr_at(h4, i, cfg.atr_period)
        while lower_pos < len(lower) and lower[lower_pos].ts <= now:
            lifecycle.observe(engine.zones, lower[lower_pos], atr)
            lower_pos += 1

        if not lower:
            lifecycle.observe(engine.zones, h4[i], atr)

    result.zones = engine.zones
    return result
