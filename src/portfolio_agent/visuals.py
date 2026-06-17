from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .config import AppConfig
from .indicators import moving_average, rolling_std
from .signals import SectorSignal


def generate_run_charts(
    out_dir: str | Path,
    config: AppConfig,
    prices: pd.DataFrame,
    signals: list[SectorSignal],
) -> dict[str, Path]:
    charts_dir = Path(out_dir) / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    chart_paths: dict[str, Path] = {}

    if signals:
        chart_paths["sector_zscores"] = _plot_sector_zscores(charts_dir, signals)
        chart_paths["valuation_bands"] = _plot_valuation_bands(charts_dir, config, prices, signals)

    chart_paths["position_vs_target"] = _plot_position_vs_target(
        charts_dir,
        config.universe.positions,
        config.universe.target_weights,
    )
    chart_paths["sector_concentration"] = _plot_sector_concentration(
        charts_dir,
        config.universe.positions,
        config.universe.ticker_sector,
        config.rules.max_sector_weight,
    )

    return chart_paths


def generate_backtest_charts(out_dir: str | Path, equity_curve: pd.DataFrame, trades: pd.DataFrame) -> dict[str, Path]:
    charts_dir = Path(out_dir) / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    chart_paths: dict[str, Path] = {}
    chart_paths["equity_curve"] = _plot_equity_curve(charts_dir, equity_curve)
    chart_paths["drawdown"] = _plot_drawdown(charts_dir, equity_curve)
    chart_paths["turnover"] = _plot_turnover(charts_dir, trades)
    return chart_paths


def _plot_sector_zscores(charts_dir: Path, signals: list[SectorSignal]) -> Path:
    frame = pd.DataFrame(
        {
            "sector": [s.sector for s in signals],
            "z": [s.z for s in signals],
        }
    ).sort_values("z")

    colors = ["#1b9e77" if v < -1 else "#d95f02" if v > 1 else "#7570b3" for v in frame["z"]]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.barh(frame["sector"], frame["z"], color=colors)
    ax.axvline(0, color="black", linewidth=1)
    ax.axvline(3, color="#d95f02", linestyle="--", linewidth=1)
    ax.axvline(-3, color="#1b9e77", linestyle="--", linewidth=1)
    ax.set_title("Sector Valuation Z-Scores")
    ax.set_xlabel("Z-score")
    ax.set_ylabel("Sector")
    fig.tight_layout()

    output = charts_dir / "sector_zscores.png"
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output


def _plot_position_vs_target(
    charts_dir: Path,
    positions: dict[str, float],
    targets: dict[str, float],
) -> Path:
    tickers = sorted(set(positions) | set(targets))
    current = [positions.get(t, 0.0) * 100 for t in tickers]
    target = [targets.get(t, 0.0) * 100 for t in tickers]

    fig, ax = plt.subplots(figsize=(12, 6))
    x = range(len(tickers))
    ax.bar([i - 0.2 for i in x], current, width=0.4, label="Current", color="#4e79a7")
    ax.bar([i + 0.2 for i in x], target, width=0.4, label="Target", color="#f28e2b")
    ax.set_xticks(list(x))
    ax.set_xticklabels(tickers, rotation=45, ha="right")
    ax.set_ylabel("Weight (%)")
    ax.set_title("Position Weights vs Target Allocation")
    ax.legend()
    fig.tight_layout()

    output = charts_dir / "position_vs_target.png"
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output


def _plot_sector_concentration(
    charts_dir: Path,
    positions: dict[str, float],
    ticker_sector: dict[str, str],
    max_sector_weight: float,
) -> Path:
    sector_weights: dict[str, float] = {}
    for ticker, weight in positions.items():
        sector = ticker_sector.get(ticker, "Unknown")
        sector_weights[sector] = sector_weights.get(sector, 0.0) + weight

    frame = pd.DataFrame(
        {
            "sector": list(sector_weights.keys()),
            "weight": [v * 100 for v in sector_weights.values()],
        }
    ).sort_values("weight", ascending=False)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = range(len(frame))
    ax.bar(list(x), frame["weight"], color="#59a14f")
    ax.axhline(max_sector_weight * 100, color="#e15759", linestyle="--", label="Sector max cap")
    ax.set_ylabel("Weight (%)")
    ax.set_title("Sector Concentration Risk")
    ax.set_xticks(list(x))
    ax.set_xticklabels(frame["sector"], rotation=45, ha="right")
    ax.legend()
    fig.tight_layout()

    output = charts_dir / "sector_concentration.png"
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output


def _plot_valuation_bands(
    charts_dir: Path,
    config: AppConfig,
    prices: pd.DataFrame,
    signals: list[SectorSignal],
) -> Path:
    selected = sorted(signals, key=lambda s: abs(s.z), reverse=True)[:6]
    if not selected:
        return charts_dir / "valuation_bands.png"

    fig, axes = plt.subplots(2, 3, figsize=(14, 8), sharex=False)
    axes_list = [ax for row in axes for ax in row]

    for idx, signal in enumerate(selected):
        ax = axes_list[idx]
        etf = signal.etf
        if etf not in prices.columns:
            ax.set_visible(False)
            continue

        series = prices[etf].dropna().tail(260)
        ma = moving_average(series, config.indicators.ma_window)
        std = rolling_std(series, config.indicators.std_window)
        upper = ma + config.indicators.extreme_z * std
        lower = ma - config.indicators.extreme_z * std

        ax.plot(series.index, series.values, label="Price", color="#4e79a7", linewidth=1.5)
        ax.plot(ma.index, ma.values, label=f"MA{config.indicators.ma_window}", color="#f28e2b", linewidth=1.2)
        ax.plot(upper.index, upper.values, label="Upper band", color="#e15759", linestyle="--", linewidth=1)
        ax.plot(lower.index, lower.values, label="Lower band", color="#59a14f", linestyle="--", linewidth=1)
        ax.set_title(f"{signal.sector} ({etf}) z={signal.z:.2f}")
        ax.tick_params(axis="x", labelrotation=45)

    for idx in range(len(selected), len(axes_list)):
        axes_list[idx].set_visible(False)

    handles, labels = axes_list[0].get_legend_handles_labels() if selected else ([], [])
    if handles:
        fig.legend(handles, labels, loc="upper center", ncol=4, frameon=False)
    fig.suptitle("Valuation Bands: Price vs MA and +/-3 STD", y=0.98)
    fig.tight_layout(rect=(0, 0, 1, 0.95))

    output = charts_dir / "valuation_bands.png"
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output


def _plot_equity_curve(charts_dir: Path, equity_curve: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(pd.to_datetime(equity_curve["date"]), equity_curve["portfolio_value"], color="#4e79a7")
    ax.set_title("Backtest Equity Curve")
    ax.set_ylabel("Portfolio Value")
    fig.tight_layout()

    output = charts_dir / "equity_curve.png"
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output


def _plot_drawdown(charts_dir: Path, equity_curve: pd.DataFrame) -> Path:
    series = equity_curve["portfolio_value"]
    running_max = series.cummax()
    dd = (series / running_max) - 1.0

    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.fill_between(pd.to_datetime(equity_curve["date"]), dd.values * 100, 0, color="#e15759", alpha=0.35)
    ax.plot(pd.to_datetime(equity_curve["date"]), dd.values * 100, color="#e15759", linewidth=1)
    ax.set_title("Backtest Drawdown")
    ax.set_ylabel("Drawdown (%)")
    fig.tight_layout()

    output = charts_dir / "drawdown.png"
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output


def _plot_turnover(charts_dir: Path, trades: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(11, 4.5))
    if trades.empty:
        ax.text(0.5, 0.5, "No trades", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
    else:
        frame = trades.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        frame["turnover"] = frame["delta_weight"].abs() * 100
        grouped = frame.groupby("date", as_index=False)["turnover"].sum()
        ax.bar(grouped["date"], grouped["turnover"], color="#76b7b2")
        ax.set_ylabel("Turnover (% weight)")
        ax.set_title("Backtest Rebalance Turnover")
    fig.tight_layout()

    output = charts_dir / "turnover.png"
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output
