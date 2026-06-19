from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from portfolio_agent.config import (
    AppConfig,
    ExecutionConfig,
    IndicatorConfig,
    MLConfig,
    NotificationConfig,
    RuleConfig,
    UniverseConfig,
    load_config,
)
from portfolio_agent.report import write_report


class ReportAndConfigTests(unittest.TestCase):
    def test_cash_only_portfolio_report_does_not_crash(self) -> None:
        cfg = AppConfig(
            indicators=IndicatorConfig(),
            rules=RuleConfig(),
            universe=UniverseConfig(
                benchmark="SPY",
                sector_etfs={},
                positions={"CASH": 1.0},
                target_weights={"CASH": 1.0},
                ticker_sector={},
                entry_prices={},
            ),
            notifications=NotificationConfig(enabled=False),
            ml=MLConfig(enabled=False),
            execution=ExecutionConfig(),
        )

        with tempfile.TemporaryDirectory() as tmp:
            _, _, summary = write_report(
                out_dir=tmp,
                config=cfg,
                prices=pd.DataFrame(),
                signals=[],
                suggestions=[],
            )

            text = summary.read_text()
            self.assertIn("Largest position: None (0.00%)", text)
            self.assertIn("No trade changes met thresholds.", text)

    def test_config_rejects_non_mapping_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("- not\n- a\n- mapping\n")

            with self.assertRaisesRegex(ValueError, "YAML mapping"):
                load_config(path)

    def test_empty_config_reports_missing_universe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("")

            with self.assertRaisesRegex(ValueError, "universe"):
                load_config(path)

    def test_config_rejects_missing_ticker_sector_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                """
universe:
  benchmark: SPY
  sector_etfs:
    Technology: XLK
  positions:
    AAA: 1.0
  target_weights:
    AAA: 1.0
  ticker_sector: {}
"""
            )

            with self.assertRaisesRegex(ValueError, "ticker_sector"):
                load_config(path)

    def test_config_rejects_invalid_probability_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                """
rules:
  max_sector_weight: 1.25
universe:
  benchmark: SPY
  sector_etfs:
    Technology: XLK
  positions:
    AAA: 1.0
  target_weights:
    AAA: 1.0
  ticker_sector:
    AAA: Technology
"""
            )

            with self.assertRaisesRegex(ValueError, "rules.max_sector_weight"):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
