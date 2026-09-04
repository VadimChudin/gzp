"""Конструктор сценариев для тестов алгоритма.

Позволяет собрать историю, в которой реакции происходят ровно там, где нужно
тесту, — иначе проверить требования ТЗ по случайным данным невозможно.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from gzp_core.config import Config
from gzp_core.data_feed import resample
from gzp_core.models import Candle

START = datetime(2026, 4, 1, tzinfo=timezone.utc)


def h1_series(
    bars: int,
    base: float = 4800.0,
    spikes: dict[int, float] | None = None,
    upper_spikes: dict[int, float] | None = None,
    rally: dict[int, float] | None = None,
    drift: float = 0.0,
    body: float = 1.6,
) -> list[Candle]:
    """Спокойный ряд H1 с точечными «проколами» в заданных барах.

    spikes        {индекс: цена минимума}   — нижние фитили
    upper_spikes  {индекс: цена максимума}  — верхние фитили
    rally         {индекс: смещение цены}   — импульс после реакции
    """
    spikes = spikes or {}
    upper_spikes = upper_spikes or {}
    rally = rally or {}

    out: list[Candle] = []
    price = base
    ts = START
    for i in range(bars):
        price += drift + rally.get(i, 0.0)
        o = price
        c = price + (body if i % 2 == 0 else -body) * 0.5
        h = max(o, c) + 0.8
        l = min(o, c) - 0.8
        if i in spikes:
            l = spikes[i]
        if i in upper_spikes:
            h = upper_spikes[i]
        out.append(Candle(ts=ts, open=o, high=h, low=l, close=c, volume=1000))
        price = c
        ts += timedelta(hours=1)
    return out


def to_h4(h1: list[Candle]) -> list[Candle]:
    return resample(h1, "H1", "H4")


@pytest.fixture
def cfg() -> Config:
    return Config()


@pytest.fixture
def scenario_4786() -> tuple[list[Candle], list[Candle]]:
    """Эталонный пример ТЗ §68.

    Около 4786 сходятся: H4-фитиль, два H1-фитиля, историческая S/R-область
    и сильная реакция вверх. Ожидание — ОДНА сильная зона, без BUY/SELL.
    """
    spikes = {
        40: 4786.0,   # ранняя реакция — формирует историческую S/R
        41: 4787.0,
        96: 4786.0,   # глубокий прокол внутри H4 → H4-фитиль
        97: 4785.0,   # H1-подтверждение
        99: 4787.0,   # ещё одно H1-подтверждение
    }
    rally = {i: 1.4 for i in range(100, 120)}  # импульс вверх после реакции
    h1 = h1_series(220, base=4800.0, spikes=spikes, rally=rally)
    return to_h4(h1), h1


@pytest.fixture
def quiet_market() -> tuple[list[Candle], list[Candle]]:
    """Рынок без значимых реакций: зон появиться не должно."""
    h1 = h1_series(200, base=4800.0)
    return to_h4(h1), h1
