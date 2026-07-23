from __future__ import annotations

import numpy as np
import pandas as pd

from .config import AppConfig


def generate_sandbox_prices(config: AppConfig, days: int = 900, seed: int = 7) -> pd.DataFrame:
    tickers = sorted(
        set(config.universe.positions)
        | set(config.universe.target_weights)
        | set(config.universe.sector_etfs.values())
        | {
            ticker
            for profile in (config.optimization.profiles or {}).values()
            for ticker in profile.assets
        }
        | {config.universe.benchmark}
    )
    tickers = [ticker for ticker in tickers if ticker != "CASH"]

    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    frame = pd.DataFrame(index=dates)

    regime = _regime_series(days)
    market_noise = rng.normal(0.0, 0.008, size=days)
    market_returns = regime + market_noise

    for idx, ticker in enumerate(tickers):
        beta = 0.75 + 0.08 * (idx % 7)
        idiosyncratic = rng.normal(0.0, 0.010 + 0.001 * (idx % 4), size=days)
        drift = 0.00010 + 0.00002 * (idx % 5)
        returns = drift + beta * market_returns + idiosyncratic

        if idx % 6 == 0 and days > 360:
            shock_start = int(days * 0.62)
            returns[shock_start : shock_start + 35] -= 0.006
        if idx % 5 == 0 and days > 500:
            meltup_start = int(days * 0.78)
            returns[meltup_start : meltup_start + 45] += 0.004

        frame[ticker] = 100.0 * np.cumprod(1.0 + returns)

    return frame.round(4)


def _regime_series(days: int) -> np.ndarray:
    out = np.full(days, 0.00025)
    if days > 300:
        out[int(days * 0.35) : int(days * 0.48)] = -0.0012
    if days > 600:
        out[int(days * 0.48) : int(days * 0.68)] = 0.0007
        out[int(days * 0.82) :] = -0.00035
    return out
