import unittest

import pandas as pd

from price_quality import inspect_price_series

from japan_equity import (
    CORE_20,
    aggregate_by_sector,
    build_market_map,
    calculate_macro_sensitivity,
    classify_macro_explainability,
    classify_driver_stability,
    core_tickers,
    estimate_market_model,
    expected_proxy_names,
    residual_returns,
    macro_information_timing,
    top_observed_correlations,
    top_macro_sensitivities,
)
class Core20MasterTest(unittest.TestCase):
    def test_master_contains_twenty_unique_stocks_with_required_metadata(self) -> None:
        self.assertEqual(len(CORE_20), 20)
        self.assertEqual(len(set(core_tickers())), 20)
        self.assertEqual(len({stock["code"] for stock in CORE_20}), 20)
        semiconductor = {"285A.T", "8035.T", "6857.T", "6146.T"}
        self.assertTrue(semiconductor.isdisjoint(core_tickers()))
        for stock in CORE_20:
            self.assertTrue(stock["sector"])
            self.assertTrue(stock["macro_themes"])
            self.assertTrue(stock["primary_drivers"])

    def test_conceptual_drivers_and_available_proxies_are_separate(self) -> None:
        inpex = next(stock for stock in CORE_20 if stock["ticker"] == "1605.T")
        self.assertIn("NATURAL_GAS", inpex["primary_drivers"])
        self.assertNotIn("NATURAL_GAS", expected_proxy_names(inpex))
        self.assertIn("WTI原油先物", expected_proxy_names(inpex))


class JapanMarketMapTest(unittest.TestCase):
    def test_calculates_all_returns_and_topix_relative_returns(self) -> None:
        index = pd.date_range("2025-01-01", periods=100, freq="B")
        prices = pd.DataFrame({ticker: range(100, 200) for ticker in core_tickers()}, index=index, dtype=float)
        topix = pd.Series(range(100, 150), index=index[::2], dtype=float)

        result = build_market_map(prices, topix)
        toyota = result[result["ticker"].eq("7203.T")].iloc[0]

        self.assertAlmostEqual(toyota["return_1d"], (199 / 198 - 1) * 100)
        self.assertAlmostEqual(toyota["return_5d"], (199 / 194 - 1) * 100)
        self.assertIsNotNone(toyota["return_1m"])
        self.assertIsNotNone(toyota["return_3m"])
        for months in (1, 3):
            start, end = toyota[f"relative_{months}m_start"], toyota[f"relative_{months}m_end"]
            expected = ((prices.loc[end, "7203.T"] / prices.loc[start, "7203.T"] - 1)
                        - (topix.loc[end] / topix.loc[start] - 1)) * 100
            self.assertAlmostEqual(toyota[f"relative_{months}m"], expected)

    def test_missing_stock_is_unavailable_without_hiding_other_stocks(self) -> None:
        index = pd.date_range("2025-01-01", periods=80, freq="B")
        prices = pd.DataFrame({"7203.T": range(80, 160)}, index=index, dtype=float)
        topix = pd.Series(range(100, 180), index=index, dtype=float)

        result = build_market_map(prices, topix)

        self.assertEqual(len(result), 20)
        self.assertEqual(result["status"].eq("Available").sum(), 1)
        self.assertTrue(pd.isna(result.loc[result["ticker"].eq("8306.T"), "return_1d"].iloc[0]))

    def test_all_stocks_unavailable_returns_explicit_status_rows(self) -> None:
        result = build_market_map(pd.DataFrame(), pd.Series(dtype=float))

        self.assertEqual(len(result), 20)
        self.assertTrue(result["status"].eq("Unavailable").all())
        self.assertTrue(result["current"].isna().all())

    def test_stale_and_short_history_are_distinct_from_missing_and_quality_blocked(self) -> None:
        index = pd.date_range("2025-01-01", periods=100, freq="B")
        stale = pd.Series(range(100, 180), index=index[:80], dtype=float)
        short = pd.Series(range(100, 120), index=index[-20:], dtype=float)
        frame = pd.DataFrame({"7203.T": stale, "8306.T": short})
        result = build_market_map(frame, pd.Series(range(200, 300), index=index, dtype=float)).set_index("ticker")
        self.assertEqual(result.loc["7203.T", "status"], "Stale")
        self.assertEqual(result.loc["8306.T", "status"], "History Limited")

    def test_sector_aggregation_excludes_missing_stocks_and_handles_single_stock(self) -> None:
        market_map = pd.DataFrame(
            [
                {"sector": "銀行", "status": "Available", "return_1d": 1.0, "return_1m": 2.0, "return_3m": 3.0},
                {"sector": "銀行", "status": "Unavailable", "return_1d": None, "return_1m": None, "return_3m": None},
                {"sector": "電力", "status": "Available", "return_1d": -1.0, "return_1m": -2.0, "return_3m": -3.0},
            ]
        )

        result = aggregate_by_sector(market_map).set_index("sector")

        self.assertEqual(result.loc["銀行", "stock_count"], 2)
        self.assertEqual(result.loc["銀行", "available_count"], 1)
        self.assertEqual(result.loc["銀行", "return_1m"], 2.0)
        self.assertEqual(result.loc["電力", "return_3m"], -3.0)


class MacroSensitivityTest(unittest.TestCase):
    def test_calculates_positive_negative_20_and_60_day_correlations(self) -> None:
        index = pd.date_range("2025-01-01", periods=180, freq="B")
        values = pd.Series([100 + (i % 7) + i * 0.1 for i in range(180)], index=index)
        prices = pd.DataFrame({"7203.T": values}, index=index)
        stock_returns = values.pct_change(fill_method=None).fillna(0)
        positive = (1 + stock_returns).cumprod() * 100
        negative = (1 - stock_returns).cumprod() * 100

        result = calculate_macro_sensitivity(
            prices, {"USD/JPY": positive, "VIX指数": negative}
        ).set_index("macro")

        self.assertIn("USD/JPY", result.index)
        self.assertGreater(result.loc["USD/JPY", "correlation_20d"], 0.9)
        self.assertGreater(result.loc["USD/JPY", "correlation_60d"], 0.9)
        self.assertLess(result.loc["VIX指数", "correlation_60d"], -0.9)

    def test_missing_macro_and_short_history_are_isolated(self) -> None:
        short_index = pd.date_range("2025-01-01", periods=10, freq="B")
        prices = pd.DataFrame({"7203.T": range(100, 110)}, index=short_index, dtype=float)

        result = calculate_macro_sensitivity(
            prices,
            {
                "USD/JPY": pd.Series(dtype=float),
                "VIX指数": pd.Series(range(10), index=short_index, dtype=float),
            },
        )

        self.assertTrue(result.empty)

    def test_top_sensitivity_ranks_by_absolute_sixty_day_correlation(self) -> None:
        frame = pd.DataFrame(
            {
                "ticker": ["7203.T"] * 4,
                "macro": ["A", "B", "C", "D"],
                "correlation_60d": [0.2, -0.9, 0.7, -0.4],
            }
        )
        result = top_macro_sensitivities(frame, "7203.T", limit=3)
        self.assertEqual(list(result["macro"]), ["B", "C", "D"])


class MarketAdjustedSensitivityTest(unittest.TestCase):
    def test_estimates_beta_and_residual(self) -> None:
        index = pd.date_range("2024-01-01", periods=280, freq="B")
        market_return = pd.Series(([0.01, -0.005, 0.003, -0.002] * 70), index=index)
        stock_return = 1.5 * market_return + 0.001
        market = (1 + market_return).cumprod() * 100
        stock = (1 + stock_return).cumprod() * 100

        residual, model = residual_returns(stock, market)

        self.assertTrue(model["available"])
        self.assertAlmostEqual(model["beta"], 1.5, places=2)
        self.assertGreater(len(residual), 250)
        self.assertLess(residual.abs().max(), 1e-10)

    def test_beta_is_unavailable_with_insufficient_observations(self) -> None:
        series = pd.Series(range(100), dtype=float)
        result = estimate_market_model(series, series, minimum_observations=200)
        self.assertFalse(result["available"])

    def test_residual_excludes_rows_whose_return_start_dates_differ(self) -> None:
        index = pd.date_range("2024-01-01", periods=280, freq="B")
        market = pd.Series(range(100, 380), index=index, dtype=float)
        stock = pd.Series(range(200, 480), index=index, dtype=float).drop(index[150])
        residual, model = residual_returns(stock, market)
        self.assertTrue(model["available"])
        self.assertNotIn(index[150], residual.index)
        self.assertNotIn(index[151], residual.index)

    def test_quality_removed_date_does_not_create_a_multiday_residual_pair(self) -> None:
        index = pd.date_range("2024-01-01", periods=280, freq="B")
        market = pd.Series(range(100, 380), index=index, dtype=float)
        raw_stock = pd.Series(range(200, 480), index=index, dtype=float)
        raw_stock.iloc[150] *= 0.1
        quality = inspect_price_series(raw_stock)
        self.assertEqual(quality.status, "cleaned")
        residual, model = residual_returns(quality.series, market)
        self.assertTrue(model["available"])
        self.assertNotIn(index[150], residual.index)
        self.assertNotIn(index[151], residual.index)

    def test_active_return_is_stock_minus_topix(self) -> None:
        index = pd.date_range("2025-01-01", periods=100, freq="B")
        prices = pd.DataFrame({"7203.T": range(100, 200)}, index=index, dtype=float)
        topix = pd.Series(range(100, 180), index=index[:80], dtype=float)
        row = build_market_map(prices, topix).query("ticker == '7203.T'").iloc[0]
        start, end = row["relative_1m_start"], row["relative_1m_end"]
        self.assertEqual(end, topix.index[-1])
        stock_return = prices.loc[end, "7203.T"] / prices.loc[start, "7203.T"] - 1
        market_return = topix.loc[end] / topix.loc[start] - 1
        self.assertAlmostEqual(row["relative_1m"], (stock_return - market_return) * 100)

    def test_missing_dates_never_compare_different_return_intervals(self) -> None:
        index = pd.date_range("2025-01-01", periods=100, freq="B")
        stock = pd.Series(range(100, 200), index=index, dtype=float).drop(index[-22])
        market = pd.Series(range(200, 300), index=index, dtype=float).drop(index[-20])
        row = build_market_map(pd.DataFrame({"7203.T": stock}), market).query("ticker == '7203.T'").iloc[0]
        start, end = row["relative_1m_start"], row["relative_1m_end"]
        self.assertIn(start, stock.index.intersection(market.index))
        self.assertIn(end, stock.index.intersection(market.index))

    def test_us_close_is_explicitly_ex_post_for_japan_decision_time(self) -> None:
        self.assertEqual(macro_information_timing("NASDAQ総合指数"), "same_date_ex_post_not_japan_decision_time")
        self.assertEqual(macro_information_timing("USD/JPY"), "same_date_observation")

    def test_stability_requires_strength_not_only_matching_sign(self) -> None:
        label, _ = classify_driver_stability(
            {120: 0.05, 60: 0.08, 20: 0.03}, {120: 120, 60: 60, 20: 20}
        )
        self.assertEqual(label, "Low")

    def test_stability_recognizes_consistent_positive_and_negative_drivers(self) -> None:
        positive, _ = classify_driver_stability(
            {120: 0.35, 60: 0.42, 20: 0.40}, {120: 120, 60: 60, 20: 20}
        )
        negative, _ = classify_driver_stability(
            {120: -0.32, 60: -0.40, 20: -0.28}, {120: 120, 60: 60, 20: 20}
        )
        self.assertEqual(positive, "High")
        self.assertEqual(negative, "High")

    def test_topix_is_excluded_from_ex_post_macro_ranking(self) -> None:
        frame = pd.DataFrame({
            "ticker": ["7203.T"] * 3,
            "macro": ["TOPIX連動ETF（1306）", "USD/JPY", "WTI原油先物"],
            "correlation_120d": [0.99, 0.2, -0.4],
        })
        result = top_observed_correlations(frame, "7203.T")
        self.assertNotIn("TOPIX連動ETF（1306）", set(result["macro"]))

    def test_macro_explainability_can_identify_unexplained_move(self) -> None:
        exposure = {"status": "Available", "recent_residual_3m": 18.0}
        drivers = [{"status": "Available", "correlation_120d": 0.08, "stability": "Low"}]
        regression = {"adjusted_r2_improvement": -0.01}
        result = classify_macro_explainability(exposure, drivers, regression)
        self.assertEqual(result["classification"], "Macro-unexplained")

    def test_missing_driver_is_unavailable_not_low_explainability(self) -> None:
        result = classify_macro_explainability(
            {"status": "Available", "recent_residual_3m": 1.0},
            [{"status": "Unavailable", "correlation_120d": None, "stability": "Unavailable"}],
            {"status": "Unavailable"},
        )
        self.assertEqual(result["classification"], "Unavailable")


def _return_since(series: pd.Series, months: int) -> float:
    clean = series.dropna().sort_index()
    base = clean.loc[: clean.index[-1] - pd.DateOffset(months=months)].iloc[-1]
    return float((clean.iloc[-1] / base - 1) * 100)


if __name__ == "__main__":
    unittest.main()
