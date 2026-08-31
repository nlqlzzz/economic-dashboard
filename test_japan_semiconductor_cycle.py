import unittest

import pandas as pd

from japan_semiconductor_cycle import (
    analyze_release_aware_lead_lag,
    analyze_semiconductor_condition_returns,
    build_inventory_cycle_map,
    build_semiconductor_backtest_signals,
    classify_inventory_cycle,
    electronic_computer_order_trends,
    semiconductor_iip_trends,
    summarize_electronic_computer_orders,
    summarize_semiconductor_iip,
)


class JapanSemiconductorCycleTest(unittest.TestCase):
    def setUp(self) -> None:
        dates = pd.date_range("2024-01-01", periods=15, freq="MS")
        self.frame = pd.DataFrame(index=dates)
        values = {
            "生産": [90 + index for index in range(15)],
            "出荷": [88 + index * 1.5 for index in range(15)],
            "在庫": [110 - index for index in range(15)],
            "在庫率": [120 - index * 1.2 for index in range(15)],
        }
        for name, series_values in values.items():
            self.frame[f"{name}_季節調整済"] = series_values
            self.frame[f"{name}_原指数"] = series_values

    def test_summarizes_latest_changes_and_three_month_average(self) -> None:
        result = summarize_semiconductor_iip(self.frame)
        summary = result["summary"].set_index("指標")

        self.assertEqual(list(result["summary"]["指標"]), ["在庫率", "出荷", "生産", "在庫"])
        self.assertAlmostEqual(summary.loc["生産", "最新値"], 104.0)
        self.assertAlmostEqual(summary.loc["生産", "3か月移動平均"], 103.0)
        self.assertAlmostEqual(summary.loc["生産", "前年同月比"], (104 / 92 - 1) * 100)
        self.assertEqual(summary.loc["生産", "対象年月"], pd.Timestamp("2025-03-01"))
        self.assertIn("需給改善方向", result["assessment"])
        self.assertIn("在庫率", result["assessment"])

    def test_reports_missing_indicator_without_failing_all(self) -> None:
        reduced = self.frame.drop(columns=["在庫率_季節調整済", "在庫率_原指数"])

        result = summarize_semiconductor_iip(reduced)

        self.assertEqual(len(result["summary"]), 3)
        self.assertTrue(any("在庫率" in message for message in result["unavailable"]))
        self.assertIn("需給改善方向", result["assessment"])

    def test_does_not_substitute_an_earlier_month_for_year_ago(self) -> None:
        missing_year_ago = self.frame.drop(index=pd.Timestamp("2024-03-01"))

        result = summarize_semiconductor_iip(missing_year_ago)
        summary = result["summary"].set_index("指標")

        self.assertTrue(pd.isna(summary.loc["生産", "前年同月比"]))

    def test_builds_compact_seasonally_adjusted_trends(self) -> None:
        trends = semiconductor_iip_trends(self.frame, months=6)

        self.assertEqual(list(trends), ["在庫率", "出荷", "生産", "在庫"])
        self.assertEqual(len(trends), 6)
        self.assertEqual(trends.index[-1], pd.Timestamp("2025-03-01"))

    def test_builds_inventory_cycle_from_exact_year_ago_values(self) -> None:
        cycle = build_inventory_cycle_map(self.frame, months=2)

        self.assertEqual(len(cycle), 2)
        self.assertEqual(cycle.iloc[-1]["対象年月"], pd.Timestamp("2025-03-01"))
        self.assertAlmostEqual(cycle.iloc[-1]["出荷前年比"], (109 / 91 - 1) * 100)
        self.assertAlmostEqual(cycle.iloc[-1]["在庫前年比"], (96 / 108 - 1) * 100)
        self.assertEqual(cycle.iloc[-1]["局面候補"], "需給改善方向")

    def test_inventory_cycle_skips_month_without_exact_year_ago(self) -> None:
        missing_year_ago = self.frame.drop(index=pd.Timestamp("2024-03-01"))

        cycle = build_inventory_cycle_map(missing_year_ago)

        self.assertNotIn(pd.Timestamp("2025-03-01"), set(cycle["対象年月"]))

    def test_classifies_all_inventory_cycle_quadrants(self) -> None:
        self.assertEqual(classify_inventory_cycle(1, -1), "需給改善方向")
        self.assertEqual(classify_inventory_cycle(1, 1), "需要拡大・在庫積み増し")
        self.assertEqual(classify_inventory_cycle(-1, 1), "需要減速・在庫過剰リスク")
        self.assertEqual(classify_inventory_cycle(-1, -1), "減産・在庫調整")

    def test_summarizes_smoothed_electronic_computer_order_trend(self) -> None:
        dates = pd.date_range("2024-01-01", periods=18, freq="MS")
        orders = pd.Series(range(100, 118), index=dates, dtype=float)

        summary = summarize_electronic_computer_orders(orders)

        self.assertEqual(summary["最新値"], 117.0)
        self.assertEqual(summary["3か月移動平均"], 116.0)
        self.assertAlmostEqual(summary["前年同月比"], (117 / 105 - 1) * 100)
        self.assertAlmostEqual(
            summary["3か月移動平均前年比"], (116 / 104 - 1) * 100
        )
        self.assertAlmostEqual(summary["6か月モメンタム"], (116 / 110 - 1) * 100)
        self.assertEqual(summary["観測数"], 18)

    def test_builds_electronic_computer_order_trends(self) -> None:
        dates = pd.date_range("2025-01-01", periods=8, freq="MS")
        orders = pd.Series(range(100, 108), index=dates, dtype=float)

        trends = electronic_computer_order_trends(orders, months=4)

        self.assertEqual(len(trends), 4)
        self.assertEqual(list(trends), ["単月受注", "3か月移動平均"])
        self.assertEqual(trends.iloc[-1]["3か月移動平均"], 106.0)

    def test_builds_backtest_signals_with_conservative_release_dates(self) -> None:
        orders = pd.Series(
            range(100, 115), index=self.frame.index, dtype=float
        )

        signals = build_semiconductor_backtest_signals(self.frame, orders)

        self.assertEqual(signals.index[0], pd.Timestamp("2025-03-01"))
        self.assertIn("電デバ出荷前年比", signals)
        self.assertIn("電子計算機等受注3か月平均前年比", signals)
        self.assertAlmostEqual(
            signals.iloc[-1]["電デバ在庫前年比"], (96 / 108 - 1) * 100
        )

    def test_lead_lag_never_uses_price_on_or_before_release_as_future(self) -> None:
        signal = pd.Series(
            [1.0, 2.0, 3.0],
            index=pd.to_datetime(["2024-03-01", "2024-04-01", "2024-05-01"]),
        )
        prices = pd.Series(
            range(100, 230),
            index=pd.date_range("2024-01-01", periods=130, freq="B"),
            dtype=float,
        )

        result = analyze_release_aware_lead_lag(signal, prices, horizons=(1,))

        self.assertEqual(result.iloc[0]["サンプル数"], 3)
        self.assertFalse(pd.isna(result.iloc[0]["相関"]))

    def test_conditional_returns_reports_sample_count_and_warning(self) -> None:
        dates = pd.to_datetime(["2024-03-01", "2024-04-01", "2024-05-01"])
        signals = pd.DataFrame(
            {"電デバ出荷前年比": [-1.0, 2.0, 3.0]}, index=dates
        )
        prices = pd.Series(
            range(100, 300),
            index=pd.date_range("2024-01-01", periods=200, freq="B"),
            dtype=float,
        )

        result = analyze_semiconductor_condition_returns(
            signals,
            "出荷前年比プラス転換",
            prices,
            horizons=(1,),
            low_sample_threshold=2,
        )

        self.assertEqual(result.iloc[0]["サンプル数"], 1)
        self.assertEqual(result.iloc[0]["注意"], "サンプル少")
        self.assertGreater(result.iloc[0]["平均"], 0)


if __name__ == "__main__":
    unittest.main()
