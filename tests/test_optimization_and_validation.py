from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from portfolio_agent.academic_factors import parse_ken_french_daily_table
from portfolio_agent.config import load_config
from portfolio_agent.historical_validation import run_historical_validation
from portfolio_agent.optimization import build_optimization_payload
from portfolio_agent.point_in_time import (
    HistoricalUniverse,
    run_point_in_time_experiment,
)
from portfolio_agent.sandbox import generate_sandbox_prices


class OptimizationAndValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config("example_config.yaml")

    def test_profiles_are_long_only_fully_invested_and_capped(self) -> None:
        prices = generate_sandbox_prices(self.config, days=900, seed=11)
        payload = build_optimization_payload(self.config, prices)

        self.assertEqual(payload["status"], "available")
        self.assertEqual({item["id"] for item in payload["profiles"]}, {"defensive", "balanced", "aggressive"})
        for profile in payload["profiles"]:
            target = {
                row["ticker"]: row["target_weight"]
                for row in profile["rows"]
            }
            self.assertAlmostEqual(sum(target.values()), 1.0, places=6)
            self.assertTrue(all(weight >= 0 for weight in target.values()))
            self.assertEqual(profile["constraints"]["leverage"], 1.0)
            risk_scale = 1.0 - profile["cash_weight"]
            for row in profile["rows"]:
                if row["ticker"] == "CASH":
                    continue
                cap = (
                    profile["constraints"]["max_fund_weight"]
                    if row["asset_type"] in {"fund", "bond", "cash"}
                    else profile["constraints"]["max_single_weight"]
                )
                self.assertLessEqual(row["target_weight"], cap * risk_scale + 1e-8)

    def test_validation_is_json_safe_and_declares_known_biases(self) -> None:
        prices = generate_sandbox_prices(self.config, days=1100, seed=17)
        payload = run_historical_validation(self.config, prices, years=3)

        self.assertEqual(payload["status"], "exploratory")
        self.assertTrue(payload["integrity"]["survivorship_bias"])
        self.assertFalse(payload["integrity"]["fundamental_layer_included"])
        self.assertGreaterEqual(len(payload["tracks"]), 5)

    def test_future_price_changes_do_not_change_past_rule_track(self) -> None:
        prices = generate_sandbox_prices(self.config, days=1200, seed=23)
        cutoff = prices.index[-120]
        original = run_historical_validation(self.config, prices, years=3)

        changed = prices.copy()
        future_mask = changed.index > cutoff
        rng = np.random.default_rng(101)
        shocks = rng.uniform(0.45, 1.75, size=(int(future_mask.sum()), len(changed.columns)))
        changed.loc[future_mask, :] = changed.loc[future_mask, :].to_numpy() * shocks
        perturbed = run_historical_validation(self.config, changed, years=3)

        original_track = _track(original, "price_rule_reconstruction")
        perturbed_track = _track(perturbed, "price_rule_reconstruction")
        original_curve = {
            row["date"]: row["portfolio_value"]
            for row in original_track["equity_curve"]
            if pd.Timestamp(row["date"]) <= cutoff
        }
        perturbed_curve = {
            row["date"]: row["portfolio_value"]
            for row in perturbed_track["equity_curve"]
            if pd.Timestamp(row["date"]) <= cutoff
        }
        self.assertEqual(original_curve.keys(), perturbed_curve.keys())
        for date, value in original_curve.items():
            self.assertAlmostEqual(value, perturbed_curve[date], places=10)

    def test_point_in_time_track_only_selects_members_known_on_that_date(self) -> None:
        prices, universe = _point_in_time_fixture()
        payload = run_point_in_time_experiment(
            self.config,
            prices,
            universe,
            years=3,
        )

        self.assertEqual(payload["status"], "partial_point_in_time")
        self.assertFalse(payload["integrity"]["survivorship_bias_eliminated"])
        self.assertTrue(payload["integrity"]["survivorship_bias_substantially_reduced"])
        dynamic = _track(payload, "historical_membership_rule")
        self.assertGreater(dynamic["rebalance_count"], 2)
        for rebalance in dynamic["selection_history"]:
            known = universe.members_as_of(pd.Timestamp(rebalance["date"]))
            selected = {row["ticker"] for row in rebalance["selected"]}
            self.assertTrue(selected.issubset(known))

    def test_future_membership_changes_do_not_change_past_dynamic_curve(self) -> None:
        prices, universe = _point_in_time_fixture()
        cutoff = prices.index[-220]
        alternative = HistoricalUniverse(
            dates=universe.dates,
            members=(
                universe.members[0],
                frozenset({"B", "D"}),
            ),
            source_url="fixture",
            source_commit="fixture-alternative",
        )
        prices["D"] = prices["C"] * 0.85

        original = run_point_in_time_experiment(self.config, prices, universe, years=3)
        changed = run_point_in_time_experiment(self.config, prices, alternative, years=3)
        original_track = _track(original, "historical_membership_rule")
        changed_track = _track(changed, "historical_membership_rule")
        original_curve = {
            row["date"]: row["portfolio_value"]
            for row in original_track["equity_curve"]
            if pd.Timestamp(row["date"]) < cutoff
        }
        changed_curve = {
            row["date"]: row["portfolio_value"]
            for row in changed_track["equity_curve"]
            if pd.Timestamp(row["date"]) < cutoff
        }
        self.assertEqual(original_curve.keys(), changed_curve.keys())
        for date, value in original_curve.items():
            self.assertAlmostEqual(value, changed_curve[date], places=10)

    def test_parses_ken_french_daily_table_without_using_footer_rows(self) -> None:
        text = "\n".join(
            [
                "Research file",
                ",Lo PRIOR,Hi PRIOR",
                "20240102, 1.00, 2.00",
                "20240103, -1.00, 0.50",
                "",
                "Average Equal Weighted Returns -- Daily",
            ]
        )
        frame = parse_ken_french_daily_table(text, "Lo PRIOR")
        self.assertEqual(list(frame.columns), ["Lo PRIOR", "Hi PRIOR"])
        self.assertEqual(len(frame), 2)
        self.assertAlmostEqual(frame.loc[pd.Timestamp("2024-01-03"), "Hi PRIOR"], 0.5)


def _track(payload: dict, track_id: str) -> dict:
    return next(item for item in payload["tracks"] if item["id"] == track_id)


def _point_in_time_fixture() -> tuple[pd.DataFrame, HistoricalUniverse]:
    index = pd.bdate_range("2021-01-04", periods=1200)
    rng = np.random.default_rng(71)
    market = np.cumprod(1.0 + rng.normal(0.00035, 0.009, len(index))) * 100.0
    prices = pd.DataFrame(
        {
            "SPY": market,
            "A": market * np.linspace(0.8, 1.45, len(index)),
            "B": market * np.linspace(1.0, 1.12, len(index)),
            "C": market * np.linspace(0.7, 1.65, len(index)),
        },
        index=index,
    )
    universe = HistoricalUniverse(
        dates=(index[0], index[-300]),
        members=(frozenset({"A", "B"}), frozenset({"B", "C"})),
        source_url="fixture",
        source_commit="fixture",
    )
    return prices, universe


if __name__ == "__main__":
    unittest.main()
