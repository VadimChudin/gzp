"""Парольный вход в приложение GZP.

Пароль в исходниках в открытом виде не хранится: сохраняется только
PBKDF2-HMAC-SHA256 хэш с солью. Проверка идёт в постоянное время.
"""

from __future__ import annotations

import binascii
import hashlib
import hmac
import os
from pathlib import Path

ITERATIONS = 240_000
SALT = binascii.unhexlify("9f2c41ab7d0e5386c1b47f2a6e93d5c8")

# PBKDF2-HMAC-SHA256(пароль продукта, SALT, ITERATIONS)
PASSWORD_HASH = "fbb14fc40ca80ed98e05d2b15be73e3ba6d8f25ae909fdd765767408ea33b736"

LOCK_AFTER_ATTEMPTS = 5


def hash_password(password: str, salt: bytes = SALT, iterations: int = ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    ).hex()


def verify(password: str) -> bool:
    """Сравнение в постоянное время — без утечки по времени ответа."""
    expected = _expected_hash()
    return hmac.compare_digest(hash_password(password), expected)


def _expected_hash() -> str:
    """Хэш можно переопределить переменной окружения при пересборке продукта."""
    return os.environ.get("GZP_PASSWORD_HASH", PASSWORD_HASH).strip().lower()


class AttemptGuard:
    """Простая защита от перебора: блокировка после N неудачных попыток."""

    def __init__(self, limit: int = LOCK_AFTER_ATTEMPTS) -> None:
        self.limit = limit
        self.failures = 0

    @property
    def locked(self) -> bool:
        return self.failures >= self.limit

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.failures)

    def check(self, password: str) -> bool:
        if self.locked:
            return False
        if verify(password):
            self.failures = 0
            return True
        self.failures += 1
        return False


def state_dir() -> Path:
    """Каталог для локального состояния приложения."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    path = Path(base) / "GZP"
    path.mkdir(parents=True, exist_ok=True)
    return path
