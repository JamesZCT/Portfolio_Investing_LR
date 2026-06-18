from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

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


def fetch_ohlc(ticker: str, lookback_days: int = 500) -> pd.DataFrame:
    import yfinance as yf

    start = date.today() - timedelta(days=lookback_days)
    frame = yf.download(
        tickers=[ticker],
        start=start.isoformat(),
        progress=False,
        auto_adjust=True,
        group_by="column",
        threads=False,
    )
    if frame.empty:
        raise RuntimeError(f"No OHLC market data returned for {ticker}")

    if isinstance(frame.columns, pd.MultiIndex):
        frame = frame.xs(ticker, level=1, axis=1)

    required = ["Open", "High", "Low", "Close"]
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise RuntimeError(f"OHLC response for {ticker} is missing: {', '.join(missing)}")

    out = frame[required].rename(columns={name: name.lower() for name in required})
    return out.sort_index().dropna(how="any")


def fetch_latest_quotes(tickers: list[str]) -> list[dict[str, Any]]:
    import yfinance as yf

    symbols = [ticker.upper().strip() for ticker in tickers if ticker.strip()]
    if not symbols:
        raise ValueError("No tickers provided")

    frame = yf.download(
        tickers=symbols,
        period="5d",
        interval="1d",
        progress=False,
        auto_adjust=True,
        group_by="ticker",
        threads=True,
    )
    if frame.empty:
        raise RuntimeError("No quote data returned from yfinance")

    quotes: list[dict[str, Any]] = []
    if isinstance(frame.columns, pd.MultiIndex):
        for ticker in symbols:
            if ticker not in frame.columns.get_level_values(0):
                continue
            quote = _latest_quote_from_frame(ticker, frame[ticker])
            if quote:
                quotes.append(quote)
    else:
        quote = _latest_quote_from_frame(symbols[0], frame)
        if quote:
            quotes.append(quote)
    return quotes


def synthesize_ohlc_from_close(series: pd.Series) -> pd.DataFrame:
    close = series.dropna()
    if close.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])

    previous = close.shift(1).fillna(close.iloc[0])
    open_ = previous * 0.998
    high = pd.concat([open_, close], axis=1).max(axis=1) * 1.008
    low = pd.concat([open_, close], axis=1).min(axis=1) * 0.992
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
        }
    )


def _latest_quote_from_frame(ticker: str, frame: pd.DataFrame) -> dict[str, Any] | None:
    if "Close" not in frame.columns:
        return None

    close = frame["Close"].dropna()
    if close.empty:
        return None

    last_date = close.index[-1]
    price = float(close.iloc[-1])
    previous = float(close.iloc[-2]) if len(close) > 1 else price
    change = price - previous
    change_pct = change / previous if previous else 0.0
    return {
        "ticker": ticker,
        "price": price,
        "previous_close": previous,
        "change": change,
        "change_pct": change_pct,
        "as_of": str(last_date.date()),
        "source": "yfinance",
    }
