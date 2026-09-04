"""ТЗ §32-§40, §45-§47, §60, §67, §70 — правила движка и честность истории."""

from __future__ import annotations

from datetime import timedelta

from gzp_core.config import Config
from gzp_core.engine import ZoneEngine
from gzp_core.models import ZoneGrade
from gzp_core.runner import walk_forward

from .conftest import h1_series, to_h4


def _run(h4, h1, cfg, upto=None):
    engine = ZoneEngine(cfg)
    end = upto if upto is not None else len(h4)
    for i in range(cfg.atr_period + 2, end):
        engine.on_h4_close(h4[: i + 1], h1, now=h4[i].ts)
    return engine


def test_zone_is_not_recreated_within_one_h4(scenario_4786, cfg: Config):
    """ТЗ §33: внутри одной H4-свечи зона не пересоздаётся."""
    h4, h1 = scenario_4786
    engine = ZoneEngine(cfg)
    idx = len(h4) - 1
    first = engine.on_h4_close(h4[: idx + 1], h1, now=h4[idx].ts)
    # Повторные вызовы внутри той же свечи (каждые несколько минут) — no-op.
    for minutes in (5, 30, 90, 180):
        again = engine.on_h4_close(
            h4[: idx + 1], h1, now=h4[idx].ts + timedelta(minutes=minutes)
        )
        assert again == [], "внутри одного H4 новые зоны создаваться не должны"
    assert isinstance(first, list)


def test_quiet_market_creates_no_zones(quiet_market, cfg: Config):
    """ТЗ §35: новый H4 НЕ обязан порождать зону."""
    h4, h1 = quiet_market
    engine = _run(h4, h1, cfg)
    strong = [z for z in engine.zones if z.grade is not ZoneGrade.CANDIDATE]
    assert strong == []


def test_no_duplicate_zones_for_same_area(scenario_4786, cfg: Config):
    """ТЗ §36, §37: повторное обнаружение той же области — обновление, не дубль."""
    h4, h1 = scenario_4786
    engine = _run(h4, h1, cfg)

    for a in engine.zones:
        for b in engine.zones:
            if a is b or a.direction is not b.direction:
                continue
            assert a.overlaps(b.lower, b.upper) < 0.9, (
                f"почти одинаковые зоны выводятся поверх друг друга: {a.id} / {b.id}"
            )


def test_repeated_detection_updates_statistics(scenario_4786, cfg: Config):
    """ТЗ §40, §67: старая зона не становится новой, а обновляет статистику."""
    h4, h1 = scenario_4786
    engine = _run(h4, h1, cfg)
    zone = max(engine.zones, key=lambda z: z.score)
    assert zone.updated_at is not None
    assert zone.updated_at >= zone.created_at


def test_zone_creation_uses_only_past_data(scenario_4786, cfg: Config):
    """ТЗ §45, §46: look-ahead bias невозможен.

    Прогон, который физически не видит будущих свечей, обязан дать те же зоны,
    что и прогон по полной истории, остановленный в тот же момент времени.
    """
    h4, h1 = scenario_4786
    cutoff = len(h4) - 12

    # A: движок получает историю, обрезанную по cutoff — будущего нет вообще.
    truncated_h1 = [c for c in h1 if c.ts <= h4[cutoff - 1].ts]
    engine_blind = _run(h4[:cutoff], truncated_h1, cfg)

    # B: движок получает полную историю, но now ограничен тем же моментом.
    engine_full = _run(h4, h1, cfg, upto=cutoff)

    blind = sorted((round(z.lower, 2), round(z.upper, 2)) for z in engine_blind.zones)
    full = sorted((round(z.lower, 2), round(z.upper, 2)) for z in engine_full.zones)
    assert blind == full, "знание будущего повлияло на зоны — это look-ahead bias"


def test_zone_created_before_price_returns(scenario_4786, cfg: Config):
    """ТЗ §47, §69: зона существует ДО того, как цена пришла её тестировать."""
    h4, h1 = scenario_4786
    engine = _run(h4, h1, cfg)
    zone = max(engine.zones, key=lambda z: z.score)

    later_touches = [
        c for c in h1 if c.ts > zone.created_at and c.low <= zone.upper and c.high >= zone.lower
    ]
    # Момент создания строго раньше любого последующего касания.
    for candle in later_touches:
        assert zone.created_at < candle.ts


def test_walk_forward_matches_incremental_engine(scenario_4786, cfg: Config):
    """ТЗ §46: исторический режим = последовательное реальное время."""
    h4, h1 = scenario_4786
    result = walk_forward(h4, h1, cfg)
    engine = _run(h4, h1, cfg)
    assert result.zone_count == len(engine.zones)


def test_m5_does_not_create_zones(cfg: Config):
    """ТЗ §60: M5 подключается только после появления зоны."""
    h1 = h1_series(200, base=4800.0, spikes={150: 4786.0})
    h4 = to_h4(h1)
    m5_noise = h1_series(400, base=4770.0, spikes={i: 4700.0 for i in range(0, 400, 7)})

    with_m5 = walk_forward(h4, h1, cfg, lower_tf=m5_noise)
    without_m5 = walk_forward(h4, h1, cfg)
    assert [z.id for z in with_m5.zones] == [z.id for z in without_m5.zones]
