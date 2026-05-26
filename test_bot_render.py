"""Render-function tests for bot.py. Run: python -m unittest test_bot_render"""
from __future__ import annotations

import os
import unittest

# Set env vars before importing bot — bot.py reads them at module load.
# load_dotenv inside bot.py uses override=False, so these values win.
os.environ["TG_BOT_TOKEN"] = "test:dummy"
os.environ["AUTHOR_TG_ID"] = "0"
os.environ.setdefault("TZ", "Europe/Moscow")

import bot
from storage import PROTEIN_TARGET, WATER_TARGET, DayState, HistoryRow


class TestCheckGlyph(unittest.TestCase):
    def test_true_is_checked(self):
        self.assertEqual(bot.check(True), "✅")

    def test_false_is_empty(self):
        self.assertEqual(bot.check(False), "⬜")


class TestWaterBar(unittest.TestCase):
    def test_empty(self):
        bar = bot.water_bar(0)
        self.assertEqual(bar.count("▰"), 0)
        self.assertEqual(bar.count("▱"), WATER_TARGET)

    def test_half(self):
        bar = bot.water_bar(6)
        self.assertEqual(bar.count("▰"), 6)
        self.assertEqual(bar.count("▱"), 6)

    def test_full(self):
        bar = bot.water_bar(WATER_TARGET)
        self.assertEqual(bar.count("▰"), WATER_TARGET)
        self.assertEqual(bar.count("▱"), 0)

    def test_bar_length_constant(self):
        for n in (0, 1, 5, 12):
            self.assertEqual(len(bot.water_bar(n)), WATER_TARGET)


class TestRenderTodayText(unittest.TestCase):
    def _empty_state(self) -> DayState:
        return DayState(date="2026-05-26")

    def _full_state(self) -> DayState:
        return DayState(
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

    def test_empty_state_shows_zero_checked(self):
        text = bot.render_today_text(self._empty_state(), current=0, best=0)
        self.assertIn("0/9", text)
        self.assertNotIn("Закрыт", text)
        self.assertIn("⬜", text)
        self.assertNotIn("✅", text)

    def test_full_state_shows_closed(self):
        text = bot.render_today_text(self._full_state(), current=1, best=1)
        self.assertIn("Закрыт", text)
        self.assertNotIn("0/9", text)

    def test_streak_footer_present(self):
        text = bot.render_today_text(self._empty_state(), current=3, best=7)
        self.assertIn("текущий *3*", text)
        self.assertIn("лучший *7*", text)

    def test_water_bar_progress_rendered(self):
        state = DayState(date="2026-05-26", water_count=4)
        text = bot.render_today_text(state, current=0, best=0)
        self.assertIn("4/12", text)
        # 4 filled, 8 empty.
        self.assertIn("▰▰▰▰▱▱▱▱▱▱▱▱", text)

    def test_protein_check_appears_when_target_reached(self):
        state = DayState(date="2026-05-26", protein_g=PROTEIN_TARGET)
        text = bot.render_today_text(state, current=0, best=0)
        self.assertIn(f"{PROTEIN_TARGET}г / {PROTEIN_TARGET}г", text)
        # The trailing ✅ after protein line should appear.
        protein_line = [l for l in text.split("\n") if "Белок" in l][0]
        self.assertIn("✅", protein_line)

    def test_protein_no_check_below_target(self):
        state = DayState(date="2026-05-26", protein_g=PROTEIN_TARGET - 10)
        text = bot.render_today_text(state, current=0, best=0)
        protein_line = [l for l in text.split("\n") if "Белок" in l][0]
        self.assertNotIn("✅", protein_line)

    def test_partial_state_counts_correctly(self):
        # Shower + 2 binary items checked = 3 items.
        state = DayState(
            date="2026-05-26",
            morning_shower=True,
            no_porn=True,
            no_shorts=True,
        )
        text = bot.render_today_text(state, current=0, best=0)
        self.assertIn("3/9", text)


class TestRenderHistoryText(unittest.TestCase):
    def test_empty_history(self):
        text = bot.render_history_text([])
        self.assertIn("Последние 7 дней", text)

    def test_mixed_history(self):
        rows = [
            HistoryRow(date="2026-05-26", checked_count=4, is_closed=False),
            HistoryRow(date="2026-05-25", checked_count=9, is_closed=True),
            HistoryRow(date="2026-05-24", checked_count=0, is_closed=False),
        ]
        text = bot.render_history_text(rows)
        self.assertIn("`2026-05-26`", text)
        self.assertIn("`2026-05-25`", text)
        self.assertIn("`2026-05-24`", text)
        # closed day shows ✅; partial shows N/9
        lines = text.split("\n")
        line_25 = [l for l in lines if "2026-05-25" in l][0]
        line_26 = [l for l in lines if "2026-05-26" in l][0]
        self.assertIn("✅", line_25)
        self.assertIn("4/9", line_26)


class TestRenderTodayKeyboard(unittest.TestCase):
    def test_keyboard_has_all_buttons(self):
        # Empty state → all checkable buttons in their unchecked form.
        state = DayState(date="2026-05-26")
        kb = bot.render_today_keyboard(state)
        # Flatten all buttons.
        all_buttons = [btn for row in kb.inline_keyboard for btn in row]
        callback_datas = [b.callback_data for b in all_buttons]
        # Expected set of callback_data values:
        expected = {
            "t:shower", "t:walk_am",
            "w:-", "w:+",
            "p:10", "p:20", "p:50", "p:r",
            "t:walk_pm",
            "t:porn", "t:mast", "t:shorts",
            "t:sleep",
        }
        self.assertEqual(set(callback_datas), expected)

    def test_button_text_reflects_state(self):
        state = DayState(date="2026-05-26", morning_shower=True)
        kb = bot.render_today_keyboard(state)
        all_buttons = [btn for row in kb.inline_keyboard for btn in row]
        shower_btn = next(b for b in all_buttons if b.callback_data == "t:shower")
        self.assertIn("✅", shower_btn.text)
        walk_btn = next(b for b in all_buttons if b.callback_data == "t:walk_am")
        self.assertIn("⬜", walk_btn.text)


if __name__ == "__main__":
    unittest.main()
