import unittest

import pandas as pd

from semiconductor_validation import (
    add_global_condition_signals,
    analyze_release_aware_correlation,
    analyze_release_aware_returns,
    build_overseas_validation_signals,
    calculate_market_momentum,
    classify_price_vs_fundamentals,
    sample_warning,
)


class SemiconductorValidationTest(unittest.TestCase):
    def test_price_vs_fundamentals_four_classifications(self) -> None:
        pulse_up = {"state": "Improving", "coverage": 3}
        pulse_down = {"state": "Weakening", "coverage": 3}
        market_up = {"state": "Rising", "direction": 1, "returns": {3: 10}}
        market_down = {"state": "Falling", "direction": -1, "returns": {3: -10}}
        self.assertEqual(classify_price_vs_fundamentals(market_up, pulse_up)["state"], "Aligned Positive")
        self.assertEqual(classify_price_vs_fundamentals(market_up, pulse_down)["state"], "Expectation-led / Divergence")
        self.assertEqual(classify_price_vs_fundamentals(market_down, pulse_up)["state"], "Fundamentals stronger than market")
        self.assertEqual(classify_price_vs_fundamentals(market_down, pulse_down)["state"], "Aligned Negative")

    def test_price_vs_fundamentals_handles_missing(self) -> None:
        missing_market = {"state": "Unavailable", "direction": 0, "returns": {}}
        self.assertEqual(classify_price_vs_fundamentals(missing_market, {"state": "Improving"})["state"], "Unavailable")
        self.assertEqual(classify_price_vs_fundamentals({"state": "Rising", "direction": 1}, {"state": "Unavailable"})["state"], "Unavailable")

    def test_market_momentum_uses_multi_month_change(self) -> None:
        prices = pd.Series([100, 105, 110, 120], index=pd.to_datetime(["2026-01-02", "2026-02-02", "2026-03-02", "2026-04-02"]))
        result = calculate_market_momentum(prices)
        self.assertEqual(result["state"], "Rising")
        self.assertAlmostEqual(result["returns"][3], 20.0)

    def test_strict_signals_exclude_unknown_release_dates(self) -> None:
        frame = _records()
        strict = build_overseas_validation_signals(frame, strict=True)
        provisional = build_overseas_validation_signals(frame, strict=False)
        self.assertNotIn("taiwan_orders", strict.columns)
        self.assertIn("taiwan_orders", provisional.columns)
        self.assertEqual(strict.attrs["validation_mode"], "strict")
        self.assertEqual(provisional.attrs["validation_mode"], "provisional")

    def test_partial_periods_never_enter_historical_signals(self) -> None:
        frame = _records()
        result = build_overseas_validation_signals(frame, strict=False)
        self.assertNotIn("korea_partial", result.columns)

    def test_future_return_starts_before_release_and_targets_after_release(self) -> None:
        prices = pd.Series(range(100, 221), index=pd.date_range("2025-12-01", periods=121, freq="D"), dtype=float)
        condition = pd.Series([True], index=[pd.Timestamp("2026-01-15")])
        result = analyze_release_aware_returns(condition, prices, horizons=(1,))
        base = prices.loc[prices.index < pd.Timestamp("2026-01-15")].iloc[-1]
        target = prices.loc[prices.index >= pd.Timestamp("2026-02-15")].iloc[0]
        self.assertAlmostEqual(result.iloc[0]["平均"], (target / base - 1) * 100)

    def test_release_aware_correlation_handles_irregular_months_without_future_leak(self) -> None:
        prices = pd.Series(range(100, 301), index=pd.date_range("2025-12-01", periods=201, freq="D"), dtype=float)
        signal = pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-01-15", "2026-03-20"]))
        result = analyze_release_aware_correlation(signal, prices, horizons=(1,))
        self.assertEqual(result.iloc[0]["サンプル数"], 2)
        self.assertFalse(pd.isna(result.iloc[0]["相関"]))

    def test_conditions_and_low_sample_warnings(self) -> None:
        signals = pd.DataFrame(
            {"taiwan_orders": [1.0, 2.0, 1.0], "korea_semiconductor_exports_monthly": [5.0, 6.0, 30.0]},
            index=pd.to_datetime(["2026-01-20", "2026-02-20", "2026-03-20"]),
        )
        enriched = add_global_condition_signals(signals)
        self.assertIn("Taiwan AND Korea Improving", enriched)
        self.assertTrue(enriched.iloc[1]["Taiwan AND Korea Improving"])
        self.assertIn("非常に少ない", sample_warning(4))
        self.assertIn("参考値", sample_warning(8))
        self.assertEqual(sample_warning(10), "")


def _records() -> pd.DataFrame:
    base = {
        "region": "Taiwan", "series_name": "orders", "reference_period": pd.Timestamp("2026-01-01"),
        "release_date": pd.NaT, "value": 100.0, "unit": "million USD", "yoy": 5.0,
        "frequency": "monthly", "source_name": "official", "source_url": "https://official.example",
        "publication_stage": "official_monthly", "is_partial_period": False,
        "period_start": pd.Timestamp("2026-01-01"), "period_end": pd.Timestamp("2026-01-31"),
        "working_days": None, "fetched_at": pd.Timestamp("2026-02-01"), "currency": "USD",
        "is_derived": False, "data_vintage": None, "yoy_is_derived": True,
    }
    return pd.DataFrame([
        {**base, "series_id": "taiwan_orders"},
        {**base, "region": "Korea", "series_id": "korea_semiconductor_exports_monthly", "release_date": pd.Timestamp("2026-02-01")},
        {**base, "region": "Korea", "series_id": "korea_partial", "release_date": pd.Timestamp("2026-01-11"), "is_partial_period": True},
    ])


if __name__ == "__main__":
    unittest.main()
