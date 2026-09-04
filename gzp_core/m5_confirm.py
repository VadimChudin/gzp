"""Отдельный модуль подтверждения направления на M5 (+опционально H1).

Реализует ТЗ §60-§63, §70(B).

ВАЖНО: это НЕ часть алгоритма поиска зон. M5 подключается только после того,
как зона уже существует и цена пришла в неё. Сам поиск зон о M5 не знает.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .config import Config
from .models import Candle, Zone, ZoneState


class Signal(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class Confirmation:
    zone_id: str
    signal: Signal
    ts: datetime
    m5_close: float
    h1_confirmed: bool = False

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id,
            "signal": self.signal.value,
            "ts": self.ts.isoformat(),
            "m5_close": round(self.m5_close, 2),
            "h1_confirmed": self.h1_confirmed,
        }


class DirectionConfirmer:
    def __init__(self, cfg: Config | None = None, require_h1: bool = False) -> None:
        self.cfg = cfg or Config()
        # ТЗ §63: более строгий сценарий — ждать ещё и закрытие H1 за границей.
        self.require_h1 = require_h1
        self._armed: dict[str, bool] = {}

    def arm(self, zone: Zone) -> None:
        """Включить наблюдение: цена вошла в область (ТЗ §60)."""
        self._armed[zone.id] = True

    def on_m5_close(
        self,
        zone: Zone,
        candle: Candle,
        h1_candle: Candle | None = None,
    ) -> Confirmation | None:
        """Закрытие M5 за границей зоны = закрепление (ТЗ §62).

        Простой прокол фитилём закреплением не считается.
        """
        if zone.state is ZoneState.BROKEN:
            return None
        if not self._armed.get(zone.id):
            # До прихода цены в зону M5 не анализируется (ТЗ §60).
            if candle.low <= zone.upper and candle.high >= zone.lower:
                self.arm(zone)
            else:
                return None

        if candle.close > zone.upper:
            signal = Signal.LONG
        elif candle.close < zone.lower:
            signal = Signal.SHORT
        else:
            return None

        h1_ok = False
        if h1_candle is not None:
            h1_ok = (
                h1_candle.close > zone.upper
                if signal is Signal.LONG
                else h1_candle.close < zone.lower
            )
        if self.require_h1 and not h1_ok:
            return None

        return Confirmation(
            zone_id=zone.id,
            signal=signal,
            ts=candle.ts,
            m5_close=candle.close,
            h1_confirmed=h1_ok,
        )
