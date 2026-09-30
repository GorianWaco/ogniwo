"""Okno ustawień progu i podglądu baterii."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from . import APP_NAME
from .battery import Sample, primary
from .config import Settings
from .idle import SLEEP_MAX_MINUTES, SLEEP_MIN_MINUTES

SnoozeCallback = Callable[[int], None]
SettingsCallback = Callable[[Settings], None]


def _css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_data(
        b"""
        .ogniwo-percent { font-size: 64px; font-weight: 800; }
        .ogniwo-ok { color: #2ea043; }
        .ogniwo-mid { color: #bf8700; }
        .ogniwo-low { color: #da3633; }
        .ogniwo-unknown { color: #8b949e; }
        .ogniwo-low progress { background-color: #da3633; }
        .ogniwo-mid progress { background-color: #bf8700; }
        .ogniwo-ok progress { background-color: #2ea043; }
        """
    )
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


class OgniwoWindow(Adw.ApplicationWindow):
    def __init__(
        self,
        *,
        on_settings: SettingsCallback,
        on_refresh: Callable[[], None],
        on_test: Callable[[], None],
        on_snooze: SnoozeCallback,
        on_quit: Callable[[], None],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.set_title(APP_NAME)
        self.set_default_size(460, 780)
        self._on_settings = on_settings
        self._updating = False
        self._hysteresis = 5
        _css()

        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)
        toolbar = Adw.ToolbarView()
        self.toasts.set_child(toolbar)

        header = Adw.HeaderBar()
        header.set_title_widget(
            Adw.WindowTitle(title=APP_NAME, subtitle="Bateria myszy")
        )
        quit_btn = Gtk.Button(label="Zakończ")
        quit_btn.connect("clicked", lambda *_a: on_quit())
        header.pack_end(quit_btn)
        toolbar.add_top_bar(header)

        self.banner = Adw.Banner()
        self.banner.set_revealed(False)
        toolbar.add_top_bar(self.banner)

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        page.set_margin_top(8)
        page.set_margin_bottom(18)
        page.set_margin_start(12)
        page.set_margin_end(12)

        page.append(self._hero())
        page.append(self._sleep_group())
        page.append(self._notify_group())
        page.append(self._poll_group(on_refresh, on_test))
        page.append(self._snooze_group(on_snooze))
        page.append(self._session_group())

        self.note = Gtk.Label(label="")
        self.note.set_wrap(True)
        self.note.set_xalign(0)
        self.note.add_css_class("dim-label")
        self.note.set_margin_start(6)
        self.note.set_margin_end(6)
        page.append(self.note)

        clamp = Adw.Clamp()
        clamp.set_child(page)
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(clamp)
        scroll.set_propagate_natural_height(True)
        toolbar.set_content(scroll)

    def _hero(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(12)
        self.percent = Gtk.Label(label="—")
        self.percent.add_css_class("ogniwo-percent")
        self.percent.add_css_class("ogniwo-unknown")
        self.percent.set_halign(Gtk.Align.CENTER)
        self.device = Gtk.Label(label="Szukam myszy…")
        self.device.add_css_class("title-3")
        self.device.set_halign(Gtk.Align.CENTER)
        self.device.set_wrap(True)
        self.bar = Gtk.ProgressBar()
        self.bar.set_fraction(0)
        self.bar.set_margin_top(8)
        self.detail = Gtk.Label(label="")
        self.detail.set_wrap(True)
        self.detail.set_justify(Gtk.Justification.CENTER)
        self.detail.add_css_class("dim-label")
        self.extra = Gtk.Label(label="")
        self.extra.set_wrap(True)
        self.extra.add_css_class("dim-label")
        box.append(self.percent)
        box.append(self.device)
        box.append(self.bar)
        box.append(self.detail)
        box.append(self.extra)
        return box

    def _sleep_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(
            title="Oszczędzanie baterii",
            description="Po tym czasie bez ruchu mysz się wyłącza. Ogniwo chowa wtedy poziom i nie budzi jej odczytem.",
        )
        self.sleep_row = Adw.SpinRow.new_with_range(SLEEP_MIN_MINUTES, SLEEP_MAX_MINUTES, 1)
        self.sleep_row.set_title("Wyłącz mysz po")
        self.sleep_row.set_subtitle("Minuty, od 1 do 60. Godzina to maksimum. Poziom wraca przy następnym ruchu.")
        self.sleep_row.connect("notify::value", self._emit_settings)
        group.add(self.sleep_row)
        return group

    def _notify_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(
            title="Powiadomienie o niskiej baterii",
            description="Sam decydujesz, od ilu procent i czy powtarzać.",
        )
        self.notify_row = Adw.SwitchRow()
        self.notify_row.set_title("Pokazuj powiadomienie")
        self.notify_row.set_subtitle("Gdy poziom spadnie do ustawionego progu")
        self.notify_row.connect("notify::active", self._emit_settings)
        group.add(self.notify_row)

        self.threshold_row = Adw.SpinRow.new_with_range(1, 95, 1)
        self.threshold_row.set_title("Próg")
        self.threshold_row.set_subtitle("Powiadomienie przy tej wartości albo niżej")
        self.threshold_row.connect("notify::value", self._emit_settings)
        group.add(self.threshold_row)

        self.repeat_row = Adw.SwitchRow()
        self.repeat_row.set_title("Przypominaj")
        self.repeat_row.set_subtitle("Bez tego jest jedno powiadomienie na zejście poniżej progu")
        self.repeat_row.connect("notify::active", self._emit_settings)
        group.add(self.repeat_row)

        self.repeat_minutes_row = Adw.SpinRow.new_with_range(5, 240, 5)
        self.repeat_minutes_row.set_title("Co ile minut")
        self.repeat_minutes_row.set_subtitle("Dopóki bateria zostaje na progu albo niżej")
        self.repeat_minutes_row.connect("notify::value", self._emit_settings)
        group.add(self.repeat_minutes_row)
        return group

    def _poll_group(self, on_refresh: Callable[[], None], on_test: Callable[[], None]) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(
            title="Odczyt",
            description="Poziom jest sprawdzany tylko wtedy, gdy mysz nie śpi. Minuta to spokojny odstęp.",
        )
        self.poll_row = Adw.SpinRow.new_with_range(15, 600, 15)
        self.poll_row.set_title("Co ile sekund")
        self.poll_row.connect("notify::value", self._emit_settings)
        group.add(self.poll_row)

        box = Gtk.Box(spacing=8, homogeneous=True)
        box.set_margin_top(6)
        refresh = Gtk.Button(label="Sprawdź teraz")
        refresh.connect("clicked", lambda *_a: on_refresh())
        test = Gtk.Button(label="Powiadomienie testowe")
        test.connect("clicked", lambda *_a: on_test())
        box.append(refresh)
        box.append(test)
        group.add(box)
        return group

    def _snooze_group(self, on_snooze: SnoozeCallback) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Wyciszenie")
        box = Gtk.Box(spacing=8, homogeneous=True)
        hour = Gtk.Button(label="Na godzinę")
        hour.connect("clicked", lambda *_a: on_snooze(3600))
        four = Gtk.Button(label="Na 4 godziny")
        four.connect("clicked", lambda *_a: on_snooze(14400))
        clear = Gtk.Button(label="Anuluj")
        clear.connect("clicked", lambda *_a: on_snooze(0))
        box.append(hour)
        box.append(four)
        box.append(clear)
        group.add(box)
        return group

    def _session_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Sesja")
        self.autostart_row = Adw.SwitchRow()
        self.autostart_row.set_title("Uruchamiaj po zalogowaniu")
        self.autostart_row.set_subtitle("Sama ikona w trayu, okno zostaje schowane")
        self.autostart_row.connect("notify::active", self._emit_settings)
        group.add(self.autostart_row)
        return group

    def load_settings(self, settings: Settings) -> None:
        self._updating = True
        try:
            self.notify_row.set_active(settings.notify_enabled)
            self.threshold_row.set_value(settings.threshold_percent)
            self.repeat_row.set_active(settings.repeat_enabled)
            self.repeat_minutes_row.set_value(settings.repeat_minutes)
            self.repeat_minutes_row.set_sensitive(settings.repeat_enabled)
            self.poll_row.set_value(settings.poll_seconds)
            self.sleep_row.set_value(settings.sleep_minutes)
            self.autostart_row.set_active(settings.autostart)
            self._hysteresis = settings.hysteresis_percent
        finally:
            self._updating = False

    def collect(self) -> Settings:
        return Settings(
            poll_seconds=int(self.poll_row.get_value()),
            notify_enabled=self.notify_row.get_active(),
            threshold_percent=int(self.threshold_row.get_value()),
            repeat_enabled=self.repeat_row.get_active(),
            repeat_minutes=int(self.repeat_minutes_row.get_value()),
            hysteresis_percent=getattr(self, "_hysteresis", 5),
            autostart=self.autostart_row.get_active(),
            sleep_minutes=int(self.sleep_row.get_value()),
        )

    def show_samples(self, samples: list[Sample], description: str, *, asleep: bool = False) -> None:
        lead = primary(samples)
        if lead is None:
            self._set_percent(None, 15)
            self.device.set_text("Nie widzę myszy z baterią")
            self.bar.set_fraction(0)
            self.detail.set_text("Podłącz odbiornik Razer. OpenRazer musi widzieć urządzenie.")
            self.extra.set_text("")
            return
        if asleep:
            self._set_percent(None, 15, label="wył.")
            self.device.set_text(f"{lead.mouse.name} · wyłączona")
            self.bar.set_fraction(0)
            self.detail.set_text("Mysz śpi. Poziom baterii jest schowany i wróci, gdy jej użyjesz.")
            self.extra.set_text("")
            return
        threshold = int(self.threshold_row.get_value())
        self._set_percent(lead.percent, threshold)
        title = lead.mouse.name
        if lead.charging is True:
            title += " · ładuje się"
        self.device.set_text(title)
        if lead.percent is None:
            self.bar.set_fraction(0)
        else:
            self.bar.set_fraction(max(0.0, min(1.0, lead.percent / 100)))
        self.detail.set_text(description)

        others = [item for item in samples if item.mouse.key != lead.mouse.key]
        if lead.mouse.charging_known is False and lead.charging is None:
            hint = "Ta mysz nie zgłasza ładowania. Widać sam poziom."
        else:
            hint = ""
        if others:
            bits = []
            for item in others:
                level = "—" if item.percent is None else f"{item.percent}%"
                bits.append(f"{item.mouse.name}: {level}")
            hint = (hint + " " + " · ".join(bits)).strip()
        if lead.error and lead.percent is None:
            hint = (hint + " " + lead.error).strip()
        self.extra.set_text(hint)

    def set_note(self, text: str) -> None:
        self.note.set_text(text)

    def toast(self, text: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=text, timeout=3))

    def show_banner(self, text: str) -> None:
        self.banner.set_title(text)
        self.banner.set_revealed(bool(text))

    def _set_percent(self, percent: int | None, threshold: int, label: str | None = None) -> None:
        for name in ("ogniwo-ok", "ogniwo-mid", "ogniwo-low", "ogniwo-unknown"):
            self.percent.remove_css_class(name)
            self.bar.remove_css_class(name)
        if label is not None:
            self.percent.set_text(label)
            tone = "ogniwo-unknown"
            self.percent.add_css_class(tone)
            self.bar.add_css_class(tone)
            return
        if percent is None:
            self.percent.set_text("—")
            tone = "ogniwo-unknown"
        else:
            self.percent.set_text(f"{percent}%")
            if percent <= threshold:
                tone = "ogniwo-low"
            elif percent < 50:
                tone = "ogniwo-mid"
            else:
                tone = "ogniwo-ok"
        self.percent.add_css_class(tone)
        self.bar.add_css_class(tone)

    def _emit_settings(self, *_args) -> None:
        if self._updating:
            return
        self.repeat_minutes_row.set_sensitive(self.repeat_row.get_active())
        self._on_settings(self.collect())
