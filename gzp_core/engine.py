"""Движок поиска зон GZP.

Реализует ТЗ §32-§40, §45-§47, §67, §70, §71.

Инварианты, которые движок обязан соблюдать:
  1. Зона фиксируется ТОЛЬКО на закрытии H4 (§32, §33).
  2. Внутри одного H4 зона не пересоздаётся (§33).
  3. Новый H4 не обязан рождать новую зону (§35, §67).
  4. Почти совпадающая область — это обновление, а не дубль (§37).
  5. Расширение зоны ограничено (§38, §39).
  6. При создании зоны используется только история ДО момента создания (§45, §46).
  7. Направление сделки не присваивается никогда (§59).
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import datetime

from .boundaries import compute_bounds, compute_reference
from .clustering import Cluster, cluster_evidence
from .config import Config
from .indicators import atr_at
from .models import (
    Candle,
    Direction,
    Evidence,
    ScoreBreakdown,
    Zone,
    ZoneGrade,
    ZoneState,
)
from .scoring import grade_for, score_cluster
from .sr import find_sr_areas
from .wicks import find_wick_events


def _zone_id(direction: Direction, reference: float, created_at: datetime) -> str:
    return f"{direction.value[0].upper()}{reference:.0f}-{created_at:%Y%m%d%H%M}"


class ZoneEngine:
    """Поиск и поддержка зон. Отвечает только на вопрос «где сильная область».

    Вопрос «что делать с ценой» решает модуль lifecycle/m5_confirm — ТЗ §70
    требует полного разделения этих двух задач.
    """

    def __init__(self, cfg: Config | None = None) -> None:
        self.cfg = cfg or Config()
        self.zones: list[Zone] = []
        self._last_h4_close: datetime | None = None

    # ── Публичный API ────────────────────────────────────────────────────────

    def on_h4_close(
        self,
        h4: list[Candle],
        h1: list[Candle],
        now: datetime | None = None,
    ) -> list[Zone]:
        """Обработать закрытие H4-свечи. Возвращает список СОЗДАННЫХ зон.

        h4/h1 должны содержать только закрытые свечи. Всё, что позже now,
        игнорируется — это защита от look-ahead bias (ТЗ §45).
        """
        if not h4:
            return []

        now = now or h4[-1].ts
        # ТЗ §33: в пределах одного H4 повторный расчёт запрещён.
        if self._last_h4_close is not None and now <= self._last_h4_close:
            return []
        self._last_h4_close = now

        h4_idx = self._index_upto(h4, now)
        h1_idx = self._index_upto(h1, now)
        if h4_idx < self.cfg.atr_period:
            return []

        atr = atr_at(h4, h4_idx, self.cfg.atr_period)
        evidence = self._collect_evidence(h4, h1, h4_idx, h1_idx)
        clusters = cluster_evidence(evidence, atr, self.cfg)

        created: list[Zone] = []
        for cluster in clusters:
            bd = score_cluster(cluster, atr, self.cfg)
            grade = grade_for(bd, self.cfg)
            lower, upper = compute_bounds(cluster, atr, self.cfg)
            reference = compute_reference(cluster, lower, upper)

            existing = self._find_existing(cluster.direction, lower, upper, reference, atr)
            if existing is not None:
                # ТЗ §37, §40: это та же область — обновляем, а не дублируем.
                self._update_zone(existing, cluster, bd, grade, lower, upper, reference, atr, now)
                continue

            # ТЗ §36, §50, §55: новая зона появляется только при достаточном Score.
            if grade is ZoneGrade.CANDIDATE:
                continue

            zone = Zone(
                id=_zone_id(cluster.direction, reference, now),
                lower=lower,
                upper=upper,
                reference=reference,
                direction=cluster.direction,
                created_at=now,
                score=bd.total,
                grade=grade,
                state=ZoneState.ACTIVE,
                breakdown=bd,
                evidence=list(cluster.members),
                updated_at=now,
            )
            self.zones.append(zone)
            created.append(zone)

        # ТЗ §35: если новых сильных зон нет — список created пуст, и это норма.
        return created

    def active_zones(self) -> list[Zone]:
        """Зоны для вывода: самые сильные сверху (ТЗ §52)."""
        alive = [z for z in self.zones if z.state is not ZoneState.BROKEN]
        alive.sort(key=lambda z: (z.score, z.updated_at or z.created_at), reverse=True)
        return alive[: self.cfg.max_zones_output]

    # ── Внутреннее ───────────────────────────────────────────────────────────

    @staticmethod
    def _index_upto(candles: list[Candle], now: datetime) -> int:
        """Индекс последней свечи, закрытой не позже now."""
        if not candles:
            return -1
        stamps = [c.ts for c in candles]
        return bisect_right(stamps, now) - 1

    def _collect_evidence(
        self,
        h4: list[Candle],
        h1: list[Candle],
        h4_idx: int,
        h1_idx: int,
    ) -> list[Evidence]:
        """H4 → H1 → S/R, строго в порядке ТЗ §71."""
        evidence: list[Evidence] = find_wick_events(h4, self.cfg, "H4", now_index=h4_idx)
        if h1_idx >= self.cfg.atr_period:
            evidence += find_wick_events(h1, self.cfg, "H1", now_index=h1_idx)
            evidence += find_sr_areas(h1, self.cfg, "H1", now_index=h1_idx)
        else:
            evidence += find_sr_areas(h4, self.cfg, "H4", now_index=h4_idx)
        return evidence

    def _find_existing(
        self,
        direction: Direction,
        lower: float,
        upper: float,
        reference: float,
        atr: float,
    ) -> Zone | None:
        """Та же самая область цены? (ТЗ §36, §37)"""
        tol = atr * self.cfg.cluster_merge_atr
        for zone in self.zones:
            if zone.direction is not direction:
                continue
            if zone.state is ZoneState.BROKEN:
                continue
            if zone.overlaps(lower, upper) >= 0.5:
                return zone
            if abs(zone.reference - reference) <= tol:
                return zone
        return None

    def _update_zone(
        self,
        zone: Zone,
        cluster: Cluster,
        bd: ScoreBreakdown,
        grade: ZoneGrade,
        lower: float,
        upper: float,
        reference: float,
        atr: float,
        now: datetime,
    ) -> None:
        """Обновление характеристик существующей зоны (ТЗ §37, §38, §39)."""
        known = {e.event_key for e in zone.evidence}
        fresh = [e for e in cluster.members if e.event_key not in known]
        zone.evidence.extend(fresh)

        # Расширение допустимо, но ограничено максимальной шириной (ТЗ §39).
        max_w = atr * self.cfg.zone_max_width_atr
        new_lower = min(zone.lower, lower)
        new_upper = max(zone.upper, upper)
        if new_upper - new_lower <= max_w:
            zone.lower, zone.upper = new_lower, new_upper
        # Иначе границы остаются прежними: бесконечно расти зона не должна.

        if bd.total > zone.score:
            zone.score = bd.total
            zone.breakdown = bd
            if grade is not ZoneGrade.CANDIDATE:
                zone.grade = grade
        # Reference уточняем только внутри актуальных границ.
        if zone.lower <= reference <= zone.upper:
            zone.reference = reference
        zone.updated_at = now
