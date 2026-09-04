"""ТЗ §41-§44, §59, §61-§66 — тесты зоны, пробой, подтверждение направления."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from gzp_core.config import Config
from gzp_core.lifecycle import ZoneLifecycle
from gzp_core.m5_confirm import DirectionConfirmer, Signal
from gzp_core.models import (
    Candle,
    Direction,
    ScoreBreakdown,
    Zone,
    ZoneGrade,
    ZoneState,
)

TS = datetime(2026, 4, 20, tzinfo=timezone.utc)
ATR = 10.0


def make_zone() -> Zone:
    return Zone(
        id="L4786-test",
        lower=4781.0,
        upper=4791.0,
        reference=4786.0,
        direction=Direction.LOWER,
        created_at=TS,
        score=72.0,
        grade=ZoneGrade.STRONG,
        state=ZoneState.ACTIVE,
        breakdown=ScoreBreakdown(),
    )


def candle(offset_h: int, o, h, l, c) -> Candle:
    return Candle(ts=TS + timedelta(hours=offset_h), open=o, high=h, low=l, close=c)


def test_first_arrival_is_recorded_as_test(cfg: Config):
    """ТЗ §41: приход цены в зону фиксируется как TEST #1."""
    zone = make_zone()
    ZoneLifecycle(cfg).observe([zone], candle(1, 4795, 4796, 4788, 4794), ATR)
    assert zone.test_count == 1
    assert zone.state is ZoneState.TESTED


def test_penetration_depth_is_measured(cfg: Config):
    """ТЗ §42: фиксируется, насколько глубоко цена вошла."""
    zone = make_zone()
    ZoneLifecycle(cfg).observe([zone], candle(1, 4790, 4792, 4782, 4790), ATR)
    shallow = zone.tests[-1].penetration_atr

    zone2 = make_zone()
    ZoneLifecycle(cfg).observe([zone2], candle(1, 4790, 4792, 4789, 4790), ATR)
    assert shallow > zone2.tests[-1].penetration_atr


def test_wick_pierce_is_not_a_breakout(cfg: Config):
    """ТЗ §43, §44: прокол фитилём с возвратом ≠ пробой."""
    zone = make_zone()
    lc = ZoneLifecycle(cfg)
    lc.observe([zone], candle(1, 4790, 4792, 4770, 4789), ATR)  # прокол вниз, закрытие внутри
    assert zone.state is not ZoneState.BROKEN
    assert zone.tests[-1].pierced is True
    assert zone.tests[-1].closed_beyond is False


def test_single_close_beyond_does_not_kill_zone(cfg: Config):
    """ТЗ §65: единичный выход за зону её не уничтожает."""
    zone = make_zone()
    lc = ZoneLifecycle(cfg)
    lc.observe([zone], candle(1, 4785, 4786, 4770, 4775), ATR)
    assert zone.state is not ZoneState.BROKEN
    assert zone.consecutive_closes_beyond == 1


def test_confirmed_breakout_invalidates_zone(cfg: Config):
    """ТЗ §44, §65: подтверждённое закрытие за зоной инвалидирует её."""
    zone = make_zone()
    lc = ZoneLifecycle(cfg)
    lc.observe([zone], candle(1, 4785, 4786, 4770, 4775), ATR)
    lc.observe([zone], candle(2, 4775, 4777, 4765, 4770), ATR)
    assert zone.state is ZoneState.BROKEN
    assert zone.broken_at is not None


def test_return_inside_resets_break_counter(cfg: Config):
    """ТЗ §43: ложный пробой не должен накапливаться как настоящий."""
    zone = make_zone()
    lc = ZoneLifecycle(cfg)
    lc.observe([zone], candle(1, 4785, 4786, 4770, 4775), ATR)
    lc.observe([zone], candle(2, 4775, 4790, 4774, 4786), ATR)  # вернулись внутрь
    assert zone.consecutive_closes_beyond == 0
    assert zone.state is not ZoneState.BROKEN


def test_broken_zone_is_not_auto_reversed(cfg: Config):
    """ТЗ §66: в v1 пробитая зона НЕ превращается автоматически в новую."""
    zone = make_zone()
    lc = ZoneLifecycle(cfg)
    lc.observe([zone], candle(1, 4785, 4786, 4770, 4775), ATR)
    lc.observe([zone], candle(2, 4775, 4777, 4765, 4770), ATR)
    before = (zone.lower, zone.upper, zone.direction)
    lc.observe([zone], candle(3, 4770, 4795, 4769, 4793), ATR)
    assert (zone.lower, zone.upper, zone.direction) == before


def test_zone_itself_carries_no_trade_direction():
    """ТЗ §9, §59: зона никогда не содержит LONG/SHORT."""
    payload = make_zone().to_dict()
    flat = str(payload).upper()
    assert "LONG" not in flat and "SHORT" not in flat and "BUY" not in flat
    assert payload["reaction_type"] in ("lower", "upper")


def test_m5_close_beyond_zone_gives_signal(cfg: Config):
    """ТЗ §62: сигнал появляется только после закрытия M5 за границей."""
    zone = make_zone()
    confirmer = DirectionConfirmer(cfg)
    confirmer.arm(zone)

    # Прокол фитилём вверх без закрытия — сигнала нет.
    assert confirmer.on_m5_close(zone, candle(1, 4788, 4799, 4787, 4790)) is None
    # Закрытие выше верхней границы — LONG.
    conf = confirmer.on_m5_close(zone, candle(2, 4790, 4796, 4789, 4795))
    assert conf is not None and conf.signal is Signal.LONG


def test_strict_mode_requires_h1_confirmation(cfg: Config):
    """ТЗ §63: строгий сценарий — M5 + H1."""
    zone = make_zone()
    strict = DirectionConfirmer(cfg, require_h1=True)
    strict.arm(zone)
    m5 = candle(2, 4790, 4796, 4789, 4795)

    assert strict.on_m5_close(zone, m5, h1_candle=candle(2, 4790, 4792, 4785, 4788)) is None
    conf = strict.on_m5_close(zone, m5, h1_candle=candle(2, 4790, 4798, 4788, 4796))
    assert conf is not None and conf.h1_confirmed is True
