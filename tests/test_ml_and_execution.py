from __future__ import annotations

import unittest

from portfolio_agent.execution import SandboxExecutionAdapter, suggestions_to_orders
from portfolio_agent.ml import build_risk_predictions
from portfolio_agent.models import TradeSuggestion
from portfolio_agent.sandbox import generate_sandbox_prices

from tests.test_portfolio_rules import make_config


class MlAndExecutionTests(unittest.TestCase):
    def test_sandbox_prices_feed_ml_predictions(self) -> None:
        cfg = make_config()
        cfg.ml.min_training_rows = 25
        cfg.ml.epochs = 25
        prices = generate_sandbox_prices(cfg, days=360, seed=11)

        predictions = build_risk_predictions(prices, ["AAA", "BBB"], cfg)

        self.assertTrue(predictions)
        self.assertIn("AAA", predictions)
        self.assertGreaterEqual(predictions["AAA"].risk_probability, 0.0)
        self.assertLessEqual(predictions["AAA"].risk_probability, 1.0)

    def test_sandbox_execution_never_places_live_orders(self) -> None:
        suggestions = [
            TradeSuggestion("AAA", "trim", -0.05, "risk trim", ("TREND_FILTER",)),
            TradeSuggestion("BBB", "block", 0.0, "blocked", ("ADD_BLOCK",)),
        ]
        orders = suggestions_to_orders(suggestions)
        results = SandboxExecutionAdapter().execute(orders)

        self.assertEqual(len(orders), 1)
        self.assertEqual(results[0].status, "simulated")
        self.assertIn("no brokerage order", results[0].message)


if __name__ == "__main__":
    unittest.main()
