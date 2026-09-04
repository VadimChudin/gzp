"""Параметры алгоритма GZP.

Все пороги вынесены сюда: ТЗ прямо требует, чтобы пороги Score, ширина зоны и
допустимое расстояние объединения были параметрами, а не константами в коде
(ТЗ §16, §39, §50).

Любой параметр можно переопределить переменной окружения GZP_<ИМЯ>.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(f"GZP_{name.upper()}")
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class Config:
    # ── Инструмент ───────────────────────────────────────────────────────────
    symbol: str = "XAUUSD"

    # ── ATR: мера текущей волатильности (ТЗ §16, §28) ────────────────────────
    atr_period: int = 14

    # ── Значимость H4-фитиля (ТЗ §6) ─────────────────────────────────────────
    # Три независимые характеристики: длина к ATR, отношение к телу, доля свечи.
    h4_wick_min_atr: float = 0.60
    h4_wick_min_body_ratio: float = 0.60
    h4_wick_min_range_ratio: float = 0.35

    # ── Значимость H1-фитиля (ТЗ §18) ────────────────────────────────────────
    h1_wick_min_atr: float = 0.65
    h1_wick_min_body_ratio: float = 0.70
    h1_wick_min_range_ratio: float = 0.38

    # ── Реакция после фитиля (ТЗ §7, §8, §27, §28) ───────────────────────────
    # Горизонт измеряется в свечах ТФ фитиля и всегда ограничен «сейчас»:
    # смотреть вперёд за пределы текущего момента запрещено (ТЗ §45).
    reaction_horizon_h4: int = 12
    reaction_horizon_h1: int = 24
    # Реакция считается сильной, если цена ушла от области на столько ATR.
    reaction_strong_atr: float = 1.00
    # Ниже этого значения реакция считается незначимой и веса не даёт.
    reaction_min_atr: float = 0.35

    # ── Окно актуальной истории (ТЗ §36) ─────────────────────────────────────
    # Зона должна опираться на актуальную историческую область. Без окна
    # алгоритм копит подтверждения годами и объявляет сильной любую область.
    h4_evidence_bars: int = 180        # ~30 торговых дней H4
    h1_evidence_bars: int = 480        # ~20 дней H1

    # ── S/R как независимый источник (ТЗ §21, §22) ───────────────────────────
    swing_lookaround: int = 3          # фрактальное окно swing high/low
    sr_history_bars: int = 600         # глубина поиска истории S/R на H1
    sr_min_touches: int = 2            # области нескольких касаний
    sr_touch_atr: float = 0.30         # что считается касанием уровня

    # ── Кластеризация реакций (ТЗ §14, §15, §16, §31) ────────────────────────
    # Максимальное расстояние между реакциями в долях ATR H4.
    cluster_merge_atr: float = 0.35

    # ── Границы и ширина зоны (ТЗ §20, §38, §39) ─────────────────────────────
    zone_min_width_atr: float = 0.12
    zone_normal_width_atr: float = 0.45
    zone_max_width_atr: float = 0.90
    # Доля веса реакций, которую должны покрыть границы зоны.
    zone_core_mass: float = 0.80

    # ── Веса факторов Score (ТЗ §24, §48, §49) ───────────────────────────────
    # Шкала откалибрована так, чтобы максимум был около 100: иначе пороги
    # Strong/Very Strong теряют смысл и «сильной» становится каждая зона.
    # Каждая группа факторов ограничена своим потолком (ТЗ §49: Score — не
    # просто количество совпадений).
    # Потолки групп задают шкалу: в сумме максимум = 100 баллов.
    cap_h4_primary: float = 30.0       # значимый H4-фитиль — наибольший вес
    cap_h4_extra: float = 12.0         # дополнительные H4-реакции
    max_h4_extra: int = 2
    cap_h1: float = 16.0               # значимые H1-фитили
    max_h1_events: int = 3
    cap_sr: float = 12.0               # исторические S/R-области
    max_sr_areas: int = 2
    w_reaction_max: float = 24.0       # сила импульса после реакции
    w_repeat_rejection: float = 6.0    # повторные независимые отвержения

    # ── Пороги силы зоны (ТЗ §50, §51) ───────────────────────────────────────
    score_strong: float = 55.0
    score_very_strong: float = 78.0
    # ТЗ §29: одного фитиля недостаточно — нужно хотя бы одно подтверждение
    # из другой независимой группы.
    min_independent_groups: int = 2

    # ── Жизненный цикл зоны (ТЗ §41-44, §65) ─────────────────────────────────
    # Приближение цены, при котором фиксируется тест зоны.
    test_proximity_atr: float = 0.15
    # Закрытие за границей на столько ATR считается подтверждённым пробоем.
    break_close_atr: float = 0.20
    # Сколько закрытий за зоной подряд нужно для инвалидации (ТЗ §44, §65).
    break_closes_required: int = 2
    # Максимальный возраст зоны без тестов, свечей H4 (0 = не устаревает).
    zone_max_age_h4: int = 0

    # ── Вывод ────────────────────────────────────────────────────────────────
    max_zones_output: int = 12

    @classmethod
    def from_env(cls) -> "Config":
        cfg = cls()
        for f in fields(cls):
            if f.type in ("float", "int"):
                current = getattr(cfg, f.name)
                value = _env_float(f.name, float(current))
                setattr(cfg, f.name, int(value) if f.type == "int" else value)
        symbol = os.environ.get("GZP_SYMBOL")
        if symbol:
            cfg.symbol = symbol
        return cfg


DEFAULT = Config()
