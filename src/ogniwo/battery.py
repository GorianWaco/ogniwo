"""Odczyt baterii myszy Razer z sysfs OpenRazera.

Sterownik zwraca surowy poziom 0–255. Procent to round(raw / 255 * 100),
tak samo jak liczy powiadomienie daemona OpenRazer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

HID_ROOT = Path("/sys/bus/hid/devices")

# Modele, dla których razermouse zawsze zapisuje charge_status = 0.
CHARGING_UNSUPPORTED_PIDS = frozenset(
    {
        0x0062,  # Atheris receiver
        0x0083,  # Basilisk X HyperSpeed
        0x0094,  # Orochi V2 receiver
        0x0095,  # Orochi V2 bluetooth
        0x009C,  # DeathAdder V2 X HyperSpeed
        0x00B4,  # Naga V2 HyperSpeed receiver
        0x00B8,  # Viper V3 HyperSpeed
        0x00B9,  # Basilisk V3 X HyperSpeed
        0x00D3,  # Basilisk Mobile wired
        0x00D4,  # Basilisk Mobile receiver
    }
)


@dataclass(frozen=True)
class Mouse:
    key: str
    name: str
    path: Path
    pid: int | None

    @property
    def charging_known(self) -> bool:
        return self.pid not in CHARGING_UNSUPPORTED_PIDS


@dataclass(frozen=True)
class Sample:
    mouse: Mouse
    percent: int | None
    charging: bool | None
    error: str | None = None


class LevelTracker:
    """Ignoruje pojedyncze zera — OpenRazer czasem dostaje pusty odczyt."""

    def __init__(self, confirm_zero: int = 3) -> None:
        self.confirm_zero = confirm_zero
        self._zeros = 0
        self.last_good: int | None = None

    def push(self, raw: int | None) -> int | None:
        if raw is None or raw < 0 or raw > 255:
            return self.last_good
        if raw == 0:
            self._zeros += 1
            if self._zeros < self.confirm_zero:
                return self.last_good
        else:
            self._zeros = 0
        percent = percent_from_raw(raw)
        self.last_good = percent
        return percent


def percent_from_raw(raw: int) -> int:
    if raw <= 0:
        return 0
    if raw >= 255:
        return 100
    return int(round(raw * 100 / 255))


def friendly_name(device_type: str) -> str:
    name = device_type.strip()
    for suffix in (" (Receiver)", " (Wired)", " (Wireless)"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name or "Mysz Razer"


def pid_from_dirname(dirname: str) -> int | None:
    parts = dirname.split(":")
    if len(parts) < 3:
        return None
    hexpid = parts[2].split(".", 1)[0]
    try:
        return int(hexpid, 16)
    except ValueError:
        return None


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _serial_key(serial: str, name: str, dirname: str) -> str:
    cleaned = serial.strip()
    if cleaned and cleaned not in {"0", "000000000000"}:
        return cleaned
    return f"{name}:{dirname}"


def discover(root: Path = HID_ROOT) -> list[Mouse]:
    if not root.is_dir():
        return []
    found: list[Mouse] = []
    for dev in sorted(path for path in root.iterdir() if path.is_dir()):
        if not (dev / "charge_level").is_file():
            continue
        try:
            dtype = _read_text(dev / "device_type")
        except OSError:
            dtype = ""
        name = friendly_name(dtype or dev.name)
        try:
            serial = _read_text(dev / "device_serial")
        except OSError:
            serial = ""
        found.append(
            Mouse(
                key=_serial_key(serial, name, dev.name),
                name=name,
                path=dev,
                pid=pid_from_dirname(dev.name),
            )
        )
    return found


def read_raw(mouse: Mouse) -> int:
    text = _read_text(mouse.path / "charge_level")
    return int(text)


def read_charging(mouse: Mouse) -> bool | None:
    if not mouse.charging_known:
        return None
    try:
        return int(_read_text(mouse.path / "charge_status")) != 0
    except (OSError, ValueError):
        return None


def sample_mice(mice: list[Mouse], trackers: dict[str, LevelTracker]) -> list[Sample]:
    samples: list[Sample] = []
    for mouse in mice:
        tracker = trackers.setdefault(mouse.key, LevelTracker())
        try:
            raw = read_raw(mouse)
            percent = tracker.push(raw)
            error = None
        except (OSError, ValueError) as exc:
            percent = tracker.last_good
            error = str(exc)
        try:
            charging = read_charging(mouse)
        except OSError:
            charging = None
        samples.append(Sample(mouse=mouse, percent=percent, charging=charging, error=error))
    return samples


def primary(samples: list[Sample]) -> Sample | None:
    known = [item for item in samples if item.percent is not None]
    if known:
        return min(known, key=lambda item: item.percent if item.percent is not None else 101)
    return samples[0] if samples else None
