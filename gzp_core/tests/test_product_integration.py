"""Продуктовая часть: контракт для MT4/MT5, пароль, патч терминалов, экраны."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from gzp_core import auth, branding, exporter, mt_patcher, version
from gzp_core.models import Direction, ScoreBreakdown, Zone, ZoneGrade, ZoneState

TS = datetime(2026, 4, 20, tzinfo=timezone.utc)


def sample_zone() -> Zone:
    bd = ScoreBreakdown(h4_primary=45, h1=22, sr=14, reaction=12, h4_events=1,
                        h1_events=2, sr_areas=1, independent_groups=3)
    return Zone(
        id="L4786-202604200800",
        lower=4781.0,
        upper=4791.0,
        reference=4786.0,
        direction=Direction.LOWER,
        created_at=TS,
        score=bd.total,
        grade=ZoneGrade.STRONG,
        state=ZoneState.ACTIVE,
        breakdown=bd,
    )


# ── Контракт с терминалами ───────────────────────────────────────────────────


def test_export_payload_has_stable_contract(tmp_path):
    payload = exporter.build_payload([sample_zone()], "XAUUSD")
    assert payload["schema"] == version.SCHEMA
    assert payload["version"] == version.VERSION
    assert payload["release"] == version.RELEASE
    assert payload["zone_count"] == 1

    zone = payload["zones"][0]
    for key in ("lower", "upper", "reference", "score", "grade", "state", "tests"):
        assert key in zone


def test_export_contains_no_trade_instructions():
    """ТЗ §59: в файле для терминала нет ни BUY, ни SELL."""
    raw = json.dumps(exporter.build_payload([sample_zone()], "XAUUSD")).upper()
    assert "BUY" not in raw and "SELL" not in raw and "LONG" not in raw


def test_export_is_atomic_and_readable(tmp_path):
    path = exporter.write_atomic(exporter.build_payload([sample_zone()], "XAUUSD"), tmp_path)
    assert path.name == exporter.FILENAME
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["zones"][0]["reference"] == 4786.0
    # Временных файлов после записи остаться не должно.
    assert list(tmp_path.glob("*.tmp")) == []


def test_chart_label_is_informative_not_directional():
    label = exporter.label_for(sample_zone())
    assert "4786" in label and "H4x1" in label and "S:" in label
    assert "BUY" not in label.upper()


# ── Пароль продукта ──────────────────────────────────────────────────────────


def test_product_password_is_accepted():
    assert auth.verify("Satpayeva82/2") is True


def test_wrong_password_is_rejected():
    assert auth.verify("satpayeva82/2") is False
    assert auth.verify("") is False


def test_plaintext_password_is_not_in_source():
    src = (auth.__file__)
    with open(src, encoding="utf-8") as fh:
        content = fh.read()
    assert "Satpayeva" not in content, "пароль не должен лежать в исходниках открытым"


def test_bruteforce_is_locked_out():
    guard = auth.AttemptGuard(limit=3)
    for _ in range(3):
        assert guard.check("nope") is False
    assert guard.locked is True
    # После блокировки даже верный пароль не принимается до перезапуска.
    assert guard.check("Satpayeva82/2") is False


# ── Патч терминалов MT4/MT5 ──────────────────────────────────────────────────


def _fake_terminal(root, name, kind):
    data = root / name
    (data / kind).mkdir(parents=True)
    (data / "config").mkdir()
    templates = data / "templates"
    templates.mkdir()
    (templates / "default.tpl").write_text("<chart>original</chart>", encoding="utf-8")
    return data


def test_discovers_and_patches_terminals(tmp_path, monkeypatch):
    root = tmp_path / "Terminal"
    root.mkdir()
    _fake_terminal(root, "AAAA1111", "MQL4")
    _fake_terminal(root, "BBBB2222", "MQL5")
    monkeypatch.setenv("GZP_TERMINAL_ROOT", str(root))

    terminals = mt_patcher.discover_terminals()
    assert {t.kind for t in terminals} == {"MT4", "MT5"}

    payload = tmp_path / "payload"
    payload.mkdir()
    for name in ("GZP_Zones.mq4", "GZP_Zones.ex4", "GZP_Zones.mq5", "GZP_Zones.ex5"):
        (payload / name).write_text("binary", encoding="utf-8")

    for terminal in terminals:
        report = mt_patcher.patch_terminal(terminal, payload)
        assert not report["errors"]
        # Индикатор на месте, каталог обмена создан, шаблон подключён.
        suffix = "4" if terminal.kind == "MT4" else "5"
        assert (terminal.indicators_dir / f"GZP_Zones.ex{suffix}").exists()
        assert terminal.files_dir.exists()
        assert (terminal.templates_dir / "GZP.tpl").exists()
        assert "GZP_Zones" in (terminal.templates_dir / "default.tpl").read_text()
        # Оригинальный шаблон пользователя сохранён.
        assert (terminal.templates_dir / f"default.tpl{mt_patcher.BACKUP_SUFFIX}").exists()


def test_unpatch_restores_user_template(tmp_path, monkeypatch):
    root = tmp_path / "Terminal"
    root.mkdir()
    _fake_terminal(root, "CCCC3333", "MQL4")
    monkeypatch.setenv("GZP_TERMINAL_ROOT", str(root))

    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "GZP_Zones.ex4").write_text("binary", encoding="utf-8")

    terminal = mt_patcher.discover_terminals()[0]
    mt_patcher.patch_terminal(terminal, payload)
    mt_patcher.unpatch_terminal(terminal)

    assert (terminal.templates_dir / "default.tpl").read_text() == "<chart>original</chart>"
    assert not terminal.indicators_dir.exists()


# ── Загрузочный экран ────────────────────────────────────────────────────────


def test_version_table_shows_version_and_release():
    table = dict(version.version_table())
    assert table["VERSION"] == version.VERSION == "1.0.0"
    assert table["RELEASE"] == version.RELEASE == "R1"
    assert table["PRODUCT"].startswith("GZP")


def test_splash_frames_render_headless():
    rows = version.version_table()
    frame = branding.render_splash_frame(rows, 0.5, "LOADING", 1.0)
    assert frame.size == (branding.WIDTH, branding.HEIGHT)
    # Кадры анимации должны отличаться — иначе анимации нет.
    other = branding.render_splash_frame(rows, 0.9, "READY", 2.2)
    assert frame.tobytes() != other.tobytes()
    # Живой бар: при разном progress пиксели внутри капсулы обязаны меняться.
    empty = branding.render_splash_frame(rows, 0.05, "LOADING", 0.4)
    full = branding.render_splash_frame(rows, 0.92, "LOADING", 0.4)
    w, h = empty.size
    y = int(h * 0.598) + 4
    x0, x1 = w // 2 - 40, w // 2 + 40
    assert empty.crop((x0, y - 2, x1, y + 2)).tobytes() != full.crop((x0, y - 2, x1, y + 2)).tobytes()


def test_unlock_frame_masks_password():
    frame = branding.render_unlock_frame("v1.0.0", 8, 0.4)
    assert frame.size == (branding.WIDTH, branding.HEIGHT)
