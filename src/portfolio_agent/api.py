from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import load_config
from .data import fetch_latest_quotes, fetch_ohlc, synthesize_ohlc_from_close
from .engine import (
    backtest_to_payload,
    result_to_dashboard_payload,
    run_analysis,
    run_backtest_for_config,
    run_strategy_comparison_for_config,
)
from .rules_catalog import rules_as_dicts
from .sandbox import generate_sandbox_prices
from .sentiment import build_sentiment_payload


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config.yaml" if (PROJECT_ROOT / "config.yaml").exists() else PROJECT_ROOT / "example_config.yaml"


def _extra_cors_origins() -> list[str]:
    raw = os.getenv("PORTFOLIO_AGENT_CORS_ORIGINS", "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]

app = FastAPI(
    title="Portfolio Investing Lab API",
    version="0.1.0",
    description="Research API for rule-based portfolio strategy analysis.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://portfolio-investing-lr.netlify.app",
        *_extra_cors_origins(),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def get_config(config_path: str = Query(str(DEFAULT_CONFIG))) -> dict[str, Any]:
    cfg = load_config(_resolve_config(config_path))
    return {
        "benchmark": cfg.universe.benchmark,
        "sector_etfs": cfg.universe.sector_etfs,
        "positions": cfg.universe.positions,
        "target_weights": cfg.universe.target_weights,
        "rules": cfg.rules.__dict__,
        "indicators": cfg.indicators.__dict__,
        "ml": cfg.ml.__dict__,
    }


@app.get("/api/rules")
def rules() -> dict[str, Any]:
    return {"rules": rules_as_dicts()}


@app.get("/api/news-sentiment")
def news_sentiment(
    config_path: str = Query(str(DEFAULT_CONFIG)),
    lookback_days: int = Query(900, ge=300, le=5000),
    mode: str = Query("real", pattern="^(real|sandbox)$"),
    market: str = Query("us", pattern="^(us|hk)$"),
) -> dict[str, Any]:
    try:
        resolved = _resolve_config(config_path)
        cfg = load_config(resolved)
        result = run_analysis(
            resolved,
            lookback_days=lookback_days,
            sandbox_days=lookback_days if mode == "sandbox" else None,
        )
        return build_sentiment_payload(
            cfg,
            market=market,
            market_regime=result.market_regime,
            mode=mode,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


@app.get("/api/dashboard")
def dashboard(
    config_path: str = Query(str(DEFAULT_CONFIG)),
    lookback_days: int = Query(900, ge=300, le=5000),
    mode: str = Query("real", pattern="^(real|sandbox)$"),
) -> dict[str, Any]:
    try:
        result = run_analysis(
            _resolve_config(config_path),
            lookback_days=lookback_days,
            sandbox_days=lookback_days if mode == "sandbox" else None,
        )
        payload = result_to_dashboard_payload(result)
        payload["mode"] = mode
        payload["lookback_days"] = lookback_days
        return payload
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


@app.get("/api/ohlc")
def ohlc(
    ticker: str = Query("SPY", min_length=1, max_length=12),
    config_path: str = Query(str(DEFAULT_CONFIG)),
    lookback_days: int = Query(260, ge=60, le=2000),
    mode: str = Query("real", pattern="^(real|sandbox)$"),
) -> dict[str, Any]:
    try:
        if mode == "sandbox":
            cfg = load_config(_resolve_config(config_path))
            prices = generate_sandbox_prices(cfg, days=lookback_days)
            selected = ticker if ticker in prices.columns else cfg.universe.benchmark
            frame = synthesize_ohlc_from_close(prices[selected])
        else:
            selected = ticker.upper()
            frame = fetch_ohlc(selected, lookback_days=lookback_days)

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
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


@app.get("/api/quotes")
def quotes(
    tickers: str = Query("SPY", min_length=1, max_length=240),
) -> dict[str, Any]:
    try:
        symbols = [ticker.strip().upper() for ticker in tickers.split(",") if ticker.strip()]
        if len(symbols) > 40:
            raise ValueError("At most 40 tickers are supported per quote request")
        return {"quotes": fetch_latest_quotes(symbols)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


@app.get("/api/backtest")
def backtest(
    config_path: str = Query(str(DEFAULT_CONFIG)),
    lookback_days: int = Query(1200, ge=300, le=6000),
    mode: str = Query("real", pattern="^(real|sandbox)$"),
    rebalance_days: int = Query(21, ge=5, le=252),
    transaction_cost_bps: float = Query(5.0, ge=0.0, le=100.0),
) -> dict[str, Any]:
    try:
        result = run_backtest_for_config(
            _resolve_config(config_path),
            lookback_days=lookback_days,
            sandbox_days=lookback_days if mode == "sandbox" else None,
            rebalance_days=rebalance_days,
            transaction_cost_bps=transaction_cost_bps,
        )
        payload = backtest_to_payload(result)
        payload["mode"] = mode
        payload["lookback_days"] = lookback_days
        return payload
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


@app.get("/api/strategies/compare")
def compare_strategies(
    config_path: str = Query(str(DEFAULT_CONFIG)),
    lookback_days: int = Query(1200, ge=300, le=6000),
    mode: str = Query("real", pattern="^(real|sandbox)$"),
    rebalance_days: int = Query(21, ge=5, le=252),
    transaction_cost_bps: float = Query(5.0, ge=0.0, le=100.0),
) -> dict[str, Any]:
    try:
        payload = run_strategy_comparison_for_config(
            _resolve_config(config_path),
            lookback_days=lookback_days,
            sandbox_days=lookback_days if mode == "sandbox" else None,
            rebalance_days=rebalance_days,
            transaction_cost_bps=transaction_cost_bps,
        )
        payload["mode"] = mode
        payload["lookback_days"] = lookback_days
        return payload
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


def _resolve_config(config_path: str | Path) -> Path:
    path = Path(config_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    return path


def main() -> int:
    import uvicorn

    uvicorn.run("portfolio_agent.api:app", host="127.0.0.1", port=8000, reload=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
