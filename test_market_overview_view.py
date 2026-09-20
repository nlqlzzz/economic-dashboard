import unittest
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from market_overview_view import (
    LATEST_VALUE_COLUMNS,
    LATEST_VALUE_WIDTH_LIMITS,
    MARKET_CHART_PLOT_HEIGHT,
    MARKET_CHART_TOP_MARGIN,
    build_latest_values_table,
    latest_value_column_widths,
    latest_values_table_html,
    market_chart_dimensions,
)


class MarketOverviewViewTest(unittest.TestCase):
    def test_latest_values_table_has_requested_columns_and_values(self):
        series = pd.Series(
            [100.0, 105.0],
            index=pd.to_datetime(["2026-09-17", "2026-09-18"]),
        )
        series.attrs.update({"unit": "米ドル", "source": "yahoo"})
        table = build_latest_values_table(
            {"情報技術（XLK）": series},
            {
                "情報技術（XLK）": {
                    "unit": "米ドル",
                    "source": "yahoo",
                    "category": "米国セクター",
                }
            },
            {"情報技術（XLK）"},
            {"yahoo": "Yahoo Finance"},
            normalized=False,
        )
        self.assertEqual(list(table.columns), LATEST_VALUE_COLUMNS)
        self.assertEqual(table.iloc[0].to_dict(), {
            "指標名": "情報技術（XLK）",
            "最新の値": "105.00 米ドル",
            "直前の値との比": "+5.00（+5.00%）",
            "重要度": "主要",
            "データ日": "2026-09-18",
            "データ元": "Yahoo Finance",
        })

    def test_latest_values_table_handles_one_observation(self):
        series = pd.Series([7.0], index=pd.to_datetime(["2026-09-18"]))
        series.attrs.update({"source": "fred"})
        table = build_latest_values_table(
            {"指標": series},
            {"指標": {"unit": "%", "source": "fred", "category": "金利"}},
            set(),
            {"fred": "FRED"},
            normalized=True,
        )
        self.assertEqual(table.iloc[0]["最新の値"], "7.00")
        self.assertEqual(table.iloc[0]["直前の値との比"], "—")
        self.assertEqual(table.iloc[0]["重要度"], "通常")

    def test_latest_value_columns_fit_content_with_bounded_width(self):
        table = pd.DataFrame(
            [{
                "指標名": "非常に長い指標名" * 30,
                "最新の値": "105.00",
                "直前の値との比": "+5.00（+5.00%）",
                "重要度": "主要",
                "データ日": "2026-09-18",
                "データ元": "Yahoo Finance",
            }],
            columns=LATEST_VALUE_COLUMNS,
        )
        widths = latest_value_column_widths(table)
        self.assertEqual(widths["指標名"], LATEST_VALUE_WIDTH_LIMITS["指標名"][1])
        self.assertLess(widths["重要度"], LATEST_VALUE_WIDTH_LIMITS["重要度"][1])
        for column, width in widths.items():
            minimum, maximum = LATEST_VALUE_WIDTH_LIMITS[column]
            self.assertGreaterEqual(width, minimum)
            self.assertLessEqual(width, maximum)

    def test_latest_value_table_is_static_scrollable_and_escapes_content(self):
        table = pd.DataFrame(
            [{column: "<unsafe>" for column in LATEST_VALUE_COLUMNS}],
            columns=LATEST_VALUE_COLUMNS,
        )
        html = latest_values_table_html(table)
        self.assertIn('class="market-latest-values-wrap"', html)
        self.assertIn("overflow-x: auto", html)
        self.assertIn("table-layout: fixed", html)
        self.assertIn("text-overflow: ellipsis", html)
        self.assertNotIn("<unsafe>", html)
        self.assertIn("&lt;unsafe&gt;", html)

    def test_market_overview_orders_returns_before_today_summary(self):
        source = Path("app.py").read_text(encoding="utf-8")
        latest = source.index('st.markdown(f"### 最新値')
        returns = source.index('st.subheader("騰落率")', latest)
        today = source.index('st.subheader("今日のマーケット")', latest)
        self.assertLess(latest, returns)
        self.assertLess(returns, today)

    def test_many_series_expand_total_chart_without_shrinking_plot_area(self):
        two_height, two_bottom = market_chart_dimensions(2)
        eleven_height, eleven_bottom = market_chart_dimensions(11)
        self.assertGreater(eleven_height, two_height)
        self.assertGreater(eleven_bottom, two_bottom)
        self.assertEqual(
            two_height - MARKET_CHART_TOP_MARGIN - two_bottom,
            MARKET_CHART_PLOT_HEIGHT,
        )
        self.assertEqual(
            eleven_height - MARKET_CHART_TOP_MARGIN - eleven_bottom,
            MARKET_CHART_PLOT_HEIGHT,
        )

    def test_market_chart_uses_dynamic_height_and_bottom_margin(self):
        source = Path("app.py").read_text(encoding="utf-8")
        self.assertIn("market_chart_dimensions(len(series_to_plot))", source)
        self.assertIn("height=chart_height", source)
        self.assertIn("b=chart_bottom_margin", source)

    def test_sidebar_category_can_be_closed_from_bottom(self):
        app = AppTest.from_string(
            '''
import streamlit as st
from market_overview_view import render_sidebar_indicator_category
with st.sidebar:
    render_sidebar_indicator_category("米国セクター", {
        "情報技術（XLK）": {"category": "米国セクター"},
        "金融（XLF）": {"category": "米国セクター"},
    })
''',
            default_timeout=30,
        ).run()
        self.assertEqual([button.label for button in app.sidebar.button], ["› 米国セクター"])
        app.sidebar.button[0].click().run()
        labels = [button.label for button in app.sidebar.button]
        self.assertIn("⌃ 米国セクターを閉じる", labels)
        self.assertEqual(len(app.sidebar.checkbox), 2)
        app.sidebar.checkbox[0].check().run()
        app.sidebar.button[-1].click().run()
        self.assertEqual([button.label for button in app.sidebar.button], ["› 米国セクター"])
        app.sidebar.button[0].click().run()
        self.assertTrue(app.sidebar.checkbox[0].value)


if __name__ == "__main__":
    unittest.main()
