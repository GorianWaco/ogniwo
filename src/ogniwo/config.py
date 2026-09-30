"""Ustawienia i stan wyciszenia."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .idle import clamp_sleep_minutes
from .policy import DeviceLatch, NotifyPolicy, RuntimeState

CONFIG_NAME = "config.json"
STATE_NAME = "state.json"


@dataclass
class Settings:
    poll_seconds: int = 60
    notify_enabled: bool = True
    threshold_percent: int = 15
    repeat_enabled: bool = False
    repeat_minutes: int = 30
    hysteresis_percent: int = 5
    autostart: bool = True
    sleep_minutes: int = 5

    def clamped(self) -> Settings:
        repeat = int(self.repeat_minutes)
        return Settings(
            poll_seconds=_clamp(int(self.poll_seconds), 15, 600),
            notify_enabled=bool(self.notify_enabled),
            threshold_percent=_clamp(int(self.threshold_percent), 1, 95),
            repeat_enabled=bool(self.repeat_enabled),
            repeat_minutes=_clamp(repeat, 5, 240),
            hysteresis_percent=_clamp(int(self.hysteresis_percent), 1, 30),
            autostart=bool(self.autostart),
            sleep_minutes=clamp_sleep_minutes(self.sleep_minutes),
        )

    def policy(self) -> NotifyPolicy:
        current = self.clamped()
        return NotifyPolicy(
            enabled=current.notify_enabled,
            threshold_percent=current.threshold_percent,
            repeat_minutes=current.repeat_minutes if current.repeat_enabled else 0,
            hysteresis_percent=current.hysteresis_percent,
        )


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(base) / "ogniwo"


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
    return Path(base) / "ogniwo"


def settings_path() -> Path:
    return config_dir() / CONFIG_NAME


def stored_sleep_minutes(path: Path) -> int | None:
    """None, gdy plik nie ma jeszcze tego pola — wtedy bierzemy wartość z myszy."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or "sleep_minutes" not in data:
        return None
    return clamp_sleep_minutes(data.get("sleep_minutes"))


def runtime_path() -> Path:
    return state_dir() / STATE_NAME


def load_settings(path: Path) -> Settings:
    if not path.is_file():
        return Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    current = Settings()
    for key, value in data.items():
        if hasattr(current, key):
            setattr(current, key, value)
    return current.clamped()


def save_settings(path: Path, settings: Settings) -> None:
    _atomic_write(path, json.dumps(asdict(settings.clamped()), indent=2) + "\n")


def load_runtime(path: Path) -> RuntimeState:
    if not path.is_file():
        return RuntimeState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return RuntimeState()
    if not isinstance(data, dict):
        return RuntimeState()
    devices: dict[str, DeviceLatch] = {}
    raw_devices = data.get("devices") or {}
    if isinstance(raw_devices, dict):
        for key, item in raw_devices.items():
            if not isinstance(item, dict):
                continue
            raw_last = item.get("last_notify_at")
            last_notify = None if raw_last in (None, "") else float(raw_last)
            devices[str(key)] = DeviceLatch(
                latched=bool(item.get("latched")),
                last_notify_at=last_notify,
            )
    try:
        snooze = float(data.get("snooze_until") or 0)
    except (TypeError, ValueError):
        snooze = 0.0
    return RuntimeState(snooze_until=snooze, devices=devices)


def save_runtime(path: Path, runtime: RuntimeState) -> None:
    payload = {
        "snooze_until": runtime.snooze_until,
        "devices": {
            key: {"latched": latch.latched, "last_notify_at": latch.last_notify_at}
            for key, latch in runtime.devices.items()
        },
    }
    _atomic_write(path, json.dumps(payload, indent=2) + "\n")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
