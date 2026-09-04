"""Единый источник версии GZP.

Загрузочный экран, инсталлятор, CI и индикаторы MT4/MT5 берут номера отсюда.
CI подставляет BUILD и COMMIT при сборке релиза (см. .github/workflows/release.yml).
"""

from __future__ import annotations

import os

PRODUCT = "GZP"
PRODUCT_FULL = "GZP — Gold Zone Pro"

# Семантическая версия продукта.
VERSION = "1.0.0"

# Номер релиза: человекочитаемая метка выпуска, растёт монотонно.
RELEASE = "R1"

# Канал поставки: stable | beta | dev
CHANNEL = "stable"

# BUILD/COMMIT переопределяются CI через переменные окружения на этапе сборки.
BUILD = os.environ.get("GZP_BUILD", "local")
COMMIT = os.environ.get("GZP_COMMIT", "0000000")

# Контракт данных между Python-ядром и индикаторами MT4/MT5.
# Индикатор обязан отказаться читать файл с другой мажорной схемой.
SCHEMA = 1


def version_string() -> str:
    return f"{PRODUCT} v{VERSION} {RELEASE}"


def full_version_string() -> str:
    return f"{PRODUCT} v{VERSION} {RELEASE} ({CHANNEL}, build {BUILD}, {COMMIT})"


def version_table() -> list[tuple[str, str]]:
    """Строки таблицы для загрузочного экрана."""
    return [
        ("PRODUCT", PRODUCT_FULL),
        ("VERSION", VERSION),
        ("RELEASE", RELEASE),
        ("CHANNEL", CHANNEL.upper()),
        ("BUILD", BUILD),
        ("COMMIT", COMMIT),
        ("SCHEMA", f"v{SCHEMA}"),
    ]
