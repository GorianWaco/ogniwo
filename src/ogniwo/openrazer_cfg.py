"""Wyłącza wbudowane powiadomienia OpenRazera, zostawiając resztę pliku."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_NOTIFIER_LINE = re.compile(r"^(\s*)battery_notifier\s*=\s*(.*?)\s*$")
_OTHER_BATTERY = re.compile(r"^\s*battery_notifier_(freq|percent)\s*=")
_FALSE_VALUES = {"false", "0", "no", "off"}


@dataclass(frozen=True)
class SilenceResult:
    changed: bool
    restarted: bool
    message: str


def disable_notifier_text(text: str) -> tuple[str, bool]:
    """Zwraca treść pliku i informację, czy `battery_notifier` był włączony."""
    lines = text.splitlines(keepends=True)
    changed = False
    found = False
    startup_at: int | None = None
    output: list[str] = []

    for line in lines:
        newline = "\n" if line.endswith("\n") else ""
        if line.endswith("\r\n"):
            newline = "\r\n"
        body = line[: len(line) - len(newline)] if newline else line
        if body.strip() == "[Startup]":
            startup_at = len(output)
        if _OTHER_BATTERY.match(body):
            output.append(line)
            continue
        match = _NOTIFIER_LINE.match(body)
        if match is None:
            output.append(line)
            continue
        found = True
        value = match.group(2).strip().lower()
        if value in _FALSE_VALUES:
            output.append(line)
            continue
        output.append(f"{match.group(1)}battery_notifier = False{newline or chr(10)}")
        changed = True

    if not found:
        insertion = "battery_notifier = False\n"
        if startup_at is None:
            if output and not output[-1].endswith(("\n", "\r\n")):
                output[-1] = output[-1] + "\n"
            output.append("\n[Startup]\n")
            output.append(insertion)
        else:
            output.insert(startup_at + 1, insertion)
        changed = True

    return "".join(output), changed


def razer_conf_path() -> Path:
    return Path.home() / ".config" / "openrazer" / "razer.conf"


def silence_openrazer(path: Path | None = None, *, restart: bool = True) -> SilenceResult:
    target = path or razer_conf_path()
    if not target.is_file():
        return SilenceResult(
            False,
            False,
            "Brak pliku OpenRazer. Ogniwo i tak pilnuje progu samodzielnie.",
        )

    original = target.read_text(encoding="utf-8")
    updated, changed = disable_notifier_text(original)
    if not changed:
        return SilenceResult(
            False,
            False,
            "Wbudowane powiadomienia OpenRazera są wyłączone. Progiem steruje Ogniwo.",
        )

    backup = target.with_name("razer.conf.bak-ogniwo")
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")
    target.write_text(updated, encoding="utf-8")

    if not restart:
        return SilenceResult(True, False, "Zapisane wyłączenie powiadomień OpenRazera.")

    reactive_was_active = _unit_active("razer-reactive.service")
    daemon = _restart_unit("openrazer-daemon.service")
    if daemon.returncode != 0:
        detail = (daemon.stderr or daemon.stdout or "").strip()
        return SilenceResult(
            True,
            False,
            "Zapisałem wyłączenie w razer.conf. Restart OpenRazera nie wyszedł"
            + (f": {detail}" if detail else "."),
        )

    reactive_note = ""
    if reactive_was_active:
        reactive = _restart_unit("razer-reactive.service")
        if reactive.returncode != 0:
            reactive_note = " Podświetlenie klawiatury trzeba włączyć ponownie w Razer Reactive."
        else:
            reactive_note = " Podświetlenie klawiatury wróciło po restarcie."

    return SilenceResult(
        True,
        True,
        "Wyłączyłem powiadomienia OpenRazera (wcześniej: co 10 minut przy 33% albo niżej) "
        "i przeładowałem daemon." + reactive_note,
    )


def _unit_active(unit: str) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.stdout.strip() == "active"


def _restart_unit(unit: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "--user", "restart", unit],
        check=False,
        capture_output=True,
        text=True,
        timeout=40,
    )
