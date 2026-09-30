"""Testy progu, odczytu i wyłączenia powiadomień OpenRazera."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ogniwo.battery import LevelTracker, friendly_name, percent_from_raw, pid_from_dirname
from ogniwo.battery import discover, sample_mice
from ogniwo.config import (
    Settings,
    load_runtime,
    load_settings,
    save_runtime,
    save_settings,
    stored_sleep_minutes,
)
from ogniwo.idle import (
    clamp_sleep_minutes,
    find_event_devices,
    is_asleep,
    read_idle_seconds,
    sleep_seconds,
    write_idle_seconds,
)
from ogniwo.icon_draw import draw_badge
from ogniwo.openrazer_cfg import disable_notifier_text
from ogniwo.policy import DeviceLatch, NotifyPolicy, RuntimeState, describe, evaluate


class PercentTests(unittest.TestCase):
    def test_naga_raw_71_is_28_percent(self) -> None:
        self.assertEqual(percent_from_raw(71), 28)

    def test_ends(self) -> None:
        self.assertEqual(percent_from_raw(0), 0)
        self.assertEqual(percent_from_raw(255), 100)

    def test_friendly_name(self) -> None:
        self.assertEqual(
            friendly_name("Razer Naga V2 HyperSpeed (Receiver)"),
            "Razer Naga V2 HyperSpeed",
        )

    def test_pid(self) -> None:
        self.assertEqual(pid_from_dirname("0003:1532:00B4.0006"), 0x00B4)


class TrackerTests(unittest.TestCase):
    def test_single_zero_keeps_last_good(self) -> None:
        tracker = LevelTracker()
        self.assertEqual(tracker.push(71), 28)
        self.assertEqual(tracker.push(0), 28)
        self.assertEqual(tracker.push(0), 28)
        self.assertEqual(tracker.push(0), 0)


class DiscoverTests(unittest.TestCase):
    def test_reads_fake_sysfs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dev = root / "0003:1532:00B4.0006"
            dev.mkdir()
            (dev / "charge_level").write_text("71\n", encoding="utf-8")
            (dev / "charge_status").write_text("0\n", encoding="utf-8")
            (dev / "device_type").write_text(
                "Razer Naga V2 HyperSpeed (Receiver)\n", encoding="utf-8"
            )
            (dev / "device_serial").write_text("EXAMPLE-SERIAL\n", encoding="utf-8")
            empty = root / "0003:1532:0293.0001"
            empty.mkdir()
            mice = discover(root)
            self.assertEqual(len(mice), 1)
            self.assertEqual(mice[0].name, "Razer Naga V2 HyperSpeed")
            self.assertFalse(mice[0].charging_known)
            samples = sample_mice(mice, {})
            self.assertEqual(samples[0].percent, 28)
            self.assertIsNone(samples[0].charging)


class PolicyTests(unittest.TestCase):
    def test_once_until_recovered(self) -> None:
        policy = NotifyPolicy(threshold_percent=15, hysteresis_percent=5, repeat_minutes=0)
        state = RuntimeState()
        state, notify = evaluate(policy, state, "m", 28, 1000)
        self.assertFalse(notify)
        state, notify = evaluate(policy, state, "m", 15, 1001)
        self.assertTrue(notify)
        state, notify = evaluate(policy, state, "m", 14, 1002)
        self.assertFalse(notify)
        state, notify = evaluate(policy, state, "m", 19, 1003)
        self.assertFalse(notify)
        self.assertTrue(state.devices["m"].latched)
        state, notify = evaluate(policy, state, "m", 20, 1004)
        self.assertFalse(notify)
        self.assertFalse(state.devices["m"].latched)
        state, notify = evaluate(policy, state, "m", 15, 1005)
        self.assertTrue(notify)

    def test_repeat(self) -> None:
        policy = NotifyPolicy(threshold_percent=30, repeat_minutes=10)
        state = RuntimeState()
        state, notify = evaluate(policy, state, "m", 28, 0)
        self.assertTrue(notify)
        state, notify = evaluate(policy, state, "m", 28, 500)
        self.assertFalse(notify)
        state, notify = evaluate(policy, state, "m", 28, 600)
        self.assertTrue(notify)

    def test_snooze_blocks(self) -> None:
        policy = NotifyPolicy(threshold_percent=40)
        state = RuntimeState(snooze_until=5000)
        state, notify = evaluate(policy, state, "m", 10, 1000)
        self.assertFalse(notify)
        state, notify = evaluate(policy, state, "m", 10, 5000)
        self.assertTrue(notify)

    def test_disabled(self) -> None:
        policy = NotifyPolicy(enabled=False, threshold_percent=90)
        state, notify = evaluate(policy, RuntimeState(), "m", 10, 1)
        self.assertFalse(notify)

    def test_describe_above(self) -> None:
        text = describe(NotifyPolicy(threshold_percent=15), RuntimeState(), "m", 28, 1)
        self.assertIn("15%", text)


class ConfigTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text('{"threshold_percent": 22}\n', encoding="utf-8")
            self.assertIsNone(stored_sleep_minutes(path))
            self.assertEqual(load_settings(path).sleep_minutes, 5)

            save_settings(path, Settings(threshold_percent=22, repeat_enabled=True, repeat_minutes=12))
            loaded = load_settings(path)
            self.assertEqual(loaded.threshold_percent, 22)
            self.assertTrue(loaded.repeat_enabled)
            self.assertEqual(loaded.repeat_minutes, 12)
            self.assertEqual(loaded.sleep_minutes, 5)
            self.assertEqual(stored_sleep_minutes(path), 5)

            save_settings(path, Settings(sleep_minutes=99))
            self.assertEqual(load_settings(path).sleep_minutes, 60)
            self.assertEqual(stored_sleep_minutes(path), 60)

            state_file = Path(tmp) / "state.json"
            runtime = RuntimeState(
                snooze_until=9,
                devices={"m": DeviceLatch(latched=True, last_notify_at=3)},
            )
            save_runtime(state_file, runtime)
            loaded_state = load_runtime(state_file)
            self.assertEqual(loaded_state.snooze_until, 9)
            self.assertTrue(loaded_state.devices["m"].latched)


class OpenRazerConfigTests(unittest.TestCase):
    def test_turns_off_only_the_switch(self) -> None:
        original = (
            "[Startup]\n"
            "battery_notifier = True\n"
            "battery_notifier_freq = 600\n"
            "battery_notifier_percent = 33\n"
        )
        updated, changed = disable_notifier_text(original)
        self.assertTrue(changed)
        self.assertIn("battery_notifier = False\n", updated)
        self.assertIn("battery_notifier_freq = 600\n", updated)
        self.assertIn("battery_notifier_percent = 33\n", updated)
        again, changed_again = disable_notifier_text(updated)
        self.assertFalse(changed_again)
        self.assertEqual(again, updated)

    def test_adds_key_when_missing(self) -> None:
        updated, changed = disable_notifier_text("[Startup]\nsync_effects_enabled = True\n")
        self.assertTrue(changed)
        self.assertIn("battery_notifier = False\n", updated)
        self.assertIn("sync_effects_enabled = True\n", updated)


class IdleTests(unittest.TestCase):
    def test_asleep_without_movement(self) -> None:
        self.assertTrue(is_asleep(None, 100, 60))
        self.assertFalse(is_asleep(80, 100, 60))
        self.assertTrue(is_asleep(40, 100, 60))

    def test_minutes_become_seconds(self) -> None:
        self.assertEqual(sleep_seconds(5), 300)
        self.assertEqual(sleep_seconds(1), 60)
        self.assertEqual(clamp_sleep_minutes(0), 1)
        self.assertEqual(clamp_sleep_minutes(15), 15)
        self.assertEqual(sleep_seconds(60), 3600)
        self.assertEqual(clamp_sleep_minutes(99), 60)

    def test_write_idle_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "device_idle_time"
            write_idle_seconds(path, 600)
            self.assertEqual(read_idle_seconds(path), 600)

    def test_event_nodes_match_mouse_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sys_root = root / "sys"
            dev_root = root / "dev"
            naga = sys_root / "event6"
            (naga / "device").mkdir(parents=True)
            (naga / "device" / "name").write_text("Razer Razer Naga V2 HyperSpeed\n", encoding="utf-8")
            (dev_root).mkdir()
            (dev_root / "event6").write_text("", encoding="utf-8")
            keyboard = sys_root / "event2"
            (keyboard / "device").mkdir(parents=True)
            (keyboard / "device" / "name").write_text("Razer Razer BlackWidow V4 X\n", encoding="utf-8")
            (dev_root / "event2").write_text("", encoding="utf-8")
            found = find_event_devices(["Razer Naga V2 HyperSpeed"], sys_root, dev_root)
            self.assertEqual(found, [dev_root / "event6"])


class IconTests(unittest.TestCase):
    def test_writes_png(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = draw_badge(28, "mid", Path(tmp) / "badge.png", size=64)
            self.assertGreater(path.stat().st_size, 200)


if __name__ == "__main__":
    unittest.main()
