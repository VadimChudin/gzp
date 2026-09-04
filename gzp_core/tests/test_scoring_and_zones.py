"""ТЗ §20, §24-§29, §39, §48-§58, §68 — Score, границы, конфлюенс."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from gzp_core.boundaries import compute_bounds, compute_reference
from gzp_core.clustering import Cluster
from gzp_core.config import Config
from gzp_core.engine import ZoneEngine
from gzp_core.models import Direction, Evidence, EvidenceKind, Reaction, ZoneGrade
from gzp_core.scoring import grade_for, score_cluster

TS = datetime(2026, 4, 15, 8, tzinfo=timezone.utc)


def ev(kind, price, ts=TS, weight=1.0, reaction_atr=1.2, inner_offset=6.0) -> Evidence:
    return Evidence(
        kind=kind,
        direction=Direction.LOWER,
        outer=price,
        inner=price + inner_offset,
        price=price,
        ts=ts,
        timeframe="H4" if kind is EvidenceKind.H4_WICK else "H1",
        event_key=f"{kind.value}:{price}:{ts.isoformat()}",
        weight_hint=weight,
        reaction=Reaction(displacement_atr=reaction_atr),
    )


def cluster(*members) -> Cluster:
    return Cluster(direction=Direction.LOWER, members=list(members))


def test_h4_alone_is_only_a_candidate(cfg: Config):
    """ТЗ §29, §55: один H4-фитиль без подтверждений — не Strong Zone."""
    c = cluster(ev(EvidenceKind.H4_WICK, 4786, weight=1.5, reaction_atr=2.0))
    bd = score_cluster(c, atr=12.0, cfg=cfg)
    assert grade_for(bd, cfg) is ZoneGrade.CANDIDATE
    assert bd.independent_groups == 1


def test_h4_plus_h1_plus_sr_is_strong(cfg: Config):
    """ТЗ §57, §68: H4 + два H1 + S/R = сильная зона."""
    c = cluster(
        ev(EvidenceKind.H4_WICK, 4786, weight=1.4, reaction_atr=1.8),
        ev(EvidenceKind.H1_WICK, 4785, ts=TS + timedelta(hours=1)),
        ev(EvidenceKind.H1_WICK, 4787, ts=TS + timedelta(hours=3)),
        ev(EvidenceKind.SR_AREA, 4786, ts=TS - timedelta(days=6)),
    )
    bd = score_cluster(c, atr=12.0, cfg=cfg)
    assert grade_for(bd, cfg) in (ZoneGrade.STRONG, ZoneGrade.VERY_STRONG)
    assert bd.independent_groups == 3
    assert bd.sr > 0, "S/R из другого времени — независимое подтверждение (ТЗ §26)"


def test_more_confirmations_score_higher(cfg: Config):
    """ТЗ §24: каждое дополнительное подтверждение усиливает зону."""
    base = ev(EvidenceKind.H4_WICK, 4786, weight=1.4, reaction_atr=1.8)
    weak = score_cluster(cluster(base), 12.0, cfg).total
    medium = score_cluster(
        cluster(base, ev(EvidenceKind.H1_WICK, 4785, ts=TS + timedelta(hours=1))), 12.0, cfg
    ).total
    strong = score_cluster(
        cluster(
            base,
            ev(EvidenceKind.H1_WICK, 4785, ts=TS + timedelta(hours=1)),
            ev(EvidenceKind.SR_AREA, 4786, ts=TS - timedelta(days=6)),
        ),
        12.0,
        cfg,
    ).total
    assert weak < medium < strong


def test_same_event_is_not_counted_twice(cfg: Config):
    """ТЗ §25: фитиль и S/R одной и той же свечи — одно доказательство."""
    h4 = ev(EvidenceKind.H4_WICK, 4786, weight=1.4)
    duplicate_sr = ev(EvidenceKind.SR_AREA, 4786.05, ts=TS)          # тот же факт
    independent_sr = ev(EvidenceKind.SR_AREA, 4786, ts=TS - timedelta(days=9))

    dup = score_cluster(cluster(h4, duplicate_sr), 12.0, cfg)
    ind = score_cluster(cluster(h4, independent_sr), 12.0, cfg)
    assert dup.sr == 0.0
    assert ind.sr > 0.0


def test_ten_small_wicks_do_not_beat_real_confluence(cfg: Config):
    """ТЗ §49: Score — это не просто количество совпадений."""
    many_small = cluster(
        ev(EvidenceKind.H4_WICK, 4786, weight=0.5, reaction_atr=0.2),
        *[
            ev(EvidenceKind.H1_WICK, 4786 + i * 0.1, ts=TS + timedelta(hours=i), weight=0.4,
               reaction_atr=0.1)
            for i in range(1, 11)
        ],
    )
    real = cluster(
        ev(EvidenceKind.H4_WICK, 4786, weight=1.5, reaction_atr=2.2),
        ev(EvidenceKind.H1_WICK, 4785, ts=TS + timedelta(hours=2), weight=1.2),
        ev(EvidenceKind.H1_WICK, 4787, ts=TS + timedelta(hours=5), weight=1.1),
        ev(EvidenceKind.SR_AREA, 4786, ts=TS - timedelta(days=7), weight=1.4),
    )
    assert score_cluster(real, 12.0, cfg).total > score_cluster(many_small, 12.0, cfg).total


def test_sr_alone_never_produces_zone(cfg: Config):
    """ТЗ §58: чистый S/R не превращает индикатор в обычный S/R-индикатор."""
    bd = score_cluster(cluster(ev(EvidenceKind.SR_AREA, 4786)), 12.0, cfg)
    assert bd.total == 0.0
    assert grade_for(bd, cfg) is ZoneGrade.CANDIDATE


def test_zone_width_is_bounded_by_volatility(cfg: Config):
    """ТЗ §39: зона не может разрастись до бесполезного диапазона."""
    atr = 10.0
    wide = cluster(
        ev(EvidenceKind.H4_WICK, 4700, inner_offset=100.0),
        ev(EvidenceKind.H4_WICK, 4800, ts=TS + timedelta(days=1), inner_offset=100.0),
    )
    lower, upper = compute_bounds(wide, atr, cfg)
    assert upper - lower <= atr * cfg.zone_max_width_atr + 1e-6


def test_zone_has_minimum_width(cfg: Config):
    """ТЗ §20 этап 5: слишком узкая зона нормализуется."""
    atr = 10.0
    tight = cluster(ev(EvidenceKind.H4_WICK, 4786, inner_offset=0.05))
    lower, upper = compute_bounds(tight, atr, cfg)
    assert upper - lower >= atr * cfg.zone_min_width_atr - 1e-6


def test_reference_price_is_inside_zone(cfg: Config):
    """ТЗ §53: reference — характерная цена ВНУТРИ зоны."""
    c = cluster(
        ev(EvidenceKind.H4_WICK, 4786),
        ev(EvidenceKind.H1_WICK, 4786, ts=TS + timedelta(hours=2)),
        ev(EvidenceKind.H1_WICK, 4787, ts=TS + timedelta(hours=4)),
    )
    lower, upper = compute_bounds(c, 12.0, cfg)
    reference = compute_reference(c, lower, upper)
    assert lower <= reference <= upper
    assert abs(reference - 4786) < 2


def test_reference_example_from_spec(scenario_4786, cfg: Config):
    """ТЗ §68: на эталонных данных появляется одна сильная зона около 4786."""
    h4, h1 = scenario_4786
    engine = ZoneEngine(cfg)
    for i in range(cfg.atr_period + 2, len(h4)):
        engine.on_h4_close(h4[: i + 1], h1, now=h4[i].ts)

    near = [z for z in engine.zones if abs(z.reference - 4786) <= 6]
    assert near, f"зона около 4786 не найдена; всего зон: {len(engine.zones)}"
    assert len(near) == 1, "область 4786 должна быть ОДНОЙ зоной, а не набором уровней"

    zone = near[0]
    assert zone.lower <= 4786 <= zone.upper
    assert zone.grade in (ZoneGrade.STRONG, ZoneGrade.VERY_STRONG)
    assert zone.breakdown.h4_events >= 1
    # Никакого торгового направления в выводе (ТЗ §59, §68).
    payload = zone.to_dict()
    assert "signal" not in payload
    assert "BUY" not in str(payload).upper()
    assert "SELL" not in str(payload).upper()
