from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .backtest import compute_metrics, downsample_equity_curve, drift_weights
from .point_in_time import HistoricalUniverse


NASDAQ100_HISTORY_COMMIT = "9a23023b59707c5372ae1fff4ed983b3ad025c74"
NASDAQ100_HISTORY_PROJECT_URL = "https://github.com/jmccarrell/n100tickers"
NASDAQ100_HISTORY_RAW_URL = (
    "https://raw.githubusercontent.com/jmccarrell/n100tickers/"
    f"{NASDAQ100_HISTORY_COMMIT}/src/nasdaq_100_ticker_history/"
    "n100-ticker-changes-{year}.yaml"
)
NASDAQ100_HISTORY_START_YEAR = 2015
NASDAQ100_HISTORY_END_YEAR = 2026

STRATEGY_SOURCE_URLS = {
    "nasdaq_100_methodology": "https://indexes.nasdaq.com/docs/Methodology_NDX.pdf",
    "nasdaq_100_factsheet": "https://indexes.nasdaq.com/docs/FS_NDX.pdf",
    "ria_public_process": (
        "https://realinvestmentadvice.com/wp-content/uploads/2022/03/"
        "advisors_brochure1.pdf"
    ),
    "ria_money_flow_discussion": (
        "https://realinvestmentadvice.com/resources/blog/"
        "the-stock-market-rally-buy-or-fade-it/"
    ),
}

STATIC_CORE_ALLOCATION = {
    "SPY": 0.50,
    "QQQ": 0.25,
    "ACTIVE": 0.15,
    "BIL": 0.10,
}
DYNAMIC_ALLOCATIONS = {
    "risk_on": {"SPY": 0.40, "QQQ": 0.35, "ACTIVE": 0.20, "BIL": 0.05},
    "neutral": {"SPY": 0.50, "QQQ": 0.25, "ACTIVE": 0.15, "BIL": 0.10},
    "defensive": {"SPY": 0.50, "QQQ": 0.15, "ACTIVE": 0.05, "BIL": 0.30},
}
DYNAMIC_RANGES = {
    "SPY": (0.40, 0.60),
    "QQQ": (0.15, 0.35),
    "ACTIVE": (0.05, 0.25),
    "BIL": (0.05, 0.30),
}


def load_nasdaq100_historical_universe(
    *,
    cache_dir: str | Path | None = None,
    source_commit: str = NASDAQ100_HISTORY_COMMIT,
    start_year: int = NASDAQ100_HISTORY_START_YEAR,
    end_year: int = NASDAQ100_HISTORY_END_YEAR,
    source_texts: dict[int, str] | None = None,
) -> HistoricalUniverse:
    if start_year > end_year:
        raise ValueError("Nasdaq-100 history start_year must not exceed end_year")

    cache_root = (
        Path(cache_dir).expanduser()
        if cache_dir is not None
        else Path.home()
        / ".cache"
        / "portfolio_agent"
        / "point_in_time"
        / "nasdaq100"
    )
    cache_root.mkdir(parents=True, exist_ok=True)

    snapshots: dict[pd.Timestamp, frozenset[str]] = {}
    for year in range(start_year, end_year + 1):
        text = (
            source_texts[year]
            if source_texts is not None and year in source_texts
            else _load_nasdaq_history_year(
                year,
                cache_root=cache_root,
                source_commit=source_commit,
            )
        )
        document = yaml.safe_load(text) or {}
        jan_members = frozenset(
            _yahoo_symbol(ticker)
            for ticker in document.get("tickers_on_Jan_1", [])
            if ticker
        )
        if not jan_members:
            raise RuntimeError(
                f"Nasdaq-100 history for {year} did not contain Jan. 1 membership"
            )

        current = set(jan_members)
        snapshots[pd.Timestamp(f"{year}-01-01")] = frozenset(current)
        changes = document.get("changes") or {}
        for raw_date, change in sorted(
            changes.items(), key=lambda item: pd.Timestamp(item[0])
        ):
            for ticker in change.get("difference", []) or []:
                current.discard(_yahoo_symbol(ticker))
            for ticker in change.get("union", []) or []:
                current.add(_yahoo_symbol(ticker))
            snapshots[pd.Timestamp(raw_date).tz_localize(None)] = frozenset(current)

    ordered = sorted(snapshots.items(), key=lambda item: item[0])
    return HistoricalUniverse(
        dates=tuple(item[0] for item in ordered),
        members=tuple(item[1] for item in ordered),
        source_url=NASDAQ100_HISTORY_PROJECT_URL,
        source_commit=source_commit,
    )


def run_index_core_strategy_comparison(
    prices: pd.DataFrame,
    nasdaq_universe: HistoricalUniverse,
    *,
    sp500_universe: HistoricalUniverse | None = None,
    years: int = 10,
    rebalance_days: int = 21,
    transaction_cost_bps: float = 8.0,
    active_count: int = 10,
    volatility_target: float = 0.15,
) -> dict[str, Any]:
    prices = prices.sort_index()
    required = {"QQQ", "SPY", "BIL"}
    missing = sorted(
        ticker
        for ticker in required
        if ticker not in prices or prices[ticker].dropna().empty
    )
    if missing:
        raise ValueError(
            "Index-core comparison is missing required prices: " + ", ".join(missing)
        )

    end = min(
        nasdaq_universe.end_date,
        *(pd.Timestamp(prices[ticker].dropna().index.max()).tz_localize(None) for ticker in required),
    )
    requested_start = end - pd.DateOffset(years=years)
    qqq_history = prices["QQQ"].loc[:end].dropna()
    if len(qqq_history) < 253:
        raise ValueError("Index-core comparison requires at least 253 QQQ observations")
    warmup = pd.Timestamp(qqq_history.index[252]).tz_localize(None)
    start = max(requested_start, warmup, nasdaq_universe.start_date)
    evaluation_index = prices.index[(prices.index >= start) & (prices.index <= end)]
    if len(evaluation_index) < 2:
        raise ValueError("Index-core comparison has no usable evaluation window")

    track_specs = {
        "qqq_passive": {
            "name_en": "Passive Nasdaq-100 (QQQ)",
            "name_zh": "被动纳斯达克 100（QQQ）",
            "description_en": "Buy-and-hold QQQ over the exact comparison window.",
            "description_zh": "在完全相同的比较区间内买入并持有 QQQ。",
        },
        "static_index_core": {
            "name_en": "Static broad-market + QQQ core",
            "name_zh": "静态大盘 + QQQ 核心",
            "description_en": (
                "A fixed 50% SPY, 25% QQQ, 15% point-in-time price-factor sleeve "
                "and 10% Treasury-bill proxy."
            ),
            "description_zh": (
                "固定配置：50% SPY、25% QQQ、15% 逐时点价格因子选股、"
                "10% 短期国债代理。"
            ),
        },
        "dynamic_qqq_challenger": {
            "name_en": "Dynamic QQQ challenger",
            "name_zh": "动态 QQQ 挑战组合",
            "description_en": (
                "A bounded core/satellite allocation that changes only among "
                "pre-declared risk-on, neutral and defensive weights."
            ),
            "description_zh": (
                "有明确上下限的核心加卫星组合，只在预先声明的进攻、"
                "中性和防守权重之间切换。"
            ),
        },
        "ria_public_proxy": {
            "name_en": "RIA-inspired public risk proxy",
            "name_zh": "RIA 启发的公开风险代理",
            "description_en": (
                "A transparent SPY/BIL exposure rule inspired by RIA's public "
                "trend and money-flow discussions. It is not RIA's proprietary MFBR."
            ),
            "description_zh": (
                "受 RIA 公开趋势与资金流讨论启发的透明 SPY/BIL 风险敞口规则；"
                "它不是 RIA 的专有 MFBR 模型。"
            ),
        },
        "qqq_volatility_control": {
            "name_en": "QQQ volatility control",
            "name_zh": "QQQ 波动率控制",
            "description_en": (
                "QQQ plus Treasury bills, targeting 15% trailing volatility "
                "without leverage."
            ),
            "description_zh": "QQQ 加短期国债，目标历史波动率 15%，不使用杠杆。",
        },
    }
    states = {
        track_id: {
            "value": 1.0,
            "weights": {"BIL": 1.0},
            "rows": [],
            "turnover": 0.0,
            "rebalances": [],
        }
        for track_id in track_specs
    }

    first_date = pd.Timestamp(evaluation_index[0]).tz_localize(None)
    initial_targets, initial_audit = _targets_as_of(
        prices,
        first_date,
        nasdaq_universe,
        sp500_universe=sp500_universe,
        active_count=active_count,
        volatility_target=volatility_target,
    )
    latest_audit = initial_audit
    for track_id, state in states.items():
        state["weights"] = initial_targets[track_id]
        state["rebalances"].append(
            _rebalance_record(first_date, initial_targets[track_id], initial_audit)
        )
        state["rows"].append(
            {
                "date": _date_string(first_date),
                "portfolio_value": 1.0,
                "daily_return": 0.0,
            }
        )

    returns = prices.pct_change(fill_method=None)
    for offset, raw_date in enumerate(evaluation_index[1:], start=1):
        dt = pd.Timestamp(raw_date).tz_localize(None)
        day_returns = returns.loc[raw_date]
        for state in states.values():
            previous_value = state["value"]
            state["_day_start_value"] = previous_value
            portfolio_return = _portfolio_return(state["weights"], day_returns)
            state["value"] *= 1.0 + portfolio_return
            state["weights"] = drift_weights(
                state["weights"],
                day_returns.fillna(0.0),
                portfolio_return,
            )
            state["rows"].append(
                {
                    "date": _date_string(dt),
                    "portfolio_value": state["value"],
                    "daily_return": (
                        state["value"] / previous_value - 1.0
                        if previous_value
                        else 0.0
                    ),
                }
            )

        if offset % rebalance_days != 0:
            continue

        targets, audit = _targets_as_of(
            prices,
            dt,
            nasdaq_universe,
            sp500_universe=sp500_universe,
            active_count=active_count,
            volatility_target=volatility_target,
        )
        latest_audit = audit
        for track_id, state in states.items():
            desired = targets[track_id]
            turnover = _turnover(state["weights"], desired)
            state["value"] *= max(
                0.0, 1.0 - turnover * transaction_cost_bps / 10_000.0
            )
            state["rows"][-1]["portfolio_value"] = state["value"]
            state["rows"][-1]["daily_return"] = (
                state["value"] / state["_day_start_value"] - 1.0
                if state["_day_start_value"]
                else 0.0
            )
            state["weights"] = desired
            state["turnover"] += turnover
            state["rebalances"].append(_rebalance_record(dt, desired, audit))

    tracks: list[dict[str, Any]] = []
    qqq_returns = pd.Series(
        states["qqq_passive"]["rows"][index]["daily_return"]
        for index in range(len(evaluation_index))
    )
    benchmark_metrics: dict[str, float] | None = None
    for track_id, spec in track_specs.items():
        state = states[track_id]
        curve = pd.DataFrame(state["rows"])
        metrics = compute_metrics(curve)
        metrics.update(
            _relative_risk_metrics(
                curve["daily_return"].astype(float),
                qqq_returns,
                metrics,
            )
        )
        if track_id == "qqq_passive":
            benchmark_metrics = metrics
        latest_weights = {
            ticker: float(weight)
            for ticker, weight in sorted(
                state["weights"].items(), key=lambda item: item[1], reverse=True
            )
            if weight > 0.0001
        }
        tracks.append(
            {
                "id": track_id,
                **spec,
                "metrics": metrics,
                "turnover": float(state["turnover"]),
                "rebalance_count": len(state["rebalances"]),
                "latest_weights": latest_weights,
                "equity_curve": downsample_equity_curve(curve).to_dict(
                    orient="records"
                ),
                "allocation_history": state["rebalances"][-24:],
            }
        )

    if benchmark_metrics is None:
        raise RuntimeError("QQQ benchmark metrics were not produced")
    for track in tracks:
        track["metrics"]["excess_cagr_vs_qqq"] = (
            track["metrics"]["cagr"] - benchmark_metrics["cagr"]
        )
        track["metrics"]["drawdown_improvement_vs_qqq"] = (
            track["metrics"]["max_drawdown"]
            - benchmark_metrics["max_drawdown"]
        )

    challenger = next(
        track for track in tracks if track["id"] == "dynamic_qqq_challenger"
    )
    beat_qqq = challenger["metrics"]["cagr"] > benchmark_metrics["cagr"]
    improved_drawdown = (
        challenger["metrics"]["max_drawdown"] > benchmark_metrics["max_drawdown"]
    )

    return {
        "status": "partial_point_in_time",
        "evaluation_start_date": _date_string(start),
        "evaluation_end_date": _date_string(end),
        "benchmark": "QQQ",
        "transaction_cost_bps": transaction_cost_bps,
        "rebalance_days": rebalance_days,
        "tracks": tracks,
        "verdict": {
            "beat_qqq_on_cagr": beat_qqq,
            "improved_max_drawdown": improved_drawdown,
            "beat_qqq_and_improved_drawdown": beat_qqq and improved_drawdown,
            "challenger_excess_cagr": challenger["metrics"]["excess_cagr_vs_qqq"],
            "challenger_drawdown_improvement": challenger["metrics"][
                "drawdown_improvement_vs_qqq"
            ],
            "explanation_en": (
                "Pass" if beat_qqq else "Did not pass"
            )
            + (
                ": the dynamic challenger beat QQQ over this fixed historical "
                "window after modeled costs."
                if beat_qqq
                else ": the dynamic challenger did not beat QQQ over this fixed "
                "historical window after modeled costs."
            ),
            "explanation_zh": (
                "通过：动态挑战组合在这一固定历史区间、计入模拟成本后跑赢 QQQ。"
                if beat_qqq
                else "未通过：动态挑战组合在这一固定历史区间、计入模拟成本后没有跑赢 QQQ。"
            ),
        },
        "latest_signal": latest_audit,
        "allocation_policy": {
            "static": STATIC_CORE_ALLOCATION,
            "dynamic_ranges": {
                key: {"minimum": bounds[0], "maximum": bounds[1]}
                for key, bounds in DYNAMIC_RANGES.items()
            },
            "dynamic_regimes": DYNAMIC_ALLOCATIONS,
            "active_sleeve_count": active_count,
            "active_sleeve_rule_en": (
                "Top point-in-time Nasdaq-100 members by 12-2 momentum, "
                "200-day trend, lower 126-day volatility and drawdown resilience."
            ),
            "active_sleeve_rule_zh": (
                "在当时 Nasdaq-100 成分股中，按 12-2 动量、200 日趋势、"
                "较低的 126 日波动率和回撤韧性综合排名。"
            ),
            "volatility_target": volatility_target,
            "parameter_selection_en": (
                "Weights, thresholds and costs were declared before observing this "
                "comparison result and are not optimized to maximize the displayed CAGR."
            ),
            "parameter_selection_zh": (
                "权重、阈值和成本在查看本次比较结果前已固定，"
                "没有为了最大化页面上的年化收益而调参。"
            ),
        },
        "universe_audit": {
            "membership_source": "jmccarrell/n100tickers",
            "membership_source_url": NASDAQ100_HISTORY_PROJECT_URL,
            "membership_source_commit": nasdaq_universe.source_commit,
            "membership_license": "MIT",
            "membership_is_official": False,
            "membership_start_date": _date_string(nasdaq_universe.start_date),
            "membership_end_date": _date_string(nasdaq_universe.end_date),
            "unique_historical_members": len(
                nasdaq_universe.unique_members(start, end)
            ),
        },
        "integrity": {
            "historical_nasdaq_membership_used": True,
            "signals_use_close_t_and_affect_t_plus_1": True,
            "parameters_optimized_on_displayed_window": False,
            "survivorship_bias_eliminated": False,
            "survivorship_bias_substantially_reduced": True,
            "delisted_price_returns_complete": False,
            "ria_proxy_is_proprietary_mfbr": False,
            "claim_level": "research_proxy_not_crsp_grade",
        },
        "source_urls": {
            "nasdaq_membership": NASDAQ100_HISTORY_PROJECT_URL,
            **STRATEGY_SOURCE_URLS,
        },
        "limitations_en": [
            "Nasdaq-100 membership is community-reconstructed, not an official licensed history.",
            "Yahoo data can omit delisting returns and some renamed securities.",
            "The active sleeve uses price factors only; point-in-time fundamentals are not yet included.",
            "The RIA-inspired track is a public proxy, not RIA's proprietary MFBR or audited client performance.",
            "One ten-year window is evidence, not a reliable forecast of future excess return.",
        ],
        "limitations_zh": [
            "Nasdaq-100 历史成分来自社区重建，不是官方授权的完整历史数据库。",
            "Yahoo 数据可能遗漏退市收益和部分更名证券。",
            "主动选股部分目前只用价格因子，尚未加入逐时点基本面。",
            "RIA 启发轨道只是公开代理，不是 RIA 的专有 MFBR 或经审计客户业绩。",
            "单一十年区间只能提供证据，不能可靠预测未来超额收益。",
        ],
    }


def _load_nasdaq_history_year(
    year: int,
    *,
    cache_root: Path,
    source_commit: str,
) -> str:
    path = cache_root / f"nasdaq100-{year}-{source_commit[:12]}.yaml"
    if path.exists():
        return path.read_text(encoding="utf-8")

    import httpx

    url = NASDAQ100_HISTORY_RAW_URL.format(year=year).replace(
        NASDAQ100_HISTORY_COMMIT, source_commit
    )
    response = httpx.get(url, follow_redirects=True, timeout=60)
    response.raise_for_status()
    path.write_text(response.text, encoding="utf-8")
    return response.text


def _targets_as_of(
    prices: pd.DataFrame,
    dt: pd.Timestamp,
    nasdaq_universe: HistoricalUniverse,
    *,
    sp500_universe: HistoricalUniverse | None,
    active_count: int,
    volatility_target: float,
) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    history = prices.loc[:dt]
    members = nasdaq_universe.members_as_of(dt)
    selected, active_scores = _select_active_sleeve(
        history,
        members,
        count=active_count,
    )
    regime, regime_evidence = _classify_dynamic_regime(history, members)
    dynamic_allocation = DYNAMIC_ALLOCATIONS[regime]
    ria_exposure, ria_evidence = _ria_public_proxy_exposure(
        history,
        dt,
        sp500_universe=sp500_universe,
    )
    qqq_weight, qqq_volatility = _volatility_control_weight(
        history["QQQ"],
        target=volatility_target,
    )

    targets = {
        "qqq_passive": {"QQQ": 1.0},
        "static_index_core": _expand_active_allocation(
            STATIC_CORE_ALLOCATION,
            selected,
        ),
        "dynamic_qqq_challenger": _expand_active_allocation(
            dynamic_allocation,
            selected,
        ),
        "ria_public_proxy": {"SPY": ria_exposure, "BIL": 1.0 - ria_exposure},
        "qqq_volatility_control": {
            "QQQ": qqq_weight,
            "BIL": 1.0 - qqq_weight,
        },
    }
    return targets, {
        "date": _date_string(dt),
        "dynamic_regime": regime,
        "dynamic_regime_evidence": regime_evidence,
        "active_selection": selected,
        "active_scores": active_scores,
        "ria_proxy": ria_evidence,
        "qqq_realized_volatility": qqq_volatility,
        "qqq_volatility_control_weight": qqq_weight,
    }


def _select_active_sleeve(
    history: pd.DataFrame,
    members: Iterable[str],
    *,
    count: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    last_date = pd.Timestamp(history.index[-1]).tz_localize(None)
    for ticker in sorted(set(members)):
        if ticker not in history:
            continue
        close = history[ticker].dropna()
        if len(close) < 253:
            continue
        latest_date = pd.Timestamp(close.index[-1]).tz_localize(None)
        if (last_date - latest_date).days > 7:
            continue
        trailing = close.tail(253)
        daily_returns = trailing.pct_change(fill_method=None).dropna()
        if len(daily_returns) < 200:
            continue
        momentum_12_2 = float(trailing.iloc[-22] / trailing.iloc[0] - 1.0)
        trend_200 = float(trailing.iloc[-1] / trailing.tail(200).mean() - 1.0)
        realized_volatility = float(
            daily_returns.tail(126).std(ddof=0) * math.sqrt(252.0)
        )
        running_max = trailing.cummax()
        max_drawdown = float((trailing / running_max - 1.0).min())
        rows.append(
            {
                "ticker": ticker,
                "momentum_12_2": momentum_12_2,
                "trend_200": trend_200,
                "realized_volatility": realized_volatility,
                "max_drawdown": max_drawdown,
            }
        )

    if not rows:
        return [], []
    frame = pd.DataFrame(rows).set_index("ticker")
    frame["momentum_rank"] = frame["momentum_12_2"].rank(pct=True)
    frame["trend_rank"] = frame["trend_200"].rank(pct=True)
    frame["low_volatility_rank"] = frame["realized_volatility"].rank(
        pct=True, ascending=False
    )
    frame["drawdown_rank"] = frame["max_drawdown"].rank(pct=True)
    frame["score"] = (
        0.40 * frame["momentum_rank"]
        + 0.25 * frame["trend_rank"]
        + 0.20 * frame["low_volatility_rank"]
        + 0.15 * frame["drawdown_rank"]
    )
    frame = frame.sort_values(["score", "momentum_12_2"], ascending=False)
    selected_frame = frame.head(max(1, count))
    selected = selected_frame.index.tolist()
    audit = [
        {
            "ticker": ticker,
            "score": float(row.score),
            "momentum_12_2": float(row.momentum_12_2),
            "trend_200": float(row.trend_200),
            "realized_volatility": float(row.realized_volatility),
            "max_drawdown": float(row.max_drawdown),
        }
        for ticker, row in selected_frame.iterrows()
    ]
    return selected, audit


def _classify_dynamic_regime(
    history: pd.DataFrame,
    members: Iterable[str],
) -> tuple[str, dict[str, Any]]:
    spy = history["SPY"].dropna()
    qqq = history["QQQ"].dropna()
    if len(spy) < 200 or len(qqq) < 200:
        return "defensive", {
            "reason": "insufficient_warmup",
            "spy_above_200d": False,
            "qqq_above_200d": False,
            "qqq_50d_above_200d": False,
            "breadth_above_200d": 0.0,
            "qqq_realized_volatility": None,
        }

    spy_above = bool(spy.iloc[-1] > spy.tail(200).mean())
    qqq_above = bool(qqq.iloc[-1] > qqq.tail(200).mean())
    qqq_fast_above = bool(qqq.tail(50).mean() > qqq.tail(200).mean())
    qqq_volatility = float(
        qqq.pct_change(fill_method=None).tail(63).std(ddof=0) * math.sqrt(252.0)
    )
    breadth = _breadth_above_moving_average(history, members, lookback=200)

    if (
        spy_above
        and qqq_above
        and qqq_fast_above
        and breadth >= 0.55
        and qqq_volatility <= 0.30
    ):
        regime = "risk_on"
    elif (
        not spy_above
        or not qqq_above
        or breadth < 0.40
        or qqq_volatility > 0.35
    ):
        regime = "defensive"
    else:
        regime = "neutral"
    return regime, {
        "spy_above_200d": spy_above,
        "qqq_above_200d": qqq_above,
        "qqq_50d_above_200d": qqq_fast_above,
        "breadth_above_200d": breadth,
        "qqq_realized_volatility": qqq_volatility,
    }


def _ria_public_proxy_exposure(
    history: pd.DataFrame,
    dt: pd.Timestamp,
    *,
    sp500_universe: HistoricalUniverse | None,
) -> tuple[float, dict[str, Any]]:
    spy = history["SPY"].dropna()
    weekly = spy.resample("W-FRI").last().pct_change(fill_method=None).dropna()
    recent = weekly.tail(20)
    positive_ratio = float((recent > 0.0).mean()) if len(recent) else 0.0
    prior = weekly.iloc[-24:-4]
    prior_ratio = float((prior > 0.0).mean()) if len(prior) else positive_ratio
    direction = positive_ratio - prior_ratio
    spy_above_200d = bool(
        len(spy) >= 200 and spy.iloc[-1] > spy.tail(200).mean()
    )
    if sp500_universe is not None:
        breadth_members = sp500_universe.members_as_of(dt)
        breadth = _breadth_above_moving_average(
            history,
            breadth_members,
            lookback=200,
        )
    else:
        breadth = float("nan")

    score = positive_ratio
    if not math.isnan(breadth):
        score = 0.5 * positive_ratio + 0.5 * breadth
    if score >= 0.60 and direction >= 0.0:
        exposure = 1.0
    elif score < 0.40:
        exposure = 0.50
    else:
        exposure = 0.75
    if not spy_above_200d:
        exposure = min(exposure, 0.75)
    return exposure, {
        "is_proprietary_mfbr": False,
        "label_en": "RIA-inspired public proxy, not MFBR",
        "label_zh": "RIA 启发的公开代理，并非 MFBR",
        "positive_week_ratio_20w": positive_ratio,
        "positive_week_ratio_direction": direction,
        "sp500_breadth_above_200d": (
            None if math.isnan(breadth) else breadth
        ),
        "spy_above_200d": spy_above_200d,
        "equity_exposure": exposure,
    }


def _volatility_control_weight(
    close: pd.Series,
    *,
    target: float,
) -> tuple[float, float | None]:
    returns = close.dropna().pct_change(fill_method=None).dropna().tail(63)
    if len(returns) < 42:
        return 0.75, None
    realized = float(returns.std(ddof=0) * math.sqrt(252.0))
    if realized <= 0:
        return 1.0, realized
    return float(np.clip(target / realized, 0.40, 1.0)), realized


def _breadth_above_moving_average(
    history: pd.DataFrame,
    members: Iterable[str],
    *,
    lookback: int,
) -> float:
    observations: list[bool] = []
    last_date = pd.Timestamp(history.index[-1]).tz_localize(None)
    for ticker in members:
        if ticker not in history:
            continue
        close = history[ticker].dropna()
        if len(close) < lookback:
            continue
        latest_date = pd.Timestamp(close.index[-1]).tz_localize(None)
        if (last_date - latest_date).days > 7:
            continue
        observations.append(bool(close.iloc[-1] > close.tail(lookback).mean()))
    return float(np.mean(observations)) if observations else 0.0


def _expand_active_allocation(
    allocation: dict[str, float],
    selected: list[str],
) -> dict[str, float]:
    weights = {
        ticker: float(weight)
        for ticker, weight in allocation.items()
        if ticker != "ACTIVE" and weight > 0.0
    }
    active_weight = float(allocation.get("ACTIVE", 0.0))
    if selected and active_weight > 0.0:
        equal_weight = active_weight / len(selected)
        for ticker in selected:
            weights[ticker] = weights.get(ticker, 0.0) + equal_weight
    else:
        weights["BIL"] = weights.get("BIL", 0.0) + active_weight
    return _normalize_weights(weights)


def _relative_risk_metrics(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    metrics: dict[str, float],
) -> dict[str, float]:
    returns = returns.reset_index(drop=True).fillna(0.0)
    benchmark = benchmark_returns.reset_index(drop=True).fillna(0.0)
    count = min(len(returns), len(benchmark))
    returns = returns.iloc[:count]
    benchmark = benchmark.iloc[:count]
    excess = returns - benchmark
    tracking_error = float(excess.std(ddof=0) * math.sqrt(252.0))
    information_ratio = (
        float(excess.mean() * 252.0 / tracking_error)
        if tracking_error > 0
        else 0.0
    )
    downside = returns[returns < 0.0]
    downside_deviation = float(
        np.sqrt(np.mean(np.square(downside))) * math.sqrt(252.0)
    ) if len(downside) else 0.0
    sortino = (
        float(returns.mean() * 252.0 / downside_deviation)
        if downside_deviation > 0
        else 0.0
    )
    max_drawdown = abs(float(metrics["max_drawdown"]))
    calmar = float(metrics["cagr"] / max_drawdown) if max_drawdown > 0 else 0.0
    upside = benchmark > 0.0
    downside_days = benchmark < 0.0
    upside_capture = _capture_ratio(returns[upside], benchmark[upside])
    downside_capture = _capture_ratio(
        returns[downside_days],
        benchmark[downside_days],
    )
    return {
        "sortino": sortino,
        "calmar": calmar,
        "tracking_error_vs_qqq": tracking_error,
        "information_ratio_vs_qqq": information_ratio,
        "upside_capture_vs_qqq": upside_capture,
        "downside_capture_vs_qqq": downside_capture,
    }


def _capture_ratio(returns: pd.Series, benchmark: pd.Series) -> float:
    denominator = float(benchmark.sum())
    if denominator == 0.0:
        return 0.0
    return float(returns.sum() / denominator)


def _portfolio_return(weights: dict[str, float], returns: pd.Series) -> float:
    return float(
        sum(
            weight * float(returns.get(ticker, 0.0))
            for ticker, weight in weights.items()
            if pd.notna(returns.get(ticker, np.nan))
        )
    )


def _turnover(current: dict[str, float], desired: dict[str, float]) -> float:
    return 0.5 * sum(
        abs(desired.get(ticker, 0.0) - current.get(ticker, 0.0))
        for ticker in set(current) | set(desired)
    )


def _rebalance_record(
    dt: pd.Timestamp,
    weights: dict[str, float],
    audit: dict[str, Any],
) -> dict[str, Any]:
    return {
        "date": _date_string(dt),
        "weights": {
            ticker: float(weight)
            for ticker, weight in sorted(
                weights.items(), key=lambda item: item[1], reverse=True
            )
            if weight > 0.0001
        },
        "dynamic_regime": audit["dynamic_regime"],
        "active_selection": audit["active_selection"],
        "ria_equity_exposure": audit["ria_proxy"]["equity_exposure"],
        "qqq_volatility_control_weight": audit["qqq_volatility_control_weight"],
    }


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    cleaned = {
        ticker: max(0.0, float(weight))
        for ticker, weight in weights.items()
        if float(weight) > 0.0
    }
    total = sum(cleaned.values())
    if total <= 0.0:
        return {"BIL": 1.0}
    return {ticker: weight / total for ticker, weight in cleaned.items()}


def _yahoo_symbol(value: Any) -> str:
    return str(value).strip().upper().replace(".", "-")


def _date_string(value: Any) -> str:
    return str(pd.Timestamp(value).date())
