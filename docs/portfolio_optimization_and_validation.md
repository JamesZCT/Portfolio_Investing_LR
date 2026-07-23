# Portfolio Optimization and Historical Validation

## Purpose

This layer turns the existing rule output into three configurable research allocations:

| Profile | Objective | Intended use |
| --- | --- | --- |
| Defensive | Minimize CVaR tail loss | Lower drawdown, higher liquidity, and a larger bond/cash buffer |
| Balanced | Risk budgeting | Spread risk contributions instead of letting one volatile holding dominate |
| Aggressive | Estimated maximum Sharpe | Seek higher risk-adjusted return while remaining long-only and unlevered |

These are research portfolios, not automatic orders. They never connect to a broker.

## Data and implementation

- Configuration: `optimization` in `example_config.yaml` and `example_hk_config.yaml`
- Optimizer: `src/portfolio_agent/optimization.py`
- Current snapshot output: `web/public/data/{market}/dashboard.json`
- Walk-forward engine: `src/portfolio_agent/historical_validation.py`
- Export command: `scripts/export_historical_validation.py`
- Published output: `web/public/data/{market}/historical_validation.json`

The optimizer uses `skfolio` with shrunk return/covariance estimates where appropriate. Each profile has an explicit candidate list, cash weight, single-stock cap, fund cap, and group cap. If a mathematical solution is infeasible, the output records the error and falls back to inverse-volatility weights.

## Reading the current allocation

For each profile:

- `Current` is the public example portfolio weight.
- `Target` is the constrained model output.
- `Gap` is target minus current.
- `ADD`, `TRIM`, and `HOLD` are research actions, not orders.
- `Why this allocation` records the objective and constraint behind the row.
- Return, volatility, Sharpe, and drawdown are trailing in-sample diagnostics.
- Turnover and estimated transaction cost show how disruptive the change would be.

Do not select a profile only because its trailing return is highest. Start with drawdown tolerance, liquidity needs, concentration, tax impact, and the walk-forward evidence.

## Walk-forward protocol

The historical study uses this order:

1. Observe prices through the close of trading day `t`.
2. Calculate the signal or optimized target using only that history.
3. Charge configured turnover costs when the allocation changes.
4. Let the new target first affect returns on trading day `t+1`.
5. Compare the resulting net value with the benchmark over the same evaluation dates.

The price-rule reconstruction uses the same technical ingredients as the opportunity map:

- trailing one-year return rank
- distance from 50-day and 200-day moving averages
- 50-day average above 200-day average
- position inside the trailing 52-week range
- an extension guard that rejects prices more than 20% above the 50-day average
- a benchmark 200-day trend filter and cash buffer

The test includes transaction costs. A unit test changes future prices and confirms that all earlier price-rule results remain unchanged.

## Honest limitations

The published validation is deliberately labeled `exploratory_not_production`.

- The candidate set is based on the current configured universe, so it has survivorship and selection bias.
- Delisted securities are not included.
- Historical point-in-time SEC filing fundamentals are not yet included.
- The technical track therefore reconstructs the price gates, not the complete current opportunity-map score.
- Taxes, changing bid-ask spreads, market impact, and intraday execution are not modeled.

Because of these limits, a high historical CAGR is a hypothesis to investigate, not proof that the strategy will repeat.

## Automation schedule

The Windows self-hosted runner performs:

- Weekdays 08:30 America/New_York: pre-open information and sentiment refresh.
- Weekdays 17:30 America/New_York: post-close market and portfolio refresh.
- Saturday after the US trading week: US and Hong Kong ten-year validation refresh.

The daily job commits public example JSON and deploys GitHub Pages. Netlify is manual-only. Ollama runs locally on the 3090 Ti; the hosted site serves the resulting JSON and does not host the model.

## Private portfolio boundary

The repository is public. Keep real holdings, account identifiers, brokerage exports, private research, OAuth tokens, and API keys outside it.

The intended personal version is:

1. Public repository for reusable code and public demo snapshots.
2. Private repository or local folder for personal configuration and records.
3. The private layer imports the public package or pins a public release.
4. Only aggregate, intentionally publishable results may cross back into the public demo.
