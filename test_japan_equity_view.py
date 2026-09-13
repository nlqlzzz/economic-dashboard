import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

from japan_equity_view import (
    JAPAN_SELECTED_TICKER_KEY,
    JAPAN_STOCK_SECTION_ORDER,
    build_price_reaction_rows,
    build_risk_items,
    build_stock_status_items,
    core20_stock_options,
)
from price_quality import inspect_price_series


def _detail(*, price_available: bool = True, fundamentals_available: bool = True) -> dict[str, object]:
    index = pd.date_range("2026-01-05", periods=140, freq="B")
    prices = pd.Series(range(100, 240), index=index, dtype=float) if price_available else pd.Series(dtype=float)
    quality = inspect_price_series(prices)
    fundamentals = (
        {
            "status": "Available",
            "momentum": "Mixed",
            "forecast": pd.DataFrame(),
            "latest_period": {
                "fiscal_year": "FY2027",
                "fiscal_quarter": "Q1",
                "disclosure_date": "2026-08-07",
            },
        }
        if fundamentals_available
        else {"status": "Unavailable"}
    )
    return {
        "quality": quality,
        "fundamentals": fundamentals,
        "performance": {
            "current": 239.0 if price_available else None,
            "return_1m": 5.0,
            "return_3m": 12.0,
            "return_6m": 20.0,
            "relative_1m": 2.0,
            "relative_3m": 4.0,
            "relative_6m": 7.0,
            "relative_1m_start": pd.Timestamp("2026-06-12"),
            "relative_1m_end": pd.Timestamp("2026-07-13"),
            "relative_3m_start": pd.Timestamp("2026-04-13"),
            "relative_3m_end": pd.Timestamp("2026-07-13"),
            "relative_6m_start": pd.Timestamp("2026-01-13"),
            "relative_6m_end": pd.Timestamp("2026-07-13"),
        },
        "market_exposure": {"status": "Unavailable"},
    }


class JapanEquityViewTest(unittest.TestCase):
    def test_primary_flow_has_requested_order(self) -> None:
        self.assertEqual(
            JAPAN_STOCK_SECTION_ORDER,
            ("業績", "評価水準", "価格の反応", "リスク・確認事項", "補助分析"),
        )

    def test_one_stable_selector_contains_all_core20_stocks(self) -> None:
        options = core20_stock_options()
        self.assertEqual(JAPAN_SELECTED_TICKER_KEY, "japan_selected_ticker")
        self.assertEqual(len(options), 20)
        self.assertEqual(len({row["ticker"] for row in options}), 20)
        self.assertTrue(any(row["ticker"] == "8306.T" for row in options))

    def test_unavailable_price_does_not_hide_available_fundamentals(self) -> None:
        detail = _detail(price_available=False, fundamentals_available=True)
        statuses = dict(build_stock_status_items(detail, {"status": "Unavailable"}))
        self.assertEqual(statuses["株価"], "利用不可")
        self.assertEqual(statuses["決算"], "利用可")

    def test_unavailable_fundamentals_does_not_hide_available_price(self) -> None:
        detail = _detail(price_available=True, fundamentals_available=False)
        statuses = dict(build_stock_status_items(detail, {"status": "Available"}))
        self.assertEqual(statuses["株価"], "利用可")
        self.assertEqual(statuses["決算"], "利用不可")
        self.assertEqual(statuses["現在値"], "239.0円")

    def test_price_reaction_distinguishes_absolute_relative_and_dates(self) -> None:
        rows = build_price_reaction_rows(_detail())
        self.assertEqual(rows[0]["絶対リターン"], "+5.0%")
        self.assertEqual(rows[0]["TOPIX比"], "+2.0pt")
        self.assertEqual(rows[0]["相対開始日"], "2026-06-12")
        self.assertEqual(rows[0]["相対終了日"], "2026-07-13")
        self.assertNotEqual(rows[0]["絶対開始日"], "—")
        self.assertNotEqual(rows[0]["絶対終了日"], "—")

    def test_data_limit_is_not_presented_as_low_risk(self) -> None:
        items = build_risk_items(
            _detail(price_available=False, fundamentals_available=False),
            {"status": "Quality Blocked"},
        )
        self.assertTrue(items["data_limits"])
        self.assertIn("低リスクとは判断できません", items["investment_checks"][0])

    def test_bank_can_use_same_screen_without_assuming_operating_profit(self) -> None:
        option = next(row for row in core20_stock_options() if row["ticker"] == "8306.T")
        self.assertIn("三菱UFJ", option["label"])
        # The view consumes the normalized fundamentals payload; it does not add
        # an operating-profit requirement for bank/insurance selectors.
        items = build_risk_items(_detail(), {"status": "Available"})
        self.assertFalse(any("営業利益" in item for item in items["data_limits"]))

    def test_selector_rerun_keeps_one_ticker_for_the_whole_screen(self) -> None:
        script = """
import pandas as pd
import japan_equity_view as view
from japan_equity import CORE_20, aggregate_by_sector, aggregate_by_theme, build_market_map
from price_quality import inspect_price_series

index = pd.date_range("2024-01-01", periods=320, freq="B")
topix = pd.Series([100 + i * 0.1 for i in range(320)], index=index, dtype=float)
prices = pd.DataFrame({
    stock["ticker"]: [100 + i * (0.08 + position * 0.002) for i in range(320)]
    for position, stock in enumerate(CORE_20)
}, index=index, dtype=float)
market_map = build_market_map(prices, topix)
view._load_fundamentals = lambda *args: {"status": "Unavailable", "reason": "固定データテスト"}
view.render_japan_core_equity(
    market_map,
    aggregate_by_sector(market_map),
    aggregate_by_theme(market_map),
    {},
    prices=prices,
    macro_series={},
    topix_quality=inspect_price_series(topix),
)
"""
        app = AppTest.from_string(script, default_timeout=30).run()
        self.assertFalse(app.exception)
        selector = next(widget for widget in app.selectbox if widget.label == "分析する銘柄")
        selector.set_value("8306.T").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state[JAPAN_SELECTED_TICKER_KEY], "8306.T")
        headings = [item.value for item in app.markdown]
        self.assertTrue(any("三菱UFJフィナンシャル・グループ（8306）" in value for value in headings))
        section_positions = [
            next(index for index, value in enumerate(headings) if section in value)
            for section in JAPAN_STOCK_SECTION_ORDER[:4]
        ]
        self.assertEqual(section_positions, sorted(section_positions))


if __name__ == "__main__":
    unittest.main()
