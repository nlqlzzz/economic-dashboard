import unittest

import pandas as pd

from regime_returns import (
    analyze_regime_forward_performance,
    current_regime_labels,
)


class RegimeReturnsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dates = pd.date_range("2020-01-31", periods=12, freq="ME")
        self.history = pd.DataFrame(
            {
                "景気": ["改善"] * 6 + ["悪化"] * 6,
                "物価": ["鈍化"] * 12,
                "金融政策": ["緩和"] * 12,
                "イールドカーブ": ["順イールド"] * 12,
            },
            index=self.dates,
        )
        self.current = {
            "景気": "改善",
            "物価": "鈍化",
            "金融政策": "緩和",
            "イールドカーブ": "順イールド",
        }

    def test_calculates_forward_return_statistics_for_exact_matches(self) -> None:
        prices = pd.Series(range(100, 112), index=self.dates, dtype=float)

        result = analyze_regime_forward_performance(
            self.history,
            self.current,
            {"株式": prices},
            {"株式": "return"},
            horizons=(1,),
            low_sample_threshold=3,
        )

        row = result.iloc[0]
        self.assertEqual(row["サンプル数"], 6)
        self.assertGreater(row["平均"], 0)
        self.assertEqual(row["上昇確率"], 100.0)
        self.assertEqual(row["単位"], "%")
        self.assertEqual(row["注意"], "")

    def test_includes_one_dimension_mismatch_in_near_mode(self) -> None:
        prices = pd.Series(range(100, 112), index=self.dates, dtype=float)

        result = analyze_regime_forward_performance(
            self.history,
            self.current,
            {"株式": prices},
            {"株式": "return"},
            minimum_matching_dimensions=3,
            horizons=(1,),
        )

        self.assertEqual(result.iloc[0]["サンプル数"], 11)

    def test_reports_yield_changes_in_basis_points(self) -> None:
        yields = pd.Series([4.0 + index * 0.1 for index in range(12)], index=self.dates)

        result = analyze_regime_forward_performance(
            self.history,
            self.current,
            {"米10年金利": yields},
            {"米10年金利": "change_bp"},
            horizons=(1,),
        )

        self.assertAlmostEqual(result.iloc[0]["平均"], 10.0)
        self.assertEqual(result.iloc[0]["単位"], "bp")

    def test_converts_current_regime_to_history_labels(self) -> None:
        labels = current_regime_labels(
            {
                "labor": {"status": "悪化"},
                "inflation": {"status": "上昇"},
                "policy": {"status": "引き締め"},
                "curve": {"status": "逆イールド"},
            }
        )

        self.assertEqual(
            labels,
            {
                "景気": "悪化",
                "物価": "上昇",
                "金融政策": "引き締め",
                "イールドカーブ": "逆イールド",
            },
        )


if __name__ == "__main__":
    unittest.main()
