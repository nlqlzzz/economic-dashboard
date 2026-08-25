import unittest

import pandas as pd

from event_analysis import EVENT_HISTORY, analyze_event_reactions


class EventAnalysisTest(unittest.TestCase):
    def test_event_history_is_ordered_and_unique(self):
        for event_name, dates in EVENT_HISTORY.items():
            with self.subTest(event=event_name):
                parsed = pd.DatetimeIndex(pd.to_datetime(dates))
                self.assertTrue(parsed.is_monotonic_increasing)
                self.assertTrue(parsed.is_unique)
                self.assertGreaterEqual(len(parsed), 16)

    def test_calculates_returns_from_previous_close(self):
        index = pd.date_range("2025-01-01", periods=35, freq="B")
        prices = pd.Series(range(100, 135), index=index, dtype=float)
        event_date = index[5]

        result = analyze_event_reactions(
            [event_date], {"株価": prices}, {"株価": "return"}
        ).set_index("期間")

        self.assertAlmostEqual(result.loc["当日", "平均"], (105 / 104 - 1) * 100)
        self.assertAlmostEqual(result.loc["翌営業日", "平均"], (106 / 104 - 1) * 100)
        self.assertAlmostEqual(result.loc["5営業日後", "平均"], (110 / 104 - 1) * 100)
        self.assertAlmostEqual(result.loc["20営業日後", "平均"], (125 / 104 - 1) * 100)
        self.assertEqual(result.loc["当日", "サンプル数"], 1)
        self.assertEqual(result.loc["当日", "注意"], "サンプル少")

    def test_uses_first_market_day_for_weekend_event(self):
        index = pd.date_range("2025-01-02", periods=8, freq="B")
        prices = pd.Series(range(100, 108), index=index, dtype=float)

        result = analyze_event_reactions(
            ["2025-01-04"], {"株価": prices}, {"株価": "return"}, horizons=(0,)
        )

        self.assertAlmostEqual(result.loc[0, "平均"], (102 / 101 - 1) * 100)

    def test_reports_yield_changes_in_basis_points(self):
        index = pd.date_range("2025-01-01", periods=8, freq="B")
        yields = pd.Series([4.0, 4.0, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6], index=index)

        result = analyze_event_reactions(
            [index[2]], {"金利": yields}, {"金利": "change_bp"}, horizons=(0,)
        )

        self.assertAlmostEqual(result.loc[0, "平均"], 10.0)
        self.assertEqual(result.loc[0, "単位"], "bp")


if __name__ == "__main__":
    unittest.main()
