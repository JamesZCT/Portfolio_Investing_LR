from __future__ import annotations

import unittest

from portfolio_agent.sec_fundamentals import (
    assess_company_facts,
    classify_business_model,
    quote_only_research,
)


def _annual(value_2024: float, value_2025: float, *, instant: bool = False) -> dict:
    rows = []
    for year, value in ((2024, value_2024), (2025, value_2025)):
        row = {
            "end": f"{year}-12-31",
            "val": value,
            "form": "10-K",
            "fp": "FY",
            "filed": f"{year + 1}-02-20",
            "frame": f"CY{year}",
        }
        if not instant:
            row["start"] = f"{year}-01-01"
        rows.append(row)
    return {"units": {"USD": rows}}


def _quarterly(value_2025: float, value_2026: float) -> list[dict]:
    return [
        {
            "start": "2025-01-01",
            "end": "2025-03-31",
            "val": value_2025,
            "form": "10-Q",
            "fp": "Q1",
            "filed": "2025-05-01",
            "frame": "CY2025Q1",
        },
        {
            "start": "2026-01-01",
            "end": "2026-03-31",
            "val": value_2026,
            "form": "10-Q",
            "fp": "Q1",
            "filed": "2026-05-01",
            "frame": "CY2026Q1",
        },
    ]


class SecFundamentalsTests(unittest.TestCase):
    def test_business_models_use_different_valuation_lenses(self) -> None:
        self.assertEqual(classify_business_model(7372, "Prepackaged Software")[0], "software")
        self.assertEqual(classify_business_model(6021, "National Commercial Banks")[0], "bank")
        self.assertEqual(classify_business_model(6798, "Real Estate Investment Trusts")[0], "reit")
        self.assertEqual(classify_business_model(1311, "Crude Petroleum and Natural Gas")[0], "energy")

    def test_quote_only_result_is_explicitly_low_confidence(self) -> None:
        research = quote_only_research(
            {
                "action": "buy_candidate",
                "score": 80,
                "profitable": True,
                "trailing_pe": 20,
                "forward_pe": 18,
                "eps_forward_growth_pct": 15,
                "reason": "Strong trend.",
            }
        )
        self.assertEqual(research["status"], "quote_only")
        self.assertEqual(research["confidence"], "low")
        self.assertIsNone(research["scorecard"]["quality"])

    def test_filing_assessment_combines_earnings_cash_flow_and_valuation(self) -> None:
        facts = {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {"USD": _annual(500, 600)["units"]["USD"] + _quarterly(100, 120)}
            },
            "NetIncomeLoss": {
                "units": {"USD": _annual(80, 100)["units"]["USD"] + _quarterly(15, 24)}
            },
            "OperatingIncomeLoss": _annual(90, 125),
            "NetCashProvidedByUsedInOperatingActivities": _annual(120, 155),
            "PaymentsToAcquirePropertyPlantAndEquipment": _annual(25, 30),
            "Assets": _annual(900, 1000, instant=True),
            "StockholdersEquity": _annual(620, 700, instant=True),
            "CashAndCashEquivalentsAtCarryingValue": _annual(180, 220, instant=True),
            "LongTermDebtCurrent": _annual(20, 20, instant=True),
            "LongTermDebtNoncurrent": _annual(90, 80, instant=True),
            "IncomeTaxExpenseBenefit": _annual(18, 24),
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": _annual(98, 124),
        }
        submissions = {
            "cik": 123456,
            "sic": "7372",
            "sicDescription": "Prepackaged Software",
            "filings": {
                "recent": {
                    "form": ["10-Q"],
                    "filingDate": ["2026-05-01"],
                    "reportDate": ["2026-03-31"],
                    "accessionNumber": ["0000123456-26-000001"],
                    "primaryDocument": ["example-20260331.htm"],
                    "items": [""],
                }
            },
        }
        company_facts = {"cik": 123456, "facts": {"us-gaap": facts}}
        quote = {
            "ticker": "GOOD",
            "action": "buy_candidate",
            "score": 82,
            "market_cap": 1_500,
            "trailing_pe": 22,
            "forward_pe": 18,
            "price_to_book": 4,
            "eps_forward_growth_pct": 18,
            "profitable": True,
        }

        research = assess_company_facts("GOOD", quote, submissions, company_facts)

        self.assertEqual(research["status"], "sec_fundamentals")
        self.assertEqual(research["business_model"], "software")
        self.assertEqual(research["decision"], "research_buy")
        self.assertEqual(research["earnings"]["revenue_growth_yoy_pct"], 20.0)
        self.assertEqual(research["earnings"]["net_income_growth_yoy_pct"], 60.0)
        self.assertGreater(research["scorecard"]["quality"], 60)
        self.assertIn("Growth and earnings improved", research["key_takeaways"])


if __name__ == "__main__":
    unittest.main()
