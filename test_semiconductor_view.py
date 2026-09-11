import unittest

import pandas as pd

from semiconductor_view import aggregate_sources, compact_status_rows, display_state


class SemiconductorViewTest(unittest.TestCase):
    def test_compact_status_rows_translate_state_and_keep_one_evidence(self):
        rows = compact_status_rows([("台湾", {"direction": "↑", "status": "Strong", "evidence": ["受注前年比 +10%", "詳細"]})])
        self.assertEqual(rows, [{"対象": "台湾", "判定": "↑ 強い", "主な根拠": "受注前年比 +10%"}])

    def test_source_aggregation_keeps_urls_but_deduplicates_provider(self):
        frame = pd.DataFrame([
            {"source_name": "韓国産業通商資源部", "source_url": "https://a.example"},
            {"source_name": "韓国産業通商資源部", "source_url": "https://b.example"},
            {"source_name": "韓国関税庁", "source_url": "https://c.example"},
        ])
        groups = aggregate_sources(frame)
        self.assertEqual([group["name"] for group in groups], ["韓国産業通商資源部", "韓国関税庁"])
        self.assertEqual(groups[0]["url"], "https://a.example")
        self.assertEqual(groups[0]["urls"], ["https://a.example", "https://b.example"])

    def test_unavailable_is_a_natural_ui_label(self):
        self.assertEqual(display_state("Unavailable"), "判定不可")


if __name__ == "__main__":
    unittest.main()
