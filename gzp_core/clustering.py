"""Объединение близких реакций в один ценовой кластер.

Реализует ТЗ §13-§16, §19, §30, §31:
  • несколько реакций в одной области — это ОДИН кластер, а не N уровней;
  • слишком далёкие цены объединять нельзя;
  • допустимое расстояние адаптируется к волатильности (ATR), а не фиксировано;
  • несколько H4-реакций рядом дают одну сильную зону, а не три зоны.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config
from .models import Direction, Evidence, EvidenceKind


@dataclass
class Cluster:
    direction: Direction
    members: list[Evidence] = field(default_factory=list)

    @property
    def prices(self) -> list[float]:
        return [e.price for e in self.members]

    @property
    def price_low(self) -> float:
        return min(self.prices)

    @property
    def price_high(self) -> float:
        return max(self.prices)

    @property
    def area_low(self) -> float:
        return min(e.low for e in self.members)

    @property
    def area_high(self) -> float:
        return max(e.high for e in self.members)

    def has_kind(self, kind: EvidenceKind) -> bool:
        return any(e.kind is kind for e in self.members)

    @property
    def h4_members(self) -> list[Evidence]:
        return [e for e in self.members if e.kind is EvidenceKind.H4_WICK]


def cluster_evidence(
    evidence: list[Evidence],
    atr: float,
    cfg: Config,
) -> list[Cluster]:
    """Агломерация по близости цены с порогом, зависящим от ATR (ТЗ §16).

    Верхние и нижние области кластеризуются отдельно: тип исторической реакции
    у них разный (ТЗ §9).
    """
    if not evidence or atr <= 0:
        return []

    tolerance = atr * cfg.cluster_merge_atr
    clusters: list[Cluster] = []

    for direction in (Direction.LOWER, Direction.UPPER):
        subset = sorted(
            [e for e in evidence if e.direction is direction], key=lambda e: e.price
        )
        if not subset:
            continue

        # Максимальный размах кластера: без него агломерация «цепочкой»
        # склеила бы 4786 и 4830 через промежуточные реакции, что запрещено
        # ТЗ §15, а итоговая зона нарушила бы ограничение ширины (ТЗ §39).
        max_span = atr * cfg.zone_max_width_atr

        current = Cluster(direction=direction, members=[subset[0]])
        for ev in subset[1:]:
            # Расстояние до соседней реакции в пределах порога (ТЗ §15, §31)
            # И общий размах области в пределах допустимой ширины зоны.
            near = ev.price - current.price_high <= tolerance
            compact = ev.price - current.price_low <= max_span
            if near and compact:
                current.members.append(ev)
            else:
                clusters.append(current)
                current = Cluster(direction=direction, members=[ev])
        clusters.append(current)

    # ТЗ §17: источником зоны является H4. Кластер без H4-фитиля не может
    # породить зону — он остаётся материалом для подтверждения.
    return [c for c in clusters if c.h4_members]
