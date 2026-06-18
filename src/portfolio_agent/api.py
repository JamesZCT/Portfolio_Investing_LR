from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import load_config
from .engine import (
    backtest_to_payload,
    result_to_dashboard_payload,
    run_analysis,
    run_backtest_for_config,
    run_buy_and_hold_baseline,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "example_config.yaml"

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
) -> dict[str, Any]:
    try:
        result = run_backtest_for_config(
            _resolve_config(config_path),
            lookback_days=lookback_days,
            sandbox_days=lookback_days if mode == "sandbox" else None,
            rebalance_days=21,
            transaction_cost_bps=5.0,
        )
        buy_hold = run_buy_and_hold_baseline(
            _resolve_config(config_path),
            lookback_days=lookback_days,
            sandbox_days=lookback_days if mode == "sandbox" else None,
        )
        return {
            "mode": mode,
            "strategies": [
                {"name": "Rule engine", "metrics": result.metrics},
                {"name": "Buy and hold proxy", "metrics": buy_hold},
            ],
        }
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
