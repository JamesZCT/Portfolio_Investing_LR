from __future__ import annotations

import unittest

import pandas as pd

from portfolio_agent.backtest import run_backtest

from tests.test_portfolio_rules import make_config


class BacktestTests(unittest.TestCase):
    def test_weights_drift_between_rebalances(self) -> None:
        cfg = make_config()
        cfg.universe.positions = {"AAA": 0.5, "BBB": 0.5}
        cfg.universe.target_weights = {"AAA": 0.5, "BBB": 0.5}

        prices = pd.DataFrame(
            {
                "AAA": [100.0, 200.0, 100.0],
                "BBB": [100.0, 100.0, 100.0],
            },
            index=pd.date_range("2024-01-01", periods=3, freq="D"),
        )

        result = run_backtest(cfg, prices, rebalance_days=99, transaction_cost_bps=0)

        self.assertAlmostEqual(
            float(result.equity_curve["portfolio_value"].iloc[-1]),
            1.0,
            places=6,
        )

    def test_rebalance_happens_after_same_day_return(self) -> None:
        cfg = make_config()
        cfg.universe.positions = {"AAA": 1.0, "BBB": 0.0}
        cfg.universe.target_weights = {"AAA": 0.0, "BBB": 1.0}
        cfg.rules.max_single_position_weight = 0.5
        cfg.rules.min_trade_weight = 0.001

        prices = pd.DataFrame(
            {
                "AAA": [100.0, 200.0],
                "BBB": [100.0, 100.0],
            },
            index=pd.date_range("2024-01-01", periods=2, freq="D"),
        )

        result = run_backtest(cfg, prices, rebalance_days=1, transaction_cost_bps=0)

        self.assertAlmostEqual(
            float(result.equity_curve["daily_return"].iloc[-1]),
            1.0,
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
