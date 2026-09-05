"""Точка входа GZP.exe и инсталлятора.

PyInstaller и Inno Setup запускают этот файл как скрипт: __package__ пустой,
поэтому здесь запрещены relative import (from .xxx). Весь код живёт в пакете
gzp_core и импортируется абсолютно.
"""

from __future__ import annotations

import sys

from gzp_core.app import main


if __name__ == "__main__":
    sys.exit(main())
