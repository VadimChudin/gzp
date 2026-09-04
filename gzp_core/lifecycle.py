"""Поведение цены относительно УЖЕ существующей зоны.

Реализует ТЗ §40-§44, §61, §64-§66.

Этот модуль никогда не создаёт и не изменяет границы зоны — он только
фиксирует, что цена сделала. Разделение обязательно по ТЗ §70.
"""

from __future__ import annotations

from .config import Config
from .models import Candle, Direction, Zone, ZoneState, ZoneTest


class ZoneLifecycle:
    def __init__(self, cfg: Config | None = None) -> None:
        self.cfg = cfg or Config()

    def observe(self, zones: list[Zone], candle: Candle, atr: float) -> list[ZoneTest]:
        """Прогнать одну закрытую свечу (M5/H1) через все живые зоны."""
        events: list[ZoneTest] = []
        for zone in zones:
            if zone.state is ZoneState.BROKEN:
                continue
            test = self._observe_zone(zone, candle, atr)
            if test is not None:
                events.append(test)
        return events

    # ── Внутреннее ───────────────────────────────────────────────────────────

    def _observe_zone(self, zone: Zone, candle: Candle, atr: float) -> ZoneTest | None:
        if atr <= 0:
            return None

        proximity = atr * self.cfg.test_proximity_atr
        touched = (candle.low - proximity) <= zone.upper and (
            candle.high + proximity
        ) >= zone.lower

        buffer = atr * self.cfg.break_close_atr
        closed_above = candle.close > zone.upper + buffer
        closed_below = candle.close < zone.lower - buffer

        # ТЗ §65: зона теряет силу, только если цена закрепилась за
        # ПРОТИВОПОЛОЖНОЙ границей. Для нижней области (историческое отвержение
        # снизу) это закрытие ниже зоны; закрытие выше — обычное положение цены
        # над областью и пробоем не является.
        if zone.direction is Direction.LOWER:
            closed_beyond = closed_below
        else:
            closed_beyond = closed_above

        # Цена может уйти от зоны решительно и больше её не касаться. По ТЗ §65
        # именно такое поведение («прошла и продолжила движение без реакции»)
        # обязано добить зону, поэтому уже начатый пробой продолжаем считать
        # и тогда, когда свеча далеко от границ.
        continuing_break = closed_beyond and (
            zone.tests or zone.consecutive_closes_beyond > 0
        )
        if not touched and not continuing_break:
            return None

        entered = candle.low <= zone.upper and candle.high >= zone.lower
        penetration = self._penetration(zone, candle) / atr

        # ТЗ §43: прокол фитилём и настоящий пробой — разные события.
        pierced = (
            (candle.low < zone.lower or candle.high > zone.upper) and not closed_beyond
        )

        reaction_atr = self._reaction_strength(zone, candle) / atr

        test = ZoneTest(
            ts=candle.ts,
            entered=entered,
            penetration_atr=round(penetration, 4),
            pierced=pierced,
            closed_beyond=closed_beyond,
            reaction_atr=round(reaction_atr, 4),
        )

        # ТЗ §41: тест фиксируется, когда цена реально пришла в зону.
        if entered or pierced:
            zone.tests.append(test)
            if zone.state is ZoneState.ACTIVE:
                zone.state = ZoneState.TESTED

        # ТЗ §44, §65: пробой подтверждается закрытием, и одного закрытия мало.
        if closed_beyond:
            side = "above" if closed_above else "below"
            if zone.last_break_side == side:
                zone.consecutive_closes_beyond += 1
            else:
                zone.last_break_side = side
                zone.consecutive_closes_beyond = 1

            if zone.consecutive_closes_beyond >= self.cfg.break_closes_required:
                zone.state = ZoneState.BROKEN
                zone.broken_at = candle.ts
                # ТЗ §66: автоматический разворот роли зоны в v1 НЕ делаем —
                # только фиксируем факт пробоя.
        else:
            # ТЗ §65: единичный фитиль за зоной её не уничтожает.
            zone.consecutive_closes_beyond = 0
            zone.last_break_side = None

        return test

    @staticmethod
    def _penetration(zone: Zone, candle: Candle) -> float:
        """Насколько глубоко цена зашла в зону (ТЗ §42)."""
        if zone.direction is Direction.LOWER:
            depth = zone.upper - candle.low
        else:
            depth = candle.high - zone.lower
        return max(0.0, min(depth, zone.width))

    @staticmethod
    def _reaction_strength(zone: Zone, candle: Candle) -> float:
        """Насколько цена ушла обратно от зоны внутри свечи (ТЗ §42)."""
        if zone.direction is Direction.LOWER:
            return max(0.0, candle.close - zone.upper)
        return max(0.0, zone.lower - candle.close)
