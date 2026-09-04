"""Контракт данных между Python-ядром GZP и индикаторами MT4/MT5.

Файл zones_gzp.json кладётся в каталог Files терминала. Индикатор читает его,
проверяет schema и рисует зоны. Никаких торговых указаний в файле нет (ТЗ §59).
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import version
from .models import Zone

FILENAME = "zones_gzp.json"


def build_payload(zones: list[Zone], symbol: str, generated_at: datetime | None = None) -> dict:
    generated_at = generated_at or datetime.now(timezone.utc)
    return {
        "schema": version.SCHEMA,
        "product": version.PRODUCT,
        "version": version.VERSION,
        "release": version.RELEASE,
        "build": version.BUILD,
        "symbol": symbol,
        "generated_at": generated_at.isoformat(),
        "zone_count": len(zones),
        "zones": [z.to_dict() for z in zones],
    }


def write_atomic(payload: dict, directory: str | Path, filename: str = FILENAME) -> Path:
    """Атомарная запись: индикатор не должен прочитать половину файла."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename

    fd, tmp = tempfile.mkstemp(dir=str(directory), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target


def export(zones: list[Zone], symbol: str, directories: list[str | Path]) -> list[Path]:
    """Разложить один и тот же снимок зон во все каталоги терминалов."""
    payload = build_payload(zones, symbol)
    return [write_atomic(payload, d) for d in directories]


def label_for(zone: Zone) -> str:
    """Подпись зоны на графике: только факты, без BUY/SELL (ТЗ §59, §68)."""
    bd = zone.breakdown
    parts = [f"{zone.reference:.2f}"]
    src = []
    if bd.h4_events:
        src.append(f"H4x{bd.h4_events}")
    if bd.h1_events:
        src.append(f"H1x{bd.h1_events}")
    if bd.sr_areas:
        src.append("SR")
    if src:
        parts.append("+".join(src))
    parts.append(f"S:{zone.score:.0f}")
    if zone.grade.value == "very_strong":
        parts.append("VERY STRONG")
    if zone.test_count:
        parts.append(f"T{zone.test_count}")
    return " | ".join(parts)
