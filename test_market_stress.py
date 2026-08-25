import unittest

import pandas as pd

from market_stress import calculate_market_stress, stress_level


class MarketStressTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dates = pd.date_range("2020-01-01", periods=1300, freq="B")
        positions = pd.Series(range(1300), index=self.dates, dtype=float)
        self.series = {
            "VIX指数": 15 + positions / 200,
            "S&P 500指数": 3000 + positions + (positions % 20) * 2,
            "UST 10Y": 2 + (positions % 30) / 100,
            "USD/JPY": 100 + positions / 100 + (positions % 15) / 20,
        }

    def test_calculates_score_and_discloses_contributions(self) -> None:
        result = calculate_market_stress(self.series, minimum_history=100)

        self.assertIsNotNone(result["score"])
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)
        self.assertEqual(result["coverage"], 5)
        self.assertEqual(len(result["components"]), 5)
        self.assertAlmostEqual(
            result["components"]["スコア寄与"].sum(), result["score"]
        )
        self.assertTrue(
            result["components"]["過去5年percentile"].between(0, 100).all()
        )
        self.assertTrue((result["components"]["サンプル数"] >= 100).all())

    def test_renormalizes_weights_when_components_are_missing(self) -> None:
        reduced = {name: series for name, series in self.series.items() if name != "VIX指数"}

        result = calculate_market_stress(reduced, minimum_history=100)

        self.assertEqual(result["coverage"], 4)
        self.assertAlmostEqual(result["components"]["ウェイト"].sum(), 100)
        self.assertTrue(any("VIX" in message for message in result["unavailable"]))

    def test_requires_at_least_three_components(self) -> None:
        result = calculate_market_stress(
            {"VIX指数": self.series["VIX指数"]}, minimum_history=100
        )

        self.assertIsNone(result["score"])
        self.assertEqual(result["level"], "算出不可")
        self.assertEqual(result["coverage"], 1)

    def test_reports_insufficient_history(self) -> None:
        short = {name: series.tail(50) for name, series in self.series.items()}

        result = calculate_market_stress(short, minimum_history=100)

        self.assertIsNone(result["score"])
        self.assertTrue(all("不足" in message for message in result["unavailable"]))

    def test_classifies_score_levels(self) -> None:
        self.assertEqual(stress_level(10), "低ストレス")
        self.assertEqual(stress_level(25), "中立")
        self.assertEqual(stress_level(50), "ストレス上昇")
        self.assertEqual(stress_level(75), "高ストレス")


if __name__ == "__main__":
    unittest.main()
