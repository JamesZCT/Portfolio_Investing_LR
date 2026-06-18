from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .backtest import write_backtest_report
from .config import load_config
from .engine import (
    load_prices_for_config,
    run_analysis,
    run_backtest_for_config,
    write_analysis_report,
)
from .notifier import send_notifications
from .sandbox import generate_sandbox_prices


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


def run_once(config_path: str, out_dir: str, prices_csv: str | None, lookback_days: int) -> int:
    result = run_analysis(config_path, lookback_days=lookback_days, prices_csv=prices_csv)
    signals_csv, rebalance_csv, summary_md = write_analysis_report(result, Path(out_dir))

    print("Portfolio agent completed.")
    print(f"Signals: {signals_csv}")
    print(f"Trades: {rebalance_csv}")
    print(f"Summary: {summary_md}")
    print(f"Sandbox execution records: {len(result.execution_results)}")
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
    result = run_backtest_for_config(
        config_path=config_path,
        lookback_days=lookback_days,
        prices_csv=prices_csv,
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
