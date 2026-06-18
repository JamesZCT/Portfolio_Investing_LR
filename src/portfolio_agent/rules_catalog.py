from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StrategyRule:
    rule_id: str
    name: str
    category: str
    formula: str
    action: str
    rationale: str
    evidence: str
    implementation_status: str
    source_url: str


RULES: tuple[StrategyRule, ...] = (
    StrategyRule(
        "TREND_200DMA",
        "200-day trend regime filter",
        "Trend / risk regime",
        "trend_state = bullish if close > SMA(close, 200), bearish otherwise",
        "Avoid adding risk in bearish regimes; optionally trim risk and raise cash.",
        "Long-term trend rules reduce the chance of staying fully exposed during major bear markets.",
        "Supported by tactical allocation and trend-following research.",
        "implemented",
        "https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf",
    ),
    StrategyRule(
        "Z_EXTREME_BANDS",
        "Volatility-adjusted extension bands",
        "Mean reversion / valuation extension",
        "z = (close - rolling_mean(close, z_window)) / rolling_std(close, z_window)",
        "Trim hyped/overextended exposure; consider washed-out candidates only with trend confirmation.",
        "Standard deviation bands express whether a move is unusual relative to recent volatility.",
        "Commonly used in Bollinger-style band analysis; best used as confirmation, not a standalone signal.",
        "implemented",
        "https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/bollinger-bands",
    ),
    StrategyRule(
        "THRESHOLD_REBALANCE",
        "Threshold rebalancing",
        "Portfolio construction",
        "drift = current_weight - target_weight; rebalance when abs(drift) > threshold",
        "Trim overweight assets and add to underweight assets when rules allow.",
        "Keeps portfolio risk aligned with the intended plan and reduces emotional decision-making.",
        "Vanguard frames rebalancing primarily as a risk-control discipline.",
        "implemented",
        "https://investor.vanguard.com/investor-resources-education/portfolio-management/rebalancing-your-portfolio",
    ),
    StrategyRule(
        "POSITION_CAP",
        "Single-position cap",
        "Risk control",
        "position_weight <= max_single_position_weight",
        "Trim positions above cap.",
        "Prevents one mistake or one winner from becoming a portfolio-level concentration risk.",
        "Widely used institutional risk-control principle.",
        "implemented",
        "https://www.investor.gov/introduction-investing/investing-basics/glossary/diversification",
    ),
    StrategyRule(
        "SECTOR_CAP",
        "Sector concentration cap",
        "Risk control",
        "sum(position_weight for same sector) <= max_sector_weight",
        "Trim sector members proportionally when the sector exceeds cap.",
        "Avoids hidden correlation risk when many holdings depend on the same macro/sector driver.",
        "Diversification principle; implemented as a quantitative portfolio constraint.",
        "implemented",
        "https://www.investor.gov/introduction-investing/investing-basics/glossary/diversification",
    ),
    StrategyRule(
        "NO_AVERAGE_DOWN",
        "No automatic averaging down",
        "Behavioral guardrail",
        "block_add if latest_price / entry_price - 1 <= -loss_block_pct",
        "Block adds to losing positions unless there is a documented thesis reset.",
        "Prevents hope-based averaging down from masquerading as disciplined investing.",
        "Behavioral finance guardrail consistent with RIA/Lance Roberts risk rules.",
        "implemented",
        "https://www.realinvestmentadvice.com/",
    ),
    StrategyRule(
        "STOP_LOSS",
        "Entry-price stop risk",
        "Drawdown control",
        "drawdown_from_entry = latest_price / entry_price - 1",
        "Partially trim when drawdown breaches configured threshold.",
        "Large losses require disproportionately large gains to recover.",
        "Risk-management principle emphasized by RIA and drawdown mathematics.",
        "implemented",
        "https://www.realinvestmentadvice.com/",
    ),
    StrategyRule(
        "TRAILING_STOP",
        "Trailing high drawdown control",
        "Drawdown control",
        "drawdown_from_peak = latest_price / trailing_high - 1",
        "Partially trim when trailing drawdown breaches threshold.",
        "Protects gains and prevents strong winners from becoming large round trips.",
        "Common systematic risk-control rule.",
        "implemented",
        "https://www.realinvestmentadvice.com/",
    ),
    StrategyRule(
        "MOMENTUM_12_1",
        "Relative and absolute momentum",
        "Momentum",
        "momentum = price[today] / price[today - lookback] - 1",
        "Prefer adds to positive-momentum assets with strong relative ranking.",
        "Momentum has long-running academic evidence across equities and asset classes.",
        "Partially implemented as signal feature; strategy harness still pending.",
        "partial",
        "https://econpapers.repec.org/RePEc%3Abla%3Ajfinan%3Av%3A48%3Ay%3A1993%3Ai%3A1%3Ap%3A65-91",
    ),
    StrategyRule(
        "VALUE_AWARENESS",
        "Valuation awareness",
        "Valuation / macro risk",
        "valuation_regime = percentile(CAPE or valuation proxy over long history)",
        "Use high valuation as a risk-context modifier, not as a precise timing signal.",
        "Valuation metrics have long-horizon return information but weak short-term timing power.",
        "Research cataloged; data ingestion pending.",
        "planned",
        "https://www.econ.yale.edu/~shiller/data.htm",
    ),
    StrategyRule(
        "VOL_TARGET",
        "Volatility targeting",
        "Risk budgeting",
        "scale = target_vol / realized_vol, bounded by min/max exposure",
        "Reduce risky exposure when realized volatility materially exceeds target.",
        "Keeps risk budget more stable across changing volatility regimes.",
        "Useful for comparison harness; not yet active in recommendations.",
        "planned",
        "https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing",
    ),
    StrategyRule(
        "ML_DRAWDOWN_RISK",
        "ML drawdown-risk overlay",
        "ML risk model",
        "p(drawdown_event) = sigmoid(beta * rolling_price_features)",
        "Block adds or trim when predicted next-horizon drawdown risk is high.",
        "A transparent ML overlay can help rank risk, but must remain explainable and subordinate to rules.",
        "implemented as lightweight logistic model.",
        "implemented",
        "https://scikit-learn.org/stable/modules/linear_model.html#logistic-regression",
    ),
)


def rules_as_dicts() -> list[dict[str, str]]:
    return [asdict(rule) for rule in RULES]
