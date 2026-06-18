from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

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

    _write_json(out_dir / "dashboard.json", dashboard)
    _write_json(out_dir / "backtest.json", backtest_payload)
    _write_json(out_dir / "strategies.json", strategies_payload)
    _write_json(out_dir / "rules.json", {"rules": rules_as_dicts()})
    _write_json(out_dir / "ohlc.json", ohlc_payload)

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


def _snapshot_metadata(config_path: Path, mode: str, lookback_days: int) -> dict[str, Any]:
    config_name = config_path.name
    is_example = config_name == "example_config.yaml"
    return {
        "config_name": config_name,
        "is_example_config": is_example,
        "mode": mode,
        "lookback_days": lookback_days,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
