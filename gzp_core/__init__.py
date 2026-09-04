"""GZP — Gold Zone Pro: поиск сильных ценовых зон по конфлюенсу H4/H1/S-R.

Публичный API пакета намеренно узкий: движок, жизненный цикл, экспорт.
"""

from .config import Config
from .engine import ZoneEngine
from .lifecycle import ZoneLifecycle
from .m5_confirm import DirectionConfirmer
from .models import Candle, Zone, ZoneGrade, ZoneState
from .runner import walk_forward
from .version import RELEASE, VERSION, version_string

__all__ = [
    "Config",
    "ZoneEngine",
    "ZoneLifecycle",
    "DirectionConfirmer",
    "Candle",
    "Zone",
    "ZoneGrade",
    "ZoneState",
    "walk_forward",
    "VERSION",
    "RELEASE",
    "version_string",
]

__version__ = VERSION
