import unittest
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from market_range import (
    MARKET_RANGE_DEFAULT,
    calculate_market_range,
    filter_market_series,
    market_data_bounds,
    market_request_start,
)
from market_range_view import MARKET_RANGE_MOBILE_CSS


class MarketRangeTest(unittest.TestCase):
    def setUp(self):
        self.latest = pd.Timestamp("2026-09-18")
        self.earliest = pd.Timestamp("2018-04-02")

    def resolve(self, preset):
        return calculate_market_range(
            preset, self.latest, self.earliest, "2026-02-01", "2026-08-31"
        )

    def test_default_is_ytd(self):
        self.assertEqual(MARKET_RANGE_DEFAULT, "YTD")

    def test_month_and_year_presets_use_latest_data_date(self):
        expected = {
            "1M": "2026-08-18",
            "3M": "2026-06-18",
            "6M": "2026-03-18",
            "1Y": "2025-09-18",
            "3Y": "2023-09-18",
            "5Y": "2021-09-18",
        }
        for preset, start in expected.items():
            with self.subTest(preset=preset):
                self.assertEqual(self.resolve(preset), (pd.Timestamp(start), self.latest))

    def test_ytd_and_all(self):
        self.assertEqual(self.resolve("YTD"), (pd.Timestamp("2026-01-01"), self.latest))
        self.assertEqual(self.resolve("ALL"), (self.earliest, self.latest))

    def test_custom_uses_sidebar_dates(self):
        self.assertEqual(
            self.resolve("Custom"),
            (pd.Timestamp("2026-02-01"), pd.Timestamp("2026-08-31")),
        )

    def test_custom_rejects_reversed_dates(self):
        with self.assertRaises(ValueError):
            calculate_market_range("Custom", self.latest, self.earliest, "2026-09-01", "2026-08-01")

    def test_request_start_has_yoy_buffer(self):
        self.assertLess(market_request_start("1M", "2026-09-21", "2026-01-01"), pd.Timestamp("2025-08-21").date())
        self.assertEqual(market_request_start("ALL", "2026-09-21", "2026-01-01").year, 1900)

    def test_bounds_and_filter_tolerate_sparse_short_series(self):
        sparse = pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-09-01", "2026-09-18"]))
        one = pd.Series([3.0], index=pd.to_datetime(["2026-09-10"]))
        bounds = market_data_bounds({"sparse": sparse, "one": one}, "2026-09-21")
        self.assertEqual(bounds, (pd.Timestamp("2026-09-01"), pd.Timestamp("2026-09-18")))
        filtered = filter_market_series({"sparse": sparse, "one": one}, "2026-09-15", "2026-09-18")
        self.assertEqual(list(filtered), ["sparse"])
        self.assertEqual(len(filtered["sparse"]), 1)

    def test_empty_data_returns_no_bounds(self):
        self.assertIsNone(market_data_bounds({"empty": pd.Series(dtype=float)}, "2026-09-21"))

    def test_control_is_placed_after_market_chart_and_before_latest_values(self):
        source = Path("app.py").read_text(encoding="utf-8")
        chart = source.index('st.plotly_chart(figure, use_container_width=True, config=exploratory_chart_config())')
        control = source.index("render_market_range_selector(", chart)
        latest = source.index('st.markdown(f"### 最新値', control)
        self.assertLess(chart, control)
        self.assertLess(control, latest)

    def test_mobile_css_keeps_presets_in_one_scrollable_row(self):
        self.assertIn("flex-wrap: nowrap !important", MARKET_RANGE_MOBILE_CSS)
        self.assertIn("overflow-x: auto !important", MARKET_RANGE_MOBILE_CSS)
        self.assertIn("white-space: nowrap !important", MARKET_RANGE_MOBILE_CSS)
        self.assertIn("word-break: keep-all !important", MARKET_RANGE_MOBILE_CSS)

    def test_apptest_shows_all_presets_and_distinguishes_custom(self):
        app = AppTest.from_string(
            """
import streamlit as st
from market_range import MARKET_RANGE_DEFAULT
from market_range_view import MARKET_RANGE_MOBILE_CSS, render_market_range_selector
st.session_state.setdefault("market_range_preset", MARKET_RANGE_DEFAULT)
st.markdown(MARKET_RANGE_MOBILE_CSS, unsafe_allow_html=True)
render_market_range_selector("YTD", "2026-01-01", "2026-09-18", "2026-09-18")
""",
            default_timeout=30,
        ).run()
        self.assertFalse(app.exception)
        self.assertEqual(
            app.radio[0].options,
            ["1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "ALL", "任意"],
        )
        self.assertEqual(app.radio[0].value, "YTD")
        self.assertTrue(any("最新データ日基準: 2026-09-18" in item.value for item in app.caption))


if __name__ == "__main__":
    unittest.main()
