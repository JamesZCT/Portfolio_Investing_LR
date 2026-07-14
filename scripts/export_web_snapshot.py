from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

from portfolio_agent.config import load_config
from portfolio_agent.data import fetch_ohlc, synthesize_ohlc_from_close
from portfolio_agent.engine import (
    backtest_to_payload,
    result_to_dashboard_payload,
    run_analysis,
    run_backtest_for_config,
    run_strategy_comparison_for_config,
)
from portfolio_agent.rules_catalog import rules_as_dicts
from portfolio_agent.sandbox import generate_sandbox_prices
from portfolio_agent.sentiment import build_sentiment_payload
from portfolio_agent.market_screener import build_market_opportunities_payload


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Export dashboard JSON snapshots for static web hosting.")
    parser.add_argument("--config", default=str(PROJECT_ROOT / "example_config.yaml"))
    parser.add_argument("--out-dir", default=str(PROJECT_ROOT / "web" / "public" / "data"))
    parser.add_argument("--mode", choices=["real", "sandbox"], default="real")
    parser.add_argument("--lookback-days", type=int, default=900)
    parser.add_argument("--rebalance-days", type=int, default=21)
    parser.add_argument("--transaction-cost-bps", type=float, default=5.0)
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    sandbox_days = args.lookback_days if args.mode == "sandbox" else None
    analysis = run_analysis(config_path, lookback_days=args.lookback_days, sandbox_days=sandbox_days)

    dashboard = result_to_dashboard_payload(analysis)
    dashboard["mode"] = args.mode
    dashboard["lookback_days"] = args.lookback_days
    dashboard["snapshot"] = _snapshot_metadata(config_path, args.mode, args.lookback_days)

    backtest = run_backtest_for_config(
        config_path,
        lookback_days=args.lookback_days,
        sandbox_days=sandbox_days,
        rebalance_days=args.rebalance_days,
        transaction_cost_bps=args.transaction_cost_bps,
    )
    backtest_payload = backtest_to_payload(backtest)
    backtest_payload["mode"] = args.mode
    backtest_payload["lookback_days"] = args.lookback_days

    strategies_payload = run_strategy_comparison_for_config(
        config_path,
        lookback_days=max(args.lookback_days, 900),
        sandbox_days=max(args.lookback_days, 900) if args.mode == "sandbox" else None,
        rebalance_days=args.rebalance_days,
        transaction_cost_bps=args.transaction_cost_bps,
    )
    strategies_payload["mode"] = args.mode
    strategies_payload["lookback_days"] = max(args.lookback_days, 900)

    cfg = load_config(config_path)
    ohlc_payload = _build_ohlc_payload(cfg.universe.benchmark, config_path, args.mode, args.lookback_days)
    quotes_payload = _build_quotes_payload(analysis.prices, _quote_tickers(cfg))
    sentiment_payload = build_sentiment_payload(
        cfg,
        market=_market_from_config(config_path),
        market_regime=analysis.market_regime,
        mode=args.mode,
    )
    opportunities_payload = build_market_opportunities_payload(
        market=_market_from_config(config_path),
        mode=args.mode,
    )

    _write_json(out_dir / "dashboard.json", dashboard)
    _write_json(out_dir / "backtest.json", backtest_payload)
    _write_json(out_dir / "strategies.json", strategies_payload)
    _write_json(out_dir / "rules.json", {"rules": rules_as_dicts()})
    _write_json(out_dir / "ohlc.json", ohlc_payload)
    _write_json(out_dir / "quotes.json", quotes_payload)
    _write_json(out_dir / "sentiment.json", sentiment_payload)
    _write_json(out_dir / "information_signs.json", sentiment_payload.get("summary", {}).get("information_signs", {}))
    _write_json(out_dir / "market_opportunities.json", opportunities_payload)
    health_payload = _build_health_payload(
        config_path=config_path,
        mode=args.mode,
        lookback_days=args.lookback_days,
        dashboard=dashboard,
        quotes=quotes_payload,
        sentiment=sentiment_payload,
        opportunities=opportunities_payload,
    )
    _write_json(out_dir / "health.json", health_payload)
    _write_json(out_dir / "history.json", _updated_history(out_dir / "history.json", health_payload, sentiment_payload))

    print(f"Exported static web snapshot to {out_dir}")
    return 0


def _build_ohlc_payload(ticker: str, config_path: Path, mode: str, lookback_days: int) -> dict[str, Any]:
    if mode == "sandbox":
        cfg = load_config(config_path)
        prices = generate_sandbox_prices(cfg, days=lookback_days)
        selected = ticker if ticker in prices.columns else cfg.universe.benchmark
        frame = synthesize_ohlc_from_close(prices[selected])
    else:
        selected = ticker.upper()
        frame = fetch_ohlc(selected, lookback_days=min(lookback_days, 1200))

    rows = [
        {
            "date": str(idx.date()),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        }
        for idx, row in frame.iterrows()
    ]
    return {"ticker": selected, "ohlc": rows}


def _quote_tickers(cfg) -> list[str]:
    tickers = [cfg.universe.benchmark]
    tickers.extend(ticker for ticker in cfg.universe.positions if ticker != "CASH")
    tickers.extend(cfg.universe.sector_etfs.values())
    deduped = []
    for ticker in tickers:
        if ticker not in deduped:
            deduped.append(ticker)
    return deduped[:40]


def _build_quotes_payload(prices, tickers: list[str]) -> dict[str, Any]:
    quotes = []
    for ticker in tickers:
        if ticker not in prices.columns:
            continue
        close = prices[ticker].dropna()
        if close.empty:
            continue
        price = float(close.iloc[-1])
        previous = float(close.iloc[-2]) if len(close) > 1 else price
        change = price - previous
        change_pct = change / previous if previous else 0.0
        quotes.append(
            {
                "ticker": ticker,
                "price": price,
                "previous_close": previous,
                "change": change,
                "change_pct": change_pct,
                "as_of": str(close.index[-1].date()),
                "source": "snapshot",
            }
        )
    return {"quotes": quotes}


def _snapshot_metadata(config_path: Path, mode: str, lookback_days: int) -> dict[str, Any]:
    config_name = config_path.name
    is_example = config_name == "example_config.yaml"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_name": config_name,
        "is_example_config": is_example,
        "mode": mode,
        "lookback_days": lookback_days,
    }


def _market_from_config(config_path: Path) -> str:
    return "hk" if "hk" in config_path.stem.lower() else "us"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _build_health_payload(
    config_path: Path,
    mode: str,
    lookback_days: int,
    dashboard: dict[str, Any],
    quotes: dict[str, Any],
    sentiment: dict[str, Any],
    opportunities: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc)
    quote_dates = [quote.get("as_of") for quote in quotes.get("quotes", []) if quote.get("as_of")]
    price_as_of = dashboard.get("price_as_of")
    days_since_price = _days_since_date(price_as_of, generated_at)
    ai_layer = sentiment.get("summary", {}).get("ai_layer", {})
    research_overlay = sentiment.get("summary", {}).get("research_overlay", {})
    information_signs = sentiment.get("summary", {}).get("information_signs", {})
    return {
        "generated_at": generated_at.isoformat(),
        "market": _market_from_config(config_path),
        "mode": mode,
        "lookback_days": lookback_days,
        "config_name": config_path.name,
        "is_example_config": config_path.name.startswith("example"),
        "price_as_of": price_as_of,
        "days_since_price": days_since_price,
        "stale_price": days_since_price is not None and days_since_price > 4,
        "quote_latest_as_of": max(quote_dates) if quote_dates else None,
        "news_article_count": sentiment.get("summary", {}).get("article_count", 0),
        "sentiment_label": sentiment.get("summary", {}).get("label"),
        "investment_posture": sentiment.get("summary", {}).get("investment_posture"),
        "forecast_bias": sentiment.get("summary", {}).get("forecast_bias"),
        "llm_status": ai_layer.get("status"),
        "llm_provider": ai_layer.get("provider"),
        "llm_model": ai_layer.get("model"),
        "research_overlay_status": research_overlay.get("status"),
        "research_overlay_note_count": research_overlay.get("note_count", 0),
        "information_signs_status": information_signs.get("status"),
        "information_sign_count": information_signs.get("sign_count", 0),
        "market_screen_status": opportunities.get("status"),
        "market_screen_analyzed_count": opportunities.get("universe", {}).get("analyzed_count", 0),
        "pipeline": {
            "price_fetch": "ok" if price_as_of else "missing",
            "rss_news": "ok" if sentiment.get("summary", {}).get("article_count", 0) else "empty",
            "local_llm": ai_layer.get("status", "unknown"),
            "private_research": research_overlay.get("status", "unknown"),
            "public_information_signs": information_signs.get("status", "unknown"),
            "broad_market_screen": opportunities.get("status", "unknown"),
        },
    }


def _updated_history(path: Path, health: dict[str, Any], sentiment: dict[str, Any], limit: int = 120) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and isinstance(existing.get("runs"), list):
                rows = [row for row in existing["runs"] if isinstance(row, dict)]
        except json.JSONDecodeError:
            rows = []

    rows.append(
        {
            "generated_at": health["generated_at"],
            "market": health["market"],
            "price_as_of": health["price_as_of"],
            "sentiment_label": health["sentiment_label"],
            "investment_posture": health["investment_posture"],
            "forecast_bias": health["forecast_bias"],
            "news_article_count": health["news_article_count"],
            "llm_status": health["llm_status"],
            "research_overlay_status": health["research_overlay_status"],
            "research_overlay_note_count": health["research_overlay_note_count"],
            "information_signs_status": health["information_signs_status"],
            "information_sign_count": health["information_sign_count"],
            "top_themes": sentiment.get("summary", {}).get("top_themes", [])[:3],
        }
    )
    rows = sorted(rows, key=lambda row: str(row.get("generated_at", "")), reverse=True)[:limit]
    return {
        "generated_at": health["generated_at"],
        "market": health["market"],
        "retention_runs": limit,
        "runs": rows,
    }


def _days_since_date(value: Any, now: datetime) -> int | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None
    return (now.date() - parsed).days


if __name__ == "__main__":
    raise SystemExit(main())
