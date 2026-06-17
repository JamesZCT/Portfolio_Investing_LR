from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .backtest import run_backtest, write_backtest_report
from .config import AppConfig, load_config
from .data import fetch_close_prices, load_close_prices_csv
from .execution import SandboxExecutionAdapter, suggestions_to_orders
from .ml import build_risk_predictions
from .notifier import send_notifications
from .portfolio import propose_rebalance
from .report import write_report
from .sandbox import generate_sandbox_prices
from .signals import build_market_regime, build_sector_signals


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rule-based investment portfolio agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Generate latest signals and rebalance suggestions")
    _add_common_args(run_parser)

    backtest_parser = subparsers.add_parser("backtest", help="Run historical backtest")
    _add_common_args(backtest_parser)
    backtest_parser.add_argument(
        "--rebalance-days",
        type=int,
        default=21,
        help="Rebalance interval in trading days",
    )
    backtest_parser.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=5.0,
        help="Transaction cost per unit turnover in basis points",
    )

    daily_parser = subparsers.add_parser("daily", help="Daily automation run with dated outputs")
    _add_common_args(daily_parser)

    sandbox_parser = subparsers.add_parser("sandbox", help="Run a toy/synthetic sandbox experiment")
    _add_common_args(sandbox_parser)
    sandbox_parser.add_argument(
        "--days",
        type=int,
        default=900,
        help="Synthetic trading days to generate",
    )

    return parser.parse_args()


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", required=True, help="Path to YAML config")
    parser.add_argument("--out", default="outputs", help="Output directory")
    parser.add_argument("--lookback-days", type=int, default=500, help="Historical lookback")
    parser.add_argument(
        "--prices-csv",
        default=None,
        help="Optional local CSV with Date column and ticker columns",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send notifications using config notification settings",
    )


def load_prices_for_config(cfg: AppConfig, prices_csv: str | None, lookback_days: int):
    tickers = set(cfg.universe.sector_etfs.values())
    tickers.update(cfg.universe.positions.keys())
    tickers.update(cfg.universe.target_weights.keys())
    tickers.add(cfg.universe.benchmark)

    ordered_tickers = sorted(t for t in tickers if t != "CASH")
    if prices_csv:
        return load_close_prices_csv(prices_csv, ordered_tickers)
    return fetch_close_prices(ordered_tickers, lookback_days=lookback_days)


def run_once(config_path: str, out_dir: str, prices_csv: str | None, lookback_days: int) -> int:
    cfg = load_config(config_path)
    prices = load_prices_for_config(cfg, prices_csv, lookback_days)
    market_regime = build_market_regime(prices=prices, config=cfg)
    signals = build_sector_signals(prices=prices, config=cfg)
    holdings = [ticker for ticker in cfg.universe.positions if ticker != "CASH"]
    latest_prices = {ticker: float(prices[ticker].dropna().iloc[-1]) for ticker in holdings if ticker in prices.columns}
    trailing_window = prices[holdings].tail(cfg.indicators.trailing_high_lookback_days)
    trailing_highs = {ticker: float(trailing_window[ticker].max()) for ticker in trailing_window.columns}
    risk_predictions = build_risk_predictions(prices, holdings, cfg)
    suggestions = propose_rebalance(
        config=cfg,
        signals=signals,
        latest_prices=latest_prices,
        trailing_highs=trailing_highs,
        market_regime=market_regime,
        risk_predictions=risk_predictions,
    )

    signals_csv, rebalance_csv, summary_md = write_report(
        out_dir=Path(out_dir),
        config=cfg,
        prices=prices,
        signals=signals,
        suggestions=suggestions,
        market_regime=market_regime,
        risk_predictions=risk_predictions,
    )

    execution_results = SandboxExecutionAdapter().execute(suggestions_to_orders(suggestions))

    print("Portfolio agent completed.")
    print(f"Signals: {signals_csv}")
    print(f"Trades: {rebalance_csv}")
    print(f"Summary: {summary_md}")
    print(f"Sandbox execution records: {len(execution_results)}")
    return 0


def run_daily(config_path: str, out_dir: str, prices_csv: str | None, lookback_days: int) -> int:
    day_folder = datetime.now().strftime("%Y-%m-%d")
    run_dir = Path(out_dir) / "daily" / day_folder
    return run_once(config_path, str(run_dir), prices_csv, lookback_days)


def run_backtest_cmd(
    config_path: str,
    out_dir: str,
    prices_csv: str | None,
    lookback_days: int,
    rebalance_days: int,
    transaction_cost_bps: float,
) -> int:
    cfg = load_config(config_path)
    prices = load_prices_for_config(cfg, prices_csv, lookback_days)
    result = run_backtest(
        config=cfg,
        prices=prices,
        rebalance_days=rebalance_days,
        transaction_cost_bps=transaction_cost_bps,
    )
    equity_csv, trades_csv, summary_md = write_backtest_report(Path(out_dir) / "backtest", result)

    print("Backtest completed.")
    print(f"Equity: {equity_csv}")
    print(f"Trades: {trades_csv}")
    print(f"Summary: {summary_md}")
    return 0


def run_sandbox(config_path: str, out_dir: str, days: int) -> int:
    cfg = load_config(config_path)
    prices = generate_sandbox_prices(cfg, days=days)
    sandbox_csv = Path(out_dir) / "sandbox_prices.csv"
    sandbox_csv.parent.mkdir(parents=True, exist_ok=True)
    prices.reset_index(names="Date").to_csv(sandbox_csv, index=False)
    print(f"Synthetic prices: {sandbox_csv}")
    return run_once(config_path, out_dir, str(sandbox_csv), lookback_days=days)


def main() -> int:
    args = parse_args()

    if args.command == "run":
        rc = run_once(args.config, args.out, args.prices_csv, args.lookback_days)
        if args.notify:
            _notify(args.config, "Portfolio Agent run", Path(args.out) / "summary.md")
        return rc
    if args.command == "daily":
        rc = run_daily(args.config, args.out, args.prices_csv, args.lookback_days)
        day_folder = datetime.now().strftime("%Y-%m-%d")
        summary_path = Path(args.out) / "daily" / day_folder / "summary.md"
        _notify(args.config, f"Portfolio Agent daily {day_folder}", summary_path)
        return rc
    if args.command == "backtest":
        rc = run_backtest_cmd(
            config_path=args.config,
            out_dir=args.out,
            prices_csv=args.prices_csv,
            lookback_days=args.lookback_days,
            rebalance_days=args.rebalance_days,
            transaction_cost_bps=args.transaction_cost_bps,
        )
        if args.notify:
            _notify(args.config, "Portfolio Agent backtest", Path(args.out) / "backtest" / "backtest_summary.md")
        return rc
    if args.command == "sandbox":
        return run_sandbox(args.config, args.out, args.days)
    raise ValueError(f"Unsupported command: {args.command}")


def _notify(config_path: str, subject: str, summary_path: Path) -> None:
    cfg = load_config(config_path)
    if summary_path.exists():
        body = summary_path.read_text()
    else:
        body = f"Run completed but summary file was not found: {summary_path}"
    results = send_notifications(cfg.notifications, subject, body)
    for result in results:
        print(f"Notify: {result}")


if __name__ == "__main__":
    sys.exit(main())
