import unittest

import pandas as pd

from price_quality import inspect_price_series


class PriceQualityTest(unittest.TestCase):
    def test_detects_and_excludes_temporary_scale_break(self) -> None:
        index = pd.date_range("2026-03-20", periods=8, freq="B")
        series = pd.Series([370, 375, 380, 38, 37, 385, 390, 392], index=index, dtype=float)

        result = inspect_price_series(series)

        self.assertEqual(result.status, "cleaned")
        self.assertEqual(len(result.excluded_dates), 2)
        self.assertEqual(len(result.series), 6)
        self.assertLess(result.series.pct_change(fill_method=None).abs().max(), 0.60)

    def test_does_not_remove_persistent_large_market_move(self) -> None:
        index = pd.date_range("2026-01-01", periods=8, freq="B")
        series = pd.Series([100, 102, 101, 35, 36, 34, 37, 38], index=index, dtype=float)

        result = inspect_price_series(series)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.excluded_dates, ())
        self.assertIn(index[3], result.flagged_dates)

    def test_normal_data_passes_unchanged(self) -> None:
        series = pd.Series([100, 101, 99, 103, 105], index=pd.date_range("2026-01-01", periods=5, freq="B"))
        result = inspect_price_series(series)
        self.assertEqual(result.status, "ok")
        pd.testing.assert_series_equal(result.series, series)


if __name__ == "__main__":
    unittest.main()
