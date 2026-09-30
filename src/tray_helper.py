#!/usr/bin/env python3
"""Ikona XEmbed dla Tray Icons Reloaded. GTK3, osobny proces od okna GTK4."""

from __future__ import annotations

import os
import sys
import threading
import warnings

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

warnings.filterwarnings("ignore", category=DeprecationWarning)


def main() -> int:
    os.environ.setdefault("GDK_BACKEND", "x11")
    icon = Gtk.StatusIcon.new_from_icon_name("battery-good-symbolic")
    icon.set_title("Ogniwo")
    icon.set_tooltip_text("Ogniwo")
    icon.set_visible(True)
    state = {"icon": "", "alive": True}

    def emit(msg: str) -> None:
        try:
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()
        except BrokenPipeError:
            GLib.idle_add(Gtk.main_quit)

    def apply_tooltip(text: str) -> bool:
        icon.set_tooltip_text(text)
        return False

    def apply_icon(name: str) -> bool:
        name = name.strip()
        if not name or name == state["icon"]:
            return False
        try:
            if os.path.isfile(name):
                icon.set_from_file(name)
            else:
                icon.set_from_icon_name(name)
            state["icon"] = name
        except Exception as exc:
            sys.stderr.write(f"ICON failed: {exc}\n")
        return False

    def do_quit() -> bool:
        state["alive"] = False
        Gtk.main_quit()
        return False

    def on_popup(_icon, button, activate_time) -> None:
        menu = Gtk.Menu()
        entries = [
            ("Otwórz Ogniwo", "CLICK"),
            ("Sprawdź teraz", "REFRESH"),
            None,
            ("Wycisz na godzinę", "SNOOZE 3600"),
            ("Wycisz na 4 godziny", "SNOOZE 14400"),
            ("Anuluj wyciszenie", "SNOOZE 0"),
            None,
            ("Zakończ", "QUIT"),
        ]
        for entry in entries:
            if entry is None:
                menu.append(Gtk.SeparatorMenuItem())
                continue
            label, command = entry
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda *_a, cmd=command: emit(cmd))
            menu.append(item)
        menu.show_all()
        menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, activate_time)

    icon.connect("activate", lambda *_a: emit("CLICK"))
    icon.connect("popup-menu", on_popup)

    def handle_line(line: str) -> None:
        if line == "EXIT":
            GLib.idle_add(do_quit)
        elif line.startswith("TOOLTIP "):
            GLib.idle_add(apply_tooltip, line[8:])
        elif line.startswith("ICON "):
            GLib.idle_add(apply_icon, line[5:])

    def reader() -> None:
        try:
            for line in sys.stdin:
                if not state["alive"]:
                    break
                handle_line(line.rstrip("\n"))
        except Exception as exc:
            sys.stderr.write(f"reader: {exc}\n")
        GLib.idle_add(do_quit)

    def announce_ready() -> bool:
        try:
            embedded = bool(icon.is_embedded())
        except Exception:
            embedded = False
        emit(f"READY embedded={1 if embedded else 0}")
        return False

    threading.Thread(target=reader, daemon=True).start()
    GLib.timeout_add(400, announce_ready)
    GLib.timeout_add(2000, announce_ready)
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
