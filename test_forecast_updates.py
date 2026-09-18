import unittest
from datetime import datetime

import pandas as pd

from decision_log import SCHEMA_VERSION, ReferencePrices, TOKYO, build_decision_snapshot
from forecast_updates import (
    FORECAST_UPDATE_METRICS,
    build_company_forecast_updates,
    forecast_update_snapshot,
)
from jquants_loader import normalize_financial_summaries


def _row(
    metric: str,
    value: float | None,
    disclosure: str,
    *,
    fiscal_year: str = "2027",
    reference_period: str = "2027-03-31",
    source_field: str = "FSales",
    forecast_scope: str = "current_fy",
    accounting_standard: str = "IFRS",
) -> dict[str, object]:
    return {
        "ticker": "7203.T",
        "fiscal_year": fiscal_year,
        "reference_period": reference_period,
        "accounting_standard": accounting_standard,
        "consolidated_flag": True,
        "currency": "JPY",
        "unit": "JPY",
        "metric": metric,
        "value": value,
        "disclosure_date": disclosure,
        "source_field": source_field,
        "forecast_scope": forecast_scope,
    }


class CompanyForecastUpdateTest(unittest.TestCase):
    def test_decision_log_database_schema_version_is_unchanged(self) -> None:
        self.assertEqual(SCHEMA_VERSION, 1)

    def test_three_metrics_compare_within_same_fiscal_cohort(self) -> None:
        rows = []
        values = {
            "forecast_revenue": (48_000, 49_000),
            "forecast_operating_profit": (4_500, 5_000),
            "forecast_net_income": (3_200, 3_400),
        }
        for metric, pair in values.items():
            rows.extend([
                _row(metric, pair[0], "2026-05-08"),
                _row(metric, pair[1], "2026-08-07"),
            ])
        result = build_company_forecast_updates(pd.DataFrame(rows))
        self.assertEqual(result["status"], "Available")
        by_metric = {row["metric"]: row for row in result["latest"]}
        self.assertEqual(set(by_metric), set(FORECAST_UPDATE_METRICS))
        self.assertEqual(by_metric["forecast_revenue"]["absolute_change"], 1_000)
        self.assertAlmostEqual(by_metric["forecast_operating_profit"]["change_pct"], 11.1111111)
        self.assertAlmostEqual(by_metric["forecast_net_income"]["change_pct"], 6.25)

    def test_different_fiscal_year_or_reference_period_is_not_compared(self) -> None:
        rows = [
            _row("forecast_revenue", 100, "2026-05-01", fiscal_year="2026", reference_period="2026-03-31"),
            _row("forecast_revenue", 110, "2026-08-01", fiscal_year="2027", reference_period="2027-03-31"),
            _row("forecast_net_income", 10, "2026-05-01", reference_period="2027-03-31"),
            _row("forecast_net_income", 12, "2026-08-01", reference_period="2027-06-30"),
        ]
        result = build_company_forecast_updates(pd.DataFrame(rows))
        self.assertEqual(result["status"], "Unavailable")

    def test_next_fy_to_current_fy_connects_when_final_definition_matches(self) -> None:
        rows = [
            _row("forecast_revenue", 100, "2026-03-01", source_field="NxFSales", forecast_scope="next_fy"),
            _row("forecast_revenue", 120, "2026-05-10", source_field="FSales", forecast_scope="current_fy"),
        ]
        result = build_company_forecast_updates(pd.DataFrame(rows))
        update = result["latest"][0]
        self.assertEqual(update["previous_forecast_scope"], "next_fy")
        self.assertEqual(update["current_forecast_scope"], "current_fy")
        self.assertEqual(update["absolute_change"], 20)

    def test_raw_nx_fnp_connects_to_later_current_fnp(self) -> None:
        raw = pd.DataFrame([
            {
                "Code": "72030", "DiscDate": "2026-05-08",
                "DocType": "FYFinancialStatements_Consolidated_IFRS",
                "CurPerType": "FY", "CurPerSt": "2025-04-01",
                "CurPerEn": "2026-03-31", "CurFYSt": "2025-04-01",
                "CurFYEn": "2026-03-31", "NxtFYSt": "2026-04-01",
                "NxtFYEn": "2027-03-31", "NxFNp": 320,
            },
            {
                "Code": "72030", "DiscDate": "2026-08-07",
                "DocType": "1QFinancialStatements_Consolidated_IFRS",
                "CurPerType": "1Q", "CurPerSt": "2026-04-01",
                "CurPerEn": "2026-06-30", "CurFYSt": "2026-04-01",
                "CurFYEn": "2027-03-31", "FNP": 340,
            },
        ])
        normalized = normalize_financial_summaries(
            raw, ticker_by_code={"7203": "7203.T"}
        )
        result = build_company_forecast_updates(normalized)
        self.assertEqual(result["status"], "Available")
        update = result["latest"][0]
        self.assertEqual(update["metric"], "forecast_net_income")
        self.assertEqual(update["fiscal_year"], "2027")
        self.assertEqual(update["reference_period"], "2027-03-31")
        self.assertEqual(update["previous_source_field"], "NxFNp")
        self.assertEqual(update["current_source_field"], "FNP")
        self.assertEqual(update["previous_forecast_scope"], "next_fy")
        self.assertEqual(update["current_forecast_scope"], "current_fy")
        self.assertEqual(update["absolute_change"], 20)

    def test_missing_value_is_not_zero_and_zero_has_no_rate(self) -> None:
        missing = build_company_forecast_updates(pd.DataFrame([
            _row("forecast_revenue", None, "2026-05-01"),
            _row("forecast_revenue", 100, "2026-08-01"),
        ]))
        self.assertEqual(missing["status"], "Unavailable")
        zero = build_company_forecast_updates(pd.DataFrame([
            _row("forecast_revenue", 0, "2026-05-01"),
            _row("forecast_revenue", 100, "2026-08-01"),
        ]))
        self.assertIsNone(zero["latest"][0]["change_pct"])

    def test_profit_crossings_use_transition_instead_of_rate(self) -> None:
        positive = build_company_forecast_updates(pd.DataFrame([
            _row("forecast_operating_profit", -100, "2026-05-01"),
            _row("forecast_operating_profit", 100, "2026-08-01"),
        ]))["latest"][0]
        negative = build_company_forecast_updates(pd.DataFrame([
            _row("forecast_net_income", 100, "2026-05-01"),
            _row("forecast_net_income", -100, "2026-08-01"),
        ]))["latest"][0]
        self.assertEqual(positive["transition_status"], "turned_positive")
        self.assertIsNone(positive["change_pct"])
        self.assertEqual(negative["transition_status"], "turned_negative")
        self.assertIsNone(negative["change_pct"])

    def test_eps_never_generates_a_comparison(self) -> None:
        result = build_company_forecast_updates(pd.DataFrame([
            _row("forecast_eps", 100, "2026-05-01", source_field="FEPS"),
            _row("forecast_eps", 120, "2026-08-01", source_field="FEPS"),
        ]))
        self.assertEqual(result["status"], "Unavailable")
        self.assertEqual(forecast_update_snapshot(result)["metrics"], {})

    def test_decision_snapshot_excludes_disclosures_after_capture_time(self) -> None:
        records = pd.DataFrame([
            _row("forecast_revenue", 100, "2026-05-01"),
            _row("forecast_revenue", 110, "2026-08-01"),
            _row("forecast_revenue", 150, "2026-10-01"),
        ])
        detail = {
            "stock": {"ticker": "7203.T"},
            "performance": {},
            "fundamentals": {
                "status": "Available",
                "latest_period": {},
                "forecast": pd.DataFrame(),
                "forecast_update_records": records,
            },
            "market_exposure": {},
            "primary_drivers": [],
        }
        snapshot = build_decision_snapshot(
            detail,
            ReferencePrices("available", 100, "2026-09-01", 200, "2026-09-01"),
            {},
            captured_at=datetime(2026, 9, 1, 12, 0, tzinfo=TOKYO),
        )
        update = snapshot["company_forecast_update"]
        self.assertEqual(update["latest_disclosure_date"], "2026-08-01")
        self.assertEqual(update["metrics"]["forecast_revenue"]["current_value"], 110)
        self.assertNotIn("forecast_eps", update["metrics"])

    def test_accounting_definition_change_is_not_compared(self) -> None:
        rows = [
            _row("forecast_revenue", 100, "2026-05-01", accounting_standard="JGAAP"),
            _row("forecast_revenue", 110, "2026-08-01", accounting_standard="IFRS"),
        ]
        self.assertEqual(
            build_company_forecast_updates(pd.DataFrame(rows))["status"],
            "Unavailable",
        )


if __name__ == "__main__":
    unittest.main()
