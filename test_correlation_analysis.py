import unittest

import pandas as pd

from correlation_analysis import (
    build_daily_change_frame,
    correlation_change_alerts,
    correlation_change_summary,
)


class CorrelationChangeTest(unittest.TestCase):
    def test_builds_price_returns_and_yield_changes(self):
        index = pd.date_range("2025-01-01", periods=4, freq="B")
        frame, labels = build_daily_change_frame(
            {
                "株価": pd.Series([100.0, 101.0, 99.0, 102.0], index=index),
                "金利": pd.Series([4.0, 4.1, 4.05, 4.2], index=index),
            },
            {"株価": "return", "金利": "change"},
        )

        self.assertAlmostEqual(frame.loc[index[1], "株価"], 1.0)
        self.assertAlmostEqual(frame.loc[index[1], "金利"], 0.1)
        self.assertEqual(labels["株価"], "観測間騰落率（%）")
        self.assertEqual(labels["金利"], "観測間変化幅（pt）")

    def test_mismatched_return_origins_are_not_compared(self):
        index = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"])
        frame, _ = build_daily_change_frame(
            {
                "銘柄": pd.Series([100.0, None, 121.0], index=index),
                "市場": pd.Series([100.0, 110.0, 121.0], index=index),
            },
            {"銘柄": "return", "市場": "return"},
        )
        self.assertTrue(pd.isna(frame.loc[index[-1], "銘柄"]))
        self.assertTrue(pd.isna(frame.loc[index[-1], "市場"]))
        starts = frame.attrs["period_metadata"].starts
        self.assertEqual(starts.loc[index[-1], "銘柄"], index[0])
        self.assertEqual(starts.loc[index[-1], "市場"], index[1])

    def test_yield_changes_also_require_the_same_start_date(self):
        index = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"])
        frame, _ = build_daily_change_frame(
            {
                "株価": pd.Series([100.0, None, 101.0], index=index),
                "金利": pd.Series([1.0, 1.1, 1.2], index=index),
            },
            {"株価": "return", "金利": "change"},
        )
        self.assertTrue(frame.loc[index[-1]].isna().all())

    def test_compares_current_correlation_with_prior_periods(self):
        index = pd.date_range("2020-01-01", periods=180, freq="B")
        left = pd.Series(
            [((position % 9) - 4) * (1 if position % 2 else -1) for position in range(180)],
            index=index,
            dtype=float,
        )
        right = left.copy()
        right.iloc[-25:] = -left.iloc[-25:]

        summary = correlation_change_summary(left, right)

        self.assertEqual(list(summary["期間"]), ["20日", "60日"])
        self.assertLess(summary.loc[0, "現在"], -0.9)
        self.assertLess(summary.loc[0, "21日差"], 0)
        self.assertGreaterEqual(summary.loc[0, "percentile"], 0)
        self.assertLessEqual(summary.loc[0, "percentile"], 100)
        self.assertEqual(summary.loc[0, "共通観測数"], 180)

    def test_alerts_on_large_change_and_distribution_tail(self):
        summary = pd.DataFrame(
            [
                {
                    "期間": "60日",
                    "21日差": -0.38,
                    "percentile": 8.0,
                }
            ]
        )

        alerts = correlation_change_alerts(summary)

        self.assertEqual(len(alerts), 2)
        self.assertIn("0.38低下", alerts[0])
        self.assertIn("下位8%", alerts[1])


if __name__ == "__main__":
    unittest.main()
