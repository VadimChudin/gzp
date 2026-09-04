"""Структуры данных GZP.

Ключевая идея ТЗ: зона — это не цена, а объект с историей происхождения и
состоянием (ТЗ §52, §54, §64). Направление сделки зона не несёт никогда
(ТЗ §9, §59) — поэтому в модели нет ни одного поля вида LONG/SHORT.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Direction(str, Enum):
    """Направление ИСТОРИЧЕСКОЙ реакции, а не торгового решения (ТЗ §9)."""

    LOWER = "lower"   # отвержение снизу (нижний фитиль)
    UPPER = "upper"   # отвержение сверху (верхний фитиль)


class EvidenceKind(str, Enum):
    H4_WICK = "h4_wick"
    H1_WICK = "h1_wick"
    SR_AREA = "sr_area"


class ZoneState(str, Enum):
    """Жизненный цикл зоны (ТЗ §64)."""

    CANDIDATE = "candidate"       # найден фитиль, подтверждений мало (ТЗ §55)
    ACTIVE = "active"             # подтверждена как Strong, ждёт цену
    TESTED = "tested"             # цена приходила, зона отработала реакцию
    BROKEN = "broken"             # цена закрепилась за зоной (ТЗ §65)


class ZoneGrade(str, Enum):
    CANDIDATE = "candidate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


@dataclass(frozen=True)
class Candle:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def body_top(self) -> float:
        return max(self.open, self.close)

    @property
    def body_bottom(self) -> float:
        return min(self.open, self.close)

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def upper_wick(self) -> float:
        """От максимума до верхней границы тела (ТЗ §4)."""
        return self.high - self.body_top

    @property
    def lower_wick(self) -> float:
        """От нижней границы тела до минимума (ТЗ §4)."""
        return self.body_bottom - self.low


@dataclass
class Reaction:
    """Что произошло ПОСЛЕ появления фитиля (ТЗ §7, §8, §27, §28)."""

    displacement_atr: float = 0.0     # величина импульса от области, в ATR
    broke_local_extreme: bool = False # пробит предыдущий локальный экстремум
    returned_to_body: bool = False    # цена вернулась внутрь тела свечи

    @property
    def is_significant(self) -> bool:
        return self.displacement_atr > 0.0


@dataclass
class Evidence:
    """Одно независимое историческое доказательство в области цены.

    event_key нужен для ТЗ §25: один и тот же исторический факт (одна свеча)
    не может дать вес несколько раз.
    """

    kind: EvidenceKind
    direction: Direction
    outer: float                      # внешний экстремум области (ТЗ §10)
    inner: float                      # внутренняя граница области (ТЗ §10)
    price: float                      # характерная цена реакции
    ts: datetime
    timeframe: str
    event_key: str
    weight_hint: float = 1.0          # относительная значимость факта 0..N
    reaction: Reaction = field(default_factory=Reaction)
    touches: int = 1

    @property
    def low(self) -> float:
        return min(self.outer, self.inner)

    @property
    def high(self) -> float:
        return max(self.outer, self.inner)


@dataclass
class ScoreBreakdown:
    """Расшифровка Score — нужна для проверки правильности алгоритма (ТЗ §54)."""

    h4_primary: float = 0.0
    h4_extra: float = 0.0
    h1: float = 0.0
    sr: float = 0.0
    reaction: float = 0.0
    repeat_rejection: float = 0.0

    h4_events: int = 0
    h1_events: int = 0
    sr_areas: int = 0
    independent_groups: int = 0

    @property
    def total(self) -> float:
        return round(
            self.h4_primary
            + self.h4_extra
            + self.h1
            + self.sr
            + self.reaction
            + self.repeat_rejection,
            2,
        )


@dataclass
class ZoneTest:
    """Один факт прихода цены в зону (ТЗ §41, §42)."""

    ts: datetime
    entered: bool
    penetration_atr: float
    pierced: bool                  # прокол фитилём без закрытия за зоной
    closed_beyond: bool            # закрытие за зоной
    reaction_atr: float            # сила ухода из зоны обратно


@dataclass
class Zone:
    """Сильная ценовая область (ТЗ §52)."""

    id: str
    lower: float
    upper: float
    reference: float               # характерная цена внутри зоны (ТЗ §53)
    direction: Direction           # тип исторической реакции (ТЗ §9)
    created_at: datetime           # момент фиксации зоны (ТЗ §45)
    score: float
    grade: ZoneGrade
    state: ZoneState
    breakdown: ScoreBreakdown
    evidence: list[Evidence] = field(default_factory=list)
    tests: list[ZoneTest] = field(default_factory=list)
    updated_at: Optional[datetime] = None
    broken_at: Optional[datetime] = None
    consecutive_closes_beyond: int = 0
    last_break_side: Optional[str] = None

    @property
    def width(self) -> float:
        return self.upper - self.lower

    @property
    def test_count(self) -> int:
        return len(self.tests)

    @property
    def timeframes(self) -> list[str]:
        return sorted({e.timeframe for e in self.evidence})

    def contains(self, price: float) -> bool:
        return self.lower <= price <= self.upper

    def overlaps(self, lower: float, upper: float) -> float:
        """Доля перекрытия с другим диапазоном 0..1 (ТЗ §37)."""
        inter = min(self.upper, upper) - max(self.lower, lower)
        if inter <= 0:
            return 0.0
        smallest = min(self.width, upper - lower)
        if smallest <= 0:
            return 1.0
        return inter / smallest

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "lower": round(self.lower, 2),
            "upper": round(self.upper, 2),
            "reference": round(self.reference, 2),
            "reaction_type": self.direction.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": (self.updated_at or self.created_at).isoformat(),
            "score": round(self.score, 2),
            "grade": self.grade.value,
            "state": self.state.value,
            "tests": self.test_count,
            "confirmations": {
                "h4": self.breakdown.h4_events,
                "h1": self.breakdown.h1_events,
                "sr": self.breakdown.sr_areas,
                "independent_groups": self.breakdown.independent_groups,
            },
            "score_breakdown": {
                "h4_primary": self.breakdown.h4_primary,
                "h4_extra": self.breakdown.h4_extra,
                "h1": self.breakdown.h1,
                "sr": self.breakdown.sr,
                "reaction": self.breakdown.reaction,
                "repeat_rejection": self.breakdown.repeat_rejection,
            },
            "timeframes": self.timeframes,
        }
