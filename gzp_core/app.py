"""Точка входа GZP.

Порядок запуска:
  1. загрузочный экран с таблицей версии и релиза (splash);
  2. проверка пароля продукта (unlock);
  3. патч терминалов MT4/MT5 (индикатор появляется в терминале сам);
  4. цикл: пересчёт зон на каждом закрытии H4 → экспорт в терминалы.

CLI:
  python -m gzp_core.app                 полный запуск с GUI
  python -m gzp_core.app --headless      без окон (сервис/CI)
  python -m gzp_core.app --patch-only    только установка индикатора
  python -m gzp_core.app --demo          прогон на синтетике, без терминалов
  python -m gzp_core.app --render-assets отрисовать PNG загрузочного экрана
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from gzp_core import branding, exporter, mt_patcher, splash, version
from gzp_core.auth import AttemptGuard
from gzp_core.config import Config
from gzp_core.data_feed import load_csv, load_mt5, resample, synth_series
from gzp_core.engine import ZoneEngine
from gzp_core.indicators import atr_at
from gzp_core.lifecycle import ZoneLifecycle
from gzp_core.models import Candle

POLL_SECONDS = 60


def resource_root() -> Path:
    """Корень поставки: исходники, GZP.exe или каталог PyInstaller.

    Установщик кладёт индикаторы в {app}\\mql. Замороженный exe ищет их рядом
    с собой и в _MEIPASS — иначе патч терминалов ставит пустую папку.
    """
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass))
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir)
        candidates.append(exe_dir / "_internal")
    candidates.append(Path(__file__).resolve().parent.parent)
    for root in candidates:
        if (root / "mql").exists():
            return root
    return candidates[0]


def mql_payload_dirs() -> list[Path]:
    root = resource_root() / "mql"
    return [root / "MT4" / "Indicators", root / "MT5" / "Indicators"]


# ── Загрузка данных ──────────────────────────────────────────────────────────


def load_history(cfg: Config, data_dir: Path | None) -> tuple[list[Candle], list[Candle], list[Candle]]:
    """H4, H1, M5. Приоритет: MT5 → CSV → синтетика."""
    try:
        h4 = load_mt5(cfg.symbol, "H4", 1500)
        h1 = load_mt5(cfg.symbol, "H1", 3000)
        m5 = load_mt5(cfg.symbol, "M5", 3000)
        if h4 and h1:
            return h4, h1, m5
    except Exception:
        pass

    if data_dir and data_dir.exists():
        def read(tf: str) -> list[Candle]:
            path = data_dir / f"{cfg.symbol}_{tf}.csv"
            return load_csv(path) if path.exists() else []

        h4, h1, m5 = read("H4"), read("H1"), read("M5")
        if h4 and h1:
            return h4, h1, m5

    h1 = synth_series(2400, "H1", seed=11)
    return resample(h1, "H1", "H4"), h1, synth_series(3000, "M5", seed=12)


# ── Основной цикл ────────────────────────────────────────────────────────────


def run_engine_once(
    cfg: Config,
    h4: list[Candle],
    h1: list[Candle],
    m5: list[Candle],
    engine: ZoneEngine,
    lifecycle: ZoneLifecycle,
) -> list:
    """Один цикл: зафиксировать зоны на закрытии H4 и проиграть младший ТФ."""
    if not h4:
        return []
    now = h4[-1].ts
    engine.on_h4_close(h4, h1, now=now)

    atr = atr_at(h4, len(h4) - 1, cfg.atr_period)
    # Жизненный цикл: только уже существующие зоны (ТЗ §60).
    for candle in m5[-500:] if m5 else h4[-50:]:
        if candle.ts <= now:
            lifecycle.observe(engine.zones, candle, atr)
    return engine.active_zones()


def service_loop(cfg: Config, data_dir: Path | None, once: bool = False) -> int:
    engine = ZoneEngine(cfg)
    lifecycle = ZoneLifecycle(cfg)
    export_dirs = mt_patcher.export_dirs() or [Path.cwd() / "output"]

    while True:
        h4, h1, m5 = load_history(cfg, data_dir)
        zones = run_engine_once(cfg, h4, h1, m5, engine, lifecycle)
        paths = exporter.export(zones, cfg.symbol, export_dirs)
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"[{stamp}] zones={len(zones)} → {', '.join(str(p) for p in paths)}")
        if once:
            return 0
        time.sleep(POLL_SECONDS)


# ── Сервисные команды ────────────────────────────────────────────────────────


def do_patch(payload_dir: Path) -> int:
    reports = mt_patcher.patch_all(payload_dir)
    if not reports:
        print("No MetaTrader terminals found. Start MT4/MT5 once, then re-run.")
        return 1
    for r in reports:
        print(f"• {r['terminal']}")
        print(f"  installed: {', '.join(r.get('installed') or []) or '—'}")
        if r.get("default_template"):
            print("  chart template: GZP set as default")
        for err in r.get("errors") or []:
            print(f"  error: {err}")
    return 0


def render_assets(out_dir: Path) -> int:
    """Эталонные кадры загрузочного экрана — используются в README и CI."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = version.version_table()
    for name, t, progress, status in (
        ("splash_start", 0.35, 0.08, "INITIALISING"),
        ("splash_mid", 1.35, 0.62, "LOADING ZONE ENGINE"),
        ("splash_ready", 2.40, 1.00, "READY"),
    ):
        branding.render_splash_frame(rows, progress, status, t).save(out_dir / f"{name}.png")
    branding.render_unlock_frame(
        f"v{version.VERSION} · {version.RELEASE} · {version.CHANNEL.upper()}", 9, 0.2
    ).save(out_dir / "unlock.png")
    print(f"assets written to {out_dir}")
    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gzp", description=version.full_version_string())
    parser.add_argument("--headless", action="store_true", help="без графических окон")
    parser.add_argument("--patch-only", action="store_true", help="только патч терминалов")
    parser.add_argument("--unpatch", action="store_true", help="удалить индикатор из терминалов")
    parser.add_argument("--demo", action="store_true", help="один прогон без терминалов")
    parser.add_argument("--once", action="store_true", help="один цикл и выход")
    parser.add_argument("--render-assets", metavar="DIR", help="отрисовать PNG экранов")
    parser.add_argument("--data-dir", metavar="DIR", help="каталог CSV с историей")
    parser.add_argument("--version", action="store_true", help="показать версию")
    args = parser.parse_args(argv)

    if args.version:
        print(version.full_version_string())
        return 0

    if args.render_assets:
        return render_assets(Path(args.render_assets))

    if args.unpatch:
        terminals = mt_patcher.discover_terminals()
        for t in terminals:
            report = mt_patcher.unpatch_terminal(t)
            print(f"• {report['terminal']}: откат выполнен")
        return 0

    if args.patch_only:
        code = 0
        found = False
        for c in mql_payload_dirs():
            if c.exists():
                found = True
                code |= do_patch(c)
        if not found:
            print(f"MQL payload not found next to {resource_root()}")
            return 1
        return code

    cfg = Config.from_env()
    data_dir = Path(args.data_dir) if args.data_dir else Path(__file__).resolve().parent / "data"

    use_gui = not args.headless and splash.gui_available()

    if use_gui:
        def work(sp: splash.Splash) -> None:
            sp.set_stage(0.18, "Checking environment")
            sp.root.update()
            sp.set_stage(0.45, "Loading market history")
            sp.root.update()
            sp.set_stage(0.78, "Building zone engine")
            sp.root.update()
            sp.set_stage(1.0, "Ready")

        splash.Splash(duration=3.2).run(work)
        if not splash.UnlockDialog(AttemptGuard()).run():
            print("Access denied.")
            return 2
    else:
        splash.console_splash(
            [(0.2, "Checking environment"), (0.6, "Loading market history"), (1.0, "Ready")]
        )
        if not splash.console_unlock(AttemptGuard()):
            print("Access denied.")
            return 2

    if args.demo:
        return service_loop(cfg, data_dir, once=True)

    for c in mql_payload_dirs():
        if c.exists():
            do_patch(c)

    return service_loop(cfg, data_dir, once=args.once)


if __name__ == "__main__":
    sys.exit(main())
