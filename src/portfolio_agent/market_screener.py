from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any

import pandas as pd

from .sec_fundamentals import enrich_shortlist_with_sec, quote_only_research


UNIVERSE_DEFINITION = (
    "US-listed common equities on Nasdaq, NYSE, or NYSE American with market capitalization above $2B "
    "and average three-month daily volume above 1M shares."
)


def build_market_opportunities_payload(market: str, mode: str = "real") -> dict[str, Any]:
    if market != "us":
        return _unavailable_payload(market, "The broad-market opportunity screen currently covers US-listed equities only.")

    try:
        quotes, eligible_total = _fetch_us_equity_universe() if mode == "real" else (_sandbox_quotes(), 6)
        return rank_market_opportunities(
            quotes,
            market=market,
            eligible_total=eligible_total,
            enable_sec_research=mode == "real",
        )
    except Exception as exc:
        return _unavailable_payload(market, f"Market screen unavailable: {str(exc)[:180]}")


def rank_market_opportunities(
    quotes: list[dict[str, Any]],
    *,
    market: str = "us",
    eligible_total: int | None = None,
    generated_at: datetime | None = None,
    enable_sec_research: bool = False,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    latest_timestamps: list[int] = []
    for quote in quotes:
        symbol = str(quote.get("symbol") or "").strip().upper()
        price = _number(quote.get("regularMarketPrice"))
        ma50 = _number(quote.get("fiftyDayAverage"))
        ma200 = _number(quote.get("twoHundredDayAverage"))
        return_1y = _number(quote.get("fiftyTwoWeekChangePercent"))
        year_low = _number(quote.get("fiftyTwoWeekLow"))
        year_high = _number(quote.get("fiftyTwoWeekHigh"))
        if not symbol or not all(value is not None and value > 0 for value in (price, ma50, ma200, year_low, year_high)):
            continue
        if return_1y is None or year_high <= year_low:
            continue

        timestamp = quote.get("regularMarketTime")
        if isinstance(timestamp, (int, float)):
            latest_timestamps.append(int(timestamp))
        rows.append(
            {
                "ticker": symbol,
                "name": str(quote.get("shortName") or quote.get("longName") or symbol),
                "exchange": str(quote.get("fullExchangeName") or quote.get("exchange") or "US"),
                "price": price,
                "market_cap": _number(quote.get("marketCap")),
                "average_volume_3m": _number(quote.get("averageDailyVolume3Month")),
                "trailing_pe": _number(quote.get("trailingPE")),
                "forward_pe": _number(quote.get("forwardPE")),
                "price_to_book": _number(quote.get("priceToBook")),
                "eps_ttm": _number(quote.get("epsTrailingTwelveMonths")),
                "eps_forward": _number(quote.get("epsForward")),
                "profitable": (_number(quote.get("epsTrailingTwelveMonths")) or 0.0) > 0.0,
                "next_earnings_date": _timestamp_date(quote.get("earningsTimestamp")),
                "earnings_date_is_estimate": bool(quote.get("isEarningsDateEstimate")),
                "analyst_rating": str(quote.get("averageAnalystRating") or "") or None,
                "return_1y_pct": return_1y,
                "distance_ma50_pct": (price / ma50 - 1.0) * 100.0,
                "distance_ma200_pct": (price / ma200 - 1.0) * 100.0,
                "range_position": (price - year_low) / (year_high - year_low),
                "range_width_pct": (year_high - year_low) / price * 100.0,
                "above_ma50": price > ma50,
                "above_ma200": price > ma200,
                "ma50_above_ma200": ma50 > ma200,
            }
        )

    if not rows:
        return _unavailable_payload(market, "No equities had complete price and trend fields.")

    frame = pd.DataFrame(rows)
    frame["score"] = (
        0.30 * frame["return_1y_pct"].rank(pct=True)
        + 0.20 * frame["distance_ma50_pct"].rank(pct=True)
        + 0.20 * frame["distance_ma200_pct"].rank(pct=True)
        + 0.15 * frame["range_position"].rank(pct=True)
        + 0.15 * (1.0 - frame["range_width_pct"].rank(pct=True))
    )
    # Strong momentum that is far above its short trend is a watch item, not a fresh buy candidate.
    frame.loc[frame["distance_ma50_pct"] > 20.0, "score"] -= 0.12
    frame["score"] = (frame["score"].clip(0.0, 1.0) * 100.0).round(1)
    frame["eps_forward_growth_pct"] = frame.apply(_forward_eps_growth, axis=1)

    upper = float(frame["score"].quantile(0.75))
    lower = float(frame["score"].quantile(0.25))
    buy_mask = (
        (frame["score"] >= upper)
        & frame["above_ma50"]
        & frame["above_ma200"]
        & frame["ma50_above_ma200"]
        & frame["profitable"]
        & (frame["distance_ma50_pct"] <= 20.0)
    )
    sell_mask = (
        (frame["score"] <= lower)
        & ~frame["above_ma50"]
        & ~frame["above_ma200"]
    )
    frame["action"] = "hold_watch"
    frame.loc[buy_mask, "action"] = "buy_candidate"
    frame.loc[sell_mask, "action"] = "sell_avoid"
    frame["reason"] = frame.apply(_reason, axis=1)

    output_columns = [
        "ticker",
        "name",
        "exchange",
        "action",
        "score",
        "price",
        "return_1y_pct",
        "distance_ma50_pct",
        "distance_ma200_pct",
        "range_position",
        "market_cap",
        "average_volume_3m",
        "trailing_pe",
        "forward_pe",
        "price_to_book",
        "eps_ttm",
        "eps_forward",
        "eps_forward_growth_pct",
        "profitable",
        "next_earnings_date",
        "earnings_date_is_estimate",
        "analyst_rating",
        "range_width_pct",
        "reason",
    ]
    for column in (
        "price",
        "return_1y_pct",
        "distance_ma50_pct",
        "distance_ma200_pct",
        "range_position",
        "range_width_pct",
        "trailing_pe",
        "forward_pe",
        "price_to_book",
        "eps_ttm",
        "eps_forward",
        "eps_forward_growth_pct",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").round(2)

    buy = frame.loc[frame["action"] == "buy_candidate"].sort_values("score", ascending=False)
    hold = frame.loc[frame["action"] == "hold_watch"].sort_values("score", ascending=False)
    sell = frame.loc[frame["action"] == "sell_avoid"].sort_values("score", ascending=True)
    analyzed = len(frame)
    total = eligible_total if eligible_total is not None else len(quotes)
    latest = max(latest_timestamps) if latest_timestamps else None
    latest_date = datetime.fromtimestamp(latest, tz=timezone.utc).date().isoformat() if latest else None

    buy_records = _records(buy, output_columns)
    hold_records = _records(hold, output_columns)
    sell_records = _records(sell, output_columns)
    record_groups = [buy_records, hold_records, sell_records]
    for group in record_groups:
        for row in group:
            row["research"] = quote_only_research(row)

    if enable_sec_research and os.getenv("SEC_FUNDAMENTALS_ENABLED", "true").lower() in {"1", "true", "yes"}:
        deep_research = enrich_shortlist_with_sec(
            record_groups,
            limit_per_group=max(0, int(os.getenv("SEC_DEEP_RESEARCH_LIMIT_PER_GROUP", "5"))),
        )
    elif enable_sec_research:
        deep_research = {
            "status": "disabled",
            "researched_count": 0,
            "failed_count": 0,
            "note": "SEC deep research is disabled for this refresh.",
        }
    else:
        deep_research = {
            "status": "not_run",
            "researched_count": 0,
            "failed_count": 0,
            "note": "SEC deep research is not run for sandbox or direct ranking tests.",
        }

    return {
        "status": "available",
        "generated_at": (generated_at or datetime.now(timezone.utc)).isoformat(),
        "market": market,
        "source": {
            "name": "Yahoo Finance via yfinance",
            "url": "https://finance.yahoo.com/research-hub/screener/",
            "note": "Convenient research feed; not an exchange-authoritative market-data service.",
        },
        "universe": {
            "definition": UNIVERSE_DEFINITION,
            "eligible_total": total,
            "fetched_count": len(quotes),
            "analyzed_count": analyzed,
            "coverage_ratio": round(analyzed / total, 4) if total else 0.0,
            "latest_price_date": latest_date,
        },
        "methodology": {
            "summary": "Two-stage screen: cross-sectional trend and momentum for the liquid US universe, followed by SEC filing, earnings, valuation, quality, and balance-sheet research for the visible shortlist.",
            "buy_rule": "A research buy requires a strong trend screen plus acceptable sector-aware quality, valuation, financial-strength, and latest-earnings evidence.",
            "sell_rule": "Bottom-quartile score and below both the 50-day and 200-day averages.",
            "policy": "Research shortlist only. Sell/avoid means review an owned position or avoid a new entry; it is not an instruction to short or trade automatically.",
            "sector_models": {
                "software": "Growth, FCF margin, forward P/E, ROIC and dilution review.",
                "banks": "P/B and P/E relative to ROE, credit quality and regulatory capital.",
                "energy": "Normalized multi-year FCF yield, leverage and cycle resilience.",
                "reits": "P/FFO, AFFO growth, occupancy and debt maturity review.",
            },
        },
        "deep_research": deep_research,
        "action_counts": {
            "buy_candidate": int((frame["action"] == "buy_candidate").sum()),
            "hold_watch": int((frame["action"] == "hold_watch").sum()),
            "sell_avoid": int((frame["action"] == "sell_avoid").sum()),
        },
        "buy_candidates": buy_records,
        "hold_watch": hold_records,
        "sell_avoid": sell_records,
    }


def _fetch_us_equity_universe() -> tuple[list[dict[str, Any]], int]:
    import yfinance as yf
    from yfinance import EquityQuery

    query = EquityQuery(
        "and",
        [
            EquityQuery("eq", ["region", "us"]),
            EquityQuery("is-in", ["exchange", "NMS", "NYQ", "ASE"]),
            EquityQuery("gt", ["intradaymarketcap", 2_000_000_000]),
            EquityQuery("gt", ["avgdailyvol3m", 1_000_000]),
        ],
    )
    quotes: list[dict[str, Any]] = []
    total = 0
    offset = 0
    while True:
        response = yf.screen(query, offset=offset, size=250, sortField="intradaymarketcap", sortAsc=False)
        page = response.get("quotes", [])
        total = int(response.get("total") or total or len(page))
        quotes.extend(item for item in page if isinstance(item, dict))
        offset += len(page)
        if not page or offset >= total:
            break
    deduped = {str(item.get("symbol")): item for item in quotes if item.get("symbol")}
    return list(deduped.values()), total


def _reason(row: pd.Series) -> str:
    if row["action"] == "buy_candidate":
        return f"Positive earnings and long-term trend; 1Y return {row['return_1y_pct']:+.1f}% and price {row['distance_ma50_pct']:+.1f}% vs 50-day average."
    if row["action"] == "sell_avoid":
        return f"Below both trend averages; 1Y return {row['return_1y_pct']:+.1f}% and price {row['distance_ma200_pct']:+.1f}% vs 200-day average."
    return f"Mixed or extended setup; score {row['score']:.1f}/100 and price {row['distance_ma50_pct']:+.1f}% vs 50-day average."


def _forward_eps_growth(row: pd.Series) -> float | None:
    trailing = _number(row.get("eps_ttm"))
    forward = _number(row.get("eps_forward"))
    if trailing is None or forward is None or trailing <= 0:
        return None
    return max(-100.0, min((forward / trailing - 1.0) * 100.0, 500.0))


def _timestamp_date(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) else None


def _records(frame: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    clean = frame[columns].head(12).astype(object).where(pd.notna(frame[columns].head(12)), None)
    return clean.to_dict(orient="records")


def _unavailable_payload(market: str, note: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": market,
        "note": note,
        "source": {"name": "Yahoo Finance via yfinance", "url": "https://finance.yahoo.com/research-hub/screener/"},
        "universe": {"definition": UNIVERSE_DEFINITION, "eligible_total": 0, "fetched_count": 0, "analyzed_count": 0, "coverage_ratio": 0.0, "latest_price_date": None},
        "methodology": {"policy": "Research shortlist only; no automated trading."},
        "deep_research": {"status": "unavailable", "researched_count": 0, "failed_count": 0, "note": note},
        "action_counts": {"buy_candidate": 0, "hold_watch": 0, "sell_avoid": 0},
        "buy_candidates": [],
        "hold_watch": [],
        "sell_avoid": [],
    }


def _sandbox_quotes() -> list[dict[str, Any]]:
    return [
        _sandbox_quote("ALPHA", 140, 120, 96, 45, 80, 145),
        _sandbox_quote("BRAVO", 118, 106, 100, 20, 82, 122),
        _sandbox_quote("CORE", 101, 100, 99, 2, 78, 112),
        _sandbox_quote("DELTA", 92, 98, 96, -8, 83, 115),
        _sandbox_quote("ECHO", 76, 91, 102, -25, 72, 121),
        _sandbox_quote("FOXTROT", 58, 80, 98, -40, 55, 116),
    ]


def _sandbox_quote(symbol: str, price: float, ma50: float, ma200: float, return_1y: float, low: float, high: float) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "shortName": f"{symbol.title()} Sandbox",
        "fullExchangeName": "Sandbox",
        "regularMarketPrice": price,
        "fiftyDayAverage": ma50,
        "twoHundredDayAverage": ma200,
        "fiftyTwoWeekChangePercent": return_1y,
        "fiftyTwoWeekLow": low,
        "fiftyTwoWeekHigh": high,
        "marketCap": 10_000_000_000,
        "averageDailyVolume3Month": 5_000_000,
        "epsTrailingTwelveMonths": 4.0 if return_1y > -15 else -1.0,
        "trailingPE": 24.0 if return_1y > -15 else None,
        "forwardPE": 20.0 if return_1y > -15 else None,
        "priceToBook": 3.0,
        "epsForward": 4.5 if return_1y > -15 else -0.5,
        "earningsTimestamp": 1_710_000_000,
        "isEarningsDateEstimate": True,
        "averageAnalystRating": "2.0 - Buy",
        "regularMarketTime": 1_700_000_000,
    }
