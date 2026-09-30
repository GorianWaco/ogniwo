"""Pętla: odczyt myszy, ikona w trayu, powiadomienie według progu."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib  # noqa: E402

from . import APP_ID, APP_NAME, __version__
from .battery import LevelTracker, Sample, discover, primary, sample_mice
from .config import (
    Settings,
    load_runtime,
    load_settings,
    runtime_path,
    save_runtime,
    save_settings,
    settings_path,
    stored_sleep_minutes,
)
from .idle import (
    IDLE_FILE,
    ActivityWatch,
    clamp_sleep_minutes,
    read_idle_seconds,
    sleep_seconds,
    write_idle_seconds,
)
from .icon_draw import draw_badge, tone_for
from .notify import Notifier
from .openrazer_cfg import silence_openrazer
from .policy import describe, evaluate
from .session import write_autostart
from .tray import Tray
from .window import OgniwoWindow


class OgniwoApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.add_main_option(
            "background",
            ord("b"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            "Uruchom samą ikonę w trayu",
            None,
        )
        self._started = False
        self._quitting = False
        self.settings = Settings()
        self.runtime = load_runtime(runtime_path())
        self.samples: list[Sample] = []
        self._trackers: dict[str, LevelTracker] = {}
        self._poll_id = 0
        self._polling = False
        self._asleep = True
        self._last_battery_read = 0.0
        self._read_gen = 0
        self._pending_battery = False
        self._sleep_write_id = 0
        self._activity = ActivityWatch(on_wake=self._on_wake)
        self._tray: Tray | None = None
        self._notifier = Notifier()
        self._icon_dir = _runtime_dir() / "icons"
        self.window: OgniwoWindow | None = None

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        options = command_line.get_options_dict()
        background = bool(options.contains("background"))
        self._ensure(show=not background)
        return 0

    def do_activate(self) -> None:
        self._ensure(show=True)

    def _ensure(self, *, show: bool) -> None:
        if self._quitting:
            return
        if not self._started:
            self._started = True
            self.hold()
            GLib.set_application_name(APP_NAME)
            first_run = not settings_path().is_file()
            self.settings = load_settings(settings_path())
            save_settings(settings_path(), self.settings)
            self._sync_autostart()
            self.window = OgniwoWindow(
                application=self,
                on_settings=self._on_settings,
                on_refresh=self.check_now,
                on_test=self.test_notify,
                on_snooze=self.snooze,
                on_quit=self.quit_app,
            )
            self.window.connect("close-request", self._hide_window)
            self.window.load_settings(self.settings)
            self._activity.set_idle_seconds(sleep_seconds(self.settings.sleep_minutes))
            self._activity.start()
            self._start_tray()
            self.refresh_now(battery=False)
            self._schedule_poll()
            threading.Thread(target=self._silence_openrazer, name="ogniwo-openrazer", daemon=True).start()
            if stored_sleep_minutes(settings_path()) is None:
                threading.Thread(target=self._adopt_sleep, name="ogniwo-sleep", daemon=True).start()
            if first_run:
                show = True
        if show and self.window is not None:
            self.window.present()

    def _hide_window(self, window: OgniwoWindow) -> bool:
        window.set_visible(False)
        return True

    def _on_settings(self, settings: Settings) -> None:
        previous = self.settings.sleep_minutes
        self.settings = settings.clamped()
        save_settings(settings_path(), self.settings)
        self._activity.set_idle_seconds(sleep_seconds(self.settings.sleep_minutes))
        self._sync_autostart()
        self._schedule_poll()
        if self.settings.sleep_minutes != previous:
            if self._sleep_write_id:
                GLib.source_remove(self._sleep_write_id)
            self._sleep_write_id = GLib.timeout_add(400, self._commit_sleep)
        self._update_view()

    def _commit_sleep(self) -> bool:
        self._sleep_write_id = 0
        minutes = self.settings.sleep_minutes
        threading.Thread(
            target=self._write_sleep,
            args=(minutes,),
            name="ogniwo-sleep",
            daemon=True,
        ).start()
        return False

    def _adopt_sleep(self) -> None:
        minutes = self._read_device_sleep()
        if minutes is None:
            return
        GLib.idle_add(self._apply_adopted_sleep, minutes)

    def _apply_adopted_sleep(self, minutes: int) -> bool:
        if self._quitting or stored_sleep_minutes(settings_path()) is not None:
            return False
        self.settings.sleep_minutes = clamp_sleep_minutes(minutes)
        save_settings(settings_path(), self.settings)
        self._activity.set_idle_seconds(sleep_seconds(self.settings.sleep_minutes))
        if self.window is not None:
            self.window.load_settings(self.settings)
        return False

    def _read_device_sleep(self) -> int | None:
        for mouse in discover():
            seconds = read_idle_seconds(mouse.path / IDLE_FILE)
            if seconds is not None:
                return clamp_sleep_minutes(round(seconds / 60))
        return None

    def _write_sleep(self, minutes: int) -> None:
        seconds = sleep_seconds(minutes)
        wrote = 0
        error = ""
        stored = 0
        for mouse in discover():
            path = mouse.path / IDLE_FILE
            if not path.is_file():
                continue
            try:
                write_idle_seconds(path, seconds)
                wrote += 1
                read_back = read_idle_seconds(path)
                if read_back is not None:
                    stored = read_back
            except OSError as exc:
                error = str(exc)
        GLib.idle_add(self._sleep_written, minutes, wrote, error, stored)

    def _sleep_written(self, minutes: int, wrote: int, error: str, stored: int) -> bool:
        if self.window is None or self._quitting:
            return False
        if wrote and stored and stored + 30 < sleep_seconds(minutes):
            accepted = clamp_sleep_minutes(round(stored / 60))
            self.settings.sleep_minutes = accepted
            save_settings(settings_path(), self.settings)
            self._activity.set_idle_seconds(sleep_seconds(accepted))
            self.window.load_settings(self.settings)
            self.window.toast(
                f"Mysz przyjęła {accepted} min. Sterownik OpenRazer obcina czas do 15 min."
            )
            return False
        if wrote:
            self.window.toast(f"Mysz wyłączy się po {minutes} min bez ruchu")
        elif error:
            self.window.toast(f"Nie zapisano czasu uśpienia: {error}")
        else:
            self.window.toast("Ta mysz nie ma ustawienia czasu uśpienia")
        return False

    def _sync_autostart(self) -> None:
        write_autostart(self.settings.autostart)

    def _schedule_poll(self) -> None:
        if self._poll_id:
            return
        self._poll_id = GLib.timeout_add_seconds(5, self._poll_tick)

    def _poll_tick(self) -> bool:
        """Chowa poziom po uśpieniu. Odczyt idzie tylko, gdy mysz właśnie się rusza."""
        now = time.monotonic()
        limit = sleep_seconds(self.settings.sleep_minutes)
        if self._activity.asleep(limit, now):
            if not self._asleep:
                self._asleep = True
                self._hide_level()
            return True
        self._asleep = False
        last = self._activity.last_activity()
        if last is None:
            return True
        recently_used = now - last < self.settings.poll_seconds
        due = now - self._last_battery_read >= self.settings.poll_seconds
        if recently_used and due:
            self.refresh_now(battery=True)
        return True

    def _hide_level(self) -> None:
        if not self.samples:
            self.refresh_now(battery=False)
            return
        self.samples = [
            Sample(mouse=item.mouse, percent=None, charging=None) for item in self.samples
        ]
        self._update_view()

    def _on_wake(self) -> None:
        GLib.idle_add(self._wake_ui)

    def _wake_ui(self) -> bool:
        if self._quitting:
            return False
        self._asleep = False
        if time.monotonic() - self._last_battery_read >= self.settings.poll_seconds:
            self.refresh_now(battery=True)
        else:
            self._update_view()
        return False

    def check_now(self) -> None:
        self.refresh_now(battery=True, touch=True)

    def refresh_now(self, battery: bool = True, *, touch: bool = False) -> None:
        if touch:
            self._activity.mark()
            self._asleep = False
        if self._polling:
            if battery:
                self._pending_battery = True
            return
        self._polling = True
        self._read_gen += 1
        generation = self._read_gen
        threading.Thread(
            target=self._read_worker,
            args=(battery, generation),
            name="ogniwo-read",
            daemon=True,
        ).start()

    def _read_worker(self, battery: bool, generation: int) -> None:
        try:
            mice = discover()
            self._activity.set_names([mouse.name for mouse in mice] or ["naga"])
            if battery:
                samples = sample_mice(mice, self._trackers)
            else:
                samples = [Sample(mouse=mouse, percent=None, charging=None) for mouse in mice]
            error = ""
        except Exception as exc:
            samples = []
            error = str(exc)
            battery = False
        GLib.idle_add(self._apply_samples, samples, error, battery, generation)

    def _apply_samples(
        self,
        samples: list[Sample],
        error: str,
        battery: bool = True,
        generation: int = 0,
    ) -> bool:
        self._polling = False
        if self._quitting or generation != self._read_gen:
            return False
        self.samples = samples
        if battery:
            self._last_battery_read = time.monotonic()
            self._asleep = False
        pending = self._pending_battery and not battery
        self._pending_battery = False
        if error and self.window is not None:
            self.window.show_banner(error)
        elif self.window is not None:
            self.window.show_banner("")
        if battery:
            self._consider_notifications()
        self._update_view()
        if pending:
            self.refresh_now(battery=True)
        return False

    def _consider_notifications(self) -> None:
        now = time.time()
        policy = self.settings.policy()
        changed = False
        before = self.runtime.copy()
        for sample in self.samples:
            self.runtime, notify = evaluate(
                policy, self.runtime, sample.mouse.key, sample.percent, now
            )
            if notify and sample.percent is not None:
                self._send_low(sample)
                changed = True
        if self.runtime.snooze_until != before.snooze_until or _latches(self.runtime) != _latches(before):
            changed = True
        if changed:
            save_runtime(runtime_path(), self.runtime)

    def _send_low(self, sample: Sample) -> None:
        percent = sample.percent if sample.percent is not None else 0
        icon = self._badge(percent)
        critical = percent <= 10
        self._notifier.send(
            sample.mouse.key,
            "Niski poziom baterii myszy",
            f"{sample.mouse.name}: {percent}%.",
            icon=icon,
            critical=critical,
        )

    def test_notify(self) -> None:
        lead = primary(self.samples)
        if lead is None or lead.percent is None:
            body = "Test Ogniwa. Nie widzę teraz poziomu baterii."
            percent = None
        else:
            body = f"Test. {lead.mouse.name}: {lead.percent}%."
            percent = lead.percent
        icon = self._badge(percent)
        self._notifier.send("test", "Ogniwo", body, icon=icon)
        if self.window is not None:
            self.window.toast("Wysłałem powiadomienie testowe")

    def snooze(self, seconds: int) -> None:
        if seconds <= 0:
            self.runtime.snooze_until = 0.0
            text = "Wyciszenie zdjęte"
        else:
            self.runtime.snooze_until = time.time() + seconds
            hours = seconds / 3600
            text = "Wyciszone na godzinę" if hours <= 1 else "Wyciszone na 4 godziny"
        save_runtime(runtime_path(), self.runtime)
        self._update_view()
        if self.window is not None:
            self.window.toast(text)

    def _update_view(self) -> None:
        lead = primary(self.samples)
        key = lead.mouse.key if lead is not None else ""
        asleep = self._asleep and lead is not None
        percent = None if asleep or lead is None else lead.percent
        text = describe(self.settings.policy(), self.runtime, key, percent, time.time())
        if self.window is not None:
            self.window.show_samples(self.samples, text, asleep=asleep)
        self._update_tray(text, asleep=asleep)

    def _update_tray(self, description: str, *, asleep: bool) -> None:
        if self._tray is None:
            return
        lead = primary(self.samples)
        percent = None if asleep or lead is None else lead.percent
        name = lead.mouse.name if lead is not None else "Brak myszy"
        if asleep:
            tooltip = f"{name} · wyłączona"
        else:
            level = "brak odczytu" if percent is None else f"{percent}%"
            tooltip = f"{name} · {level} · {description}"
        self._tray.send("TOOLTIP " + tooltip.replace("\n", " "))
        self._tray.send(f"ICON {self._badge(percent, asleep=asleep)}")

    def _badge(self, percent: int | None, *, asleep: bool = False) -> Path:
        if asleep:
            path = self._icon_dir / "badge-off.png"
            if not path.is_file():
                draw_badge(None, "unknown", path, text="wył")
            return path
        tone = tone_for(percent, self.settings.threshold_percent)
        label = "na" if percent is None else str(percent)
        path = self._icon_dir / f"badge-{label}-{tone}.png"
        if not path.is_file():
            draw_badge(percent, tone, path)
        return path

    def _start_tray(self) -> None:
        try:
            self._tray = Tray(self._on_tray)
        except (OSError, FileNotFoundError) as exc:
            if self.window is not None:
                self.window.show_banner(f"Tray nie wystartował: {exc}")

    def _on_tray(self, event: str) -> None:
        GLib.idle_add(self._handle_tray, event)

    def _handle_tray(self, event: str) -> bool:
        if event.startswith("READY"):
            return False
        if event == "CLICK" and self.window is not None:
            self.window.present()
        elif event == "REFRESH":
            self.check_now()
        elif event == "QUIT":
            self.quit_app()
        elif event.startswith("SNOOZE "):
            try:
                seconds = int(event.split(None, 1)[1])
            except (IndexError, ValueError):
                seconds = 0
            self.snooze(seconds)
        elif event == "EXITED" and not self._quitting and self.window is not None:
            self.window.show_banner("Ikona w trayu zniknęła. Otwórz Ogniwo ponownie.")
        return False

    def _silence_openrazer(self) -> None:
        result = silence_openrazer()
        GLib.idle_add(self._show_silence, result.message, result.restarted)

    def _show_silence(self, message: str, restarted: bool) -> bool:
        if self.window is not None:
            self.window.set_note(message)
        if restarted:
            GLib.timeout_add_seconds(2, self._refresh_after_restart)
        return False

    def _refresh_after_restart(self) -> bool:
        self.refresh_now()
        return False

    def quit_app(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        if self._poll_id:
            GLib.source_remove(self._poll_id)
            self._poll_id = 0
        if self._sleep_write_id:
            GLib.source_remove(self._sleep_write_id)
            self._sleep_write_id = 0
            self._write_sleep(self.settings.sleep_minutes)
        self._activity.stop()
        if self._tray is not None:
            self._tray.close()
        save_runtime(runtime_path(), self.runtime)
        self.release()
        self.quit()


def _runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR", f"/tmp/ogniwo-{os.getuid()}")
    path = Path(base) / "ogniwo"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _latches(runtime) -> tuple:
    return tuple(
        sorted(
            (key, latch.latched, latch.last_notify_at)
            for key, latch in runtime.devices.items()
        )
    )


def main(argv: list[str] | None = None) -> int:
    app = OgniwoApp()
    return app.run(sys.argv if argv is None else [sys.argv[0], *argv])
