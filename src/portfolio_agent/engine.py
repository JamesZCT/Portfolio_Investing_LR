from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .backtest import run_backtest
from .config import AppConfig, load_config
from .data import fetch_close_prices, load_close_prices_csv
from .execution import SandboxExecutionAdapter, suggestions_to_orders
from .ml import build_risk_predictions
from .portfolio import propose_rebalance
from .report import write_report
from .sandbox import generate_sandbox_prices
from .signals import build_market_regime, build_sector_signals


@dataclass
class AnalysisResult:
    config: AppConfig
    prices: pd.DataFrame
    market_regime: Any
    signals: list[Any]
    suggestions: list[Any]
    risk_predictions: dict[str, Any]
    execution_results: list[Any]


def load_prices_for_config(cfg: AppConfig, prices_csv: str | None, lookback_days: int) -> pd.DataFrame:
    tickers = set(cfg.universe.sector_etfs.values())
    tickers.update(cfg.universe.positions.keys())
    tickers.update(cfg.universe.target_weights.keys())
    tickers.add(cfg.universe.benchmark)

    ordered_tickers = sorted(t for t in tickers if t != "CASH")
    if prices_csv:
        return load_close_prices_csv(prices_csv, ordered_tickers)
    return fetch_close_prices(ordered_tickers, lookback_days=lookback_days)


def run_analysis(
    config_path: str | Path,
    lookback_days: int = 900,
    prices_csv: str | None = None,
    sandbox_days: int | None = None,
) -> AnalysisResult:
    cfg = load_config(config_path)
    if sandbox_days is not None:
        prices = generate_sandbox_prices(cfg, days=sandbox_days)
    else:
        prices = load_prices_for_config(cfg, prices_csv, lookback_days)

    market_regime = build_market_regime(prices=prices, config=cfg)
    signals = build_sector_signals(prices=prices, config=cfg)
    holdings = [ticker for ticker in cfg.universe.positions if ticker != "CASH"]
    latest_prices = {
        ticker: float(prices[ticker].dropna().iloc[-1])
        for ticker in holdings
        if ticker in prices.columns and not prices[ticker].dropna().empty
    }
    trailing_window = prices[[ticker for ticker in holdings if ticker in prices.columns]].tail(
        cfg.indicators.trailing_high_lookback_days
    )
    trailing_highs = {ticker: float(trailing_window[ticker].max()) for ticker in trailing_window.columns}
    risk_predictions = build_risk_predictions(prices, holdings, cfg)
    suggestions = propose_rebalance(
        config=cfg,
        signals=signals,
        latest_prices=latest_prices,
        trailing_highs=trailing_highs,
        market_regime=market_regime,
        risk_predictions=risk_predictions,
    )
    execution_results = SandboxExecutionAdapter().execute(suggestions_to_orders(suggestions))

    return AnalysisResult(
        config=cfg,
        prices=prices,
        market_regime=market_regime,
        signals=signals,
        suggestions=suggestions,
        risk_predictions=risk_predictions,
        execution_results=execution_results,
    )


def write_analysis_report(result: AnalysisResult, out_dir: str | Path) -> tuple[Path, Path, Path]:
    return write_report(
        out_dir=Path(out_dir),
        config=result.config,
        prices=result.prices,
        signals=result.signals,
        suggestions=result.suggestions,
        market_regime=result.market_regime,
        risk_predictions=result.risk_predictions,
    )


def run_backtest_for_config(
    config_path: str | Path,
    lookback_days: int = 900,
    prices_csv: str | None = None,
    sandbox_days: int | None = None,
    rebalance_days: int = 21,
    transaction_cost_bps: float = 5.0,
):
    cfg = load_config(config_path)
    if sandbox_days is not None:
        prices = generate_sandbox_prices(cfg, days=sandbox_days)
    else:
        prices = load_prices_for_config(cfg, prices_csv, lookback_days)
    return run_backtest(
        config=cfg,
        prices=prices,
        rebalance_days=rebalance_days,
        transaction_cost_bps=transaction_cost_bps,
    )


def run_buy_and_hold_baseline(
    config_path: str | Path,
    lookback_days: int = 900,
    prices_csv: str | None = None,
    sandbox_days: int | None = None,
) -> dict[str, float]:
    from .backtest import compute_metrics

    cfg = load_config(config_path)
    if sandbox_days is not None:
        prices = generate_sandbox_prices(cfg, days=sandbox_days)
    else:
        prices = load_prices_for_config(cfg, prices_csv, lookback_days)

    holdings = [ticker for ticker in cfg.universe.positions if ticker != "CASH" and ticker in prices.columns]
    if not holdings:
        raise ValueError("No priced holdings available for buy-and-hold baseline")

    raw_weights = {ticker: cfg.universe.positions.get(ticker, 0.0) for ticker in holdings}
    cash_weight = cfg.universe.positions.get("CASH", 0.0)
    total = sum(raw_weights.values()) + cash_weight
    if total <= 0:
        raise ValueError("Initial positions must sum to a positive value")

    weights = {ticker: weight / total for ticker, weight in raw_weights.items()}
    cash_weight = cash_weight / total
    returns = prices[holdings].pct_change().fillna(0.0)

    value = 1.0
    rows = []
    for idx, dt in enumerate(returns.index):
        if idx == 0:
            rows.append({"date": dt, "portfolio_value": value, "daily_return": 0.0})
            continue
        day_return = float(sum(weights[ticker] * returns.at[dt, ticker] for ticker in holdings))
        day_return += cash_weight * 0.0
        value *= 1.0 + day_return
        rows.append({"date": dt, "portfolio_value": value, "daily_return": day_return})

    return compute_metrics(pd.DataFrame(rows))


def result_to_dashboard_payload(result: AnalysisResult) -> dict[str, Any]:
    cfg = result.config
    price_tail = result.prices.tail(260)
    benchmark = cfg.universe.benchmark
    benchmark_series = []
    if benchmark in price_tail.columns:
        benchmark_series = [
            {"date": str(idx.date()), "value": float(value)}
            for idx, value in price_tail[benchmark].dropna().items()
        ]

    return {
        "market_regime": asdict(result.market_regime),
        "signals": [asdict(item) for item in result.signals],
        "suggestions": [_suggestion_to_dict(item) for item in result.suggestions],
        "risk_predictions": [asdict(item) for item in result.risk_predictions.values()],
        "execution_results": [asdict(item) for item in result.execution_results],
        "positions": cfg.universe.positions,
        "target_weights": cfg.universe.target_weights,
        "sector_weights": _sector_weights(cfg.universe.positions, cfg.universe.ticker_sector),
        "benchmark_series": benchmark_series,
        "price_as_of": str(result.prices.index.max().date()) if not result.prices.empty else None,
        "universe": {
            "benchmark": cfg.universe.benchmark,
            "sector_etfs": cfg.universe.sector_etfs,
            "tickers": sorted(t for t in cfg.universe.positions if t != "CASH"),
        },
    }


def backtest_to_payload(backtest_result) -> dict[str, Any]:
    equity = backtest_result.equity_curve.copy()
    equity["date"] = pd.to_datetime(equity["date"]).dt.strftime("%Y-%m-%d")
    trades = backtest_result.trades.copy()
    if not trades.empty:
        trades["date"] = pd.to_datetime(trades["date"]).dt.strftime("%Y-%m-%d")
    return {
        "metrics": backtest_result.metrics,
        "equity_curve": equity.to_dict(orient="records"),
        "trades": trades.to_dict(orient="records"),
    }


def _suggestion_to_dict(item) -> dict[str, Any]:
    return {
        "ticker": item.ticker,
        "action": item.action,
        "delta_weight": item.delta_weight,
        "reason": item.reason,
        "rule_ids": list(item.rule_ids),
        "metadata": item.metadata,
    }


def _sector_weights(positions: dict[str, float], ticker_sector: dict[str, str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for ticker, weight in positions.items():
        if ticker == "CASH":
            continue
        sector = ticker_sector.get(ticker, "Unknown")
        out[sector] = out.get(sector, 0.0) + weight
    return out
