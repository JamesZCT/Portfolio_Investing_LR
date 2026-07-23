from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from .backtest import compute_metrics, downsample_equity_curve, drift_weights
from .config import AppConfig, OptimizationProfileConfig
from .optimization import optimize_profile


@dataclass
class ValidationTrack:
    track_id: str
    name_en: str
    name_zh: str
    description_en: str
    description_zh: str
    equity_curve: pd.DataFrame
    metrics: dict[str, float]
    turnover: float
    rebalance_count: int
    latest_holdings: list[str]


def run_historical_validation(
    config: AppConfig,
    prices: pd.DataFrame,
    *,
    years: int = 10,
    rule_rebalance_days: int = 21,
    optimizer_rebalance_days: int = 63,
    transaction_cost_bps: float | None = None,
) -> dict[str, Any]:
    if prices.empty:
        raise ValueError("Historical validation requires price data")
    prices = prices.sort_index().ffill()
    costs = (
        config.optimization.transaction_cost_bps
        if transaction_cost_bps is None
        else transaction_cost_bps
    )
    evaluation_start = _evaluation_start(config, prices, years)
    benchmark = config.universe.benchmark
    if benchmark not in prices:
        raise ValueError(f"Historical validation is missing benchmark {benchmark}")

    tracks = [
        _simulate_static_benchmark(prices, benchmark, evaluation_start),
        _simulate_track(
            prices=prices,
            evaluation_start=evaluation_start,
            rebalance_days=rule_rebalance_days,
            transaction_cost_bps=costs,
            target_builder=lambda history: _price_rule_target(config, history),
            track_id="price_rule_reconstruction",
            name_en="Price-rule reconstruction",
            name_zh="价格规则重建",
            description_en=(
                "Monthly cross-sectional momentum/trend screen using only information "
                "available at each rebalance close."
            ),
            description_zh="每月使用当时收盘前可见数据进行横截面动量和趋势筛选。",
        ),
    ]
    for profile_id, profile in (config.optimization.profiles or {}).items():
        tracks.append(
            _simulate_track(
                prices=prices,
                evaluation_start=evaluation_start,
                rebalance_days=optimizer_rebalance_days,
                transaction_cost_bps=costs,
                target_builder=lambda history, pid=profile_id, item=profile: _profile_target(
                    config, pid, item, history
                ),
                track_id=f"optimizer_{profile_id}",
                name_en=f"{profile.name_en} optimizer",
                name_zh=f"{profile.name_zh}优化组合",
                description_en=(
                    f"Quarterly walk-forward {profile.objective} allocation with a "
                    "two-year minimum training window."
                ),
                description_zh=(
                    f"每季度滚动执行 {profile.objective} 配置，至少使用两年历史训练窗口。"
                ),
            )
        )

    benchmark_metrics = tracks[0].metrics
    track_payloads = []
    for track in tracks:
        metrics = dict(track.metrics)
        metrics["excess_cagr_vs_benchmark"] = (
            metrics["cagr"] - benchmark_metrics["cagr"]
        )
        metrics["drawdown_improvement_vs_benchmark"] = (
            metrics["max_drawdown"] - benchmark_metrics["max_drawdown"]
        )
        frame = track.equity_curve.copy()
        frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
        frame = downsample_equity_curve(frame)
        track_payloads.append(
            {
                "id": track.track_id,
                "name_en": track.name_en,
                "name_zh": track.name_zh,
                "description_en": track.description_en,
                "description_zh": track.description_zh,
                "metrics": metrics,
                "turnover": track.turnover,
                "rebalance_count": track.rebalance_count,
                "latest_holdings": track.latest_holdings,
                "equity_curve": frame.to_dict(orient="records"),
            }
        )

    candidate_assets = sorted(_validation_assets(config))
    return {
        "status": "exploratory",
        "requested_years": years,
        "source_start_date": _date_string(prices.index.min()),
        "evaluation_start_date": _date_string(evaluation_start),
        "evaluation_end_date": _date_string(prices.index.max()),
        "data_as_of": _date_string(prices.index.max()),
        "benchmark": benchmark,
        "transaction_cost_bps": costs,
        "tracks": track_payloads,
        "universe": {
            "tickers": candidate_assets,
            "size": len(candidate_assets),
            "definition_en": (
                "Current configured and optimizer candidate assets with available history."
            ),
            "definition_zh": "当前配置及优化器候选资产中具有足够历史数据的标的。",
        },
        "integrity": {
            "lookahead_protection": (
                "A target is calculated after day t closes and first affects returns on day t+1."
            ),
            "lookahead_protection_zh": "目标权重在 t 日收盘后计算，最早影响 t+1 日收益。",
            "transaction_costs_included": True,
            "fundamental_layer_included": False,
            "survivorship_bias": True,
            "delisted_securities_included": False,
            "claim_level": "exploratory_not_production",
        },
        "limitations_en": [
            "The current configured universe creates survivorship and selection bias.",
            "Historical point-in-time SEC fundamentals and delisted securities are not yet included.",
            "The price-rule track reconstructs the technical opportunity-map gates, not its current fundamental score.",
            "Taxes, bid-ask spread variation, market impact, and intraday execution are not modeled.",
        ],
        "limitations_zh": [
            "当前配置的候选池存在幸存者偏差和选择偏差。",
            "尚未纳入逐时点 SEC 基本面和退市证券。",
            "价格规则轨道重建机会地图的技术门槛，不包含今天的基本面评分。",
            "未模拟税务、买卖价差变化、市场冲击和日内成交。",
        ],
    }


def _evaluation_start(config: AppConfig, prices: pd.DataFrame, years: int) -> pd.Timestamp:
    requested = pd.Timestamp(prices.index.max()) - pd.DateOffset(years=years)
    minimum_index = min(config.optimization.min_history_days, max(1, len(prices) - 1))
    warmup = pd.Timestamp(prices.index[minimum_index])
    return max(requested, warmup)


def _simulate_static_benchmark(
    prices: pd.DataFrame,
    benchmark: str,
    evaluation_start: pd.Timestamp,
) -> ValidationTrack:
    frame = prices.loc[prices.index >= evaluation_start, [benchmark]].dropna()
    returns = frame[benchmark].pct_change(fill_method=None).fillna(0.0)
    equity = (1.0 + returns).cumprod()
    curve = pd.DataFrame(
        {
            "date": frame.index,
            "portfolio_value": equity.values,
            "daily_return": returns.values,
        }
    )
    return ValidationTrack(
        track_id="benchmark",
        name_en=f"{benchmark} benchmark",
        name_zh=f"{benchmark} 基准",
        description_en="Passive benchmark held over the same out-of-sample window.",
        description_zh="在同一滚动样本外区间被动持有基准。",
        equity_curve=curve,
        metrics=compute_metrics(curve),
        turnover=0.0,
        rebalance_count=0,
        latest_holdings=[benchmark],
    )


def _simulate_track(
    *,
    prices: pd.DataFrame,
    evaluation_start: pd.Timestamp,
    rebalance_days: int,
    transaction_cost_bps: float,
    target_builder: Callable[[pd.DataFrame], dict[str, float]],
    track_id: str,
    name_en: str,
    name_zh: str,
    description_en: str,
    description_zh: str,
) -> ValidationTrack:
    evaluation = prices.loc[prices.index >= evaluation_start]
    returns = prices.pct_change(fill_method=None).fillna(0.0)
    weights: dict[str, float] = {"CASH": 1.0}
    value = 1.0
    total_turnover = 0.0
    rebalance_count = 0
    rows: list[dict[str, Any]] = []

    for offset, dt in enumerate(evaluation.index):
        previous_value = value
        day_returns = returns.loc[dt]
        portfolio_return = float(
            sum(
                weight * float(day_returns.get(ticker, 0.0))
                for ticker, weight in weights.items()
                if ticker != "CASH"
            )
        )
        value *= 1.0 + portfolio_return
        weights = drift_weights(weights, day_returns, portfolio_return)

        if offset % rebalance_days == 0:
            history = prices.loc[:dt]
            desired = _normalize_target(target_builder(history))
            turnover = 0.5 * sum(
                abs(desired.get(ticker, 0.0) - weights.get(ticker, 0.0))
                for ticker in set(desired) | set(weights)
            )
            value *= max(0.0, 1.0 - turnover * transaction_cost_bps / 10_000.0)
            weights = desired
            total_turnover += turnover
            rebalance_count += 1

        net_return = value / previous_value - 1.0 if previous_value else 0.0
        rows.append(
            {
                "date": dt,
                "portfolio_value": value,
                "daily_return": net_return,
            }
        )

    curve = pd.DataFrame(rows)
    latest_holdings = [
        ticker
        for ticker, weight in sorted(weights.items(), key=lambda item: item[1], reverse=True)
        if ticker != "CASH" and weight > 0.005
    ]
    return ValidationTrack(
        track_id=track_id,
        name_en=name_en,
        name_zh=name_zh,
        description_en=description_en,
        description_zh=description_zh,
        equity_curve=curve,
        metrics=compute_metrics(curve),
        turnover=float(total_turnover),
        rebalance_count=rebalance_count,
        latest_holdings=latest_holdings,
    )


def _price_rule_target(config: AppConfig, history: pd.DataFrame) -> dict[str, float]:
    target, _ = build_price_rule_target(
        config,
        history,
        assets=_validation_assets(config),
    )
    return target


def build_price_rule_target(
    config: AppConfig,
    history: pd.DataFrame,
    *,
    assets: set[str] | frozenset[str] | list[str] | tuple[str, ...],
) -> tuple[dict[str, float], dict[str, Any]]:
    latest_history_date = pd.Timestamp(history.index.max())
    eligible_assets = [
        ticker
        for ticker in assets
        if ticker != config.universe.benchmark
        and ticker in history
        and history[ticker].notna().sum() >= 253
    ]
    rows = []
    for ticker in eligible_assets:
        close = history[ticker].dropna().tail(253)
        if len(close) < 253:
            continue
        if pd.Timestamp(close.index[-1]) < latest_history_date - pd.Timedelta(days=10):
            continue
        latest = float(close.iloc[-1])
        ma50 = float(close.tail(50).mean())
        ma200 = float(close.tail(200).mean())
        high = float(close.max())
        low = float(close.min())
        rows.append(
            {
                "ticker": ticker,
                "return_1y": latest / float(close.iloc[0]) - 1.0,
                "distance_ma50": latest / ma50 - 1.0,
                "distance_ma200": latest / ma200 - 1.0,
                "range_position": (latest - low) / (high - low) if high > low else 0.5,
                "inverse_range_width": -(high / low - 1.0) if low > 0 else -10.0,
                "gate": (
                    latest > ma50
                    and latest > ma200
                    and ma50 > ma200
                    and latest <= ma50 * 1.20
                ),
            }
        )
    if not rows:
        return {"CASH": 1.0}, {
            "price_eligible_count": 0,
            "selected": [],
            "market_regime": "cash",
        }
    screen = pd.DataFrame(rows).set_index("ticker")
    score = (
        0.30 * screen["return_1y"].rank(pct=True)
        + 0.20 * screen["distance_ma50"].rank(pct=True)
        + 0.20 * screen["distance_ma200"].rank(pct=True)
        + 0.15 * screen["range_position"].rank(pct=True)
        + 0.15 * screen["inverse_range_width"].rank(pct=True)
    )
    threshold = float(score.quantile(0.75))
    selected = score[(score >= threshold) & screen["gate"]].sort_values(ascending=False).head(8)
    if selected.empty:
        return {"CASH": 1.0}, {
            "price_eligible_count": len(screen),
            "selected": [],
            "market_regime": "cash",
        }

    benchmark = history[config.universe.benchmark].dropna()
    bullish = len(benchmark) >= 200 and float(benchmark.iloc[-1]) >= float(benchmark.tail(200).mean())
    risk_budget = 1.0 if bullish else 0.50
    weight = min(config.rules.max_single_position_weight, risk_budget / len(selected))
    target = {ticker: weight for ticker in selected.index}
    target["CASH"] = max(0.0, 1.0 - sum(target.values()))
    return target, {
        "price_eligible_count": len(screen),
        "selected": [
            {
                "ticker": ticker,
                "score": float(selected.loc[ticker]),
                "return_1y": float(screen.loc[ticker, "return_1y"]),
                "distance_ma200": float(screen.loc[ticker, "distance_ma200"]),
            }
            for ticker in selected.index
        ],
        "market_regime": "bullish" if bullish else "defensive",
    }


def _profile_target(
    config: AppConfig,
    profile_id: str,
    profile: OptimizationProfileConfig,
    history: pd.DataFrame,
) -> dict[str, float]:
    payload = optimize_profile(config, profile_id, profile, history)
    return {
        row["ticker"]: float(row["target_weight"])
        for row in payload["rows"]
        if float(row["target_weight"]) > 0
    }


def _validation_assets(config: AppConfig) -> set[str]:
    assets = {
        ticker
        for ticker in set(config.universe.positions) | set(config.universe.target_weights)
        if ticker != "CASH"
    }
    for profile in (config.optimization.profiles or {}).values():
        assets.update(profile.assets)
    assets.add(config.universe.benchmark)
    return assets


def _normalize_target(weights: dict[str, float]) -> dict[str, float]:
    cleaned = {ticker: max(0.0, float(weight)) for ticker, weight in weights.items()}
    total = sum(cleaned.values())
    if total <= 0:
        return {"CASH": 1.0}
    return {ticker: weight / total for ticker, weight in cleaned.items()}


def _date_string(value: Any) -> str:
    return str(pd.Timestamp(value).date())
