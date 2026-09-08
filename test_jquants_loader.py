import os
import unittest
from unittest.mock import patch

import pandas as pd

from jquants_loader import (
    JQuantsConfigurationError,
    add_fiscal_yoy,
    assess_coverage,
    derive_standalone_quarters,
    fetch_financial_summaries,
    get_jquants_api_key,
    normalize_financial_summaries,
    to_jquants_code,
)


def _raw_rows() -> pd.DataFrame:
    return pd.DataFrame([
        {"Code": "72030", "DiscDate": "2025-08-01", "DocType": "1QConsolidated_JP", "CurPerType": "Q1", "CurPerSt": "2025-04-01", "CurPerEn": "2025-06-30", "CurFYSt": "2025-04-01", "CurFYEn": "2026-03-31", "Sales": 10, "OP": 2, "NP": 1, "EPS": 5, "FSales": 100},
        {"Code": "72030", "DiscDate": "2025-11-01", "DocType": "2QConsolidated_JP", "CurPerType": "Q2", "CurPerSt": "2025-04-01", "CurPerEn": "2025-09-30", "CurFYSt": "2025-04-01", "CurFYEn": "2026-03-31", "Sales": 30, "OP": 6, "NP": 3, "EPS": 15},
        {"Code": "72030", "DiscDate": "2026-02-01", "DocType": "3QConsolidated_JP", "CurPerType": "Q3", "CurPerSt": "2025-04-01", "CurPerEn": "2025-12-31", "CurFYSt": "2025-04-01", "CurFYEn": "2026-03-31", "Sales": 60, "OP": 12, "NP": 6, "EPS": 30},
        {"Code": "72030", "DiscDate": "2026-05-01", "DocType": "FYConsolidated_JP", "CurPerType": "FY", "CurPerSt": "2025-04-01", "CurPerEn": "2026-03-31", "CurFYSt": "2025-04-01", "CurFYEn": "2026-03-31", "Sales": 100, "OP": 20, "NP": 10, "EPS": 50},
    ])


class JQuantsCodeTest(unittest.TestCase):
    def test_jquants_code_conversion(self) -> None:
        self.assertEqual(to_jquants_code("7203"), "72030")
        self.assertEqual(to_jquants_code("7203.T"), "72030")
        self.assertEqual(to_jquants_code("72030"), "72030")
        with self.assertRaises(ValueError):
            to_jquants_code("Toyota")


class JQuantsNormalizationTest(unittest.TestCase):
    def setUp(self) -> None:
        raw = _raw_rows().copy()
        raw["DocType"] = raw["DocType"].str.replace("Consolidated", "FinancialStatements_Consolidated", regex=False)
        self.normalized = normalize_financial_summaries(
            raw, ticker_by_code={"7203": "7203.T"}, company_by_code={"7203": "トヨタ自動車"}, fetched_at="2026-09-09T00:00:00+00:00"
        )

    def test_normalizes_source_neutral_schema_without_release_date_guessing(self) -> None:
        row = self.normalized[(self.normalized.metric == "revenue") & (self.normalized.fiscal_quarter == "Q2")].iloc[0]
        self.assertEqual(row["ticker"], "7203.T")
        self.assertEqual(row["disclosure_date"], "2025-11-01")
        self.assertEqual(row["reference_period"], "2025-09-30")
        self.assertTrue(row["is_cumulative"])
        self.assertFalse(row["is_derived"])
        self.assertEqual(row["accounting_standard"], "Japan GAAP")

    def test_normalizes_jquants_one_q_period_label_and_epoch_milliseconds(self) -> None:
        raw = _raw_rows().iloc[:1].copy()
        raw.loc[:, "CurPerType"] = "1Q"
        raw["DiscDate"] = raw["DiscDate"].astype(object)
        raw.loc[:, "DiscDate"] = 1754006400000
        result = normalize_financial_summaries(raw, ticker_by_code={"7203": "7203.T"})
        row = result[result.metric.eq("revenue")].iloc[0]
        self.assertEqual(row["fiscal_quarter"], "Q1")
        self.assertEqual(row["disclosure_date"], "2025-08-01")

    def test_derived_quarters_require_explicit_cumulative_definition(self) -> None:
        derived = derive_standalone_quarters(self.normalized)
        revenue = derived[derived.metric.eq("revenue")].set_index("fiscal_quarter")
        self.assertEqual(revenue.loc["Q1", "value"], 10.0)
        self.assertEqual(revenue.loc["Q2", "value"], 20.0)
        self.assertEqual(revenue.loc["Q3", "value"], 30.0)
        self.assertEqual(revenue.loc["Q4", "value"], 40.0)
        self.assertTrue(revenue.loc["Q2", "is_derived"])

    def test_unknown_cumulative_definition_is_not_derived(self) -> None:
        uncertain = self.normalized.copy()
        uncertain["is_cumulative"] = uncertain["is_cumulative"].astype(object)
        uncertain.loc[uncertain.fiscal_quarter.eq("Q2"), "is_cumulative"] = None
        derived = derive_standalone_quarters(uncertain)
        self.assertNotIn("Q2", set(derived.fiscal_quarter))

    def test_yoy_requires_same_fiscal_quarter(self) -> None:
        rows = pd.DataFrame([
            {"ticker": "7203.T", "code": "7203", "metric": "revenue", "fiscal_year": "2025", "fiscal_quarter": "Q1", "accounting_standard": "Japan GAAP", "consolidated_flag": True, "is_derived": False, "value": 100},
            {"ticker": "7203.T", "code": "7203", "metric": "revenue", "fiscal_year": "2026", "fiscal_quarter": "Q1", "accounting_standard": "Japan GAAP", "consolidated_flag": True, "is_derived": False, "value": 120},
            {"ticker": "7203.T", "code": "7203", "metric": "revenue", "fiscal_year": "2026", "fiscal_quarter": "Q2", "accounting_standard": "Japan GAAP", "consolidated_flag": True, "is_derived": False, "value": 130},
        ])
        result = add_fiscal_yoy(rows)
        self.assertAlmostEqual(float(result.loc[1, "yoy"]), 20.0)
        self.assertTrue(pd.isna(result.loc[2, "yoy"]))

    def test_coverage_counts_only_actual_quarters(self) -> None:
        rows = pd.concat([self.normalized] * 2, ignore_index=True)
        report = assess_coverage(rows, ["7203.T", "8306.T"]).set_index("metric")
        self.assertEqual(report.loc["revenue", "coverage"], 1)
        self.assertEqual(report.loc["revenue", "coverage_total"], 2)


class JQuantsFetchTest(unittest.TestCase):
    def test_local_streamlit_secret_is_a_safe_fallback_for_standalone_tools(self) -> None:
        with patch.dict(os.environ, {"JQUANTS_API_KEY": ""}, clear=False), patch("jquants_loader._read_streamlit_runtime_secret", return_value=None), patch("jquants_loader._read_local_streamlit_secret", return_value="test-key"):
            self.assertEqual(get_jquants_api_key(), "test-key")

    def test_missing_key_fails_safely(self) -> None:
        with patch.dict(os.environ, {"JQUANTS_API_KEY": ""}, clear=False), patch("jquants_loader.get_jquants_api_key", return_value=None):
            with self.assertRaises(JQuantsConfigurationError):
                fetch_financial_summaries(["7203"], sleep=lambda _: None)

    def test_partial_api_failure_does_not_discard_other_code(self) -> None:
        class Client:
            def get_fin_summary(self, code: str):
                if code == "83060":
                    raise RuntimeError("temporary failure")
                return _raw_rows().iloc[:1]

        with patch("jquants_loader.get_jquants_api_key", return_value="test-key"):
            result = fetch_financial_summaries(["7203", "8306"], client_factory=lambda _: Client(), requests_per_minute=0, sleep=lambda _: None)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.failures, ("83060",))
