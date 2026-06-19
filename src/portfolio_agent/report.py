from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import AppConfig
from .models import MarketRegime, RiskPrediction, SectorSignal, TradeSuggestion
from .visuals import generate_run_charts


def signals_to_frame(signals: list[SectorSignal]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sector": s.sector,
                "etf": s.etf,
                "price": round(s.price, 4),
                "ma": round(s.ma, 4),
                "std": round(s.std, 4),
                "z": round(s.z, 4),
                "pct_from_ma": round(100 * s.pct_from_ma, 2),
                "status": s.status,
                "trend_state": s.trend_state,
                "trend_ma": round(s.trend_ma, 4),
                "momentum": round(100 * s.momentum, 2),
                "realized_vol": round(100 * s.realized_vol, 2),
            }
            for s in signals
        ]
    )


def suggestions_to_frame(suggestions: list[TradeSuggestion]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": s.ticker,
                "action": s.action,
                "delta_weight": round(100 * s.delta_weight, 2),
                "reason": s.reason,
                "rule_ids": ",".join(s.rule_ids),
            }
            for s in suggestions
        ]
    )


def risk_predictions_to_frame(risk_predictions: dict[str, RiskPrediction]) -> pd.DataFrame:
    rows = []
    for item in sorted(risk_predictions.values(), key=lambda x: x.risk_probability, reverse=True):
        row = {
            "ticker": item.ticker,
            "risk_probability": round(100 * item.risk_probability, 2),
            "risk_level": item.risk_level,
            "model_version": item.model_version,
        }
        row.update({name: round(value, 4) for name, value in item.features.items()})
        rows.append(row)
    return pd.DataFrame(rows)


def write_report(
    out_dir: str | Path,
    config: AppConfig,
    prices: pd.DataFrame,
    signals: list[SectorSignal],
    suggestions: list[TradeSuggestion],
    market_regime: MarketRegime | None = None,
    risk_predictions: dict[str, RiskPrediction] | None = None,
) -> tuple[Path, Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    risk_predictions = risk_predictions or {}

    signals_csv = out_dir / "sector_signals.csv"
    rebalance_csv = out_dir / "rebalance_suggestions.csv"
    risk_csv = out_dir / "ml_risk_predictions.csv"
    summary_md = out_dir / "summary.md"

    signals_df = signals_to_frame(signals)
    sug_df = suggestions_to_frame(suggestions)
    risk_df = risk_predictions_to_frame(risk_predictions)

    signals_df.to_csv(signals_csv, index=False)
    sug_df.to_csv(rebalance_csv, index=False)
    risk_df.to_csv(risk_csv, index=False)

    chart_paths = generate_run_charts(out_dir, config, prices, signals)

    hyped = [s.sector for s in signals if s.status == "hyped"]
    undervalued = [s.sector for s in signals if s.status == "undervalued"]

    risk_snapshot = _build_risk_snapshot(config)
    valuation_summary = _build_valuation_summary(signals)

    lines = [
        "# Portfolio Agent Report",
        "",
        "## Executive Summary",
        f"- Market regime: {_format_market_regime(market_regime)}",
        f"- Hyped sectors: {', '.join(hyped) if hyped else 'None'}",
        f"- Undervalued sectors: {', '.join(undervalued) if undervalued else 'None'}",
        f"- Suggested trades: {len(suggestions)}",
        f"- High ML risk names: {_format_high_risk_names(risk_predictions)}",
        "",
        "## Risk Snapshot",
        f"- Largest position: {risk_snapshot['largest_position']}",
        f"- Max single-name cap: {risk_snapshot['single_cap']}",
        f"- Largest sector: {risk_snapshot['largest_sector']}",
        f"- Max sector cap: {risk_snapshot['sector_cap']}",
        "",
        "## Valuation Summary",
    ]

    if not valuation_summary:
        lines.append("No valuation summary available (insufficient data).")
    else:
        lines.extend(valuation_summary)

    lines.extend([
        "",
        "## Action Items",
    ])

    if not suggestions:
        lines.append("No trade changes met thresholds.")
    else:
        for item in sorted(suggestions, key=lambda x: (x.action, -abs(x.delta_weight))):
            lines.append(f"- {item.action.upper()} {item.ticker}: {100 * item.delta_weight:+.2f}%")
            if item.rule_ids:
                lines.append(f"  - rules: {', '.join(item.rule_ids)}")
            for reason in _split_reasons(item.reason):
                lines.append(f"  - why: {reason}")

    lines.extend([
        "",
        "## ML Risk Snapshot",
    ])
    if risk_df.empty:
        lines.append("ML risk model did not have enough data to emit predictions.")
    else:
        for item in sorted(risk_predictions.values(), key=lambda x: x.risk_probability, reverse=True)[:8]:
            lines.append(
                f"- {item.ticker}: {item.risk_level} risk "
                f"({100 * item.risk_probability:.1f}% next-horizon drawdown probability)"
            )

    lines.extend([
        "",
        "## Visuals",
    ])

    for label, path in chart_paths.items():
        rel = path.relative_to(out_dir)
        lines.append(f"- {label}: `{rel}`")

    summary_md.write_text("\n".join(lines))
    return signals_csv, rebalance_csv, summary_md


def _split_reasons(reason: str) -> list[str]:
    return [part.strip() for part in reason.split(";") if part.strip()]


def _build_risk_snapshot(config: AppConfig) -> dict[str, str]:
    positions = {k: v for k, v in config.universe.positions.items() if k != "CASH"}
    ticker_sector = config.universe.ticker_sector

    if not positions:
        return {
            "largest_position": "None (0.00%)",
            "single_cap": f"{100 * config.rules.max_single_position_weight:.2f}%",
            "largest_sector": "None (0.00%)",
            "sector_cap": f"{100 * config.rules.max_sector_weight:.2f}%",
        }

    largest_ticker = max(positions, key=positions.get)
    largest_weight = positions[largest_ticker]

    sector_weights: dict[str, float] = {}
    for ticker, weight in positions.items():
        sector = ticker_sector.get(ticker, "Unknown")
        sector_weights[sector] = sector_weights.get(sector, 0.0) + weight

    largest_sector = max(sector_weights, key=sector_weights.get)
    largest_sector_weight = sector_weights[largest_sector]

    return {
        "largest_position": f"{largest_ticker} ({100 * largest_weight:.2f}%)",
        "single_cap": f"{100 * config.rules.max_single_position_weight:.2f}%",
        "largest_sector": f"{largest_sector} ({100 * largest_sector_weight:.2f}%)",
        "sector_cap": f"{100 * config.rules.max_sector_weight:.2f}%",
    }


def _build_valuation_summary(signals: list[SectorSignal]) -> list[str]:
    if not signals:
        return []

    most_cheap = sorted(signals, key=lambda s: s.z)[:3]
    most_expensive = sorted(signals, key=lambda s: s.z, reverse=True)[:3]
    lines: list[str] = ["- Most undervalued sectors (by z-score):"]
    for item in most_cheap:
        lines.append(
            f"  - {item.sector}: z={item.z:.2f}, price vs MA={100 * item.pct_from_ma:+.2f}% ({item.status})"
        )
    lines.append("- Most expensive/hyped sectors (by z-score):")
    for item in most_expensive:
        lines.append(
            f"  - {item.sector}: z={item.z:.2f}, price vs MA={100 * item.pct_from_ma:+.2f}% ({item.status})"
        )
    return lines


def _format_market_regime(market_regime: MarketRegime | None) -> str:
    if market_regime is None:
        return "unknown"
    return (
        f"{market_regime.trend_state} "
        f"({market_regime.benchmark} {market_regime.price:.2f}, "
        f"MA={market_regime.trend_ma:.2f}, "
        f"momentum={100 * market_regime.momentum:+.2f}%, "
        f"drawdown={100 * market_regime.drawdown:.2f}%)"
    )


def _format_high_risk_names(risk_predictions: dict[str, RiskPrediction]) -> str:
    names = [
        f"{item.ticker} ({100 * item.risk_probability:.1f}%)"
        for item in sorted(risk_predictions.values(), key=lambda x: x.risk_probability, reverse=True)
        if item.risk_level == "high"
    ]
    return ", ".join(names) if names else "None"
