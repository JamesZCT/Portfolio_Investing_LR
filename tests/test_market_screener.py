from __future__ import annotations

import unittest
import json

from portfolio_agent.market_screener import build_market_opportunities_payload, rank_market_opportunities


class MarketScreenerTests(unittest.TestCase):
    def test_sandbox_screen_separates_positive_and_negative_trends(self) -> None:
        payload = build_market_opportunities_payload("us", mode="sandbox")

        self.assertEqual(payload["status"], "available")
        self.assertEqual(payload["universe"]["analyzed_count"], 6)
        self.assertEqual(payload["universe"]["coverage_ratio"], 1.0)
        self.assertIn("ALPHA", {row["ticker"] for row in payload["buy_candidates"]})
        self.assertIn("FOXTROT", {row["ticker"] for row in payload["sell_avoid"]})
        json.dumps(payload, allow_nan=False)

    def test_missing_trend_fields_are_reported_as_incomplete_coverage(self) -> None:
        valid = {
            "symbol": "GOOD",
            "shortName": "Good Company",
            "regularMarketPrice": 110,
            "fiftyDayAverage": 105,
            "twoHundredDayAverage": 100,
            "fiftyTwoWeekChangePercent": 12,
            "fiftyTwoWeekLow": 80,
            "fiftyTwoWeekHigh": 120,
        }
        incomplete = {"symbol": "MISSING", "regularMarketPrice": 10}

        payload = rank_market_opportunities([valid, incomplete], eligible_total=4)

        self.assertEqual(payload["universe"]["fetched_count"], 2)
        self.assertEqual(payload["universe"]["analyzed_count"], 1)
        self.assertEqual(payload["universe"]["coverage_ratio"], 0.25)

    def test_non_us_screen_is_explicitly_unavailable(self) -> None:
        payload = build_market_opportunities_payload("hk", mode="sandbox")
        self.assertEqual(payload["status"], "unavailable")
        self.assertIn("US-listed", payload["note"])


if __name__ == "__main__":
    unittest.main()
