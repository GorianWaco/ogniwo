"""Autostart w sesji GNOME."""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import APP_ID, APP_NAME

_ENABLED = re.compile(r"^X-GNOME-Autostart-enabled=(.*)$", re.MULTILINE)
_HIDDEN = re.compile(r"^Hidden=true\s*$", re.MULTILINE)


def autostart_path() -> Path:
    config = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(config) / "autostart" / f"{APP_ID}.desktop"


def background_command() -> str:
    local = Path.home() / ".local" / "bin" / "ogniwo"
    if os.access(local, os.X_OK):
        return f"{local} --background"
    return "python3 -m ogniwo --background"


def autostart_enabled(path: Path | None = None) -> bool:
    target = path or autostart_path()
    if not target.is_file():
        return False
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return False
    if _HIDDEN.search(text):
        return False
    match = _ENABLED.search(text)
    if match is None:
        return True
    return match.group(1).strip().lower() == "true"


def write_autostart(enabled: bool, path: Path | None = None, command: str | None = None) -> None:
    target = path or autostart_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    flag = "true" if enabled else "false"
    exec_line = command or background_command()
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={APP_NAME}",
        "GenericName=Bateria myszy",
        "Comment=Poziom baterii myszy w trayu i próg powiadomienia",
        f"Exec={exec_line}",
        f"Icon={APP_ID}",
        "Terminal=false",
        "Categories=Settings;Hardware;",
        f"X-GNOME-Autostart-enabled={flag}",
        "X-GNOME-Autostart-Delay=4",
    ]
    if not enabled:
        lines.append("Hidden=true")
    lines.append("")
    target.write_text("\n".join(lines), encoding="utf-8")
