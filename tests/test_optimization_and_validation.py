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
from portfolio_agent.strategy_comparison import (
    DYNAMIC_RANGES,
    load_nasdaq100_historical_universe,
    run_index_core_strategy_comparison,
)


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

    def test_reconstructs_nasdaq_membership_from_yearly_snapshots(self) -> None:
        source_texts = {
            2020: _nasdaq_yaml(
                2020,
                ["AAPL", "MSFT"],
                {"2020-12-21": {"difference": ["MSFT"], "union": ["OKTA"]}},
            ),
            2021: _nasdaq_yaml(
                2021,
                ["AAPL", "OKTA"],
                {"2021-12-20": {"difference": ["OKTA"], "union": ["NVDA"]}},
            ),
        }
        universe = load_nasdaq100_historical_universe(
            start_year=2020,
            end_year=2021,
            source_texts=source_texts,
        )

        self.assertEqual(universe.members_as_of("2020-01-01"), {"AAPL", "MSFT"})
        self.assertEqual(universe.members_as_of("2020-12-21"), {"AAPL", "OKTA"})
        self.assertEqual(universe.members_as_of("2021-12-20"), {"AAPL", "NVDA"})

    def test_dynamic_qqq_challenger_respects_predeclared_ranges(self) -> None:
        prices, universe = _strategy_comparison_fixture()
        payload = run_index_core_strategy_comparison(
            prices,
            universe,
            sp500_universe=universe,
            years=3,
        )

        self.assertEqual(payload["status"], "partial_point_in_time")
        self.assertFalse(payload["integrity"]["parameters_optimized_on_displayed_window"])
        self.assertFalse(payload["integrity"]["ria_proxy_is_proprietary_mfbr"])
        challenger = _track(payload, "dynamic_qqq_challenger")
        for rebalance in challenger["allocation_history"]:
            weights = rebalance["weights"]
            active_weight = 1.0 - sum(
                weights.get(ticker, 0.0) for ticker in ("SPY", "QQQ", "BIL")
            )
            expanded = {
                "SPY": weights.get("SPY", 0.0),
                "QQQ": weights.get("QQQ", 0.0),
                "BIL": weights.get("BIL", 0.0),
                "ACTIVE": active_weight,
            }
            self.assertAlmostEqual(sum(weights.values()), 1.0, places=10)
            for sleeve, value in expanded.items():
                lower, upper = DYNAMIC_RANGES[sleeve]
                self.assertGreaterEqual(value, lower - 1e-9)
                self.assertLessEqual(value, upper + 1e-9)

    def test_index_core_active_selection_uses_members_known_on_date(self) -> None:
        prices, universe = _strategy_comparison_fixture()
        payload = run_index_core_strategy_comparison(
            prices,
            universe,
            sp500_universe=universe,
            years=3,
        )
        challenger = _track(payload, "dynamic_qqq_challenger")
        for rebalance in challenger["allocation_history"]:
            known = universe.members_as_of(rebalance["date"])
            self.assertTrue(set(rebalance["active_selection"]).issubset(known))

    def test_future_prices_do_not_change_past_qqq_challenger_curve(self) -> None:
        prices, universe = _strategy_comparison_fixture()
        cutoff = prices.index[-180]
        original = run_index_core_strategy_comparison(
            prices,
            universe,
            sp500_universe=universe,
            years=3,
        )
        changed = prices.copy()
        rng = np.random.default_rng(91)
        future = changed.index > cutoff
        changed.loc[future, :] *= rng.uniform(
            0.35,
            1.80,
            size=(int(future.sum()), len(changed.columns)),
        )
        perturbed = run_index_core_strategy_comparison(
            changed,
            universe,
            sp500_universe=universe,
            years=3,
        )
        original_curve = _curve_through(
            _track(original, "dynamic_qqq_challenger"),
            cutoff,
        )
        changed_curve = _curve_through(
            _track(perturbed, "dynamic_qqq_challenger"),
            cutoff,
        )
        self.assertEqual(original_curve.keys(), changed_curve.keys())
        for date, value in original_curve.items():
            self.assertAlmostEqual(value, changed_curve[date], places=10)


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


def _strategy_comparison_fixture() -> tuple[pd.DataFrame, HistoricalUniverse]:
    index = pd.bdate_range("2020-01-02", periods=1450)
    rng = np.random.default_rng(812)
    market_returns = rng.normal(0.00035, 0.010, len(index))
    qqq_returns = 1.15 * market_returns + rng.normal(0.00012, 0.005, len(index))
    bill_returns = np.full(len(index), 0.00012)
    prices = pd.DataFrame(
        {
            "SPY": 100.0 * np.cumprod(1.0 + market_returns),
            "QQQ": 100.0 * np.cumprod(1.0 + qqq_returns),
            "BIL": 100.0 * np.cumprod(1.0 + bill_returns),
        },
        index=index,
    )
    members = [f"N{number:02d}" for number in range(14)]
    for number, ticker in enumerate(members):
        alpha = 0.00003 * (number - 5)
        noise = rng.normal(alpha, 0.006 + number * 0.00015, len(index))
        prices[ticker] = 50.0 * np.cumprod(1.0 + market_returns + noise)
    change_date = index[-500]
    universe = HistoricalUniverse(
        dates=(index[0], change_date, index[-1]),
        members=(
            frozenset(members[:12]),
            frozenset(members[2:14]),
            frozenset(members[2:14]),
        ),
        source_url="fixture",
        source_commit="fixture-nasdaq",
    )
    return prices, universe


def _nasdaq_yaml(
    year: int,
    tickers: list[str],
    changes: dict[str, dict[str, list[str]]],
) -> str:
    import yaml

    return yaml.safe_dump(
        {
            "year": year,
            "tickers_on_Jan_1": tickers,
            "changes": changes,
        },
        sort_keys=False,
    )


def _curve_through(track: dict, cutoff: pd.Timestamp) -> dict[str, float]:
    return {
        row["date"]: row["portfolio_value"]
        for row in track["equity_curve"]
        if pd.Timestamp(row["date"]) <= cutoff
    }


if __name__ == "__main__":
    unittest.main()
