import unittest

import pandas as pd

from similar_periods import build_point_in_time_features, find_similar_periods


class SimilarPeriodsTest(unittest.TestCase):
    def test_standardization_does_not_change_past_when_future_is_added(self) -> None:
        dates = pd.date_range("2020-01-01", periods=8, freq="B")
        original = pd.DataFrame({"feature": range(8)}, index=dates, dtype=float)
        extended = pd.concat(
            [original, pd.DataFrame({"feature": [1000.0]}, index=[dates[-1] + pd.offsets.BDay()])]
        )

        original_standardized, _ = build_point_in_time_features(original, minimum_history=3)
        extended_standardized, _ = build_point_in_time_features(extended, minimum_history=3)

        pd.testing.assert_series_equal(
            original_standardized["feature"],
            extended_standardized.loc[original_standardized.index, "feature"],
            check_freq=False,
        )

    def test_excludes_nearby_candidates_and_calculates_returns(self) -> None:
        dates = pd.date_range("2020-01-01", periods=90, freq="B")
        feature = pd.DataFrame(
            {"feature": [float((position % 20) - 10) for position in range(90)]},
            index=dates,
        )
        prices = pd.Series(range(100, 190), index=dates, dtype=float)

        matches, summary, contributions = find_similar_periods(
            feature,
            prices,
            "return",
            neighbor_count=3,
            exclusion_sessions=5,
            horizons=(1, 5, 20),
        )

        positions = [dates.get_loc(day) for day in matches["類似局面の日付"]]
        self.assertEqual(len(matches), 3)
        self.assertTrue(
            all(
                abs(left - right) > 5
                for index, left in enumerate(positions)
                for right in positions[index + 1 :]
            )
        )
        self.assertTrue(all(len(dates) - 1 - position > 5 for position in positions))
        self.assertEqual(summary["サンプル数"].tolist(), [3, 3, 3])
        self.assertGreater(matches["1営業日後"].min(), 0)
        self.assertEqual(len(contributions), 3)

    def test_macro_mismatch_is_reported_as_contribution(self) -> None:
        dates = pd.date_range("2020-01-01", periods=50, freq="B")
        features = pd.DataFrame(
            {
                "numeric": [float(position % 10) for position in range(50)],
                "マクロ:景気": ["改善"] * 25 + ["悪化"] * 25,
            },
            index=dates,
        )
        prices = pd.Series(range(100, 150), index=dates, dtype=float)

        _, _, contributions = find_similar_periods(
            features,
            prices,
            "return",
            neighbor_count=2,
            exclusion_sessions=2,
            horizons=(1,),
        )

        self.assertIn("マクロ:景気", contributions["特徴量"].tolist())
        self.assertTrue(contributions["距離への寄与率"].between(0, 100).all())

    def test_yield_outcomes_are_basis_points(self) -> None:
        dates = pd.date_range("2020-01-01", periods=45, freq="B")
        features = pd.DataFrame(
            {"numeric": [float(position % 5) for position in range(45)]}, index=dates
        )
        yields = pd.Series([4 + position * 0.01 for position in range(45)], index=dates)

        matches, summary, _ = find_similar_periods(
            features,
            yields,
            "change_bp",
            neighbor_count=1,
            exclusion_sessions=2,
            horizons=(1,),
        )

        self.assertAlmostEqual(matches.iloc[0]["1営業日後"], 1.0)
        self.assertEqual(summary.iloc[0]["単位"], "bp")


if __name__ == "__main__":
    unittest.main()
