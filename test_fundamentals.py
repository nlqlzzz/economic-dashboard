import unittest
import pandas as pd
from fundamentals import (build_annual_forecast_series, build_fundamentals_cards,
                          build_fundamentals_summary, chart_axis_ticks, format_eps,
                          format_financial_value, format_jpy, format_yoy)


def records() -> pd.DataFrame:
    rows=[]
    for year in ("2025", "2026"):
        for quarter, value in (("Q1", 10), ("Q2", 30), ("Q3", 60), ("FY", 100)):
            for metric in ("revenue", "net_income", "eps", "operating_profit"):
                rows.append({"metric":metric,"value":value,"ticker":"7203.T","code":"7203","fiscal_year":year,"fiscal_quarter":quarter,"accounting_standard":"IFRS","consolidated_flag":True,"is_cumulative":quarter != "Q1","is_derived":False,"document_type":"FinancialStatements","disclosure_date":f"{year}-08-01","period_start":f"{int(year)-1}-04-01","reference_period":f"{year}-03-31","fiscal_year_start":f"{int(year)-1}-04-01","fiscal_year_end":f"{year}-03-31","unit":None,"currency":"JPY"})
    return pd.DataFrame(rows)


class FundamentalsTest(unittest.TestCase):
    def test_builds_derived_history_and_momentum(self):
        data=build_fundamentals_summary(records(), "自動車")
        self.assertEqual(data["status"], "Available")
        self.assertEqual(data["history_status"], "Full history")
        self.assertEqual(data["operating_status"], "Available")

    def test_bank_marks_operating_profit_not_applicable(self):
        data=build_fundamentals_summary(records(), "銀行")
        self.assertEqual(data["operating_status"], "Not Applicable")
        self.assertNotIn("operating_profit", set(data["latest"].metric))

    def test_empty_data_is_unavailable(self):
        self.assertEqual(build_fundamentals_summary(pd.DataFrame(), "銀行")["status"], "Unavailable")

    def test_japanese_value_formatters(self):
        self.assertEqual(format_jpy(12_600_000_000_000), "12.6兆円")
        self.assertEqual(format_jpy(817_200_000_000), "8,172億円")
        self.assertEqual(format_eps(62.0), "62円")
        self.assertEqual(format_yoy(1.9), "前年比 +1.9%")
        self.assertEqual(format_financial_value(100, "revenue", None), "100（単位未確認）")

    def test_mobile_card_payload_is_compact(self):
        cards = build_fundamentals_cards(build_fundamentals_summary(records(), "自動車"))
        self.assertEqual([card["metric"] for card in cards], ["revenue", "net_income", "eps", "operating_profit"])

    def test_axis_ticks_use_compact_japanese_amounts_and_eps(self):
        yen_ticks = chart_axis_ticks(pd.Series([2_469_000_000_000, 3_000_000_000_000]), "revenue")
        eps_ticks = chart_axis_ticks(pd.Series([81.0, 100.0]), "eps")
        self.assertTrue(all("兆円" in text for text in yen_ticks["ticktext"]))
        self.assertTrue(all(text.endswith("円") for text in eps_ticks["ticktext"]))

    def test_annual_forecast_never_uses_quarterly_standalone_history(self):
        raw = records()
        raw = pd.concat([raw, pd.DataFrame([{
            "metric": "forecast_revenue", "value": 120, "ticker": "7203.T", "code": "7203",
            "fiscal_year": "2027", "fiscal_quarter": "FY", "document_type": "Forecast",
            "disclosure_date": "2026-08-01", "period_start": "2026-04-01", "reference_period": "2027-03-31", "fiscal_year_start": "2026-04-01", "fiscal_year_end": "2027-03-31", "accounting_standard": "IFRS", "consolidated_flag": True, "unit": None, "currency": "JPY",
        }])], ignore_index=True)
        series = build_annual_forecast_series(build_fundamentals_summary(raw, "自動車"), "revenue")
        self.assertEqual(list(series["期"]), ["2025", "2026", "2027"])
        self.assertTrue(series.loc[series["期"].eq("2027"), "実績"].isna().all())
        self.assertEqual(float(series.loc[series["期"].eq("2027"), "会社予想"].iloc[0]), 120.0)

    def test_eps_is_not_derived_by_cumulative_subtraction(self):
        data = build_fundamentals_summary(records(), "自動車")
        eps = data["history"][data["history"].metric.eq("eps")]
        self.assertFalse(eps["is_derived"].any())
        self.assertIn("Q2", set(eps["fiscal_quarter"]))

    def test_profit_turnaround_is_not_weakening_and_eps_is_not_second_vote(self):
        raw = records()
        raw.loc[(raw.fiscal_year == "2025") & (raw.metric.isin(("net_income", "eps", "operating_profit"))), "value"] = -10
        raw.loc[(raw.fiscal_year == "2026") & (raw.metric.isin(("net_income", "eps", "operating_profit"))), "value"] = 10
        data = build_fundamentals_summary(raw, "自動車")
        self.assertNotEqual(data["momentum"], "Weakening")
        self.assertIn("黒字転換", data["momentum_reason"])

    def test_latest_cohort_does_not_backfill_missing_metric_from_old_period(self):
        raw = records()
        dates = {"Q1": ("2025-06-30", "2025-08-01"), "Q2": ("2025-09-30", "2025-11-01"), "Q3": ("2025-12-31", "2026-02-01"), "FY": ("2026-03-31", "2026-05-01")}
        for quarter, (reference, disclosure) in dates.items():
            mask = (raw.fiscal_year == "2026") & (raw.fiscal_quarter == quarter)
            raw.loc[mask, "reference_period"] = reference
            raw.loc[mask, "disclosure_date"] = disclosure
        raw = raw[~((raw.fiscal_year == "2026") & (raw.fiscal_quarter == "FY") & (raw.metric == "net_income"))]
        data = build_fundamentals_summary(raw, "自動車")
        latest = data["latest"]
        self.assertNotIn("net_income", set(latest.metric))

    def test_old_forecast_is_not_presented_as_current_outlook(self):
        raw = records()
        raw = pd.concat([raw, pd.DataFrame([{
            "metric": "forecast_eps", "value": 99, "ticker": "7203.T", "code": "7203",
            "fiscal_year": "2024", "fiscal_quarter": "FY", "document_type": "Forecast",
            "disclosure_date": "2024-05-01", "period_start": "2023-04-01", "reference_period": "2024-03-31",
            "fiscal_year_start": "2023-04-01", "fiscal_year_end": "2024-03-31", "unit": None, "currency": "JPY",
        }])], ignore_index=True)
        data = build_fundamentals_summary(raw, "自動車")
        self.assertTrue(data["forecast"].empty)
