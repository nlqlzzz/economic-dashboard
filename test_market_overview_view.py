import unittest
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from market_overview_view import (
    LATEST_VALUE_COLUMNS,
    LATEST_VALUE_WIDTH_LIMITS,
    build_latest_values_table,
    latest_value_column_widths,
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

    def test_latest_value_table_does_not_stretch_columns_to_container(self):
        source = Path("app.py").read_text(encoding="utf-8")
        table_call = source.index("latest_values_table,")
        table_call_end = source.index(")\n    for name, series", table_call)
        self.assertIn("use_container_width=False", source[table_call:table_call_end])

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
