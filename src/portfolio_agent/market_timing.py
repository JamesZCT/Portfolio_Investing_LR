from __future__ import annotations

from typing import Any, Iterable

import pandas as pd


US_TIMING_TICKERS = ("SPY", "QQQ", "VTI", "VXUS")


def build_market_timing_payload(
    prices: pd.DataFrame,
    *,
    benchmark: str,
    sector_etfs: Iterable[str] = (),
) -> dict[str, Any]:
    """Build a transparent public-rule proxy for DCA and tactical timing.

    The payload deliberately keeps scheduled investing separate from tactical
    exposure changes. It does not reproduce RIA's proprietary money-flow model.
    """

    requested = list(US_TIMING_TICKERS) if benchmark == "SPY" else [benchmark]
    if benchmark not in requested:
        requested.insert(0, benchmark)
    available = [ticker for ticker in requested if ticker in prices.columns]
    breadth = _sector_breadth(prices, sector_etfs)
    rows = [_timing_row(ticker, prices[ticker], breadth) for ticker in available]
    rows = [row for row in rows if row is not None]
    benchmark_row = next((row for row in rows if row["ticker"] == benchmark), None)

    return {
        "status": "available" if rows else "insufficient_data",
        "as_of": _latest_date(prices),
        "benchmark": benchmark,
        "summary": {
            "regime": benchmark_row["regime"] if benchmark_row else "unknown",
            "dca_action": benchmark_row["dca_action"] if benchmark_row else "review_data",
            "tactical_action": benchmark_row["tactical_action"] if benchmark_row else "review_data",
            "headline": benchmark_row["headline"] if benchmark_row else "Insufficient timing history",
        },
        "breadth": breadth,
        "rows": rows,
        "methodology": {
            "name": "Public 50/200-day trend and pullback proxy",
            "dca_policy": (
                "Scheduled long-term contributions remain separate from tactical timing. "
                "A moving-average signal does not automatically stop core DCA."
            ),
            "tactical_policy": (
                "A staged add requires an established rising trend and a controlled test of the 50-day average. "
                "Tactical risk reduction requires a 200-day break plus multiple confirmations."
            ),
            "decision_authority": "Deterministic price rules only; news and LLM commentary have zero decision weight.",
            "ria_disclosure": (
                "This is a transparent research proxy derived from public trend concepts. "
                "It is not RIA's proprietary Money Flow Buy/Sell model or client advice."
            ),
        },
    }


def _timing_row(ticker: str, values: pd.Series, breadth: dict[str, Any]) -> dict[str, Any] | None:
    series = values.dropna().astype(float)
    if len(series) < 220:
        return None

    ma50_series = series.rolling(50, min_periods=50).mean()
    ma200_series = series.rolling(200, min_periods=200).mean()
    price = float(series.iloc[-1])
    ma50 = float(ma50_series.iloc[-1])
    ma200 = float(ma200_series.iloc[-1])
    distance_ma50 = price / ma50 - 1.0
    distance_ma200 = price / ma200 - 1.0
    slope50 = _slope(ma50_series, 20)
    slope200 = _slope(ma200_series, 20)
    rsi14 = _rsi(series, 14)
    weekly_macd, weekly_signal = _weekly_macd(series)
    cross = _latest_cross(ma50_series, ma200_series)
    recent_touch = _recent_50dma_touch(series, ma50_series)

    above50 = price >= ma50
    above200 = price >= ma200
    golden_stack = ma50 >= ma200
    rising50 = slope50 > 0
    rising200 = slope200 > 0
    weekly_positive = weekly_macd >= weekly_signal
    breadth200 = breadth.get("above_200dma_pct")

    bearish_confirmations = [
        not rising200,
        not golden_stack,
        not weekly_positive,
        breadth200 is not None and breadth200 < 0.40,
    ]
    confirmation_count = sum(bool(value) for value in bearish_confirmations)

    pullback_setup = (
        above50
        and above200
        and golden_stack
        and rising50
        and rising200
        and recent_touch
        and 0.0 <= distance_ma50 <= 0.035
        and 35.0 <= rsi14 <= 65.0
    )
    extended = distance_ma50 >= 0.08 or rsi14 >= 70.0

    if not above200 and confirmation_count >= 3:
        regime = "risk_off"
        tactical_action = "reduce_tactical"
        headline = "Reduce tactical risk; keep long-term contributions tied to the written plan"
    elif not above200:
        regime = "defensive_watch"
        tactical_action = "wait_for_confirmation"
        headline = "200-day support is broken, but confirmation is incomplete"
    elif pullback_setup:
        regime = "bullish_pullback"
        tactical_action = "staged_add"
        headline = "Rising 50-day support held; a staged tactical add is eligible"
    elif above50 and golden_stack and rising200 and extended:
        regime = "bullish_extended"
        tactical_action = "hold_no_chase"
        headline = "Trend is constructive, but price is extended; hold without chasing"
    elif above50 and golden_stack and rising200:
        regime = "bullish"
        tactical_action = "hold_core"
        headline = "Trend supports holding core exposure"
    elif above200:
        regime = "caution"
        tactical_action = "wait_for_50dma_reclaim"
        headline = "Long trend remains intact; wait for short-trend confirmation"
    else:
        regime = "mixed"
        tactical_action = "wait_for_confirmation"
        headline = "Evidence is mixed; avoid a one-shot timing decision"

    evidence = [
        _position_evidence(price, ma50, ma200),
        f"50-day slope over 20 sessions: {slope50:+.1%}; 200-day slope: {slope200:+.1%}.",
        f"RSI(14): {rsi14:.1f}; weekly MACD is {'above' if weekly_positive else 'below'} its signal line.",
    ]
    if cross["event"] != "none":
        evidence.append(f"Most recent {cross['label'].lower()} occurred on {cross['date']}.")
    if breadth.get("available_count"):
        evidence.append(
            f"Sector ETF breadth: {breadth['above_50dma_pct']:.0%} above 50-day and "
            f"{breadth['above_200dma_pct']:.0%} above 200-day averages."
        )

    return {
        "ticker": ticker,
        "as_of": str(series.index[-1].date()),
        "price": round(price, 4),
        "ma50": round(ma50, 4),
        "ma200": round(ma200, 4),
        "distance_ma50_pct": round(distance_ma50 * 100.0, 2),
        "distance_ma200_pct": round(distance_ma200 * 100.0, 2),
        "ma50_slope_20d_pct": round(slope50 * 100.0, 2),
        "ma200_slope_20d_pct": round(slope200 * 100.0, 2),
        "rsi14": round(rsi14, 1),
        "weekly_macd": round(weekly_macd, 4),
        "weekly_macd_signal": round(weekly_signal, 4),
        "weekly_macd_positive": weekly_positive,
        "recent_50dma_touch": recent_touch,
        "cross": cross,
        "bearish_confirmation_count": confirmation_count,
        "regime": regime,
        "dca_action": "continue_core_dca",
        "tactical_action": tactical_action,
        "headline": headline,
        "evidence": evidence,
    }


def _sector_breadth(prices: pd.DataFrame, tickers: Iterable[str]) -> dict[str, Any]:
    available = []
    above50 = 0
    above200 = 0
    golden = 0
    for ticker in dict.fromkeys(tickers):
        if ticker not in prices.columns:
            continue
        series = prices[ticker].dropna().astype(float)
        if len(series) < 200:
            continue
        ma50 = float(series.tail(50).mean())
        ma200 = float(series.tail(200).mean())
        price = float(series.iloc[-1])
        available.append(ticker)
        above50 += int(price >= ma50)
        above200 += int(price >= ma200)
        golden += int(ma50 >= ma200)
    count = len(available)
    return {
        "label": "Sector ETF breadth",
        "available_count": count,
        "tickers": available,
        "above_50dma_pct": round(above50 / count, 4) if count else None,
        "above_200dma_pct": round(above200 / count, 4) if count else None,
        "ma50_above_ma200_pct": round(golden / count, 4) if count else None,
        "note": "Breadth uses configured sector ETFs, not every listed stock.",
    }


def _slope(series: pd.Series, sessions: int) -> float:
    values = series.dropna()
    if len(values) <= sessions or float(values.iloc[-sessions - 1]) == 0.0:
        return 0.0
    return float(values.iloc[-1] / values.iloc[-sessions - 1] - 1.0)


def _rsi(series: pd.Series, window: int) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0.0).ewm(alpha=1.0 / window, adjust=False).mean()
    loss = (-delta.clip(upper=0.0)).ewm(alpha=1.0 / window, adjust=False).mean()
    denominator = float(loss.iloc[-1])
    if denominator == 0.0:
        return 100.0
    relative_strength = float(gain.iloc[-1]) / denominator
    return 100.0 - (100.0 / (1.0 + relative_strength))


def _weekly_macd(series: pd.Series) -> tuple[float, float]:
    weekly = series.resample("W-FRI").last().dropna()
    macd = weekly.ewm(span=12, adjust=False).mean() - weekly.ewm(span=26, adjust=False).mean()
    signal = macd.ewm(span=9, adjust=False).mean()
    return float(macd.iloc[-1]), float(signal.iloc[-1])


def _latest_cross(ma50: pd.Series, ma200: pd.Series) -> dict[str, Any]:
    spread = (ma50 - ma200).dropna()
    if spread.empty:
        return {"event": "none", "label": "No completed cross", "date": None, "sessions_ago": None}
    state = spread >= 0
    changed = state.ne(state.shift(1))
    cross_dates = spread.index[changed]
    if len(cross_dates) <= 1:
        return {"event": "none", "label": "No recent cross", "date": None, "sessions_ago": None}
    date = cross_dates[-1]
    sessions_ago = len(spread.loc[date:]) - 1
    if sessions_ago > 63:
        return {"event": "none", "label": "No recent cross", "date": None, "sessions_ago": sessions_ago}
    event = "golden_cross" if bool(state.loc[date]) else "death_cross"
    return {
        "event": event,
        "label": "Golden cross" if event == "golden_cross" else "Death cross",
        "date": str(date.date()),
        "sessions_ago": sessions_ago,
    }


def _recent_50dma_touch(series: pd.Series, ma50: pd.Series) -> bool:
    aligned = pd.concat([series.rename("price"), ma50.rename("ma50")], axis=1).dropna().tail(10)
    if aligned.empty:
        return False
    distance = (aligned["price"] / aligned["ma50"] - 1.0).abs()
    return bool(distance.min() <= 0.015)


def _position_evidence(price: float, ma50: float, ma200: float) -> str:
    relation50 = "above" if price >= ma50 else "below"
    relation200 = "above" if price >= ma200 else "below"
    return f"Price is {relation50} the 50-day average and {relation200} the 200-day average."


def _latest_date(prices: pd.DataFrame) -> str | None:
    if prices.empty:
        return None
    return str(prices.index.max().date())
