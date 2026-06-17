from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd


def fetch_close_prices(tickers: list[str], lookback_days: int = 500) -> pd.DataFrame:
    import yfinance as yf

    if not tickers:
        raise ValueError("No tickers provided")

    start = date.today() - timedelta(days=lookback_days)
    frame = yf.download(
        tickers=tickers,
        start=start.isoformat(),
        progress=False,
        auto_adjust=True,
        group_by="ticker",
        threads=True,
    )

    if frame.empty:
        raise RuntimeError("No market data returned from yfinance")

    if isinstance(frame.columns, pd.MultiIndex):
        close = frame.xs("Close", level=1, axis=1)
    else:
        close = frame[["Close"]].rename(columns={"Close": tickers[0]})

    close = close.sort_index().dropna(how="all")
    return close


def load_close_prices_csv(path: str | Path, tickers: list[str]) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["Date"]).set_index("Date").sort_index()
    missing = [t for t in tickers if t not in frame.columns]
    if missing:
        missing_str = ", ".join(missing)
        raise ValueError(f"CSV is missing required tickers: {missing_str}")
    return frame[tickers].dropna(how="all")
