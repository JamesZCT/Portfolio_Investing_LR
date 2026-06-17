# Investment Rules Research Brief

Source PDF: `/Users/jameszhu/Downloads/Real_Investment_Advice.pdf`

This project should implement rules as testable portfolio policies, not as
predictions. Each rule needs:

- a precise signal definition
- a position/allocation action
- a backtest result against a passive benchmark
- a reason code in daily reports
- configuration knobs for personal risk tolerance

## Priority Rules

### 1. Long-term trend regime filter

Use a 200-day moving average or 10-month moving average on the broad market
benchmark and sector ETFs.

Rule:

- If price is above long-term moving average: risk-on or neutral.
- If price is below long-term moving average: reduce risky exposure, raise cash,
  or avoid adding to weak assets.
- Require confirmation, such as month-end close or two consecutive closes, to
  reduce whipsaw.

Why:

- RIA emphasizes following the long-term trend and treating markets as either
  bullish or bearish.
- Meb Faber's tactical asset allocation research uses a simple trend rule and
  reports equity-like returns with lower volatility/drawdowns.
- AQR's century-long trend-following research supports time-series momentum
  across long histories and asset classes.

Implementation:

- `signals.py`: add `trend_state` for benchmark, sectors, and holdings.
- `portfolio.py`: block adds when trend is negative; optionally trim risk.
- `backtest.py`: compare no-filter vs trend-filter strategies.

Sources:

- https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf
- https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing

### 2. Extreme valuation or extension bands

Use z-scores and standard-deviation bands around moving averages to detect
overextended or washed-out sectors.

Rule:

- If price is more than `extreme_z` standard deviations above its moving average,
  classify as overextended/hyped and trim overweight exposure.
- If price is more than `extreme_z` standard deviations below its moving average,
  classify as washed-out/undervalued candidate, but only add if trend/risk rules
  allow.
- Default `extreme_z`: 2.0 for moderate signal, 3.0 for rare/extreme signal.

Why:

- RIA explicitly uses overextension/extreme concepts and the existing code
  already includes z-score, moving average, and standard-deviation logic.
- Bollinger-style bands are a common way to express volatility-adjusted
  overbought/oversold conditions, but they should be confirmation signals, not
  standalone buy/sell commands.

Implementation:

- Existing `signals.py` is close; add configurable band families:
  `moderate_z`, `extreme_z`, `panic_z`.
- Reports should show the current z-score, band status, and action implication.

Sources:

- https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/bollinger-bands
- https://www.bollingerbands.com/bollinger-band-rules

### 3. Rule-based rebalancing with drift thresholds

Rebalance by calendar review plus drift thresholds.

Rule:

- Review monthly or quarterly.
- Rebalance only when position, sector, or asset-class drift exceeds a threshold.
- Suggested defaults:
  - position drift: 2-3 percentage points
  - asset-class drift: 5 percentage points
  - max single position: 5-10% unless explicitly allowed
  - max sector: 25-35%

Why:

- RIA stresses trimming winners, buying underweights, and keeping risk aligned.
- Vanguard research frames rebalancing primarily as risk control, not return
  maximization, and discusses calendar plus threshold approaches.

Implementation:

- Existing `portfolio.py` already handles target weights, overweight triggers,
  single-position caps, and sector caps.
- Add asset-class-level caps and drift reports.

Sources:

- https://investor.vanguard.com/investor-resources-education/portfolio-management/rebalancing-your-portfolio
- https://indexacapital.com/bundles/unaiadvisor/docs/papers/2010-Vanguard-Best-practices-for-portfolio-rebalancing.pdf

### 4. Never average down without explicit thesis reset

Do not add to a loser merely because it is cheaper.

Rule:

- Block adds to any holding below entry price by more than `loss_block_pct`,
  unless a manual override flag exists in the config.
- Suggested default: 10%.
- Override must include a written reason in config/report output.

Why:

- RIA explicitly warns against adding to losing positions.
- This is a behavioral guardrail: it prevents hope-based averaging down from
  masquerading as discipline.

Implementation:

- `portfolio.py`: add an `eligible_to_add` function.
- `config.yaml`: optional `thesis_overrides`.
- `report.py`: show blocked adds and why.

### 5. Drawdown and stop-risk controls

Use stop-loss and trailing-drawdown rules as risk reducers, not panic triggers.

Rule:

- If holding falls below entry by `stop_loss_pct`, propose a partial trim.
- If holding falls from trailing high by `trailing_stop_pct`, propose a partial
  trim.
- Suggested defaults:
  - entry stop: 12-15%
  - trailing stop: 15-25%
  - trim fraction: 25-50%

Why:

- RIA emphasizes cutting losers early, respecting drawdowns, and avoiding large
  irrecoverable losses.
- The math of loss makes deep drawdowns disproportionately damaging.

Implementation:

- Existing `portfolio.py` already includes stop-loss and trailing-stop logic.
- Add tests and better reporting.

### 6. Liquidity/cash buffer rule

Keep enough cash or near-cash allocation for optionality and forced-sale
avoidance.

Rule:

- Maintain a minimum cash buffer.
- Increase cash target when benchmark trend is bearish or portfolio volatility is
  elevated.
- Suggested defaults:
  - normal cash: 2-5%
  - defensive cash: 10-25%

Why:

- RIA treats liquidity as optionality.
- Cash gives the system a non-emotional way to wait when risk/reward is poor.

Implementation:

- Add synthetic `CASH` allocation support across config, backtest, and reports.
- Backtest against Treasury bill or money-market proxy.

### 7. Momentum confirmation and relative-strength ranking

Prefer additions to assets with positive absolute momentum and strong relative
momentum.

Rule:

- Rank candidates by 6- or 12-month total return.
- Require positive absolute momentum versus cash/T-bills before adding risk.
- Use relative momentum to choose between eligible sectors/assets.

Why:

- Momentum has substantial academic evidence.
- RIA's "do more of what works" maps naturally to a momentum/relative-strength
  framework when bounded by risk caps.

Implementation:

- Add `momentum.py` or extend `signals.py`.
- Add config: `momentum_lookback_days`, `momentum_skip_recent_days`.

Sources:

- https://econpapers.repec.org/RePEc%3Abla%3Ajfinan%3Av%3A48%3Ay%3A1993%3Ai%3A1%3Ap%3A65-91
- https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2881657_code1556771.pdf?abstractid=2042750

### 8. Value/valuation awareness

Use valuation as a long-term risk signal, not a precise timing signal.

Rule:

- Track broad market valuation metrics such as CAPE or forward yield proxies.
- Reduce aggressiveness when valuations are extreme and trend/momentum are
  deteriorating.
- Do not sell solely because valuation is high.

Why:

- RIA argues valuation cycles matter.
- Campbell/Shiller-style valuation research supports long-horizon return
  relevance, but valuation alone is poor for short-term timing.

Implementation:

- Add optional macro/valuation data ingestion.
- Report valuation regime as context, not as an automatic order.

Sources:

- https://www.econ.yale.edu/~shiller/data.htm
- https://www.nber.org/system/files/working_papers/w8221/w8221.pdf

### 9. Volatility targeting and risk budget

Adjust total risk exposure when realized volatility rises sharply.

Rule:

- Compute realized volatility for benchmark and portfolio.
- If volatility exceeds target/range, reduce gross risky exposure or tighten
  position caps.
- Suggested defaults:
  - portfolio target vol: configurable
  - lookback: 20, 60, and 120 trading days

Why:

- RIA distinguishes volatility from permanent risk, but still treats volatility
  as a trigger for process and risk-control review.
- Volatility targeting is testable and pairs well with trend filters.

Implementation:

- Add `risk.py`: realized vol, drawdown, beta, concentration.
- Add backtest modes with and without vol targeting.

### 10. Written policy and audit trail

Every recommendation should cite the rule that caused it.

Rule:

- No silent trade suggestions.
- Every add/trim/hold must include rule IDs and inputs.
- Keep daily historical reports for review.

Why:

- RIA repeatedly stresses written rules, pre-commitment, automation, and
  accountability.
- This makes the project useful even if no trades are made: it trains process.

Implementation:

- Add rule IDs to `TradeSuggestion`.
- Store JSON reports alongside CSV/Markdown.
- Add a `portfolio-agent explain` command for the current recommendation set.

## Backtest Plan

Benchmarks:

- static buy-and-hold target portfolio
- calendar-only rebalance
- threshold rebalance
- trend-filtered strategy
- trend + z-score trim strategy
- trend + z-score + stop-risk strategy
- trend + relative momentum strategy

Metrics:

- CAGR
- annualized volatility
- Sharpe ratio
- Sortino ratio
- max drawdown
- recovery time after drawdown
- turnover
- transaction costs
- hit rate of signals
- percent time in cash
- tax-unaware vs tax-aware turnover proxy

Validation:

- Walk-forward tests by decade/regime.
- Stress periods: 2000-2002, 2008-2009, 2020, 2022.
- Sensitivity tests for moving-average windows, z-score thresholds, rebalance
  bands, stop levels, and transaction costs.

## GitHub Readiness

Before pushing:

- keep `config.yaml` private and ignored
- commit only sanitized examples
- add tests for rules and backtest accounting
- add CI that runs formatting, unit tests, and a smoke backtest using
  `example_config.yaml`
- push to a private GitHub repository first

