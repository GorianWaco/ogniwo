"""Kiedy wysłać powiadomienie o niskiej baterii."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class NotifyPolicy:
    enabled: bool = True
    threshold_percent: int = 15
    repeat_minutes: int = 0
    hysteresis_percent: int = 5


@dataclass
class DeviceLatch:
    latched: bool = False
    last_notify_at: float | None = None


@dataclass
class RuntimeState:
    snooze_until: float = 0.0
    devices: dict[str, DeviceLatch] = field(default_factory=dict)

    def copy(self) -> RuntimeState:
        return RuntimeState(
            snooze_until=self.snooze_until,
            devices={
                key: DeviceLatch(latch.latched, latch.last_notify_at)
                for key, latch in self.devices.items()
            },
        )


def evaluate(
    policy: NotifyPolicy,
    runtime: RuntimeState,
    key: str,
    percent: int | None,
    now: float,
) -> tuple[RuntimeState, bool]:
    state = runtime.copy()

    if state.snooze_until and now >= state.snooze_until:
        state.snooze_until = 0.0

    if percent is None or not policy.enabled:
        return state, False

    if state.snooze_until and now < state.snooze_until:
        return state, False

    latch = state.devices.setdefault(key, DeviceLatch())
    recover = policy.threshold_percent + max(0, policy.hysteresis_percent)
    if percent >= recover:
        latch.latched = False

    if percent > policy.threshold_percent:
        return state, False

    if policy.repeat_minutes <= 0:
        if latch.latched:
            return state, False
        latch.latched = True
        latch.last_notify_at = now
        return state, True

    interval = policy.repeat_minutes * 60
    if latch.last_notify_at is not None and now - latch.last_notify_at < interval:
        latch.latched = True
        return state, False

    latch.latched = True
    latch.last_notify_at = now
    return state, True


def describe(
    policy: NotifyPolicy,
    runtime: RuntimeState,
    key: str,
    percent: int | None,
    now: float,
) -> str:
    if percent is None:
        return "Czekam na odczyt baterii."
    if not policy.enabled:
        return "Powiadomienia są wyłączone. Ikona w trayu dalej pokazuje poziom."
    if runtime.snooze_until and now < runtime.snooze_until:
        clock = time.strftime("%H:%M", time.localtime(runtime.snooze_until))
        return f"Wyciszone do {clock}."

    latch = runtime.devices.get(key) or DeviceLatch()
    recover = policy.threshold_percent + max(0, policy.hysteresis_percent)
    if percent > policy.threshold_percent:
        return (
            f"Powiadomienie, gdy bateria spadnie do {policy.threshold_percent}% "
            "albo niżej."
        )
    if policy.repeat_minutes > 0:
        return (
            f"Bateria jest na poziomie progu. Przypomnienie co "
            f"{policy.repeat_minutes} min."
        )
    if latch.latched:
        return (
            f"To zejście już zgłoszone. Kolejne powiadomienie po wzroście "
            f"powyżej {recover}%."
        )
    return "Przy następnym odczycie wyślę powiadomienie."
