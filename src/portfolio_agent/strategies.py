from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .backtest import compute_metrics, drift_weights, run_backtest
from .config import AppConfig
from .indicators import moving_average


@dataclass
class StrategyComparison:
    name: str
    description: str
    metrics: dict[str, float]
    equity_curve: pd.DataFrame
    turnover: float


def compare_strategies(
    config: AppConfig,
    prices: pd.DataFrame,
    rebalance_days: int = 21,
    transaction_cost_bps: float = 5.0,
) -> list[StrategyComparison]:
    holdings = _priced_holdings(config, prices)
    if not holdings:
        raise ValueError("No priced holdings available for strategy comparison")

    returns = prices[holdings].pct_change().fillna(0.0)
    initial_weights = _normalized_weights(config.universe.positions, holdings)
    target_weights = _normalized_weights(config.universe.target_weights, holdings)

    out = [
        _simulate_static(
            name="Buy & Hold",
            description="Initial allocation held without rebalancing.",
            returns=returns,
            weights=initial_weights,
        ),
        _simulate_rebalance(
            name="Calendar Rebalance",
            description=f"Rebalance to targets every {rebalance_days} trading days.",
            returns=returns,
            initial_weights=initial_weights,
            target_weights=target_weights,
            rebalance_days=rebalance_days,
            transaction_cost_bps=transaction_cost_bps,
            threshold=None,
        ),
        _simulate_rebalance(
            name="Threshold Rebalance",
            description="Rebalance only when target drift exceeds configured thresholds.",
            returns=returns,
            initial_weights=initial_weights,
            target_weights=target_weights,
            rebalance_days=rebalance_days,
            transaction_cost_bps=transaction_cost_bps,
            threshold=config.rules.overweight_trigger,
        ),
        _simulate_trend_filter(
            config=config,
            prices=prices,
            returns=returns,
            initial_weights=initial_weights,
            target_weights=target_weights,
            rebalance_days=rebalance_days,
            transaction_cost_bps=transaction_cost_bps,
        ),
    ]

    rule_engine = run_backtest(
        config=config,
        prices=prices,
        rebalance_days=rebalance_days,
        transaction_cost_bps=transaction_cost_bps,
    )
    rule_turnover = 0.0
    if not rule_engine.trades.empty:
        rule_turnover = float(rule_engine.trades["delta_weight"].abs().sum())
    out.append(
        StrategyComparison(
            name="Rule Engine",
            description="Full current rule stack: trend, z-score, caps, stops, cash buffer, and ML risk overlay.",
            metrics=rule_engine.metrics,
            equity_curve=rule_engine.equity_curve,
            turnover=rule_turnover,
        )
    )

    return out


def comparison_to_payload(comparisons: list[StrategyComparison]) -> dict:
    return {
        "strategies": [
            {
                "name": item.name,
                "description": item.description,
                "metrics": item.metrics,
                "turnover": item.turnover,
                "equity_curve": _equity_payload(item.equity_curve),
            }
            for item in comparisons
        ]
    }


def _priced_holdings(config: AppConfig, prices: pd.DataFrame) -> list[str]:
    tickers = sorted(
        ticker
        for ticker in set(config.universe.positions) | set(config.universe.target_weights)
        if ticker != "CASH" and ticker in prices.columns
    )
    return tickers


def _normalized_weights(raw: dict[str, float], holdings: list[str]) -> dict[str, float]:
    weights = {ticker: raw.get(ticker, 0.0) for ticker in holdings}
    total = sum(weights.values())
    if total <= 0:
        return {ticker: 1.0 / len(holdings) for ticker in holdings}
    return {ticker: weight / total for ticker, weight in weights.items()}


def _simulate_static(
    name: str,
    description: str,
    returns: pd.DataFrame,
    weights: dict[str, float],
) -> StrategyComparison:
    value = 1.0
    rows = []
    for idx, dt in enumerate(returns.index):
        if idx == 0:
            rows.append({"date": dt, "portfolio_value": value, "daily_return": 0.0})
            continue
        day_return = float(sum(weights[ticker] * returns.at[dt, ticker] for ticker in weights))
        value *= 1.0 + day_return
        weights = drift_weights(weights, returns.loc[dt], day_return)
        rows.append({"date": dt, "portfolio_value": value, "daily_return": day_return})

    equity = pd.DataFrame(rows)
    return StrategyComparison(name, description, compute_metrics(equity), equity, turnover=0.0)


def _simulate_rebalance(
    name: str,
    description: str,
    returns: pd.DataFrame,
    initial_weights: dict[str, float],
    target_weights: dict[str, float],
    rebalance_days: int,
    transaction_cost_bps: float,
    threshold: float | None,
) -> StrategyComparison:
    value = 1.0
    weights = dict(initial_weights)
    rows = []
    total_turnover = 0.0

    for idx, dt in enumerate(returns.index):
        if idx == 0:
            rows.append({"date": dt, "portfolio_value": value, "daily_return": 0.0})
            continue

        day_return = float(sum(weights[ticker] * returns.at[dt, ticker] for ticker in weights))
        value *= 1.0 + day_return
        weights = drift_weights(weights, returns.loc[dt], day_return)

        if idx % rebalance_days == 0:
            should_rebalance = True
            if threshold is not None:
                should_rebalance = any(abs(weights.get(t, 0.0) - target_weights.get(t, 0.0)) > threshold for t in target_weights)
            if should_rebalance:
                turnover = sum(abs(target_weights.get(t, 0.0) - weights.get(t, 0.0)) for t in target_weights)
                total_turnover += turnover
                value *= 1.0 - turnover * (transaction_cost_bps / 10_000.0)
                weights = dict(target_weights)

        rows.append({"date": dt, "portfolio_value": value, "daily_return": day_return})

    equity = pd.DataFrame(rows)
    return StrategyComparison(name, description, compute_metrics(equity), equity, turnover=total_turnover)


def _simulate_trend_filter(
    config: AppConfig,
    prices: pd.DataFrame,
    returns: pd.DataFrame,
    initial_weights: dict[str, float],
    target_weights: dict[str, float],
    rebalance_days: int,
    transaction_cost_bps: float,
) -> StrategyComparison:
    value = 1.0
    weights = dict(initial_weights)
    rows = []
    total_turnover = 0.0
    benchmark = config.universe.benchmark
    benchmark_ma = moving_average(prices[benchmark], config.indicators.trend_ma_window) if benchmark in prices.columns else None

    for idx, dt in enumerate(returns.index):
        if idx == 0:
            rows.append({"date": dt, "portfolio_value": value, "daily_return": 0.0})
            continue

        day_return = float(sum(weights.get(ticker, 0.0) * returns.at[dt, ticker] for ticker in returns.columns))
        value *= 1.0 + day_return
        weights = drift_weights(weights, returns.loc[dt], day_return)

        if idx % rebalance_days == 0:
            bearish = False
            if benchmark_ma is not None and dt in benchmark_ma.index and benchmark in prices.columns:
                ma_value = benchmark_ma.at[dt]
                bearish = pd.notna(ma_value) and float(prices.at[dt, benchmark]) < float(ma_value)

            desired = _scaled_weights(target_weights, 1.0 - config.rules.defensive_cash_weight) if bearish else dict(target_weights)
            turnover = sum(abs(desired.get(t, 0.0) - weights.get(t, 0.0)) for t in set(desired) | set(weights))
            if turnover > config.rules.min_trade_weight:
                total_turnover += turnover
                value *= 1.0 - turnover * (transaction_cost_bps / 10_000.0)
                weights = desired

        rows.append({"date": dt, "portfolio_value": value, "daily_return": day_return})

    equity = pd.DataFrame(rows)
    return StrategyComparison(
        "Trend Filter",
        f"Target allocation when {benchmark} is above MA{config.indicators.trend_ma_window}; defensive cash when below.",
        compute_metrics(equity),
        equity,
        turnover=total_turnover,
    )


def _scaled_weights(weights: dict[str, float], scale: float) -> dict[str, float]:
    scaled = {ticker: weight * scale for ticker, weight in weights.items()}
    scaled["CASH"] = max(0.0, 1.0 - sum(scaled.values()))
    return scaled


def _equity_payload(equity: pd.DataFrame) -> list[dict[str, float | str]]:
    frame = equity.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
    return frame.to_dict(orient="records")
