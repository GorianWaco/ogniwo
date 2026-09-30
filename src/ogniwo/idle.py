"""Czas uśpienia myszy i śledzenie ruchu, bez budzenia jej odczytem baterii."""

from __future__ import annotations

import os
import select
import threading
import time
from collections.abc import Callable
from pathlib import Path

SLEEP_MIN_MINUTES = 1
SLEEP_MAX_MINUTES = 60
IDLE_FILE = "device_idle_time"


def clamp_sleep_minutes(value: object, default: int = 5) -> int:
    try:
        minutes = int(round(float(value)))
    except (TypeError, ValueError):
        minutes = default
    return max(SLEEP_MIN_MINUTES, min(SLEEP_MAX_MINUTES, minutes))


def sleep_seconds(minutes: int) -> int:
    return clamp_sleep_minutes(minutes) * 60


def is_asleep(last_activity: float | None, now: float, idle_seconds: int) -> bool:
    """Brak ruchu od startu programu też znaczy: nie pokazuj poziomu."""
    if last_activity is None:
        return True
    return now - last_activity >= max(1, idle_seconds)


def read_idle_seconds(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        seconds = int(text)
    except (OSError, ValueError):
        return None
    if seconds <= 0:
        return None
    return seconds


def write_idle_seconds(path: Path, seconds: int) -> None:
    path.write_text(f"{int(seconds)}\n", encoding="utf-8")


def find_event_devices(
    names: list[str],
    sys_root: Path = Path("/sys/class/input"),
    dev_root: Path = Path("/dev/input"),
) -> list[Path]:
    needles = [name.strip().lower() for name in names if name.strip()]
    if not needles or not sys_root.is_dir():
        return []
    found: list[Path] = []
    for event in sorted(sys_root.glob("event*")):
        name_file = event / "device" / "name"
        try:
            device_name = name_file.read_text(encoding="utf-8", errors="replace").strip().lower()
        except OSError:
            continue
        if not any(needle in device_name for needle in needles):
            continue
        node = dev_root / event.name
        if node.exists():
            found.append(node)
    return found


class ActivityWatch:
    """Ostatni ruch myszy z evdev. Sam odczyt nie rusza sysfs OpenRazera."""

    def __init__(self, on_wake: Callable[[], None] | None = None) -> None:
        self._on_wake = on_wake
        self._last: float | None = None
        self._idle_seconds = sleep_seconds(5)
        self._names: list[str] = ["naga"]
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.watching = False

    def set_idle_seconds(self, seconds: int) -> None:
        with self._lock:
            self._idle_seconds = max(1, int(seconds))

    def set_names(self, names: list[str]) -> None:
        cleaned = [name.strip() for name in names if name.strip()]
        with self._lock:
            self._names = cleaned or ["naga"]

    def mark(self, when: float | None = None) -> None:
        with self._lock:
            self._last = time.monotonic() if when is None else when

    def last_activity(self) -> float | None:
        with self._lock:
            return self._last

    def asleep(self, idle_seconds: int | None = None, now: float | None = None) -> bool:
        with self._lock:
            last = self._last
            limit = self._idle_seconds if idle_seconds is None else idle_seconds
        return is_asleep(last, time.monotonic() if now is None else now, limit)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ogniwo-activity", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)

    def _names_now(self) -> list[str]:
        with self._lock:
            return list(self._names)

    def _run(self) -> None:
        open_fds: list[int] = []
        open_paths: tuple[str, ...] = ()
        while not self._stop.is_set():
            paths = tuple(str(path) for path in find_event_devices(self._names_now()))
            if paths != open_paths:
                for fd in open_fds:
                    os.close(fd)
                open_fds = []
                opened: list[str] = []
                for path in paths:
                    try:
                        open_fds.append(os.open(path, os.O_RDONLY | os.O_NONBLOCK))
                        opened.append(path)
                    except OSError:
                        continue
                open_paths = tuple(opened)
                self.watching = bool(open_fds)
            if not open_fds:
                self._stop.wait(1.0)
                continue
            try:
                readable, _, _ = select.select(open_fds, [], [], 1.0)
            except (OSError, ValueError):
                open_paths = ()
                continue
            if not readable:
                continue
            saw_input = False
            for fd in readable:
                try:
                    chunk = os.read(fd, 4096)
                except BlockingIOError:
                    continue
                except OSError:
                    open_paths = ()
                    continue
                if chunk:
                    saw_input = True
            if not saw_input:
                continue
            was_asleep = self.asleep()
            self.mark()
            if was_asleep and self._on_wake is not None:
                self._on_wake()
        for fd in open_fds:
            os.close(fd)
        self.watching = False
