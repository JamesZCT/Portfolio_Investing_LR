from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from portfolio_agent.engine import run_buy_and_hold_baseline
from portfolio_agent.strategies import compare_strategies

from tests.test_portfolio_rules import make_config


def drift_exposing_prices() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "AAA": [100.0, 200.0, 100.0],
            "BBB": [100.0, 100.0, 100.0],
        },
        index=pd.date_range("2024-01-01", periods=3, freq="D"),
    )


def config_loadable_prices() -> pd.DataFrame:
    prices = drift_exposing_prices()
    prices["SPY"] = [100.0, 100.0, 100.0]
    prices["XLK"] = [100.0, 100.0, 100.0]
    prices["XLV"] = [100.0, 100.0, 100.0]
    return prices


class StrategiesAndEngineTests(unittest.TestCase):
    def test_strategy_buy_and_hold_weights_drift(self) -> None:
        cfg = make_config()
        cfg.universe.positions = {"AAA": 0.5, "BBB": 0.5}
        cfg.universe.target_weights = {"AAA": 0.5, "BBB": 0.5}

        comparisons = compare_strategies(
            cfg,
            drift_exposing_prices(),
            rebalance_days=99,
            transaction_cost_bps=0,
        )

        buy_and_hold = next(item for item in comparisons if item.name == "Buy & Hold")
        self.assertAlmostEqual(buy_and_hold.metrics["final_value"], 1.0, places=6)

    def test_engine_buy_and_hold_baseline_weights_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            prices_path = root / "prices.csv"
            config_path.write_text(
                """
universe:
  benchmark: SPY
  sector_etfs:
    Technology: XLK
    Healthcare: XLV
  positions:
    AAA: 0.5
    BBB: 0.5
  target_weights:
    AAA: 0.5
    BBB: 0.5
  ticker_sector:
    AAA: Technology
    BBB: Healthcare
"""
            )
            config_loadable_prices().reset_index(names="Date").to_csv(prices_path, index=False)

            metrics = run_buy_and_hold_baseline(
                config_path=config_path,
                prices_csv=str(prices_path),
            )

        self.assertAlmostEqual(metrics["final_value"], 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
