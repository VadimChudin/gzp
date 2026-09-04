"""Zone Strength Score.

Реализует ТЗ §24, §25, §26, §29, §48-§51, §55-§58:
  • у каждого фактора свой вес, H4 весит больше случайного H1 (§49);
  • один и тот же исторический факт не может дать вес дважды (§25);
  • повторные НЕЗАВИСИМЫЕ реакции ценнее (§26);
  • только H4 без подтверждений → кандидат, не Strong (§55);
  • только S/R → не Strong (§58);
  • порог Strong и Very Strong — параметры (§50, §51).
"""

from __future__ import annotations

from datetime import timedelta

from .config import Config
from .clustering import Cluster
from .models import EvidenceKind, ScoreBreakdown, ZoneGrade


def _dedup_events(cluster: Cluster) -> dict[EvidenceKind, list]:
    """Убираем повторный счёт одного и того же факта (ТЗ §25).

    Один и тот же исторический момент (свеча) внутри одного вида доказательств
    учитывается один раз — по максимальному весу.
    """
    best: dict[tuple[EvidenceKind, str], object] = {}
    for ev in cluster.members:
        # Ключ независимости: вид доказательства + момент времени.
        key = (ev.kind, ev.ts.isoformat())
        prev = best.get(key)
        if prev is None or ev.weight_hint > prev.weight_hint:  # type: ignore[union-attr]
            best[key] = ev

    grouped: dict[EvidenceKind, list] = {
        EvidenceKind.H4_WICK: [],
        EvidenceKind.H1_WICK: [],
        EvidenceKind.SR_AREA: [],
    }
    for (kind, _), ev in best.items():
        grouped[kind].append(ev)

    for kind in grouped:
        grouped[kind].sort(
            key=lambda e: (e.weight_hint, e.reaction.displacement_atr), reverse=True
        )
    return grouped


SAME_EVENT_WINDOW = timedelta(hours=4)

# Значимость факта считается «отличной», когда он вдвое перекрывает минимальные
# требования значимости. Дальше рост качества не учитывается: иначе один
# аномальный фитиль перевесил бы весь конфлюенс (ТЗ §49).
QUALITY_SATURATION = 2.0


def _same_event(a, b, atr: float, price_tol_atr: float) -> bool:
    """Описывают ли два доказательства ОДИН И ТОТ ЖЕ исторический факт (ТЗ §25).

    Критерий двойной: почти одна цена И один и тот же временной интервал H4.
    Повторное отвержение той же цены в ДРУГОЕ время событием-дублем не является —
    наоборот, по ТЗ §26 оно ценнее.
    """
    if atr <= 0:
        return False
    close_in_price = abs(a.price - b.price) <= atr * price_tol_atr
    close_in_time = abs(a.ts - b.ts) < SAME_EVENT_WINDOW
    return close_in_price and close_in_time


def _drop_dependent(events: list, references: list, atr: float, price_tol_atr: float) -> list:
    """Убрать доказательства, дублирующие уже учтённый факт."""
    return [
        ev
        for ev in events
        if not any(_same_event(ev, ref, atr, price_tol_atr) for ref in references)
    ]


def score_cluster(cluster: Cluster, atr: float, cfg: Config) -> ScoreBreakdown:
    grouped = _dedup_events(cluster)
    h4 = grouped[EvidenceKind.H4_WICK]
    # H1-фитиль, совпадающий с экстремумом H4 внутри той же H4-свечи, —
    # это тот же самый факт, а не независимое подтверждение (ТЗ §25).
    h1 = _drop_dependent(grouped[EvidenceKind.H1_WICK], h4, atr, price_tol_atr=0.05)
    sr = _drop_dependent(grouped[EvidenceKind.SR_AREA], h4 + h1, atr, price_tol_atr=0.05)

    bd = ScoreBreakdown()
    if not h4:
        return bd

    # Качество факта 0..1: насколько он превосходит минимальные требования.
    # Именно качество, а не количество, различает зоны (ТЗ §49).
    def quality(ev) -> float:
        return min(ev.weight_hint, QUALITY_SATURATION) / QUALITY_SATURATION

    # ── H4: главный источник зоны (ТЗ §17) ───────────────────────────────────
    primary = h4[0]
    bd.h4_primary = round(cfg.cap_h4_primary * quality(primary), 2)

    extra_h4 = h4[1 : 1 + cfg.max_h4_extra]
    if extra_h4:
        share = len(extra_h4) / cfg.max_h4_extra
        avg = sum(quality(e) for e in extra_h4) / len(extra_h4)
        bd.h4_extra = round(cfg.cap_h4_extra * share * avg, 2)

    # ── H1: подтверждение и уточнение (ТЗ §18, §56) ──────────────────────────
    used_h1 = h1[: cfg.max_h1_events]
    if used_h1:
        share = len(used_h1) / cfg.max_h1_events
        avg = sum(quality(e) for e in used_h1) / len(used_h1)
        bd.h1 = round(cfg.cap_h1 * share * avg, 2)

    # ── S/R: независимое подтверждение (ТЗ §21, §57) ─────────────────────────
    used_sr = sr[: cfg.max_sr_areas]
    if used_sr:
        share = len(used_sr) / cfg.max_sr_areas
        # Для S/R качество — это количество касаний области (ТЗ §22).
        avg = sum(min(e.touches, 4) / 4 for e in used_sr) / len(used_sr)
        bd.sr = round(cfg.cap_sr * share * max(avg, 0.5), 2)

    # ── Поведение после реакции (ТЗ §27, §28) ────────────────────────────────
    best_reaction = max((e.reaction.displacement_atr for e in h4 + used_h1), default=0.0)
    if best_reaction >= cfg.reaction_min_atr:
        ratio = min(best_reaction / cfg.reaction_strong_atr, 1.0)
        bd.reaction = round(cfg.w_reaction_max * ratio, 2)
        # Пробой предыдущего экстремума после отвержения — признак силы, но он
        # не должен подменять сам размер импульса.
        if any(e.reaction.broke_local_extreme for e in h4 + used_h1):
            bd.reaction = round(min(bd.reaction * 1.15, cfg.w_reaction_max), 2)

    # ── Повторные независимые отвержения в разное время (ТЗ §26) ─────────────
    distinct_moments = {e.ts for e in h4 + used_h1 + used_sr}
    bd.repeat_rejection = round(
        cfg.w_repeat_rejection * min(max(len(distinct_moments) - 1, 0) / 3.0, 1.0), 2
    )

    # Отчёт показывает УЧТЁННЫЕ подтверждения: именно они дали Score.
    # Сырое количество фитилей в области было бы обманчивым (ТЗ §49, §54).
    bd.h4_events = 1 + len(extra_h4)
    bd.h1_events = len(used_h1)
    bd.sr_areas = len(used_sr)
    # Независимые группы доказательств: H4 / H1 / S/R.
    bd.independent_groups = sum(
        1 for group in (h4, used_h1, used_sr) if group
    )
    return bd


def grade_for(bd: ScoreBreakdown, cfg: Config) -> ZoneGrade:
    """Классификация зоны по Score и структуре подтверждений."""
    total = bd.total

    # ТЗ §29 и §55: один H4-фитиль без подтверждений — только кандидат,
    # даже если его Score формально высок.
    if bd.independent_groups < cfg.min_independent_groups:
        return ZoneGrade.CANDIDATE
    # ТЗ §58: S/R сам по себе Strong-зоной не становится (кластер без H4
    # отфильтрован ещё в clustering, здесь — страховка).
    if bd.h4_events == 0:
        return ZoneGrade.CANDIDATE

    if total >= cfg.score_very_strong:
        return ZoneGrade.VERY_STRONG
    if total >= cfg.score_strong:
        return ZoneGrade.STRONG
    return ZoneGrade.CANDIDATE
