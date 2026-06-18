# Investment Portfolio Agent

A statistics-driven portfolio assistant for personal use.

It combines:
- signal detection using moving average, rolling standard deviation, and z-score rules
- rebalance suggestions that trim hyped/overweight exposure and reallocate to underweight/undervalued areas
- a sandbox-only execution boundary so recommendations can be simulated without placing live brokerage orders
- a lightweight ML risk model that estimates next-horizon drawdown risk from price-derived features
- backtesting and daily automation workflows

## Features

1. Quant signal engine
- 200-day moving average (configurable)
- rolling standard deviation and z-score
- 3-sigma style extreme detection (`extreme_z`, default `3.0`)
- sector state classification: `undervalued`, `hyped`, `cool`, `warm`, `neutral`
- valuation visuals (price vs MA and +/- 3 std bands)

2. Portfolio rebalance logic
- trims positions above target weights
- trims additional exposure when sector signal is hyped
- reallocates freed weight to underweight names, with higher priority for undervalued sectors
- enforces risk controls:
- `max_single_position_weight`
- `max_sector_weight`
- `stop_loss_pct` + `stop_trim_fraction`
- `trailing_stop_pct` + `trailing_stop_trim_fraction`

3. Backtest module
- periodic rebalance simulation (default every 21 trading days)
- transaction cost model in bps
- outputs equity curve, trade log, and performance metrics (CAGR, vol, Sharpe, max drawdown)

4. Daily automation agent
- `daily` command writes dated report folders (`outputs/daily/YYYY-MM-DD`)
- local macOS scheduler helper (`launchd`) script
- GitHub Actions scheduled workflow for cloud automation

5. Sandbox experiments
- `sandbox` command generates synthetic market regimes and runs the agent without live data
- simulated execution records are produced through a sandbox adapter
- live brokerage execution is intentionally not implemented, but the adapter boundary exists

6. ML risk scoring
- trains a transparent logistic model on rolling price features
- estimates probability of a next-horizon drawdown event
- can block adds or trim exposure when risk is elevated

7. Notifications
- Slack webhook notifications
- Telegram bot notifications
- SMTP email notifications
- `dry_run` mode for safe testing

8. Visual analytics outputs
- sector z-score chart
- valuation bands chart
- position vs target allocation chart
- sector concentration risk chart
- backtest equity curve, drawdown, and turnover charts

## Installation

```bash
cd /Users/jameszhu/Documents/New\ project
./scripts/bootstrap.sh
source .venv/bin/activate
```

`scripts/bootstrap.sh` creates `.venv` and installs all required packages from `requirements.txt` and `pyproject.toml`.

## Full-stack local run

1. Run the backend API:

```bash
portfolio-agent-api
```

2. Run the frontend:

```bash
cd web
npm ci
npm run dev
```

3. Open `http://127.0.0.1:5173`.

Docker is also supported:

```bash
docker compose up --build
```

The API exposes:
- `/api/dashboard`
- `/api/backtest`
- `/api/strategies/compare`
- `/api/ohlc`
- `/api/quotes`
- `/api/rules`

## Commands

1. Run latest analysis

```bash
portfolio-agent run --config config.yaml --out outputs
```

2. Run backtest

```bash
portfolio-agent backtest --config config.yaml --out outputs --lookback-days 1200 --rebalance-days 21 --transaction-cost-bps 5
```

3. Run daily agent once

```bash
portfolio-agent daily --config config.yaml --out outputs
```

4. Run with local prices CSV (offline mode)

```bash
portfolio-agent run --config config.yaml --prices-csv your_prices.csv --out outputs
```

5. Run toy sandbox experiment

```bash
portfolio-agent sandbox --config example_config.yaml --out outputs/sandbox --days 900
```

6. Run API server

```bash
portfolio-agent-api
```

7. Run frontend dashboard

```bash
cd web
npm install
npm run dev
```

8. Export a static web snapshot for Netlify or offline viewing

```bash
python scripts/export_web_snapshot.py --config example_config.yaml --mode real --lookback-days 900
```

9. Send notifications on run/backtest

```bash
portfolio-agent run --config config.yaml --out outputs --notify
portfolio-agent backtest --config config.yaml --out outputs --notify
```

Note: `daily` always attempts notification dispatch through configured notification settings.

CSV format requirements:
- one `Date` column (`YYYY-MM-DD`)
- one close-price column per ticker used in your config

## Scheduling automation

1. Local macOS daily scheduler (09:00 local time)

```bash
./scripts/setup_daily_launchd.sh
```

2. GitHub Actions daily workflow
- file: `.github/workflows/daily-portfolio-agent.yml`
- schedule: daily at `13:30 UTC`
- optional secret: `PORTFOLIO_CONFIG_YAML` (raw YAML content)
- workflow outputs are uploaded as artifacts

## Netlify hosting

The dashboard can run on Netlify without a local FastAPI server. Netlify serves:
- the React dashboard from `web/dist`
- same-origin API routes from `web/netlify/functions/api.ts`
- generated model snapshots from `web/public/data/*.json`

The hosted `/api/*` contract is:
- `/api/health`: Netlify Function health check
- `/api/dashboard`: latest generated dashboard snapshot
- `/api/backtest`: latest generated backtest snapshot
- `/api/strategies/compare`: latest generated strategy comparison snapshot
- `/api/rules`: rules catalog snapshot
- `/api/ohlc`: benchmark OHLC snapshot
- `/api/quotes`: live quote lookup with snapshot fallback

The recommended free/low-friction path is:

1. Generate public demo data from `example_config.yaml`:

```bash
python scripts/export_web_snapshot.py --config example_config.yaml --mode real --lookback-days 900
```

2. Build the frontend:

```bash
cd web
npm ci
npm run build
```

3. Deploy with Netlify using the root `netlify.toml`.

Netlify builds from `web/`, publishes `web/dist`, and sets `VITE_DATA_MODE=api` with a blank `VITE_API_BASE` so the browser calls the same-origin `/api/*` functions. The frontend still falls back to `/data/*.json` snapshots if an API request fails.

Keep personal `config.yaml` data private. If you generate snapshots from your real portfolio, treat the generated `web/public/data/*.json` files as sensitive unless the repo and Netlify site are private.

## GitHub and CI/CD

The repository includes:
- `.github/workflows/ci.yml`: runs Python compile checks, unit tests, API sandbox smoke tests, snapshot export, and frontend build on push/PR.
- `.github/workflows/refresh-web-snapshot.yml`: refreshes `web/public/data/*.json` on a market-day schedule or manual trigger.
- `.github/workflows/daily-portfolio-agent.yml`: runs the research agent and uploads report artifacts.

Required private repository secrets for hands-free deploys:
- `NETLIFY_AUTH_TOKEN`: Netlify personal access token used by GitHub Actions to deploy the rebuilt site.
- `NETLIFY_SITE_ID`: Netlify site id for deployment.

Optional private repository secrets:
- `PORTFOLIO_CONFIG_YAML`: optional private portfolio config YAML. If absent, workflows use `example_config.yaml`.

The current Netlify site id is:

```text
fb8a2f11-95d3-45e9-bc1b-6357eb48a5bb
```

The project source repository is:

```text
https://github.com/JamesZCT/Portfolio_Investing_LR
```

The scheduled snapshot workflow commits refreshed market data to `main` and deploys the rebuilt frontend/functions through the Netlify CLI. Netlify Git builds are intentionally paused because this Free-plan private repo is blocked by Netlify's verified contributor policy; GitHub Actions direct deploy avoids that limitation once `NETLIFY_AUTH_TOKEN` is set.

Usage controls:
- The hosted dashboard loads its default real-data view through `/api/bootstrap`, reducing startup function calls from several requests to one.
- The refresh workflow deploys only when `web/public/data/*.json` changes.
- The schedule runs once per weekday after market close instead of polling intraday.
- `/api/quotes` provides live quotes on demand, while heavier strategy and backtest data comes from refreshed snapshots.

## Config

Use `config.yaml` (or start from `example_config.yaml`):
- `positions`: current portfolio weights (sum near `1.0`)
- `target_weights`: strategic weights (sum near `1.0`)
- `ticker_sector`: ticker to sector mapping
- `sector_etfs`: sector proxy tickers for signal detection
- `entry_prices`: used by stop-loss logic
- `notifications`: channel environment variable names and dry-run toggle

## Output structure

- `outputs/sector_signals.csv`
- `outputs/rebalance_suggestions.csv`
- `outputs/ml_risk_predictions.csv`
- `outputs/summary.md`
- `outputs/charts/sector_zscores.png`
- `outputs/charts/valuation_bands.png`
- `outputs/charts/position_vs_target.png`
- `outputs/charts/sector_concentration.png`
- `outputs/backtest/backtest_equity_curve.csv`
- `outputs/backtest/backtest_trades.csv`
- `outputs/backtest/backtest_summary.md`
- `outputs/backtest/charts/equity_curve.png`
- `outputs/backtest/charts/drawdown.png`
- `outputs/backtest/charts/turnover.png`
- `outputs/daily/YYYY-MM-DD/...`

## Disclaimer

This is educational workflow tooling, not financial advice.
Validate tax, liquidity, risk, and execution constraints before trading.
