"""Rozmowa z pomocnikiem GTK3, który trzyma ikonę XEmbed w panelu."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path


def helper_path() -> Path:
    env = os.environ.get("OGNIWO_TRAY_HELPER", "").strip()
    if env:
        return Path(env)
    package_dir = Path(__file__).resolve().parent
    candidate = package_dir.parent / "tray_helper.py"
    if candidate.is_file():
        return candidate
    return package_dir / "tray_helper.py"


class Tray:
    def __init__(self, on_event: Callable[[str], None]) -> None:
        self._on_event = on_event
        self._proc: subprocess.Popen[str] | None = None
        path = helper_path()
        if not path.is_file():
            raise FileNotFoundError(path)
        env = os.environ.copy()
        env["GDK_BACKEND"] = "x11"
        self._proc = subprocess.Popen(
            [sys.executable, "-u", str(path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=env,
        )
        threading.Thread(target=self._read, name="ogniwo-tray", daemon=True).start()

    def send(self, line: str) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.poll() is not None:
            return
        try:
            proc.stdin.write(line.rstrip("\n") + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    def close(self) -> None:
        self.send("EXIT")
        proc = self._proc
        if proc is None:
            return
        try:
            proc.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            proc.terminate()

    def _read(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            text = line.strip()
            if text:
                self._on_event(text)
        self._on_event("EXITED")
