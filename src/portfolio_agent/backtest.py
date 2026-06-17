from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import AppConfig
from .ml import build_risk_predictions
from .portfolio import apply_trade_suggestions, propose_rebalance
from .signals import build_market_regime, build_sector_signals
from .visuals import generate_backtest_charts


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict[str, float]


def run_backtest(
    config: AppConfig,
    prices: pd.DataFrame,
    rebalance_days: int = 21,
    transaction_cost_bps: float = 5.0,
) -> BacktestResult:
    holdings = sorted(
        t
        for t in set(config.universe.target_weights.keys()) | set(config.universe.positions.keys())
        if t != "CASH"
    )
    missing = [t for t in holdings if t not in prices.columns]
    if missing:
        missing_str = ", ".join(missing)
        raise ValueError(f"Backtest prices are missing holdings: {missing_str}")

    returns = prices[holdings].pct_change().fillna(0.0)
    returns["CASH"] = 0.0
    dates = returns.index

    weights = {t: config.universe.positions.get(t, 0.0) for t in holdings}
    if "CASH" in config.universe.positions:
        weights["CASH"] = config.universe.positions["CASH"]
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("Initial positions must sum to a positive value")
    weights = {k: v / total for k, v in weights.items()}

    value = 1.0
    equity_rows: list[dict[str, float | str]] = []
    trade_rows: list[dict[str, float | str]] = []

    for i, dt in enumerate(dates):
        if i == 0:
            equity_rows.append({"date": dt, "portfolio_value": value, "daily_return": 0.0})
            continue

        should_rebalance = (i % rebalance_days) == 0
        if should_rebalance:
            history = prices.loc[:dt]
            market_regime = build_market_regime(history, config)
            signals = build_sector_signals(history, config)
            latest_prices = {ticker: float(history[ticker].iloc[-1]) for ticker in holdings}
            trailing_window = history[holdings].tail(config.indicators.trailing_high_lookback_days)
            trailing_highs = {ticker: float(trailing_window[ticker].max()) for ticker in holdings}
            risk_predictions = build_risk_predictions(history, holdings, config)
            suggestions = propose_rebalance(
                config,
                signals,
                current_positions=weights,
                latest_prices=latest_prices,
                trailing_highs=trailing_highs,
                market_regime=market_regime,
                risk_predictions=risk_predictions,
            )

            turnover = sum(abs(s.delta_weight) for s in suggestions if s.ticker != "CASH")
            if turnover > 0:
                cost = turnover * (transaction_cost_bps / 10_000.0)
                value *= 1.0 - cost

            weights = apply_trade_suggestions(weights, suggestions)

            for s in suggestions:
                trade_rows.append(
                    {
                        "date": dt,
                        "ticker": s.ticker,
                        "action": s.action,
                        "delta_weight": s.delta_weight,
                        "reason": s.reason,
                        "rule_ids": ",".join(s.rule_ids),
                    }
                )

        day_return = float(sum(weights.get(t, 0.0) * returns.at[dt, t] for t in returns.columns))
        value *= 1.0 + day_return
        equity_rows.append({"date": dt, "portfolio_value": value, "daily_return": day_return})

    equity = pd.DataFrame(equity_rows)
    trades = pd.DataFrame(trade_rows)
    metrics = compute_metrics(equity)
    return BacktestResult(equity_curve=equity, trades=trades, metrics=metrics)


def compute_metrics(equity_curve: pd.DataFrame) -> dict[str, float]:
    returns = equity_curve["daily_return"].fillna(0.0)
    value_series = equity_curve["portfolio_value"]

    n_days = max(1, len(equity_curve) - 1)
    years = n_days / 252.0

    final_value = float(value_series.iloc[-1])
    cagr = (final_value ** (1.0 / years) - 1.0) if years > 0 else 0.0

    vol = float(returns.std(ddof=0) * math.sqrt(252.0))
    sharpe = float((returns.mean() * 252.0) / vol) if vol > 0 else 0.0

    running_max = value_series.cummax()
    drawdown = (value_series / running_max) - 1.0
    max_drawdown = float(drawdown.min())

    return {
        "final_value": final_value,
        "cagr": float(cagr),
        "annualized_volatility": vol,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
    }


def write_backtest_report(out_dir: str | Path, result: BacktestResult) -> tuple[Path, Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    equity_csv = out_dir / "backtest_equity_curve.csv"
    trades_csv = out_dir / "backtest_trades.csv"
    summary_md = out_dir / "backtest_summary.md"

    result.equity_curve.to_csv(equity_csv, index=False)
    result.trades.to_csv(trades_csv, index=False)
    chart_paths = generate_backtest_charts(out_dir, result.equity_curve, result.trades)

    m = result.metrics
    lines = [
        "# Backtest Summary",
        "",
        f"- Final value: {m['final_value']:.4f}",
        f"- CAGR: {100.0 * m['cagr']:.2f}%",
        f"- Annualized volatility: {100.0 * m['annualized_volatility']:.2f}%",
        f"- Sharpe: {m['sharpe']:.3f}",
        f"- Max drawdown: {100.0 * m['max_drawdown']:.2f}%",
        "",
        f"- Total trade records: {len(result.trades)}",
        "",
        "## Visuals",
    ]
    for label, path in chart_paths.items():
        lines.append(f"- {label}: `{path.relative_to(out_dir)}`")
    summary_md.write_text("\n".join(lines))

    metrics_json = out_dir / "backtest_metrics.json"
    metrics_json.write_text(json.dumps(result.metrics, indent=2))

    return equity_csv, trades_csv, summary_md
