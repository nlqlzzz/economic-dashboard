import unittest

import pandas as pd

from validation_timing import exclusion_summary, evaluate_paired_release_returns, evaluate_release_return


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

    def test_pair_quality_cleaning_happens_before_common_dates_are_selected(self) -> None:
        dates = pd.date_range("2026-01-01", "2026-04-30", freq="B")
        asset = pd.Series(100.0, index=dates)
        benchmark = pd.Series(100.0, index=dates)
        asset.loc["2026-01-16"] = 10.0
        left, right = evaluate_paired_release_returns(
            asset, benchmark, "2026-01-15", 1, as_of="2026-04-30"
        )
        self.assertEqual((left.status, right.status), ("eligible", "eligible"))
        self.assertEqual((left.start_date, left.end_date), (right.start_date, right.end_date))
        self.assertEqual(left.start_date, pd.Timestamp("2026-01-19"))
        self.assertEqual(left.end_date, pd.Timestamp("2026-02-19"))
        self.assertEqual(left.excluded_dates, (pd.Timestamp("2026-01-16"),))
        self.assertEqual(left.quality_status, "cleaned")
        self.assertIn("1観測除外", left.quality_reason)

    def test_long_missing_end_is_not_silently_used_as_one_month(self) -> None:
        dates = pd.date_range("2026-01-01", "2026-04-30", freq="B")
        prices = pd.Series(100.0, index=dates).drop(
            pd.date_range("2026-02-16", "2026-03-13", freq="B")
        )
        result = evaluate_release_return(prices, "2026-01-15", 1, as_of="2026-04-30")
        self.assertEqual(result.start_date, pd.Timestamp("2026-01-16"))
        self.assertEqual(result.end_date, pd.Timestamp("2026-03-16"))
        self.assertEqual(result.status, "end_too_late")
        self.assertIsNone(result.value)
        self.assertEqual(exclusion_summary([result.status]), "終点価格の遅延超過 1件")

    def test_weekend_adjustment_within_seven_days_is_eligible(self) -> None:
        prices = pd.Series(100.0, index=pd.date_range("2026-01-01", "2026-04-30", freq="B"))
        result = evaluate_release_return(prices, "2026-01-16", 1, as_of="2026-04-30")
        self.assertEqual(result.start_date, pd.Timestamp("2026-01-19"))
        self.assertEqual(result.end_date, pd.Timestamp("2026-02-19"))
        self.assertEqual(result.status, "eligible")

    def test_long_missing_start_is_distinct_from_missing_history(self) -> None:
        prices = pd.Series(100.0, index=pd.date_range("2026-02-02", "2026-05-29", freq="B"))
        delayed = evaluate_release_return(prices, "2026-01-15", 1, as_of="2026-05-29")
        no_history = evaluate_release_return(pd.Series(dtype=float), "2026-01-15", 1)
        self.assertEqual(delayed.status, "start_too_late")
        self.assertEqual(no_history.status, "missing_start")

    def test_pair_is_ineligible_when_one_price_series_is_blocked(self) -> None:
        dates = pd.date_range("2026-01-01", periods=80, freq="B")
        asset = pd.Series(range(100, 180), index=dates, dtype=float)
        asset.iloc[-20:] *= 0.2
        benchmark = pd.Series(range(200, 280), index=dates, dtype=float)
        left, right = evaluate_paired_release_returns(asset, benchmark, dates[5], 1)
        self.assertEqual(left.status, "pair_quality_blocked")
        self.assertEqual(right.status, "pair_quality_blocked")
        self.assertIsNone(left.value)
        self.assertIsNone(right.value)

    def test_one_sided_long_gap_excludes_both_pair_returns_on_same_candidate_end(self) -> None:
        dates = pd.date_range("2026-01-01", "2026-04-30", freq="B")
        missing = pd.date_range("2026-02-16", "2026-03-13", freq="B")
        asset = pd.Series(100.0, index=dates).drop(missing)
        benchmark = pd.Series(100.0, index=dates)
        left, right = evaluate_paired_release_returns(
            asset, benchmark, "2026-01-15", 1, as_of="2026-04-30"
        )
        self.assertEqual((left.status, right.status), ("end_too_late", "end_too_late"))
        self.assertEqual((left.start_date, left.end_date), (right.start_date, right.end_date))
        self.assertEqual(left.end_date, pd.Timestamp("2026-03-16"))


if __name__ == "__main__":
    unittest.main()
