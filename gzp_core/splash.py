"""Окно загрузочного экрана GZP и экран ввода пароля.

Кадры рисует branding.py (Pillow), Tk используется только как поверхность
вывода. Такой разрез даёт премиальную картинку без тяжёлых GUI-зависимостей
и позволяет тестировать визуал headless.

Сценарий запуска продукта:
    splash (анимация + таблица версии) → unlock (пароль) → основное приложение

Если графическая среда недоступна (сервер, CI), классы деградируют в
консольный режим и приложение продолжает работать.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from . import branding, version
from .auth import AttemptGuard

FPS = 30
FRAME_MS = int(1000 / FPS)


def gui_available() -> bool:
    try:
        import tkinter  # noqa: F401
    except Exception:
        return False
    try:
        import tkinter as tk

        root = tk.Tk()
        root.destroy()
        return True
    except Exception:
        return False


class _Window:
    """Общая основа: borderless окно по центру с одним Canvas."""

    def __init__(self, title: str) -> None:
        import tkinter as tk
        from PIL import ImageTk

        self._tk = tk
        self._ImageTk = ImageTk
        self.root = tk.Tk()
        self.root.title(title)
        self.root.overrideredirect(True)
        self.root.configure(bg="#08090b")

        w, h = branding.WIDTH, branding.HEIGHT
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        try:
            self.root.attributes("-alpha", 0.0)  # плавное появление
        except Exception:
            pass

        self.canvas = tk.Canvas(
            self.root, width=w, height=h, highlightthickness=0, bd=0, bg="#08090b"
        )
        self.canvas.pack()
        self._image_id = None
        self._photo = None
        self.t0 = time.monotonic()

    def show_frame(self, image) -> None:
        self._photo = self._ImageTk.PhotoImage(image)
        if self._image_id is None:
            self._image_id = self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            self.canvas.itemconfig(self._image_id, image=self._photo)

    def fade_in(self, elapsed: float, duration: float = 0.45) -> None:
        try:
            self.root.attributes("-alpha", min(1.0, elapsed / duration))
        except Exception:
            pass

    def close(self) -> None:
        try:
            self.root.destroy()
        except Exception:
            pass


class Splash(_Window):
    """Анимированный загрузочный экран с таблицей версии и релиза."""

    def __init__(self, duration: float = 3.6) -> None:
        super().__init__(version.version_string())
        self.duration = duration
        self.progress = 0.0
        self._shown = 0.0
        self.status = "LOADING"
        self._done = False

    def set_stage(self, progress: float, status: str) -> None:
        self.progress = max(0.0, min(1.0, progress))
        self.status = status.upper()

    def run(self, work: Optional[Callable[["Splash"], None]] = None) -> None:
        """Показать анимацию. work выполняется поэтапно через after()."""
        rows = version.version_table()

        def tick() -> None:
            elapsed = time.monotonic() - self.t0
            self.fade_in(elapsed)
            # Бар едет к целевому прогрессу, а не прыгает — как на референсе.
            gap = self.progress - self._shown
            self._shown += gap * 0.14
            if abs(gap) < 0.002:
                self._shown = self.progress
            frame = branding.render_splash_frame(rows, self._shown, self.status, elapsed)
            self.show_frame(frame)
            if elapsed >= self.duration and self._done and self._shown >= 0.995:
                self.root.quit()
                return
            self.root.after(FRAME_MS, tick)

        def run_work() -> None:
            if work is not None:
                try:
                    work(self)
                except Exception as exc:  # pragma: no cover - показываем в UI
                    self.set_stage(1.0, f"ERROR: {exc}")
            else:
                self.set_stage(1.0, "READY")
            self._done = True

        self.root.after(FRAME_MS, tick)
        self.root.after(220, run_work)
        self.root.mainloop()
        self.close()



def sanitize_paste(text: str) -> str:
    """Оставляет только печатные символы пароля; убирает перевод строки из буфера."""
    if not text:
        return ""
    # Пароль — одна строка: берём первую непустую строку, если скопировали с Enter.
    first = text.replace("\r\n", "\n").replace("\r", "\n").split("\n", 1)[0]
    return "".join(ch for ch in first if ch.isprintable())


class UnlockDialog(_Window):
    """Экран ввода пароля продукта."""

    def __init__(self, guard: AttemptGuard | None = None) -> None:
        super().__init__(f"{version.PRODUCT} — Secure Access")
        self.guard = guard or AttemptGuard()
        self.password = ""
        self.error: str | None = None
        self.granted = False

        self.root.bind("<Key>", self._on_key)
        self.root.bind("<Return>", lambda _e: self._submit())
        self.root.bind("<BackSpace>", lambda _e: self._backspace())
        self.root.bind("<Escape>", lambda _e: self._cancel())
        self.root.bind("<Control-v>", self._paste)
        self.root.bind("<Control-V>", self._paste)
        self.root.bind("<Command-v>", self._paste)
        self.root.bind("<Shift-Insert>", self._paste)
        self.root.bind("<<Paste>>", self._paste)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Button-3>", self._paste)
        self.canvas.bind("<Control-Button-1>", self._paste)

    # ── Ввод ─────────────────────────────────────────────────────────────────

    def _on_key(self, event) -> None:
        if event.keysym in ("Return", "BackSpace", "Escape", "Tab"):
            return
        # Ctrl / Command / Alt — не печатаем символ (иначе Ctrl+V добавит «v»).
        state = int(getattr(event, "state", 0) or 0)
        if state & 0x4 or state & 0x8:
            return
        if event.char and event.char.isprintable():
            self.password += event.char
            self.error = None

    def _backspace(self) -> None:
        self.password = self.password[:-1]
        self.error = None

    def _paste(self, _event=None) -> str:
        """Вставка из буфера обмена в поле пароля (Ctrl+V / Cmd+V / Shift+Insert / ПКМ)."""
        try:
            clip = self.root.clipboard_get()
        except Exception:
            return "break"
        cleaned = sanitize_paste(clip)
        if cleaned:
            self.password += cleaned
            self.error = None
        return "break"

    def _on_click(self, event) -> None:
        # Клик по кнопке UNLOCK.
        if event.y > branding.HEIGHT * 0.55 and event.y < branding.HEIGHT * 0.70:
            self._submit()

    def _submit(self) -> None:
        if self.guard.locked:
            self.error = "LOCKED — RESTART REQUIRED"
            return
        if self.guard.check(self.password):
            self.granted = True
            self.root.quit()
        else:
            self.password = ""
            if self.guard.locked:
                self.error = "TOO MANY ATTEMPTS — LOCKED"
            else:
                self.error = f"INVALID PASSWORD — {self.guard.remaining} ATTEMPTS LEFT"

    def _cancel(self) -> None:
        self.granted = False
        self.root.quit()

    # ── Цикл ─────────────────────────────────────────────────────────────────

    def run(self) -> bool:
        footer = f"v{version.VERSION} · {version.RELEASE} · {version.CHANNEL.upper()}"

        def tick() -> None:
            elapsed = time.monotonic() - self.t0
            self.fade_in(elapsed)
            frame = branding.render_unlock_frame(
                footer, len(self.password), elapsed, error=self.error
            )
            self.show_frame(frame)
            self.root.after(FRAME_MS, tick)

        self.root.after(FRAME_MS, tick)
        self.root.mainloop()
        self.close()
        return self.granted


# ── Консольный запас ─────────────────────────────────────────────────────────


def console_splash(stages: list[tuple[float, str]]) -> None:
    print(branding_banner())
    for progress, status in stages:
        bar_len = 34
        filled = int(bar_len * progress)
        bar = "█" * filled + "·" * (bar_len - filled)
        print(f"  [{bar}] {int(progress * 100):3d}%  {status}")


def branding_banner() -> str:
    lines = [
        "",
        "   ██████  ███████ ██████",
        "  ██       ██      ██   ██",
        "  ██   ███  ███    ██████",
        "  ██    ██     ██  ██",
        "   ██████  ███████ ██",
        "",
    ]
    for label, value in version.version_table():
        lines.append(f"  {label:<9} {value}")
    lines.append("")
    return "\n".join(lines)


def console_unlock(guard: AttemptGuard | None = None) -> bool:
    import getpass

    guard = guard or AttemptGuard()
    while not guard.locked:
        try:
            pwd = getpass.getpass("  GZP password: ")
        except (EOFError, KeyboardInterrupt):
            return False
        if guard.check(pwd):
            return True
        print(f"  Invalid password. Attempts left: {guard.remaining}")
    return False
