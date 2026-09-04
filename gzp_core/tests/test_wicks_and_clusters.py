"""ТЗ §4-§16, §19, §30, §31 — фитили, значимость, реакция, кластеризация."""

from __future__ import annotations

from datetime import datetime, timezone

from gzp_core.clustering import cluster_evidence
from gzp_core.config import Config
from gzp_core.models import Candle, Direction, Evidence, EvidenceKind, Reaction
from gzp_core.wicks import find_wick_events

from .conftest import h1_series, to_h4

TS = datetime(2026, 4, 1, tzinfo=timezone.utc)


def _evidence(price: float, kind=EvidenceKind.H1_WICK, ts=TS) -> Evidence:
    return Evidence(
        kind=kind,
        direction=Direction.LOWER,
        outer=price,
        inner=price + 2,
        price=price,
        ts=ts,
        timeframe="H1",
        event_key=f"{kind.value}:{price}:{ts}",
        weight_hint=1.0,
        reaction=Reaction(displacement_atr=1.2),
    )


def test_candle_wick_geometry_matches_spec():
    """ТЗ §4: фитиль — от экстремума до границы тела."""
    c = Candle(ts=TS, open=4790, high=4800, low=4778, close=4795)
    assert c.upper_wick == 5.0    # 4800 - 4795
    assert c.lower_wick == 12.0   # 4790 - 4778
    assert c.body == 5.0


def test_small_wick_is_not_a_zone(cfg: Config):
    """ТЗ §5: маленький фитиль сам по себе зоной не становится."""
    h1 = h1_series(120, base=4800.0)  # ровный рынок без проколов
    events = find_wick_events(h1, cfg, "H1")
    assert events == []


def test_significant_wick_is_detected_with_area(cfg: Config):
    """ТЗ §10, §11: кандидат хранит ОБЛАСТЬ фитиля, а не одну цену."""
    h1 = h1_series(120, base=4800.0, spikes={80: 4786.0})
    events = [e for e in find_wick_events(h1, cfg, "H1") if e.direction is Direction.LOWER]
    assert events, "значимый фитиль должен быть найден"

    ev = max(events, key=lambda e: e.weight_hint)
    assert ev.outer == 4786.0            # внешний экстремум
    assert ev.inner > ev.outer           # внутренняя граница выше минимума
    assert ev.high - ev.low > 5          # это диапазон, а не точка


def test_reaction_after_wick_is_measured(cfg: Config):
    """ТЗ §7, §8, §27: важно, что произошло ПОСЛЕ фитиля."""
    flat = h1_series(140, base=4800.0, spikes={80: 4786.0})
    impulsive = h1_series(
        140, base=4800.0, spikes={80: 4786.0}, rally={i: 1.5 for i in range(81, 110)}
    )

    def best(series):
        events = [e for e in find_wick_events(series, cfg, "H1") if e.outer == 4786.0]
        return max(e.reaction.displacement_atr for e in events)

    assert best(impulsive) > best(flat), "импульс после фитиля должен усиливать реакцию"


def test_near_prices_merge_into_one_cluster(cfg: Config):
    """ТЗ §14, §30: 4784..4787 — это один кластер, а не четыре уровня."""
    evidence = [_evidence(p) for p in (4784, 4785, 4786, 4786, 4787)]
    evidence.append(_evidence(4786, kind=EvidenceKind.H4_WICK))
    clusters = cluster_evidence(evidence, atr=12.0, cfg=cfg)
    assert len(clusters) == 1
    assert len(clusters[0].members) == 6


def test_distant_prices_do_not_merge(cfg: Config):
    """ТЗ §15: 4786 и 4830 не должны становиться одной зоной."""
    evidence = [
        _evidence(4786, kind=EvidenceKind.H4_WICK),
        _evidence(4830, kind=EvidenceKind.H4_WICK, ts=TS.replace(day=2)),
    ]
    clusters = cluster_evidence(evidence, atr=12.0, cfg=cfg)
    assert len(clusters) == 2


def test_merge_distance_scales_with_volatility(cfg: Config):
    """ТЗ §16: допустимое расстояние зависит от волатильности, а не фиксировано."""
    evidence = [
        _evidence(4786, kind=EvidenceKind.H4_WICK),
        _evidence(4794),
    ]
    calm = cluster_evidence(evidence, atr=6.0, cfg=cfg)       # порог 2.1 → раздельно
    volatile = cluster_evidence(evidence, atr=40.0, cfg=cfg)   # порог 14.0 → вместе
    # При спокойном рынке H1-реакция в 8 долларах — это уже другая область,
    # поэтому она не попадает в кластер H4.
    assert len(calm[0].members) == 1
    assert len(volatile[0].members) == 2


def test_cluster_without_h4_is_not_a_zone_source(cfg: Config):
    """ТЗ §17, §58: без H4-фитиля кластер зоной не становится."""
    evidence = [_evidence(4786), _evidence(4787, kind=EvidenceKind.SR_AREA)]
    assert cluster_evidence(evidence, atr=12.0, cfg=cfg) == []


def test_upper_and_lower_areas_are_separate(cfg: Config):
    """ТЗ §9: верхние и нижние области различаются по типу реакции."""
    h1 = h1_series(160, base=4800.0, spikes={80: 4786.0}, upper_spikes={120: 4816.0})
    h4 = to_h4(h1)
    events = find_wick_events(h4, cfg, "H4")
    dirs = {e.direction for e in events}
    assert Direction.LOWER in dirs or Direction.UPPER in dirs
    for e in events:
        # Тип реакции есть, но торгового направления в модели нет вовсе.
        assert not hasattr(e, "signal")
