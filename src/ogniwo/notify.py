"""Powiadomienia pulpitu. Jedno id na urządzenie, żeby nie stosować stosu."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class Notifier:
    def __init__(self) -> None:
        self._ids: dict[str, int] = {}
        self._send = shutil.which("notify-send")

    def send(
        self,
        key: str,
        title: str,
        body: str,
        *,
        icon: Path | None = None,
        critical: bool = False,
    ) -> None:
        if not self._send:
            return
        command = [self._send, "-a", "Ogniwo", "-p", "-t", "12000"]
        if critical:
            command.extend(["-u", "critical"])
        if icon is not None and icon.is_file():
            command.extend(["-i", str(icon)])
        else:
            command.extend(["-i", "battery-caution-symbolic"])
        replace = self._ids.get(key)
        if replace:
            command.extend(["-r", str(replace)])
        command.extend([title, body])
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return
        token = (result.stdout or "").strip()
        if token.isdigit():
            self._ids[key] = int(token)
