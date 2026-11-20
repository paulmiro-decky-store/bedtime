import json
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules"))

from bedtime_core import (  # noqa: E402
    BedtimeState,
    StateStore,
    is_game_reaper,
    load_managed_config,
    next_occurrence,
    normalize_settings,
    parse_hhmm,
    status_payload,
    validate_settings_patch,
)


class TimeTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_hhmm("07:05"), (7, 5))
        for bad in ("7:05", "24:00", "12:60", "", None, 1230):
            with self.assertRaises(ValueError):
                parse_hhmm(bad)

    def test_next_occurrence_today_and_tomorrow(self):
        now = datetime(2026, 11, 20, 20, 0, 30)
        self.assertEqual(next_occurrence("21:30", now), datetime(2026, 11, 20, 21, 30))
        self.assertEqual(next_occurrence("01:00", now), datetime(2026, 11, 21, 1, 0))
        self.assertEqual(next_occurrence("20:00", now), datetime(2026, 11, 21, 20, 0))


class StateTests(unittest.TestCase):
    def test_countdown_uses_boottime(self):
        now = datetime(2026, 11, 20, 20, 0, 0)
        st = BedtimeState.create("21:00", now=now, now_boot=1000.0, boot_id="b")
        self.assertEqual(st.remaining(1000.0), 3600)
        self.assertEqual(st.remaining(4600.0), 0)
        self.assertEqual(st.warned, [])

    def test_warnings(self):
        now = datetime(2026, 11, 20, 20, 0, 0)
        st = BedtimeState.create("20:30", now=now, now_boot=0.0, boot_id="b")
        self.assertEqual(st.due_warnings(0.0), [])
        self.assertEqual(st.due_warnings(15 * 60), [15])          # 15 min left
        st.warned.append(15)
        self.assertEqual(st.due_warnings(25 * 60 + 1), [5])
        st.warned.append(5)
        self.assertEqual(st.due_warnings(29 * 60), [1])
        st.warned.append(1)
        self.assertEqual(st.due_warnings(29 * 60 + 30), [])
        self.assertEqual(st.due_warnings(31 * 60), [])            # past bedtime

    def test_thresholds_already_passed_are_skipped(self):
        now = datetime(2026, 11, 20, 20, 0, 0)
        st = BedtimeState.create("20:04", now=now, now_boot=0.0, boot_id="b")
        self.assertEqual(sorted(st.warned), [5, 15])
        self.assertEqual(st.due_warnings(3 * 60), [1])

    def test_store_discards_other_boot(self):
        with tempfile.TemporaryDirectory() as d:
            st = BedtimeState.create("21:00", boot_id="boot-a")
            StateStore(d, boot_id="boot-a").save(st)
            self.assertIsNotNone(StateStore(d, boot_id="boot-a").load())
            self.assertIsNone(StateStore(d, boot_id="boot-b").load())
            self.assertFalse(os.path.exists(os.path.join(d, StateStore.FILENAME)))

    def test_store_corrupt_file(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, StateStore.FILENAME), "w") as fh:
                fh.write("{nope")
            self.assertIsNone(StateStore(d).load())

    def test_status_payload(self):
        settings = normalize_settings(None)
        self.assertFalse(status_payload(None, settings)["set"])
        now = datetime(2026, 11, 20, 20, 0, 0)
        st = BedtimeState.create("21:15", now=now, now_boot=0.0, boot_id="b")
        p = status_payload(st, settings, now_boot=0.0)
        self.assertEqual((p["bedtime"], p["remainingText"], p["reached"]), ("21:15", "1 h 15 min", False))
        self.assertTrue(status_payload(st, settings, now_boot=99999)["reached"])


class SettingsTests(unittest.TestCase):
    def test_normalize(self):
        s = normalize_settings({"defaultBedtime": "bad", "port": "8080", "listenAddress": " ::1 "})
        self.assertEqual(s, {"defaultBedtime": "21:00", "port": 8080, "listenAddress": "::1"})

    def test_validate(self):
        self.assertEqual(validate_settings_patch({"port": "123"}), {"port": 123})
        for bad in ({"port": 0}, {"port": True}, {"listenAddress": ""}, {"defaultBedtime": "9pm"}):
            with self.assertRaises(ValueError):
                validate_settings_patch(bad)

    def test_managed_config(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.json")
            with open(path, "w") as fh:
                json.dump({"listenAddress": None, "port": 8000}, fh)
            self.assertEqual(load_managed_config(path), {"port": 8000})
            self.assertEqual(load_managed_config(os.path.join(d, "missing")), {})


class ProcessTests(unittest.TestCase):
    def test_reaper_detection(self):
        self.assertTrue(is_game_reaper(
            ["/home/deck/.local/share/Steam/ubuntu12_32/reaper", "SteamLaunch", "AppId=620", "--", "x"]))
        self.assertFalse(is_game_reaper(["/usr/bin/steam", "SteamLaunch", "AppId=620"]))
        self.assertFalse(is_game_reaper(["reaper", "AppId=620"]))
        self.assertFalse(is_game_reaper([]))


if __name__ == "__main__":
    unittest.main()
