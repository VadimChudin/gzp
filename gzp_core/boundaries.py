"""Определение итоговых границ зоны и reference-уровня.

Реализует ТЗ §12, §20, §39, §53:
  Этап 1 — собраны все связанные реакции (сделано в clustering);
  Этап 2 — определён ценовой кластер;
  Этап 3 — берётся диапазон, где сосредоточена основная масса реакций;
  Этап 4 — проверяется, не слишком ли широкая зона;
  Этап 5 — границы нормализуются по волатильности.

Ключевой момент §12: длинный фитиль целиком зоной не становится — реакция
могла концентрироваться в его части, поэтому используется весовая масса.
"""

from __future__ import annotations

from collections import Counter

from .config import Config
from .clustering import Cluster
from .models import Direction, EvidenceKind


def _core_range(cluster: Cluster, core_mass: float) -> tuple[float, float]:
    """Диапазон, покрывающий заданную долю веса реакций (ТЗ §20, этап 3)."""
    weighted = sorted(
        ((e.price, max(e.weight_hint, 0.01)) for e in cluster.members),
        key=lambda p: p[0],
    )
    total = sum(w for _, w in weighted)
    if total <= 0:
        return cluster.price_low, cluster.price_high

    target_tail = (1.0 - core_mass) / 2.0

    def quantile(q: float) -> float:
        acc = 0.0
        for price, weight in weighted:
            acc += weight
            if acc / total >= q:
                return price
        return weighted[-1][0]

    low = quantile(target_tail)
    high = quantile(1.0 - target_tail)
    if high < low:
        low, high = high, low
    return low, high


def compute_bounds(cluster: Cluster, atr: float, cfg: Config) -> tuple[float, float]:
    """Итоговые границы зоны с ограничением ширины (ТЗ §20, §39)."""
    core_low, core_high = _core_range(cluster, cfg.zone_core_mass)

    # ТЗ §19: H4-фитиль показывает, что область исторически уходила глубже —
    # эту структуру нужно сохранять, а не брать простое пересечение.
    h4 = cluster.h4_members
    if cluster.direction is Direction.LOWER:
        deepest = min(e.outer for e in h4)
        inner_edge = max(e.inner for e in h4)
        low = min(core_low, deepest)
        high = max(core_high, min(inner_edge, deepest + atr * cfg.zone_normal_width_atr))
    else:
        highest = max(e.outer for e in h4)
        inner_edge = min(e.inner for e in h4)
        high = max(core_high, highest)
        low = min(core_low, max(inner_edge, highest - atr * cfg.zone_normal_width_atr))

    min_w = atr * cfg.zone_min_width_atr
    max_w = atr * cfg.zone_max_width_atr
    width = high - low

    if width < min_w:
        # Этап 5: нормализация слишком узкой зоны вокруг её центра.
        center = (high + low) / 2.0
        low, high = center - min_w / 2.0, center + min_w / 2.0
    elif width > max_w:
        # Этап 4: зона не должна превращаться в огромный диапазон (ТЗ §39).
        # Обрезаем со стороны внутренней границы, сохраняя исторический
        # экстремум — именно он является якорем области.
        if cluster.direction is Direction.LOWER:
            high = low + max_w
        else:
            low = high - max_w

    return round(low, 4), round(high, 4)


def compute_reference(cluster: Cluster, lower: float, upper: float) -> float:
    """Reference Price — наиболее характерная цена внутри зоны (ТЗ §53).

    Приоритет: самая частая цена реакций → центр весов → самый значимый H4.
    """
    inside = [e for e in cluster.members if lower <= e.price <= upper]
    pool = inside or cluster.members

    rounded = Counter(round(e.price, 0) for e in pool)
    top_price, top_count = rounded.most_common(1)[0]
    if top_count >= 2:
        # Наиболее часто встречающаяся цена реакций.
        matching = [e.price for e in pool if round(e.price, 0) == top_price]
        return round(sum(matching) / len(matching), 2)

    h4 = [e for e in pool if e.kind is EvidenceKind.H4_WICK]
    if h4:
        best = max(h4, key=lambda e: (e.weight_hint, e.reaction.displacement_atr))
        return round(min(max(best.price, lower), upper), 2)

    weights = sum(max(e.weight_hint, 0.01) for e in pool)
    center = sum(e.price * max(e.weight_hint, 0.01) for e in pool) / weights
    return round(min(max(center, lower), upper), 2)
