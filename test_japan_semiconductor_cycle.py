import unittest

import pandas as pd

from japan_semiconductor_cycle import (
    semiconductor_iip_trends,
    summarize_semiconductor_iip,
)


class JapanSemiconductorCycleTest(unittest.TestCase):
    def setUp(self) -> None:
        dates = pd.date_range("2024-01-01", periods=15, freq="MS")
        self.frame = pd.DataFrame(index=dates)
        values = {
            "生産": [90 + index for index in range(15)],
            "出荷": [88 + index * 1.5 for index in range(15)],
            "在庫": [110 - index for index in range(15)],
            "在庫率": [120 - index * 1.2 for index in range(15)],
        }
        for name, series_values in values.items():
            self.frame[f"{name}_季節調整済"] = series_values
            self.frame[f"{name}_原指数"] = series_values

    def test_summarizes_latest_changes_and_three_month_average(self) -> None:
        result = summarize_semiconductor_iip(self.frame)
        summary = result["summary"].set_index("指標")

        self.assertEqual(list(result["summary"]["指標"]), ["在庫率", "出荷", "生産", "在庫"])
        self.assertAlmostEqual(summary.loc["生産", "最新値"], 104.0)
        self.assertAlmostEqual(summary.loc["生産", "3か月移動平均"], 103.0)
        self.assertAlmostEqual(summary.loc["生産", "前年同月比"], (104 / 92 - 1) * 100)
        self.assertEqual(summary.loc["生産", "対象年月"], pd.Timestamp("2025-03-01"))
        self.assertIn("需給改善方向", result["assessment"])
        self.assertIn("在庫率", result["assessment"])

    def test_reports_missing_indicator_without_failing_all(self) -> None:
        reduced = self.frame.drop(columns=["在庫率_季節調整済", "在庫率_原指数"])

        result = summarize_semiconductor_iip(reduced)

        self.assertEqual(len(result["summary"]), 3)
        self.assertTrue(any("在庫率" in message for message in result["unavailable"]))
        self.assertIn("需給改善方向", result["assessment"])

    def test_does_not_substitute_an_earlier_month_for_year_ago(self) -> None:
        missing_year_ago = self.frame.drop(index=pd.Timestamp("2024-03-01"))

        result = summarize_semiconductor_iip(missing_year_ago)
        summary = result["summary"].set_index("指標")

        self.assertTrue(pd.isna(summary.loc["生産", "前年同月比"]))

    def test_builds_compact_seasonally_adjusted_trends(self) -> None:
        trends = semiconductor_iip_trends(self.frame, months=6)

        self.assertEqual(list(trends), ["在庫率", "出荷", "生産", "在庫"])
        self.assertEqual(len(trends), 6)
        self.assertEqual(trends.index[-1], pd.Timestamp("2025-03-01"))


if __name__ == "__main__":
    unittest.main()
