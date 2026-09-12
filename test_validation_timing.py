import unittest

import pandas as pd

from validation_timing import evaluate_paired_release_returns, evaluate_release_return


class ValidationTimingTest(unittest.TestCase):
    def test_asset_and_benchmark_use_identical_holiday_adjusted_period(self) -> None:
        dates = pd.date_range("2026-01-01", "2026-04-30", freq="B")
        asset = pd.Series(range(100, 100 + len(dates)), index=dates, dtype=float).drop(pd.Timestamp("2026-02-17"))
        benchmark = pd.Series(range(200, 200 + len(dates)), index=dates, dtype=float).drop(pd.Timestamp("2026-01-16"))
        left, right = evaluate_paired_release_returns(
            asset, benchmark, "2026-01-15", 1, as_of="2026-04-30"
        )
        self.assertEqual(left.status, "eligible")
        self.assertEqual((left.start_date, left.end_date), (right.start_date, right.end_date))
        self.assertEqual(left.start_date, pd.Timestamp("2026-01-19"))
        self.assertEqual(left.end_date, pd.Timestamp("2026-02-19"))

    def test_persistent_extreme_move_blocks_return_instead_of_repairing_price(self) -> None:
        dates = pd.date_range("2026-01-01", periods=80, freq="B")
        prices = pd.Series(range(100, 180), index=dates, dtype=float)
        prices.iloc[-20:] *= 0.2
        result = evaluate_release_return(prices, dates[5], 1)
        self.assertEqual(result.status, "quality_blocked")
        self.assertIsNone(result.value)


if __name__ == "__main__":
    unittest.main()
