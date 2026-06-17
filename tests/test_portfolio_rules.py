from __future__ import annotations

import unittest

from portfolio_agent.config import (
    AppConfig,
    ExecutionConfig,
    IndicatorConfig,
    MLConfig,
    NotificationConfig,
    RuleConfig,
    UniverseConfig,
)
from portfolio_agent.models import MarketRegime, TradeSuggestion
from portfolio_agent.portfolio import apply_trade_suggestions, propose_rebalance


def make_config() -> AppConfig:
    return AppConfig(
        indicators=IndicatorConfig(ma_window=20, trend_ma_window=20, std_window=10, z_window=10),
        rules=RuleConfig(
            min_history_days=30,
            min_trade_weight=0.005,
            underweight_trigger=0.01,
            overweight_trigger=0.01,
            max_single_position_weight=0.75,
            max_sector_weight=0.90,
            trend_filter_enabled=True,
            bear_market_trim_fraction=0.20,
            allow_countertrend_buys=False,
            loss_block_pct=0.10,
            stop_loss_pct=0.90,
            trailing_stop_pct=0.90,
        ),
        universe=UniverseConfig(
            benchmark="SPY",
            sector_etfs={"Technology": "XLK", "Healthcare": "XLV"},
            positions={"AAA": 0.70, "BBB": 0.30},
            target_weights={"AAA": 0.40, "BBB": 0.60},
            ticker_sector={"AAA": "Technology", "BBB": "Healthcare"},
            entry_prices={"AAA": 100.0, "BBB": 100.0},
        ),
        notifications=NotificationConfig(enabled=False),
        ml=MLConfig(enabled=True, high_risk_trim_fraction=0.10),
        execution=ExecutionConfig(mode="sandbox", allow_live_brokerage=False),
    )


class PortfolioRuleTests(unittest.TestCase):
    def test_cash_allocation_survives_trade_application(self) -> None:
        updated = apply_trade_suggestions(
            {"AAA": 1.0},
            [
                TradeSuggestion("AAA", "trim", -0.20, "trim test"),
                TradeSuggestion("CASH", "hold", 0.20, "cash buffer"),
            ],
        )

        self.assertAlmostEqual(updated["AAA"], 0.80)
        self.assertAlmostEqual(updated["CASH"], 0.20)

    def test_bearish_regime_trims_and_blocks_countertrend_adds(self) -> None:
        cfg = make_config()
        cfg.rules.bear_market_trim_fraction = 0.0
        regime = MarketRegime("SPY", 90.0, 100.0, "bearish", -1.5, -0.1, 0.25, -0.12)
        suggestions = propose_rebalance(
            cfg,
            signals=[],
            latest_prices={"AAA": 95.0, "BBB": 101.0},
            trailing_highs={"AAA": 110.0, "BBB": 105.0},
            market_regime=regime,
        )

        actions = {(s.ticker, s.action) for s in suggestions}
        self.assertIn(("AAA", "trim"), actions)
        self.assertIn(("CASH", "hold"), actions)
        self.assertIn(("BBB", "block"), actions)

    def test_average_down_add_is_blocked(self) -> None:
        cfg = make_config()
        suggestions = propose_rebalance(
            cfg,
            signals=[],
            latest_prices={"AAA": 105.0, "BBB": 85.0},
            trailing_highs={"AAA": 110.0, "BBB": 110.0},
        )

        blocked = [s for s in suggestions if s.ticker == "BBB" and s.action == "block"]
        self.assertEqual(len(blocked), 1)
        self.assertIn("down", blocked[0].reason)


if __name__ == "__main__":
    unittest.main()
