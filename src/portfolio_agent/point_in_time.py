from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

from .backtest import compute_metrics, downsample_equity_curve, drift_weights
from .config import AppConfig
from .historical_validation import build_price_rule_target


SP500_HISTORY_COMMIT = "a91ef88fad5ace83bed1f3452f451247295bcd18"
SP500_HISTORY_URL = (
    "https://raw.githubusercontent.com/hanshof/sp500_constituents/"
    f"{SP500_HISTORY_COMMIT}/sp_500_historical_components.csv"
)
SP500_HISTORY_PROJECT_URL = "https://github.com/hanshof/sp500_constituents"


@dataclass(frozen=True)
class HistoricalUniverse:
    dates: tuple[pd.Timestamp, ...]
    members: tuple[frozenset[str], ...]
    source_url: str
    source_commit: str

    @property
    def start_date(self) -> pd.Timestamp:
        return self.dates[0]

    @property
    def end_date(self) -> pd.Timestamp:
        return self.dates[-1]

    def members_as_of(self, value: Any) -> frozenset[str]:
        dt = pd.Timestamp(value).tz_localize(None)
        index = bisect_right(self.dates, dt) - 1
        return self.members[index] if index >= 0 else frozenset()

    def unique_members(self, start: Any, end: Any) -> set[str]:
        start_dt = pd.Timestamp(start).tz_localize(None)
        end_dt = pd.Timestamp(end).tz_localize(None)
        selected = [
            members
            for dt, members in zip(self.dates, self.members, strict=True)
            if start_dt <= dt <= end_dt
        ]
        selected.append(self.members_as_of(start_dt))
        selected.append(self.members_as_of(end_dt))
        return set().union(*selected)


def load_sp500_historical_universe(
    *,
    cache_dir: str | Path | None = None,
    source_url: str = SP500_HISTORY_URL,
    source_commit: str = SP500_HISTORY_COMMIT,
) -> HistoricalUniverse:
    cache_root = _cache_root(cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)
    membership_path = cache_root / f"sp500-membership-{source_commit[:12]}.csv"

    if membership_path.exists():
        text = membership_path.read_text(encoding="utf-8")
    else:
        import httpx

        response = httpx.get(source_url, follow_redirects=True, timeout=60)
        response.raise_for_status()
        text = response.text
        membership_path.write_text(text, encoding="utf-8")

    frame = pd.read_csv(StringIO(text), parse_dates=["date"]).sort_values("date")
    frame = frame.dropna(subset=["date", "tickers"]).drop_duplicates("date", keep="last")
    if frame.empty:
        raise RuntimeError("Historical S&P 500 membership source returned no snapshots")

    dates: list[pd.Timestamp] = []
    members: list[frozenset[str]] = []
    for row in frame.itertuples(index=False):
        tickers = frozenset(
            _yahoo_symbol(item)
            for item in str(row.tickers).split(",")
            if str(item).strip()
        )
        if not tickers:
            continue
        dates.append(pd.Timestamp(row.date).tz_localize(None))
        members.append(tickers)
    if not dates:
        raise RuntimeError("Historical S&P 500 membership source contained no usable symbols")

    return HistoricalUniverse(
        dates=tuple(dates),
        members=tuple(members),
        source_url=source_url,
        source_commit=source_commit,
    )


def fetch_point_in_time_prices(
    universe: HistoricalUniverse,
    *,
    years: int = 10,
    benchmark: str = "SPY",
    extra_tickers: Iterable[str] = (),
    cache_dir: str | Path | None = None,
    cache_key: str = "sp500",
    batch_size: int = 60,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    end = universe.end_date + pd.Timedelta(days=7)
    start = universe.end_date - pd.DateOffset(years=years + 2)
    requested = sorted(
        universe.unique_members(start, universe.end_date)
        | {benchmark}
        | {str(ticker).upper() for ticker in extra_tickers}
    )
    cache_root = _cache_root(cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)
    price_path = (
        cache_root / f"{cache_key}-prices-{universe.source_commit[:12]}.csv.gz"
    )

    if price_path.exists():
        cached = pd.read_csv(price_path, index_col=0, parse_dates=True).sort_index()
    else:
        cached = pd.DataFrame()

    missing = [ticker for ticker in requested if ticker not in cached.columns]
    if missing:
        downloaded = _download_adjusted_close(
            missing,
            start=start,
            end=end,
            batch_size=batch_size,
        )
        if cached.empty:
            cached = downloaded
        else:
            cached = cached.combine_first(downloaded)
            for ticker in downloaded:
                cached[ticker] = downloaded[ticker].combine_first(cached.get(ticker))
        for ticker in missing:
            if ticker not in cached:
                cached[ticker] = np.nan
        cached = cached.sort_index().sort_index(axis=1)
        cached.to_csv(price_path, compression="gzip")

    prices = cached.reindex(columns=requested).loc[
        (cached.index >= start) & (cached.index <= end)
    ]
    any_price = [ticker for ticker in requested if prices[ticker].notna().any()]
    audit = {
        "requested_tickers": len(requested),
        "tickers_with_any_price": len(any_price),
        "ticker_price_coverage": len(any_price) / len(requested) if requested else 0.0,
        "downloaded_tickers": len(missing),
    }
    return prices, audit


def run_point_in_time_experiment(
    config: AppConfig,
    prices: pd.DataFrame,
    universe: HistoricalUniverse,
    *,
    years: int = 10,
    rebalance_days: int = 21,
    transaction_cost_bps: float | None = None,
    price_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prices = prices.sort_index()
    benchmark = config.universe.benchmark
    if benchmark not in prices or prices[benchmark].dropna().empty:
        raise ValueError(f"Point-in-time experiment is missing benchmark {benchmark}")

    end = min(
        pd.Timestamp(prices[benchmark].dropna().index.max()).tz_localize(None),
        universe.end_date,
    )
    requested_start = end - pd.DateOffset(years=years)
    benchmark_history = prices[benchmark].loc[:end].dropna()
    warmup_index = min(252, max(0, len(benchmark_history) - 1))
    warmup = pd.Timestamp(benchmark_history.index[warmup_index]).tz_localize(None)
    start = max(requested_start, warmup, universe.start_date)
    costs = (
        config.optimization.transaction_cost_bps
        if transaction_cost_bps is None
        else transaction_cost_bps
    )

    current_members = universe.members_as_of(end)
    survivor_track = _simulate_rule_track(
        config=config,
        prices=prices,
        start=start,
        end=end,
        rebalance_days=rebalance_days,
        transaction_cost_bps=costs,
        universe=universe,
        fixed_members=current_members,
        track_id="current_members_survivor_rule",
        name_en="Current members replayed backward",
        name_zh="当前成分倒放",
        description_en=(
            "Intentionally biased control: today's final S&P 500 membership is reused "
            "throughout history with the same price rule."
        ),
        description_zh="故意保留偏差的对照组：整段历史都使用期末成分，再运行同一价格规则。",
    )
    historical_track = _simulate_rule_track(
        config=config,
        prices=prices,
        start=start,
        end=end,
        rebalance_days=rebalance_days,
        transaction_cost_bps=costs,
        universe=universe,
        fixed_members=None,
        track_id="historical_membership_rule",
        name_en="Historical membership rule",
        name_zh="历史时点成分规则",
        description_en=(
            "At each rebalance, candidates are restricted to the S&P 500 membership "
            "snapshot known on that date."
        ),
        description_zh="每次调仓只允许使用当时已知的 S&P 500 历史成分。",
    )
    benchmark_track = _benchmark_track(prices, benchmark, start, end)
    benchmark_cagr = benchmark_track["metrics"]["cagr"]
    for track in (benchmark_track, survivor_track, historical_track):
        track["metrics"]["excess_cagr_vs_benchmark"] = (
            track["metrics"]["cagr"] - benchmark_cagr
        )
        track["metrics"]["drawdown_improvement_vs_benchmark"] = (
            track["metrics"]["max_drawdown"]
            - benchmark_track["metrics"]["max_drawdown"]
        )

    unique_members = universe.unique_members(start, end)
    removed_members = unique_members - current_members
    price_columns = set(prices.columns)
    removed_with_prices = {
        ticker
        for ticker in removed_members
        if ticker in price_columns and prices[ticker].loc[:end].notna().any()
    }
    observations = historical_track.pop("_universe_observations")
    covered_observations = historical_track.pop("_covered_observations")
    historical_track["selection_history"] = historical_track["selection_history"][-24:]
    survivor_track["selection_history"] = survivor_track["selection_history"][-12:]

    return {
        "status": "partial_point_in_time",
        "evaluation_start_date": _date_string(start),
        "evaluation_end_date": _date_string(end),
        "benchmark": benchmark,
        "transaction_cost_bps": costs,
        "tracks": [benchmark_track, survivor_track, historical_track],
        "bias_effect": {
            "survivor_minus_historical_cagr": (
                survivor_track["metrics"]["cagr"]
                - historical_track["metrics"]["cagr"]
            ),
            "survivor_minus_historical_sharpe": (
                survivor_track["metrics"]["sharpe"]
                - historical_track["metrics"]["sharpe"]
            ),
        },
        "universe_audit": {
            "membership_source": "hanshof/sp500_constituents",
            "membership_source_url": SP500_HISTORY_PROJECT_URL,
            "membership_source_commit": universe.source_commit,
            "membership_license": "MIT",
            "membership_is_official": False,
            "membership_start_date": _date_string(universe.start_date),
            "membership_end_date": _date_string(universe.end_date),
            "unique_historical_members": len(unique_members),
            "final_members": len(current_members),
            "removed_members_included": len(removed_members),
            "removed_members_with_price_history": len(removed_with_prices),
            "rebalance_member_observations": observations,
            "price_eligible_observations": covered_observations,
            "rebalance_price_coverage": (
                covered_observations / observations if observations else 0.0
            ),
            **(price_audit or {}),
        },
        "integrity": {
            "historical_membership_used": True,
            "same_rule_in_both_bias_tracks": True,
            "lookahead_protection": (
                "Membership and prices are read as of close t; new weights first affect t+1."
            ),
            "survivorship_bias_eliminated": False,
            "survivorship_bias_substantially_reduced": True,
            "delisted_price_returns_complete": False,
            "claim_level": "research_proxy_not_crsp_grade",
        },
        "limitations_en": [
            "Historical membership is community-reconstructed, not official S&P or CRSP data.",
            "Yahoo price history is incomplete for some delisted and renamed securities.",
            "Missing CRSP delisting returns can still make failed holdings look better than reality.",
            "S&P 500 membership is a large-cap liquid proxy, not the full U.S. listed market.",
            "The rule uses historical price evidence only; point-in-time fundamentals are not included.",
        ],
        "limitations_zh": [
            "历史成分来自社区重建数据，不是 S&P 或 CRSP 官方数据库。",
            "Yahoo 对部分退市和更名证券的历史价格并不完整。",
            "缺少 CRSP 退市收益时，失败持仓仍可能被高估。",
            "S&P 500 只是大型高流动性股票代理，并非全部美国上市股票。",
            "本轨道只使用当时价格证据，尚未加入逐时点基本面数据。",
        ],
    }


def _simulate_rule_track(
    *,
    config: AppConfig,
    prices: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    rebalance_days: int,
    transaction_cost_bps: float,
    universe: HistoricalUniverse,
    fixed_members: frozenset[str] | None,
    track_id: str,
    name_en: str,
    name_zh: str,
    description_en: str,
    description_zh: str,
) -> dict[str, Any]:
    evaluation = prices.loc[(prices.index >= start) & (prices.index <= end)]
    returns = prices.pct_change(fill_method=None)
    weights: dict[str, float] = {"CASH": 1.0}
    value = 1.0
    total_turnover = 0.0
    rows: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    universe_observations = 0
    covered_observations = 0

    for offset, dt in enumerate(evaluation.index):
        previous_value = value
        day_returns = returns.loc[dt]
        portfolio_return = float(
            sum(
                weight * float(day_returns.get(ticker, 0.0))
                for ticker, weight in weights.items()
                if ticker != "CASH"
                and pd.notna(day_returns.get(ticker, np.nan))
            )
        )
        value *= 1.0 + portfolio_return
        weights = drift_weights(weights, day_returns.fillna(0.0), portfolio_return)

        members = fixed_members or universe.members_as_of(dt)
        should_rebalance = offset % rebalance_days == 0
        if should_rebalance and members:
            history = prices.loc[:dt]
            desired, audit = build_price_rule_target(
                config,
                history,
                assets=members,
            )
            desired = _normalize_target(desired)
            turnover = 0.5 * sum(
                abs(desired.get(ticker, 0.0) - weights.get(ticker, 0.0))
                for ticker in set(desired) | set(weights)
            )
            value *= max(0.0, 1.0 - turnover * transaction_cost_bps / 10_000.0)
            weights = desired
            total_turnover += turnover
            universe_observations += len(members)
            covered_observations += int(audit["price_eligible_count"])
            selections.append(
                {
                    "date": _date_string(dt),
                    "reason": "scheduled",
                    "membership_count": len(members),
                    "price_eligible_count": audit["price_eligible_count"],
                    "selected": audit["selected"],
                    "market_regime": audit["market_regime"],
                    "cash_weight": desired.get("CASH", 0.0),
                }
            )

        rows.append(
            {
                "date": _date_string(dt),
                "portfolio_value": value,
                "daily_return": value / previous_value - 1.0 if previous_value else 0.0,
            }
        )

    curve = pd.DataFrame(rows)
    metrics = compute_metrics(curve)
    published_curve = downsample_equity_curve(curve)
    latest_holdings = [
        ticker
        for ticker, weight in sorted(weights.items(), key=lambda item: item[1], reverse=True)
        if ticker != "CASH" and weight > 0.005
    ]
    return {
        "id": track_id,
        "name_en": name_en,
        "name_zh": name_zh,
        "description_en": description_en,
        "description_zh": description_zh,
        "metrics": metrics,
        "turnover": float(total_turnover),
        "rebalance_count": len(selections),
        "latest_holdings": latest_holdings,
        "equity_curve": published_curve.to_dict(orient="records"),
        "selection_history": selections,
        "_universe_observations": universe_observations,
        "_covered_observations": covered_observations,
    }


def _benchmark_track(
    prices: pd.DataFrame,
    benchmark: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    close = prices[benchmark].loc[(prices.index >= start) & (prices.index <= end)].dropna()
    returns = close.pct_change(fill_method=None).fillna(0.0)
    curve = pd.DataFrame(
        {
            "date": close.index.map(_date_string),
            "portfolio_value": (1.0 + returns).cumprod().values,
            "daily_return": returns.values,
        }
    )
    metrics = compute_metrics(curve)
    published_curve = downsample_equity_curve(curve)
    return {
        "id": "point_in_time_benchmark",
        "name_en": f"{benchmark} point-in-time benchmark",
        "name_zh": f"{benchmark} 同期基准",
        "description_en": "Passive benchmark over the exact membership experiment window.",
        "description_zh": "在与历史成分实验完全相同的区间被动持有基准。",
        "metrics": metrics,
        "turnover": 0.0,
        "rebalance_count": 0,
        "latest_holdings": [benchmark],
        "equity_curve": published_curve.to_dict(orient="records"),
    }


def _download_adjusted_close(
    tickers: list[str],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    batch_size: int,
) -> pd.DataFrame:
    import yfinance as yf

    frames: list[pd.DataFrame] = []
    for offset in range(0, len(tickers), batch_size):
        batch = tickers[offset : offset + batch_size]
        frame = yf.download(
            tickers=batch,
            start=_date_string(start),
            end=_date_string(end),
            progress=False,
            auto_adjust=True,
            group_by="ticker",
            threads=True,
            timeout=45,
        )
        close = _extract_close(frame, batch)
        if not close.empty:
            frames.append(close)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1).sort_index()


def _extract_close(frame: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    if isinstance(frame.columns, pd.MultiIndex):
        if "Close" in frame.columns.get_level_values(1):
            return frame.xs("Close", level=1, axis=1)
        if "Close" in frame.columns.get_level_values(0):
            return frame["Close"]
    if "Close" in frame:
        return frame[["Close"]].rename(columns={"Close": tickers[0]})
    return pd.DataFrame()


def _cache_root(value: str | Path | None) -> Path:
    if value is not None:
        return Path(value).expanduser()
    return Path.home() / ".cache" / "portfolio_agent" / "point_in_time"


def _yahoo_symbol(value: str) -> str:
    return value.strip().upper().replace(".", "-")


def _normalize_target(weights: dict[str, float]) -> dict[str, float]:
    cleaned = {ticker: max(0.0, float(weight)) for ticker, weight in weights.items()}
    total = sum(cleaned.values())
    if total <= 0:
        return {"CASH": 1.0}
    return {ticker: weight / total for ticker, weight in cleaned.items()}


def _date_string(value: Any) -> str:
    return str(pd.Timestamp(value).date())
