"""Unit tests for storage module. Run: python -m unittest test_storage"""
from __future__ import annotations

import os
import tempfile
import unittest

import storage
from storage import (
    PROTEIN_TARGET,
    WATER_TARGET,
    DayState,
    bump_protein,
    bump_water,
    compute_streaks,
    get_day,
    get_history,
    init_db,
    reset_protein,
    set_binary,
)


class StorageTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        init_db(self._tmp.name)

    def tearDown(self):
        storage._DB_PATH = None
        os.unlink(self._tmp.name)


class TestDayState(unittest.TestCase):
    def test_empty_state_is_not_closed(self):
        s = DayState(date="2026-05-26")
        self.assertFalse(s.is_closed())
        self.assertEqual(s.checked_count(), 0)

    def test_fully_filled_is_closed(self):
        s = DayState(
            date="2026-05-26",
            morning_shower=True,
            morning_walk=True,
            water_count=WATER_TARGET,
            protein_g=PROTEIN_TARGET,
            evening_walk=True,
            no_porn=True,
            no_masturbation=True,
            no_shorts=True,
            sleep=True,
        )
        self.assertTrue(s.is_closed())
        self.assertEqual(s.checked_count(), 9)

    def test_water_below_target_not_counted(self):
        s = DayState(date="2026-05-26", water_count=WATER_TARGET - 1)
        self.assertEqual(s.checked_count(), 0)

    def test_protein_at_or_above_target_counts(self):
        s = DayState(date="2026-05-26", protein_g=PROTEIN_TARGET)
        self.assertEqual(s.checked_count(), 1)
        s2 = DayState(date="2026-05-26", protein_g=PROTEIN_TARGET + 50)
        self.assertEqual(s2.checked_count(), 1)


class TestGetDay(StorageTestBase):
    def test_missing_date_returns_zero_state(self):
        s = get_day("2026-05-26")
        self.assertEqual(s.date, "2026-05-26")
        self.assertFalse(s.morning_shower)
        self.assertEqual(s.water_count, 0)

    def test_get_after_set(self):
        set_binary("2026-05-26", "morning_shower", True)
        s = get_day("2026-05-26")
        self.assertTrue(s.morning_shower)


class TestSetBinary(StorageTestBase):
    def test_toggles(self):
        set_binary("2026-05-26", "no_porn", True)
        self.assertTrue(get_day("2026-05-26").no_porn)
        set_binary("2026-05-26", "no_porn", False)
        self.assertFalse(get_day("2026-05-26").no_porn)

    def test_unknown_field_rejected(self):
        with self.assertRaises(ValueError):
            set_binary("2026-05-26", "nonsense_field", True)


class TestWaterBump(StorageTestBase):
    def test_increment_from_zero(self):
        bump_water("2026-05-26", 1)
        self.assertEqual(get_day("2026-05-26").water_count, 1)

    def test_clamp_upper(self):
        for _ in range(20):
            bump_water("2026-05-26", 1)
        self.assertEqual(get_day("2026-05-26").water_count, WATER_TARGET)

    def test_clamp_lower(self):
        bump_water("2026-05-26", -5)
        self.assertEqual(get_day("2026-05-26").water_count, 0)


class TestProteinBump(StorageTestBase):
    def test_increment(self):
        bump_protein("2026-05-26", 50)
        bump_protein("2026-05-26", 20)
        self.assertEqual(get_day("2026-05-26").protein_g, 70)

    def test_no_upper_cap(self):
        bump_protein("2026-05-26", 200)
        self.assertEqual(get_day("2026-05-26").protein_g, 200)

    def test_clamp_lower(self):
        bump_protein("2026-05-26", -50)
        self.assertEqual(get_day("2026-05-26").protein_g, 0)

    def test_reset(self):
        bump_protein("2026-05-26", 100)
        reset_protein("2026-05-26")
        self.assertEqual(get_day("2026-05-26").protein_g, 0)


class TestHistory(StorageTestBase):
    def test_history_returns_n_days_most_recent_first(self):
        rows = get_history(7, "2026-05-26")
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0].date, "2026-05-26")
        self.assertEqual(rows[6].date, "2026-05-20")

    def test_history_reflects_data(self):
        # Fully close 2026-05-25.
        d = "2026-05-25"
        for key in (
            "morning_shower",
            "morning_walk",
            "evening_walk",
            "no_porn",
            "no_masturbation",
            "no_shorts",
            "sleep",
        ):
            set_binary(d, key, True)
        for _ in range(WATER_TARGET):
            bump_water(d, 1)
        bump_protein(d, PROTEIN_TARGET)
        rows = get_history(7, "2026-05-26")
        # Find row for 2026-05-25.
        target = next(r for r in rows if r.date == d)
        self.assertTrue(target.is_closed)
        self.assertEqual(target.checked_count, 9)


class TestStreaks(StorageTestBase):
    def _close_day(self, d: str):
        for key in (
            "morning_shower",
            "morning_walk",
            "evening_walk",
            "no_porn",
            "no_masturbation",
            "no_shorts",
            "sleep",
        ):
            set_binary(d, key, True)
        for _ in range(WATER_TARGET):
            bump_water(d, 1)
        bump_protein(d, PROTEIN_TARGET)

    def test_empty_db_zero_streaks(self):
        cur, best = compute_streaks("2026-05-26")
        self.assertEqual((cur, best), (0, 0))

    def test_single_closed_day_yesterday(self):
        self._close_day("2026-05-25")
        cur, best = compute_streaks("2026-05-26")
        self.assertEqual(cur, 1)
        self.assertEqual(best, 1)

    def test_single_closed_day_today(self):
        self._close_day("2026-05-26")
        cur, best = compute_streaks("2026-05-26")
        self.assertEqual(cur, 1)
        self.assertEqual(best, 1)

    def test_consecutive_three_days(self):
        self._close_day("2026-05-24")
        self._close_day("2026-05-25")
        self._close_day("2026-05-26")
        cur, best = compute_streaks("2026-05-26")
        self.assertEqual(cur, 3)
        self.assertEqual(best, 3)

    def test_broken_streak_current_zero_but_best_preserved(self):
        # Closed run: May 20-22 (3 days), gap, then nothing recent.
        self._close_day("2026-05-20")
        self._close_day("2026-05-21")
        self._close_day("2026-05-22")
        cur, best = compute_streaks("2026-05-26")
        self.assertEqual(cur, 0)
        self.assertEqual(best, 3)

    def test_current_anchors_on_yesterday_when_today_open(self):
        self._close_day("2026-05-24")
        self._close_day("2026-05-25")
        # 2026-05-26 not closed.
        cur, best = compute_streaks("2026-05-26")
        self.assertEqual(cur, 2)
        self.assertEqual(best, 2)

    def test_two_runs_best_is_longer(self):
        # Run A: May 10-12 (3 days). Run B: May 20-21 (2 days). Current=0 (gap to today).
        for d in ("2026-05-10", "2026-05-11", "2026-05-12"):
            self._close_day(d)
        for d in ("2026-05-20", "2026-05-21"):
            self._close_day(d)
        cur, best = compute_streaks("2026-05-26")
        self.assertEqual(cur, 0)
        self.assertEqual(best, 3)


if __name__ == "__main__":
    unittest.main()
