from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from bigtech_capex import (
    BIGTECH_CAPEX_DATA_PATH,
    BigTechCapexDataError,
    build_bigtech_capex_summaries,
    effective_change_label,
    load_bigtech_capex_research,
    validate_bigtech_capex_research,
)


class BigTechCapexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads(BIGTECH_CAPEX_DATA_PATH.read_text(encoding="utf-8"))

    def payload(self):
        return copy.deepcopy(self.raw)

    def test_json_schema_loads_and_has_only_three_adopted_companies(self):
        dataset = load_bigtech_capex_research()
        self.assertEqual(len(dataset["records"]), 8)
        self.assertEqual({row["company"] for row in dataset["records"]}, {"Microsoft", "Alphabet", "Meta"})
        self.assertTrue(all(isinstance(row["published_at"], pd.Timestamp) for row in dataset["records"]))

    def test_duplicate_disclosure_is_rejected(self):
        payload = self.payload()
        payload["records"].append(copy.deepcopy(payload["records"][0]))
        with self.assertRaisesRegex(BigTechCapexDataError, "duplicate disclosure"):
            validate_bigtech_capex_research(payload)

    def test_invalid_range_is_rejected(self):
        payload = self.payload()
        alphabet = next(row for row in payload["records"] if row["company"] == "Alphabet")
        alphabet["guidance_low_bn"] = 200
        alphabet["guidance_high_bn"] = 100
        with self.assertRaisesRegex(BigTechCapexDataError, "low <= high"):
            validate_bigtech_capex_research(payload)

    def test_missing_source_url_is_rejected(self):
        payload = self.payload()
        payload["records"][0]["source_url"] = ""
        with self.assertRaisesRegex(BigTechCapexDataError, "source_url"):
            validate_bigtech_capex_research(payload)

    def test_invalid_status_is_rejected(self):
        payload = self.payload()
        payload["records"][0]["comparison_status"] = "maybe"
        with self.assertRaisesRegex(BigTechCapexDataError, "comparison_status"):
            validate_bigtech_capex_research(payload)

    def test_target_year_change_is_initial(self):
        previous = {"target_year": "CY2026"}
        current = {
            "target_year": "CY2027",
            "comparison_status": "exact",
            "change_label": "raised",
        }
        self.assertEqual(effective_change_label(current, previous), "initial")

    def test_definition_changed_overrides_numeric_drop(self):
        previous = {"target_year": "CY2026"}
        current = {
            "target_year": "CY2026",
            "comparison_status": "definition_changed",
            "change_label": "lowered",
        }
        self.assertEqual(effective_change_label(current, previous), "definition_changed")

    def test_company_summaries_preserve_expected_labels(self):
        summaries = {item["company"]: item for item in build_bigtech_capex_summaries(load_bigtech_capex_research()["records"])}
        microsoft = summaries["Microsoft"]
        self.assertEqual(microsoft["previous_guidance"], "約190 bn USD")
        self.assertEqual(microsoft["current_guidance"], "約175 bn USD")
        self.assertEqual(microsoft["change_label"], "definition_changed")
        self.assertEqual(microsoft["economic_plan_change"], "unchanged")
        self.assertNotEqual(microsoft["change_label_ja"], "減額")
        self.assertEqual(summaries["Alphabet"]["change_label"], "raised")
        self.assertEqual(summaries["Meta"]["change_label"], "lower_bound_raised")

    def test_missing_json_is_wrapped_as_dataset_error(self):
        missing = Path(tempfile.gettempdir()) / "does-not-exist-bigtech-capex.json"
        with self.assertRaisesRegex(BigTechCapexDataError, "読み込めません"):
            load_bigtech_capex_research(missing)

    @patch("semiconductor_view.st")
    def test_ui_missing_json_warns_without_raising(self, streamlit):
        from semiconductor_view import render_bigtech_capex_research

        render_bigtech_capex_research("missing-bigtech-capex.json")
        streamlit.warning.assert_called_once()
        self.assertIn("表示できません", streamlit.warning.call_args.args[0])

    def test_apptest_renders_mobile_first_company_cards_and_definition_warning(self):
        app = AppTest.from_string(
            """
from semiconductor_view import render_bigtech_capex_research
render_bigtech_capex_research()
""",
            default_timeout=30,
        ).run()
        self.assertFalse(app.exception)
        markdown = [item.value for item in app.markdown]
        for company in ("Microsoft", "Alphabet", "Meta"):
            self.assertTrue(any(company in value for value in markdown))
        self.assertTrue(any("約190 bn USD" in value and "約175 bn USD" in value for value in markdown))
        self.assertTrue(any("定義変更" in value for value in markdown))
        self.assertFalse(any(value.strip() == "**減額**" for value in markdown))
        self.assertTrue(any("economic investment planは据え置き" in item.value for item in app.info))


if __name__ == "__main__":
    unittest.main()
