import unittest

import pandas as pd

from japan_equity import (
    CORE_20,
    aggregate_by_sector,
    build_market_map,
    calculate_macro_sensitivity,
    core_tickers,
    expected_proxy_names,
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
        self.assertAlmostEqual(toyota["relative_1m"], toyota["return_1m"] - _return_since(topix, 1))
        self.assertAlmostEqual(toyota["relative_3m"], toyota["return_3m"] - _return_since(topix, 3))

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


def _return_since(series: pd.Series, months: int) -> float:
    clean = series.dropna().sort_index()
    base = clean.loc[: clean.index[-1] - pd.DateOffset(months=months)].iloc[-1]
    return float((clean.iloc[-1] / base - 1) * 100)


if __name__ == "__main__":
    unittest.main()
