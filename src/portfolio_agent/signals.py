from __future__ import annotations

import pandas as pd

from .config import AppConfig
from .indicators import moving_average, rolling_std, zscore
from .models import MarketRegime, SectorSignal


def build_market_regime(prices: pd.DataFrame, config: AppConfig) -> MarketRegime:
    benchmark = config.universe.benchmark
    if benchmark not in prices.columns:
        return MarketRegime(
            benchmark=benchmark,
            price=0.0,
            trend_ma=0.0,
            trend_state="unknown",
            z=0.0,
            momentum=0.0,
            realized_vol=0.0,
            drawdown=0.0,
        )

    series = prices[benchmark].dropna()
    if series.empty:
        return MarketRegime(benchmark, 0.0, 0.0, "unknown", 0.0, 0.0, 0.0, 0.0)

    ind = config.indicators
    price = float(series.iloc[-1])
    trend_ma = _latest_float(moving_average(series, ind.trend_ma_window), default=0.0)
    trend_state = _trend_state(price, trend_ma, len(series), ind.trend_ma_window)
    z = _latest_float(zscore(series, ind.z_window), default=0.0)
    momentum = _momentum(series, ind.momentum_lookback_days)
    realized_vol = _realized_vol(series, ind.volatility_window)
    trailing_high = float(series.tail(ind.trailing_high_lookback_days).max())
    drawdown = (price / trailing_high) - 1.0 if trailing_high > 0 else 0.0

    return MarketRegime(
        benchmark=benchmark,
        price=price,
        trend_ma=trend_ma,
        trend_state=trend_state,
        z=z,
        momentum=momentum,
        realized_vol=realized_vol,
        drawdown=drawdown,
    )


def build_sector_signals(prices: pd.DataFrame, config: AppConfig) -> list[SectorSignal]:
    out: list[SectorSignal] = []
    ind = config.indicators

    for sector, etf in config.universe.sector_etfs.items():
        if etf not in prices.columns:
            continue
        series = prices[etf].dropna()
        if len(series) < config.rules.min_history_days:
            continue

        ma = moving_average(series, ind.ma_window)
        std = rolling_std(series, ind.std_window)
        z = zscore(series, ind.z_window)

        last_price = float(series.iloc[-1])
        last_ma = float(ma.iloc[-1])
        last_std = float(std.iloc[-1])
        last_z = float(z.iloc[-1])
        pct_from_ma = (last_price / last_ma) - 1.0 if last_ma else 0.0
        trend_ma = _latest_float(moving_average(series, ind.trend_ma_window), default=0.0)
        trend_state = _trend_state(last_price, trend_ma, len(series), ind.trend_ma_window)
        momentum = _momentum(series, ind.momentum_lookback_days)
        realized_vol = _realized_vol(series, ind.volatility_window)

        upper_3std = last_ma + (ind.extreme_z * last_std)
        lower_3std = last_ma - (ind.extreme_z * last_std)

        if pd.isna(last_ma) or pd.isna(last_std) or pd.isna(last_z):
            status = "insufficient_data"
        elif last_price >= upper_3std or last_z >= ind.extreme_z:
            status = "hyped"
        elif last_price <= lower_3std or last_z <= -ind.extreme_z:
            status = "undervalued"
        elif last_z >= ind.moderate_z:
            status = "extended"
        elif last_z <= -ind.moderate_z:
            status = "washed_out"
        elif last_z > 1.0:
            status = "warm"
        elif last_z < -1.0:
            status = "cool"
        else:
            status = "neutral"

        out.append(
            SectorSignal(
                sector=sector,
                etf=etf,
                price=last_price,
                ma=last_ma,
                std=last_std,
                z=last_z,
                pct_from_ma=pct_from_ma,
                status=status,
                trend_state=trend_state,
                trend_ma=trend_ma,
                momentum=momentum,
                realized_vol=realized_vol,
            )
        )

    return sorted(out, key=lambda s: s.z)


def _latest_float(series: pd.Series, default: float) -> float:
    clean = series.dropna()
    if clean.empty:
        return default
    return float(clean.iloc[-1])


def _trend_state(price: float, trend_ma: float, n_obs: int, window: int) -> str:
    if n_obs < window or trend_ma <= 0:
        return "unknown"
    if price > trend_ma:
        return "bullish"
    if price < trend_ma:
        return "bearish"
    return "neutral"


def _momentum(series: pd.Series, lookback: int) -> float:
    if len(series) <= lookback:
        return 0.0
    start = float(series.iloc[-lookback - 1])
    end = float(series.iloc[-1])
    if start <= 0:
        return 0.0
    return (end / start) - 1.0


def _realized_vol(series: pd.Series, window: int) -> float:
    returns = series.pct_change().dropna().tail(window)
    if returns.empty:
        return 0.0
    return float(returns.std(ddof=0) * (252.0 ** 0.5))
