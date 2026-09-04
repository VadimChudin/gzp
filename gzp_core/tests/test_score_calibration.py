"""ТЗ §49-§51 — шкала Score должна РАЗЛИЧАТЬ зоны.

ТЗ разрешает подбирать конкретные числа на истории (§24), но требует, чтобы
Score не был просто количеством совпадений. Практический критерий: на реальном
прогоне оценки не должны упираться в максимум, иначе пороги Strong и
Very Strong теряют смысл и «исключительной» становится каждая область.
"""

from __future__ import annotations

import statistics

from gzp_core.config import Config
from gzp_core.data_feed import resample, synth_series
from gzp_core.engine import ZoneEngine
from gzp_core.models import ZoneGrade

MAX_POSSIBLE = 100.0


def _run(cfg: Config):
    h1 = synth_series(1600, "H1", seed=11)
    h4 = resample(h1, "H1", "H4")
    engine = ZoneEngine(cfg)
    for i in range(cfg.atr_period + 2, len(h4)):
        engine.on_h4_close(h4[: i + 1], h1, now=h4[i].ts)
    return engine.zones


def test_score_ceiling_matches_configured_scale(cfg: Config):
    """Максимум шкалы складывается из потолков групп и равен 100 баллам."""
    total = (
        cfg.cap_h4_primary
        + cfg.cap_h4_extra
        + cfg.cap_h1
        + cfg.cap_sr
        + cfg.w_reaction_max
        + cfg.w_repeat_rejection
    )
    assert total == MAX_POSSIBLE
    assert cfg.score_strong < cfg.score_very_strong < MAX_POSSIBLE


def test_scores_are_spread_not_saturated(cfg: Config):
    """Оценки не должны стоять на максимуме — иначе градация бессмысленна."""
    zones = _run(cfg)
    assert len(zones) >= 5, "недостаточно зон для оценки калибровки"

    scores = [z.score for z in zones]
    assert max(scores) <= MAX_POSSIBLE + 1e-6
    # Разброс: между лучшей и худшей зоной должна быть содержательная разница.
    assert max(scores) - min(scores) >= 10.0
    # Медиана не прижата к потолку.
    assert statistics.median(scores) < MAX_POSSIBLE * 0.95


def test_very_strong_is_not_the_default_grade(cfg: Config):
    """ТЗ §51: Very Strong — исключение, а не норма."""
    zones = _run(cfg)
    very = [z for z in zones if z.grade is ZoneGrade.VERY_STRONG]
    assert len(very) / len(zones) < 0.6, "почти все зоны стали Very Strong"


def test_stricter_significance_produces_fewer_zones():
    """Порог значимости фитиля реально управляет количеством зон (ТЗ §5, §50)."""
    permissive = _run(Config(h4_wick_min_atr=0.45, h1_wick_min_atr=0.50))
    strict = _run(Config(h4_wick_min_atr=0.85, h1_wick_min_atr=0.90))
    assert len(strict) < len(permissive)


def test_thresholds_are_configurable_without_code_change():
    """ТЗ §50: сам порог обязан быть параметром."""
    lenient = _run(Config(score_strong=40.0, score_very_strong=95.0))
    demanding = _run(Config(score_strong=90.0, score_very_strong=99.0))
    assert len(demanding) < len(lenient)
