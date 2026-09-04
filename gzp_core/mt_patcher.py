"""Обнаружение и патч терминалов MetaTrader 4/5.

Задача модуля: после установки GZP индикатор должен САМ появиться в терминале
и отображаться на графике — без ручного копирования файлов пользователем.

Что делает патч для каждого найденного терминала:
  1. кладёт GZP_Zones.ex4/.ex5 (и исходник) в MQL4|MQL5/Indicators/GZP;
  2. создаёт каталог MQL4|MQL5/Files/GZP — туда ядро пишет zones_gzp.json;
  3. ставит шаблон GZP.tpl и делает резервную копию default.tpl,
     чтобы индикатор появлялся на новых графиках автоматически.

Все изменения обратимы: unpatch() возвращает default.tpl из резервной копии.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

BACKUP_SUFFIX = ".gzp-backup"
SUBDIR = "GZP"


@dataclass
class Terminal:
    data_dir: Path
    kind: str          # MT4 | MT5

    @property
    def mql_dir(self) -> Path:
        return self.data_dir / ("MQL4" if self.kind == "MT4" else "MQL5")

    @property
    def indicators_dir(self) -> Path:
        return self.mql_dir / "Indicators" / SUBDIR

    @property
    def files_dir(self) -> Path:
        return self.mql_dir / "Files" / SUBDIR

    @property
    def templates_dir(self) -> Path:
        return self.data_dir / "templates"

    def __str__(self) -> str:  # pragma: no cover - для логов
        return f"{self.kind} @ {self.data_dir}"


# ── Поиск терминалов ─────────────────────────────────────────────────────────


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / "MetaQuotes" / "Terminal")
    # Portable-установки рядом с исполняемым файлом терминала.
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        if base:
            roots.append(Path(base))
    override = os.environ.get("GZP_TERMINAL_ROOT")
    if override:
        roots.insert(0, Path(override))
    return [r for r in roots if r.exists()]


def discover_terminals(extra_roots: list[Path] | None = None) -> list[Terminal]:
    """Все терминалы, в которые можно поставить индикатор."""
    found: dict[Path, Terminal] = {}
    roots = list(extra_roots or []) + _candidate_roots()

    for root in roots:
        if not root.exists():
            continue
        # Каталоги данных: <root>/<hash>/MQL4|MQL5
        for depth in ("*", "*/*"):
            for mql in root.glob(f"{depth}/MQL4"):
                data_dir = mql.parent
                if data_dir not in found and _is_terminal_dir(data_dir):
                    found[data_dir] = Terminal(data_dir=data_dir, kind="MT4")
            for mql in root.glob(f"{depth}/MQL5"):
                data_dir = mql.parent
                if data_dir not in found and _is_terminal_dir(data_dir):
                    found[data_dir] = Terminal(data_dir=data_dir, kind="MT5")

    return sorted(found.values(), key=lambda t: (t.kind, str(t.data_dir)))


def _is_terminal_dir(path: Path) -> bool:
    """Отсекаем случайные папки: у терминала есть config или templates."""
    if (path / "config").exists() or (path / "templates").exists():
        return True
    return (path / "MQL4").exists() or (path / "MQL5").exists()


# ── Шаблон графика ───────────────────────────────────────────────────────────


def build_template(kind: str) -> str:
    """Минимальный .tpl с подключённым индикатором GZP.

    Формат templates совместим с MT4 и MT5: секция <indicator> внутри окна.
    """
    name = "GZP\\\\GZP_Zones" if kind == "MT4" else "GZP\\\\GZP_Zones"
    return f"""<chart>
symbol=XAUUSD
period=240
digits=2
shift=1
scale=4
graph=1
grid=0
<window>
height=100
<indicator>
name=Custom Indicator
path=Indicators\\{SUBDIR}\\GZP_Zones
apply=0
show_data=1
scale_inherit=0
period_flags=0
</indicator>
</window>
</chart>
""".replace("{name}", name)


# ── Патч / откат ─────────────────────────────────────────────────────────────


def patch_terminal(
    terminal: Terminal,
    payload_dir: Path,
    set_default_template: bool = True,
) -> dict:
    """Установить индикатор в один терминал. Возвращает отчёт."""
    report: dict[str, object] = {"terminal": str(terminal), "installed": [], "errors": []}

    terminal.indicators_dir.mkdir(parents=True, exist_ok=True)
    terminal.files_dir.mkdir(parents=True, exist_ok=True)
    terminal.templates_dir.mkdir(parents=True, exist_ok=True)

    wanted = (".ex4", ".mq4") if terminal.kind == "MT4" else (".ex5", ".mq5")
    for src in sorted(payload_dir.glob("GZP_Zones.*")):
        if src.suffix.lower() not in wanted:
            continue
        try:
            shutil.copy2(src, terminal.indicators_dir / src.name)
            report["installed"].append(src.name)  # type: ignore[union-attr]
        except OSError as exc:
            report["errors"].append(f"{src.name}: {exc}")  # type: ignore[union-attr]

    tpl = terminal.templates_dir / "GZP.tpl"
    try:
        tpl.write_text(build_template(terminal.kind), encoding="utf-8")
        report["template"] = str(tpl)
    except OSError as exc:
        report["errors"].append(f"template: {exc}")  # type: ignore[union-attr]
        return report

    if set_default_template:
        default = terminal.templates_dir / "default.tpl"
        backup = terminal.templates_dir / f"default.tpl{BACKUP_SUFFIX}"
        try:
            if default.exists() and not backup.exists():
                shutil.copy2(default, backup)
            shutil.copy2(tpl, default)
            report["default_template"] = True
        except OSError as exc:
            report["errors"].append(f"default template: {exc}")  # type: ignore[union-attr]

    return report


def unpatch_terminal(terminal: Terminal) -> dict:
    """Убрать индикатор и вернуть прежний default.tpl."""
    report: dict[str, object] = {"terminal": str(terminal), "removed": []}
    if terminal.indicators_dir.exists():
        shutil.rmtree(terminal.indicators_dir, ignore_errors=True)
        report["removed"].append("indicators")  # type: ignore[union-attr]

    backup = terminal.templates_dir / f"default.tpl{BACKUP_SUFFIX}"
    default = terminal.templates_dir / "default.tpl"
    if backup.exists():
        shutil.copy2(backup, default)
        backup.unlink(missing_ok=True)
        report["restored_default_template"] = True
    (terminal.templates_dir / "GZP.tpl").unlink(missing_ok=True)
    return report


def patch_all(payload_dir: str | Path, set_default_template: bool = True) -> list[dict]:
    payload_dir = Path(payload_dir)
    return [
        patch_terminal(t, payload_dir, set_default_template)
        for t in discover_terminals()
    ]


def export_dirs() -> list[Path]:
    """Куда ядро должно писать zones_gzp.json — Files всех найденных терминалов."""
    dirs = [t.files_dir for t in discover_terminals()]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    return dirs
