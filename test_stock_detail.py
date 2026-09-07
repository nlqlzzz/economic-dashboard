import unittest

import pandas as pd

from japan_equity import CORE_20, cumulative_residual_return
from japan_equity_view import _missing
from price_quality import inspect_price_series
from stock_detail import (
    build_stock_detail_analysis,
    classify_stock_specific_move,
    select_core20_anchors,
)


def _prices(periods: int = 320) -> tuple[pd.DataFrame, pd.Series, dict[str, pd.Series]]:
    index = pd.date_range("2024-01-01", periods=periods, freq="B")
    topix = pd.Series([100 + index_number * 0.12 for index_number in range(periods)], index=index, dtype=float)
    frame = pd.DataFrame(
        {
            stock["ticker"]: [100 + index_number * (0.10 + position * 0.003) for index_number in range(periods)]
            for position, stock in enumerate(CORE_20)
        },
        index=index,
        dtype=float,
    )
    macros = {
        "USD/JPY": pd.Series([140 + index_number * 0.02 for index_number in range(periods)], index=index),
        "JGB 10Y": pd.Series([0.7 + index_number * 0.001 for index_number in range(periods)], index=index),
        "UST 10Y": pd.Series([4.0 + index_number * 0.001 for index_number in range(periods)], index=index),
        "WTI原油先物": pd.Series([70 + index_number * 0.03 for index_number in range(periods)], index=index),
        "SOX指数": pd.Series([3000 + index_number * 2 for index_number in range(periods)], index=index),
        "NASDAQ総合指数": pd.Series([15000 + index_number * 3 for index_number in range(periods)], index=index),
        "S&P 500指数": pd.Series([4500 + index_number * 1 for index_number in range(periods)], index=index),
        "中国：上海総合指数": pd.Series([3000 + index_number * 0.5 for index_number in range(periods)], index=index),
        "VIX指数": pd.Series([20 - index_number * 0.005 for index_number in range(periods)], index=index),
    }
    return frame, topix, macros


class StockDetailTest(unittest.TestCase):
    def test_anchor_selection_uses_theme_and_driver_evidence(self) -> None:
        inpex = next(stock for stock in CORE_20 if stock["ticker"] == "1605.T")
        anchors = select_core20_anchors(inpex, CORE_20)

        self.assertTrue(anchors)
        mitsubishi = next(anchor for anchor in anchors if anchor["ticker"] == "8058.T")
        self.assertTrue(any("共通テーマ" in reason for reason in mitsubishi["anchor_reasons"]))
        self.assertTrue(any("共通Driver" in reason for reason in mitsubishi["anchor_reasons"]))

    def test_anchor_selection_can_return_no_strong_anchor(self) -> None:
        stock = {"ticker": "9999.T", "sector": "独自", "macro_themes": ("独自テーマ",), "primary_drivers": ("UNIQUE",)}
        self.assertEqual(select_core20_anchors(stock, CORE_20), [])

    def test_residual_period_is_compounded_not_simple_sum(self) -> None:
        residual = pd.Series([1.0, 1.0, 1.0])
        self.assertAlmostEqual(cumulative_residual_return(residual, 3), 3.0301, places=3)

    def test_stock_specific_classifications(self) -> None:
        unexplained = classify_stock_specific_move(
            {"explainability": {"classification": "Macro-unexplained"}}, {"residual_3m": 15.0}, []
        )
        consistent = classify_stock_specific_move(
            {"explainability": {"classification": "High"}}, {"residual_3m": 3.0}, []
        )
        self.assertEqual(unexplained["classification"], "Stock-specific / Unexplained")
        self.assertEqual(consistent["classification"], "Macro-consistent")

    def test_proxy_missing_value_is_safe_for_ui(self) -> None:
        self.assertTrue(_missing(None))
        self.assertTrue(_missing(float("nan")))
        self.assertTrue(_missing(pd.NA))
        self.assertFalse(_missing("SOX指数"))

    def test_arbitrary_ticker_can_build_stock_detail(self) -> None:
        prices, topix, macros = _prices()
        stock = {
            "ticker": "9999.T", "code": "9999", "name": "任意銘柄", "sector": "任意セクター",
            "macro_themes": ("円安",), "primary_drivers": ("USDJPY",),
        }
        arbitrary_prices = prices["7203.T"] * 1.05
        detail = build_stock_detail_analysis(
            stock, arbitrary_prices, inspect_price_series(topix), macros, CORE_20, prices
        )
        self.assertEqual(detail["stock"]["ticker"], "9999.T")
        self.assertIn("return_1m", detail["performance"])
        self.assertIn("classification", detail["movement"])

    def test_each_core20_stock_can_build_detail(self) -> None:
        prices, topix, macros = _prices()
        topix_quality = inspect_price_series(topix)
        for stock in CORE_20:
            detail = build_stock_detail_analysis(
                stock, prices[stock["ticker"]], topix_quality, macros, CORE_20, prices
            )
            self.assertEqual(detail["stock"]["ticker"], stock["ticker"])
            self.assertIn("market_exposure", detail)

    def test_blocked_price_quality_isolated(self) -> None:
        prices, topix, macros = _prices()
        broken = prices["7203.T"].copy()
        broken.iloc[-3:] = broken.iloc[-3:] * 0.2
        detail = build_stock_detail_analysis(
            CORE_20[0], broken, inspect_price_series(topix), macros, CORE_20, prices
        )
        self.assertEqual(detail["market_exposure"]["status"], "Unavailable")


if __name__ == "__main__":
    unittest.main()
