from __future__ import annotations

import argparse
import json
from pathlib import Path

from portfolio_agent.config import load_config
from portfolio_agent.data import fetch_close_prices
from portfolio_agent.historical_validation import run_historical_validation
from portfolio_agent.sandbox import generate_sandbox_prices


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export an honest walk-forward historical validation snapshot."
    )
    parser.add_argument("--config", default=str(PROJECT_ROOT / "example_config.yaml"))
    parser.add_argument("--out", default=None)
    parser.add_argument("--market", choices=["us", "hk"], default="us")
    parser.add_argument("--mode", choices=["real", "sandbox"], default="real")
    parser.add_argument("--years", type=int, default=10)
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    config = load_config(config_path)

    history_days = int((args.years + 3) * 365.25)
    tickers = sorted(
        {
            config.universe.benchmark,
            *(
                ticker
                for profile in (config.optimization.profiles or {}).values()
                for ticker in profile.assets
            ),
            *(ticker for ticker in config.universe.positions if ticker != "CASH"),
        }
    )
    if args.mode == "sandbox":
        prices = generate_sandbox_prices(config, days=int((args.years + 3) * 252))
    else:
        prices = fetch_close_prices(tickers, lookback_days=history_days)
    payload = run_historical_validation(config, prices, years=args.years)
    payload["mode"] = args.mode

    output_path = (
        Path(args.out)
        if args.out
        else PROJECT_ROOT / "web" / "public" / "data" / args.market / "historical_validation.json"
    )
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"Exported historical validation to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
