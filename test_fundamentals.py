import unittest
import pandas as pd
from fundamentals import build_fundamentals_summary


def records() -> pd.DataFrame:
    rows=[]
    for year in ("2025", "2026"):
        for quarter, value in (("Q1", 10), ("Q2", 30), ("Q3", 60), ("FY", 100)):
            for metric in ("revenue", "net_income", "eps", "operating_profit"):
                rows.append({"metric":metric,"value":value,"ticker":"7203.T","code":"7203","fiscal_year":year,"fiscal_quarter":quarter,"accounting_standard":"IFRS","consolidated_flag":True,"is_cumulative":quarter != "Q1","is_derived":False,"document_type":"FinancialStatements","disclosure_date":f"{year}-08-01","unit":None,"currency":"JPY"})
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
