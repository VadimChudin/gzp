"""Источники свечей: MetaTrader 5, CSV, синтетика для тестов.

Порядок выбора в рантайме: MT5 (если доступен) → CSV → ошибка.
Синтетика используется только в тестах и демо-режиме.
"""

from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Candle

TF_MINUTES = {"M5": 5, "M15": 15, "H1": 60, "H4": 240, "D1": 1440}


# ── CSV ──────────────────────────────────────────────────────────────────────


def _detect_encoding(path: Path) -> str:
    head = path.read_bytes()[:4]
    if head[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"
    return "utf-8-sig"


def load_csv(path: str | Path) -> list[Candle]:
    """CSV из MetaTrader (tab/comma, с заголовком или без)."""
    path = Path(path)
    text = path.read_text(encoding=_detect_encoding(path), errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []

    delim = "\t" if "\t" in lines[0] else (";" if ";" in lines[0] else ",")
    rows = list(csv.reader(lines, delimiter=delim))

    header = rows[0]
    has_header = not _looks_numeric(header[-1] if header else "")
    if has_header:
        rows = rows[1:]

    candles: list[Candle] = []
    for row in rows:
        row = [c.strip() for c in row if c.strip() != ""]
        if len(row) < 5:
            continue
        try:
            ts = _parse_ts(row)
            offset = 2 if _is_split_datetime(row) else 1
            o, h, l, c = (float(row[offset + i]) for i in range(4))
            v = float(row[offset + 4]) if len(row) > offset + 4 else 0.0
        except (ValueError, IndexError):
            continue
        candles.append(Candle(ts=ts, open=o, high=h, low=l, close=c, volume=v))

    candles.sort(key=lambda c: c.ts)
    return candles


def _looks_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def _is_split_datetime(row: list[str]) -> bool:
    return len(row) > 1 and ":" in row[1] and "." not in row[1][:3]


def _parse_ts(row: list[str]) -> datetime:
    raw = f"{row[0]} {row[1]}" if _is_split_datetime(row) else row[0]
    raw = raw.replace("/", ".").replace("T", " ").strip()
    for fmt in (
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%Y.%m.%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"unrecognised timestamp: {raw!r}")


# ── MetaTrader 5 ─────────────────────────────────────────────────────────────


def load_mt5(symbol: str, timeframe: str, bars: int = 2000) -> list[Candle]:
    """Свечи напрямую из терминала MT5 (только Windows с установленным MT5)."""
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError as exc:  # pragma: no cover - зависит от платформы
        raise RuntimeError("MetaTrader5 package is not available") from exc

    tf_map = {
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        rates = mt5.copy_rates_from_pos(symbol, tf_map[timeframe], 0, bars)
    finally:
        mt5.shutdown()

    if rates is None:
        raise RuntimeError(f"no rates for {symbol} {timeframe}")

    out = []
    for r in rates:
        out.append(
            Candle(
                ts=datetime.fromtimestamp(int(r["time"]), tz=timezone.utc),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=float(r["tick_volume"]),
            )
        )
    # Последняя свеча может быть незакрытой — алгоритм работает только с
    # закрытыми свечами (ТЗ §3).
    return out[:-1] if len(out) > 1 else out


# ── Синтетика для тестов и демо ──────────────────────────────────────────────


def synth_series(
    bars: int,
    timeframe: str = "H4",
    start_price: float = 4700.0,
    seed: int = 7,
    start: datetime | None = None,
) -> list[Candle]:
    """Псевдослучайный XAUUSD-подобный ряд с воспроизводимым seed."""
    rnd = random.Random(seed)
    step = timedelta(minutes=TF_MINUTES[timeframe])
    ts = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = start_price
    out: list[Candle] = []

    for i in range(bars):
        drift = math.sin(i / 18.0) * 1.2
        o = price
        c = o + drift + rnd.uniform(-4.0, 4.0)
        h = max(o, c) + abs(rnd.gauss(0, 2.0))
        l = min(o, c) - abs(rnd.gauss(0, 2.0))
        out.append(
            Candle(ts=ts, open=o, high=h, low=l, close=c, volume=rnd.uniform(500, 2500))
        )
        price = c
        ts += step
    return out


def resample(candles: list[Candle], src_tf: str, dst_tf: str) -> list[Candle]:
    """Агрегация младшего ТФ в старший (нужно для тестов H1 → H4)."""
    factor = TF_MINUTES[dst_tf] // TF_MINUTES[src_tf]
    if factor <= 1:
        return list(candles)

    out: list[Candle] = []
    for i in range(0, len(candles) - factor + 1, factor):
        chunk = candles[i : i + factor]
        out.append(
            Candle(
                ts=chunk[-1].ts,
                open=chunk[0].open,
                high=max(c.high for c in chunk),
                low=min(c.low for c in chunk),
                close=chunk[-1].close,
                volume=sum(c.volume for c in chunk),
            )
        )
    return out
