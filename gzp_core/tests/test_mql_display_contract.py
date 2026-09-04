"""Контракт отображения: индикаторы MT4/MT5 обязаны корректно прочитать файл.

MQL-код здесь не выполняется, поэтому тест воспроизводит ТУ ЖЕ логику разбора,
что реализована в GZP_Zones.mq4/.mq5 (поиск ключа → двоеточие → значение до
разделителя), и проверяет на реальном payload. Если схема экспорта изменится
несовместимо, тест упадёт раньше, чем это увидит пользователь в терминале.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from gzp_core import exporter, version
from gzp_core.models import Direction, ScoreBreakdown, Zone, ZoneGrade, ZoneState

MQL_DIR = Path(__file__).resolve().parents[2] / "mql"


def _payload() -> str:
    bd = ScoreBreakdown(h4_primary=45, h4_extra=16, h1=22, sr=14, reaction=12,
                        h4_events=2, h1_events=2, sr_areas=1, independent_groups=3)
    zone = Zone(
        id="L4786-202604200800",
        lower=4781.0,
        upper=4791.0,
        reference=4786.0,
        direction=Direction.LOWER,
        created_at=datetime(2026, 4, 20, 8, tzinfo=timezone.utc),
        score=bd.total,
        grade=ZoneGrade.VERY_STRONG,
        state=ZoneState.ACTIVE,
        breakdown=bd,
    )
    return json.dumps(exporter.build_payload([zone], "XAUUSD"), ensure_ascii=False, indent=2)


# ── Эмуляция парсера из MQL ──────────────────────────────────────────────────


def mql_extract_number(text: str, key: str) -> float | None:
    needle = key if key.startswith('"') else f'"{key}"'
    pos = text.find(needle)
    if pos < 0:
        return None
    colon = text.find(":", pos)
    buf = ""
    for ch in text[colon + 1 :]:
        if ch in " \n\r\t":
            if buf:
                break
            continue
        if ch in ",}]":
            break
        buf += ch
    return float(buf) if buf else None


def mql_extract_string(text: str, key: str) -> str:
    pos = text.find(f'"{key}"')
    if pos < 0:
        return ""
    colon = text.find(":", pos)
    first = text.find('"', colon + 1)
    last = text.find('"', first + 1)
    return text[first + 1 : last]


def mql_find_object_end(text: str, start: int) -> int:
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def mql_parse_zones(payload: str) -> list[dict]:
    zones = []
    cursor = payload.find('"zones"')
    assert cursor >= 0
    while True:
        start = payload.find("{", cursor)
        if start < 0:
            break
        end = mql_find_object_end(payload, start)
        if end < 0:
            break
        obj = payload[start : end + 1]
        if '"reference"' in obj:
            zones.append(obj)
        cursor = end + 1
    return zones


# ── Тесты ────────────────────────────────────────────────────────────────────


def test_indicator_parser_reads_every_field():
    payload = _payload()
    assert mql_extract_number(payload, "schema") == version.SCHEMA
    assert mql_extract_string(payload, "version") == version.VERSION
    assert mql_extract_string(payload, "release") == version.RELEASE
    assert mql_extract_string(payload, "symbol") == "XAUUSD"

    objects = mql_parse_zones(payload)
    assert len(objects) == 1

    obj = objects[0]
    assert mql_extract_number(obj, "lower") == 4781.0
    assert mql_extract_number(obj, "upper") == 4791.0
    assert mql_extract_number(obj, "reference") == 4786.0
    assert mql_extract_number(obj, "score") == 109.0
    assert mql_extract_number(obj, "tests") == 0
    assert mql_extract_string(obj, "grade") == "very_strong"
    assert mql_extract_string(obj, "state") == "active"


def test_confirmation_counters_do_not_collide_with_breakdown():
    """"h4" из confirmations не должен путаться с "h4_primary" из breakdown."""
    obj = mql_parse_zones(_payload())[0]
    assert mql_extract_number(obj, '"h4"') == 2
    assert mql_extract_number(obj, '"h1"') == 2
    assert mql_extract_number(obj, '"sr"') == 1


def test_created_at_is_parsable_by_indicator():
    """MQL режет ISO-строку по позициям — формат обязан быть стабильным."""
    obj = mql_parse_zones(_payload())[0]
    iso = mql_extract_string(obj, "created_at")
    assert len(iso) >= 19
    assert iso[4] == "-" and iso[7] == "-" and iso[10] == "T"
    date, clock = iso[:10].replace("-", "."), iso[11:19]
    assert re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", date)
    assert re.fullmatch(r"\d{2}:\d{2}:\d{2}", clock)


def test_both_indicators_exist_and_share_schema():
    mq4 = (MQL_DIR / "MT4" / "Indicators" / "GZP_Zones.mq4").read_text(encoding="utf-8")
    mq5 = (MQL_DIR / "MT5" / "Indicators" / "GZP_Zones.mq5").read_text(encoding="utf-8")
    for src in (mq4, mq5):
        assert f"#define GZP_SCHEMA      {version.SCHEMA}" in src
        assert "zones_gzp.json" in src
        # ТЗ §59: индикатор не рисует торговых сигналов.
        assert "BUY" not in src.upper().replace("BUFFER", "")
        assert '"SELL"' not in src.upper()


def test_mt4_indicator_avoids_mql5_only_api():
    src = (MQL_DIR / "MT4" / "Indicators" / "GZP_Zones.mq4").read_text(encoding="utf-8")
    for forbidden in ("SeriesInfoInteger", "IndicatorSetString", "ObjectsDeleteAll"):
        assert forbidden not in src


def test_mt5_indicator_avoids_mql4_only_api():
    src = (MQL_DIR / "MT5" / "Indicators" / "GZP_Zones.mq5").read_text(encoding="utf-8")
    for forbidden in ("WindowFirstVisibleBar", "StrToDouble", "StrToTime", "IndicatorShortName"):
        assert forbidden not in src
    assert "Time[0]" not in src
