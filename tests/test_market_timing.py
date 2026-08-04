from __future__ import annotations

import json
import unittest

import numpy as np
import pandas as pd

from portfolio_agent.market_timing import build_market_timing_payload


class MarketTimingTests(unittest.TestCase):
    def test_bullish_trend_keeps_dca_separate_from_tactical_action(self) -> None:
        dates = pd.bdate_range("2025-01-02", periods=300)
        trend = 100.0 * np.power(1.0012, np.arange(len(dates)))
        prices = pd.DataFrame({ticker: trend * (1.0 + index * 0.01) for index, ticker in enumerate(["SPY", "QQQ", "VTI", "VXUS", "XLK", "XLF"])}, index=dates)

        payload = build_market_timing_payload(prices, benchmark="SPY", sector_etfs=["XLK", "XLF"])
        spy = next(row for row in payload["rows"] if row["ticker"] == "SPY")

        self.assertEqual(payload["status"], "available")
        self.assertEqual(spy["dca_action"], "continue_core_dca")
        self.assertIn(spy["tactical_action"], {"hold_core", "staged_add", "hold_no_chase"})
        self.assertGreater(spy["ma200_slope_20d_pct"], 0)
        self.assertEqual(payload["breadth"]["above_200dma_pct"], 1.0)
        json.dumps(payload, allow_nan=False)

    def test_confirmed_bearish_trend_reduces_only_tactical_sleeve(self) -> None:
        dates = pd.bdate_range("2025-01-02", periods=300)
        downtrend = 300.0 * np.power(0.9975, np.arange(len(dates)))
        prices = pd.DataFrame({ticker: downtrend for ticker in ["SPY", "QQQ", "VTI", "VXUS", "XLK", "XLF"]}, index=dates)

        payload = build_market_timing_payload(prices, benchmark="SPY", sector_etfs=["XLK", "XLF"])
        spy = next(row for row in payload["rows"] if row["ticker"] == "SPY")

        self.assertEqual(spy["regime"], "risk_off")
        self.assertEqual(spy["tactical_action"], "reduce_tactical")
        self.assertEqual(spy["dca_action"], "continue_core_dca")
        self.assertGreaterEqual(spy["bearish_confirmation_count"], 3)

    def test_short_history_is_reported_without_inventing_a_signal(self) -> None:
        dates = pd.bdate_range("2026-01-02", periods=120)
        prices = pd.DataFrame({"SPY": np.linspace(100, 120, len(dates))}, index=dates)

        payload = build_market_timing_payload(prices, benchmark="SPY")

        self.assertEqual(payload["status"], "insufficient_data")
        self.assertEqual(payload["rows"], [])


if __name__ == "__main__":
    unittest.main()
