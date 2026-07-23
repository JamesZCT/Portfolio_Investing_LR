from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd
from skfolio import RiskMeasure
from skfolio.moments import ShrunkCovariance, ShrunkMu
from skfolio.optimization import MeanRisk, ObjectiveFunction, RiskBudgeting
from skfolio.prior import EmpiricalPrior

from .config import AppConfig, OptimizationProfileConfig


OBJECTIVE_LABELS = {
    "min_cvar": {
        "en": "Minimize expected tail loss (CVaR)",
        "zh": "最小化极端下跌期望损失（CVaR）",
    },
    "risk_budgeting": {
        "en": "Spread risk contributions across assets",
        "zh": "分散各资产对整体风险的贡献",
    },
    "max_sharpe": {
        "en": "Maximize estimated return per unit of volatility",
        "zh": "最大化每单位波动率的估计收益",
    },
}


def build_optimization_payload(config: AppConfig, prices: pd.DataFrame) -> dict[str, Any]:
    optimization = config.optimization
    if not optimization.enabled:
        return {
            "status": "disabled",
            "profiles": [],
            "methodology": "Portfolio optimization is disabled in this configuration.",
        }

    profiles = [
        optimize_profile(config, profile_id, profile, prices)
        for profile_id, profile in (optimization.profiles or {}).items()
    ]
    return {
        "status": "available" if any(item["status"] == "optimized" for item in profiles) else "fallback",
        "data_as_of": _date_string(prices.index.max()) if not prices.empty else None,
        "lookback_days": optimization.lookback_days,
        "min_history_days": optimization.min_history_days,
        "transaction_cost_bps": optimization.transaction_cost_bps,
        "methodology": (
            "Long-only constrained research portfolios built with skfolio. "
            "Metrics are trailing-sample diagnostics, not promised future returns."
        ),
        "methodology_zh": (
            "使用 skfolio 构建的只做多约束研究组合。指标是历史样本诊断，"
            "不是未来收益承诺。"
        ),
        "profiles": profiles,
    }


def optimize_profile(
    config: AppConfig,
    profile_id: str,
    profile: OptimizationProfileConfig,
    prices: pd.DataFrame,
) -> dict[str, Any]:
    requested_assets = list(dict.fromkeys(profile.assets))
    eligible = [
        ticker
        for ticker in requested_assets
        if ticker in prices.columns
        and prices[ticker].notna().sum() >= config.optimization.min_history_days
    ]
    missing = sorted(set(requested_assets) - set(eligible))
    frame = prices[eligible].tail(config.optimization.lookback_days).ffill().dropna()
    returns = frame.pct_change(fill_method=None).dropna()

    if len(eligible) < 2 or len(returns) < config.optimization.min_history_days - 1:
        return _fallback_profile(
            config,
            profile_id,
            profile,
            returns,
            eligible,
            missing,
            "Insufficient common price history for constrained optimization.",
        )

    max_weights = _max_weights(config, profile, eligible)
    groups = {
        ticker: [(config.optimization.asset_groups or {}).get(ticker, "Other")]
        for ticker in eligible
    }
    group_constraints = _feasible_group_constraints(
        groups,
        max_weights,
        profile.max_group_weight,
    )

    try:
        model = _build_model(profile, max_weights, groups, group_constraints)
        model.fit(returns)
        raw_weights = pd.Series(model.weights_, index=eligible, dtype=float).clip(lower=0.0)
        if float(raw_weights.sum()) <= 0:
            raise ValueError("Optimizer returned zero total weight")
        raw_weights /= float(raw_weights.sum())
        status = "optimized"
        fallback_reason = None
    except Exception as exc:
        return _fallback_profile(
            config,
            profile_id,
            profile,
            returns,
            eligible,
            missing,
            f"Constrained optimizer fallback: {type(exc).__name__}: {exc}",
        )

    return _profile_payload(
        config=config,
        profile_id=profile_id,
        profile=profile,
        returns=returns,
        raw_weights=raw_weights,
        missing=missing,
        group_constraints=group_constraints,
        status=status,
        fallback_reason=fallback_reason,
    )


def _build_model(
    profile: OptimizationProfileConfig,
    max_weights: dict[str, float],
    groups: dict[str, list[str]],
    group_constraints: list[str],
):
    common = {
        "min_weights": 0.0,
        "max_weights": max_weights,
        "groups": groups,
        "linear_constraints": group_constraints,
    }
    if profile.objective == "min_cvar":
        return MeanRisk(
            objective_function=ObjectiveFunction.MINIMIZE_RISK,
            risk_measure=RiskMeasure.CVAR,
            **common,
        )
    if profile.objective == "max_sharpe":
        return MeanRisk(
            objective_function=ObjectiveFunction.MAXIMIZE_RATIO,
            risk_measure=RiskMeasure.STANDARD_DEVIATION,
            prior_estimator=EmpiricalPrior(
                mu_estimator=ShrunkMu(),
                covariance_estimator=ShrunkCovariance(),
            ),
            **common,
        )
    return RiskBudgeting(
        risk_measure=RiskMeasure.VARIANCE,
        **common,
    )


def _fallback_profile(
    config: AppConfig,
    profile_id: str,
    profile: OptimizationProfileConfig,
    returns: pd.DataFrame,
    eligible: list[str],
    missing: list[str],
    reason: str,
) -> dict[str, Any]:
    if eligible:
        volatility = returns.std().replace(0.0, np.nan) if not returns.empty else pd.Series(dtype=float)
        inverse = (1.0 / volatility).replace([np.inf, -np.inf], np.nan).dropna()
        if inverse.empty:
            raw_weights = pd.Series(1.0 / len(eligible), index=eligible)
        else:
            raw_weights = inverse.reindex(eligible).fillna(0.0)
            raw_weights /= float(raw_weights.sum())
        raw_weights = _cap_and_normalize(
            raw_weights,
            _max_weights(config, profile, eligible),
        )
    else:
        raw_weights = pd.Series(dtype=float)
    return _profile_payload(
        config=config,
        profile_id=profile_id,
        profile=profile,
        returns=returns,
        raw_weights=raw_weights,
        missing=missing,
        group_constraints=[],
        status="fallback",
        fallback_reason=reason,
    )


def _profile_payload(
    *,
    config: AppConfig,
    profile_id: str,
    profile: OptimizationProfileConfig,
    returns: pd.DataFrame,
    raw_weights: pd.Series,
    missing: list[str],
    group_constraints: list[str],
    status: str,
    fallback_reason: str | None,
) -> dict[str, Any]:
    investable = max(0.0, 1.0 - profile.cash_weight)
    target = {ticker: float(weight * investable) for ticker, weight in raw_weights.items()}
    if profile.cash_weight > 0:
        target["CASH"] = profile.cash_weight
    current = dict(config.universe.positions)
    all_tickers = sorted(set(current) | set(target), key=lambda ticker: (ticker != "CASH", ticker))
    rows = []
    for priority, ticker in enumerate(
        sorted(all_tickers, key=lambda name: abs(target.get(name, 0.0) - current.get(name, 0.0)), reverse=True),
        start=1,
    ):
        current_weight = float(current.get(ticker, 0.0))
        target_weight = float(target.get(ticker, 0.0))
        delta = target_weight - current_weight
        action = "ADD" if delta > 0.005 else "TRIM" if delta < -0.005 else "HOLD"
        reason_en, reason_zh = _allocation_reason(
            ticker,
            action,
            profile,
            config,
        )
        rows.append(
            {
                "priority": priority,
                "ticker": ticker,
                "group": (config.optimization.asset_groups or {}).get(ticker, "Cash" if ticker == "CASH" else "Other"),
                "asset_type": (config.optimization.asset_types or {}).get(
                    ticker, "cash" if ticker == "CASH" else "stock"
                ),
                "action": action,
                "current_weight": current_weight,
                "target_weight": target_weight,
                "delta_weight": delta,
                "reason_en": reason_en,
                "reason_zh": reason_zh,
                "rule_ids": [
                    f"OPT_{profile.objective.upper()}",
                    "LONG_ONLY",
                    "POSITION_CAP",
                    "TRANSACTION_COST_REVIEW",
                ],
            }
        )

    diagnostics = _diagnostics(returns, raw_weights * investable)
    turnover = 0.5 * sum(
        abs(target.get(ticker, 0.0) - current.get(ticker, 0.0))
        for ticker in set(target) | set(current)
    )
    diagnostics["turnover"] = float(turnover)
    diagnostics["estimated_transaction_cost"] = float(
        turnover * config.optimization.transaction_cost_bps / 10_000.0
    )

    labels = OBJECTIVE_LABELS[profile.objective]
    return {
        "id": profile_id,
        "name_en": profile.name_en,
        "name_zh": profile.name_zh,
        "risk_level": profile.risk_level,
        "objective": profile.objective,
        "objective_en": labels["en"],
        "objective_zh": labels["zh"],
        "status": status,
        "fallback_reason": fallback_reason,
        "cash_weight": profile.cash_weight,
        "metrics": diagnostics,
        "rows": rows,
        "missing_assets": missing,
        "constraints": {
            "long_only": True,
            "max_single_weight": profile.max_single_weight,
            "max_fund_weight": profile.max_fund_weight,
            "max_group_weight": profile.max_group_weight,
            "group_constraints": group_constraints,
            "leverage": 1.0,
        },
        "evidence": {
            "start_date": _date_string(returns.index.min()) if not returns.empty else None,
            "end_date": _date_string(returns.index.max()) if not returns.empty else None,
            "observations": int(len(returns)),
            "basis_en": "Trailing in-sample daily returns; review with walk-forward validation.",
            "basis_zh": "基于历史样本内日收益；还需结合滚动样本外验证。",
        },
    }


def _max_weights(
    config: AppConfig,
    profile: OptimizationProfileConfig,
    assets: list[str],
) -> dict[str, float]:
    asset_types = config.optimization.asset_types or {}
    return {
        ticker: (
            profile.max_fund_weight
            if asset_types.get(ticker, "stock") in {"fund", "bond", "cash"}
            else profile.max_single_weight
        )
        for ticker in assets
    }


def _cap_and_normalize(
    weights: pd.Series,
    max_weights: dict[str, float],
) -> pd.Series:
    if weights.empty:
        return weights
    caps = pd.Series(max_weights, dtype=float).reindex(weights.index)
    if float(caps.sum()) < 1.0 - 1e-9:
        raise ValueError("Fallback asset caps cannot support a fully invested risk sleeve")
    result = weights.clip(lower=0.0)
    result = result / float(result.sum()) if float(result.sum()) > 0 else pd.Series(
        1.0 / len(result), index=result.index
    )
    for _ in range(100):
        over = result > caps + 1e-12
        if not over.any():
            break
        result[over] = caps[over]
        remaining = 1.0 - float(result[over].sum())
        under = ~over
        if not under.any():
            break
        base = result[under]
        if float(base.sum()) <= 0:
            base = pd.Series(1.0, index=base.index)
        result[under] = base / float(base.sum()) * remaining
    return result / float(result.sum())


def _feasible_group_constraints(
    groups: dict[str, list[str]],
    max_weights: dict[str, float],
    group_cap: float,
) -> list[str]:
    capacity: dict[str, float] = {}
    for ticker, labels in groups.items():
        group = labels[0]
        capacity[group] = capacity.get(group, 0.0) + max_weights[ticker]
    effective_capacity = sum(min(group_cap, value) for value in capacity.values())
    if effective_capacity < 0.999:
        return []
    return [f"{group} <= {group_cap}" for group in sorted(capacity)]


def _diagnostics(returns: pd.DataFrame, weights: pd.Series) -> dict[str, float | None]:
    if returns.empty or weights.empty:
        return {
            "annualized_return": None,
            "annualized_volatility": None,
            "sharpe_ratio": None,
            "max_drawdown": None,
        }
    aligned = returns.reindex(columns=weights.index).fillna(0.0)
    portfolio_returns = aligned @ weights
    annualized_return = float(portfolio_returns.mean() * 252.0)
    annualized_volatility = float(portfolio_returns.std(ddof=1) * np.sqrt(252.0))
    equity = (1.0 + portfolio_returns).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    return {
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "sharpe_ratio": (
            annualized_return / annualized_volatility if annualized_volatility > 0 else None
        ),
        "max_drawdown": float(drawdown.min()),
    }


def _allocation_reason(
    ticker: str,
    action: str,
    profile: OptimizationProfileConfig,
    config: AppConfig,
) -> tuple[str, str]:
    if ticker == "CASH":
        return (
            f"Keep the configured {profile.cash_weight:.0%} liquidity and drawdown buffer.",
            f"保留配置中的 {profile.cash_weight:.0%} 流动性和回撤缓冲。",
        )
    group = (config.optimization.asset_groups or {}).get(ticker, "Other")
    objective = OBJECTIVE_LABELS[profile.objective]
    if action == "ADD":
        return (
            f"Increase toward the constrained {profile.name_en} solution; {objective['en'].lower()}.",
            f"提高至受约束的{profile.name_zh}目标；{objective['zh']}。",
        )
    if action == "TRIM":
        return (
            f"Reduce concentration so the {group} exposure fits the {profile.name_en} risk budget.",
            f"降低集中度，使 {group} 敞口符合{profile.name_zh}的风险预算。",
        )
    return (
        "Current weight is already close to the constrained target.",
        "当前权重已接近受约束的目标。",
    )


def _date_string(value: Any) -> str:
    return str(pd.Timestamp(value).date())
