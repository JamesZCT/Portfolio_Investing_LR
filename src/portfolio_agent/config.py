from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class IndicatorConfig:
    ma_window: int = 200
    trend_ma_window: int = 200
    std_window: int = 60
    z_window: int = 60
    moderate_z: float = 2.0
    extreme_z: float = 3.0
    momentum_lookback_days: int = 126
    volatility_window: int = 21
    trailing_high_lookback_days: int = 252


@dataclass
class RuleConfig:
    min_history_days: int = 260
    max_trim_fraction_per_position: float = 0.25
    min_trade_weight: float = 0.005
    overweight_trigger: float = 0.03
    underweight_trigger: float = 0.03
    max_single_position_weight: float = 0.15
    max_sector_weight: float = 0.35
    trend_filter_enabled: bool = True
    bear_market_trim_fraction: float = 0.15
    allow_countertrend_buys: bool = False
    loss_block_pct: float = 0.10
    min_cash_weight: float = 0.02
    defensive_cash_weight: float = 0.10
    stop_loss_pct: float = 0.12
    stop_trim_fraction: float = 0.5
    trailing_stop_pct: float = 0.15
    trailing_stop_trim_fraction: float = 0.33


@dataclass
class UniverseConfig:
    benchmark: str
    sector_etfs: dict[str, str]
    positions: dict[str, float]
    target_weights: dict[str, float]
    ticker_sector: dict[str, str]
    entry_prices: dict[str, float]


@dataclass
class NotificationConfig:
    enabled: bool = False
    dry_run: bool = True
    slack_webhook_env: str = "SLACK_WEBHOOK_URL"
    telegram_bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    telegram_chat_id_env: str = "TELEGRAM_CHAT_ID"
    smtp_host_env: str = "SMTP_HOST"
    smtp_port_env: str = "SMTP_PORT"
    smtp_user_env: str = "SMTP_USER"
    smtp_pass_env: str = "SMTP_PASS"
    email_from_env: str = "EMAIL_FROM"
    email_to_env: str = "EMAIL_TO"


@dataclass
class MLConfig:
    enabled: bool = True
    horizon_days: int = 21
    risk_event_threshold: float = 0.08
    min_training_rows: int = 120
    epochs: int = 400
    learning_rate: float = 0.08
    high_risk_probability: float = 0.65
    medium_risk_probability: float = 0.45
    high_risk_trim_fraction: float = 0.10
    model_version: str = "logistic_price_risk_v1"


@dataclass
class ExecutionConfig:
    mode: str = "sandbox"
    allow_live_brokerage: bool = False


@dataclass
class AppConfig:
    indicators: IndicatorConfig
    rules: RuleConfig
    universe: UniverseConfig
    notifications: NotificationConfig
    ml: MLConfig
    execution: ExecutionConfig


def _require(data: dict[str, Any], key: str) -> Any:
    if key not in data:
        raise ValueError(f"Missing required config key: {key}")
    return data[key]


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError("Config file must contain a YAML mapping at the top level")

    indicators_raw = raw.get("indicators", {})
    rules_raw = raw.get("rules", {})
    universe_raw = _require(raw, "universe")
    notifications_raw = raw.get("notifications", {})
    ml_raw = raw.get("ml", {})
    execution_raw = raw.get("execution", {})

    indicators = IndicatorConfig(
        ma_window=int(indicators_raw.get("ma_window", 200)),
        trend_ma_window=int(indicators_raw.get("trend_ma_window", indicators_raw.get("ma_window", 200))),
        std_window=int(indicators_raw.get("std_window", 60)),
        z_window=int(indicators_raw.get("z_window", 60)),
        moderate_z=float(indicators_raw.get("moderate_z", 2.0)),
        extreme_z=float(indicators_raw.get("extreme_z", 3.0)),
        momentum_lookback_days=int(indicators_raw.get("momentum_lookback_days", 126)),
        volatility_window=int(indicators_raw.get("volatility_window", 21)),
        trailing_high_lookback_days=int(indicators_raw.get("trailing_high_lookback_days", 252)),
    )
    rules = RuleConfig(
        min_history_days=int(rules_raw.get("min_history_days", 260)),
        max_trim_fraction_per_position=float(
            rules_raw.get("max_trim_fraction_per_position", 0.25)
        ),
        min_trade_weight=float(rules_raw.get("min_trade_weight", 0.005)),
        overweight_trigger=float(rules_raw.get("overweight_trigger", 0.03)),
        underweight_trigger=float(rules_raw.get("underweight_trigger", 0.03)),
        max_single_position_weight=float(rules_raw.get("max_single_position_weight", 0.15)),
        max_sector_weight=float(rules_raw.get("max_sector_weight", 0.35)),
        trend_filter_enabled=bool(rules_raw.get("trend_filter_enabled", True)),
        bear_market_trim_fraction=float(rules_raw.get("bear_market_trim_fraction", 0.15)),
        allow_countertrend_buys=bool(rules_raw.get("allow_countertrend_buys", False)),
        loss_block_pct=float(rules_raw.get("loss_block_pct", 0.10)),
        min_cash_weight=float(rules_raw.get("min_cash_weight", 0.02)),
        defensive_cash_weight=float(rules_raw.get("defensive_cash_weight", 0.10)),
        stop_loss_pct=float(rules_raw.get("stop_loss_pct", 0.12)),
        stop_trim_fraction=float(rules_raw.get("stop_trim_fraction", 0.5)),
        trailing_stop_pct=float(rules_raw.get("trailing_stop_pct", 0.15)),
        trailing_stop_trim_fraction=float(rules_raw.get("trailing_stop_trim_fraction", 0.33)),
    )

    universe = UniverseConfig(
        benchmark=str(_require(universe_raw, "benchmark")),
        sector_etfs=dict(_require(universe_raw, "sector_etfs")),
        positions={k: float(v) for k, v in dict(_require(universe_raw, "positions")).items()},
        target_weights={
            k: float(v) for k, v in dict(_require(universe_raw, "target_weights")).items()
        },
        ticker_sector=dict(_require(universe_raw, "ticker_sector")),
        entry_prices={k: float(v) for k, v in dict(universe_raw.get("entry_prices", {})).items()},
    )

    notifications = NotificationConfig(
        enabled=bool(notifications_raw.get("enabled", False)),
        dry_run=bool(notifications_raw.get("dry_run", True)),
        slack_webhook_env=str(notifications_raw.get("slack_webhook_env", "SLACK_WEBHOOK_URL")),
        telegram_bot_token_env=str(
            notifications_raw.get("telegram_bot_token_env", "TELEGRAM_BOT_TOKEN")
        ),
        telegram_chat_id_env=str(notifications_raw.get("telegram_chat_id_env", "TELEGRAM_CHAT_ID")),
        smtp_host_env=str(notifications_raw.get("smtp_host_env", "SMTP_HOST")),
        smtp_port_env=str(notifications_raw.get("smtp_port_env", "SMTP_PORT")),
        smtp_user_env=str(notifications_raw.get("smtp_user_env", "SMTP_USER")),
        smtp_pass_env=str(notifications_raw.get("smtp_pass_env", "SMTP_PASS")),
        email_from_env=str(notifications_raw.get("email_from_env", "EMAIL_FROM")),
        email_to_env=str(notifications_raw.get("email_to_env", "EMAIL_TO")),
    )

    ml = MLConfig(
        enabled=bool(ml_raw.get("enabled", True)),
        horizon_days=int(ml_raw.get("horizon_days", 21)),
        risk_event_threshold=float(ml_raw.get("risk_event_threshold", 0.08)),
        min_training_rows=int(ml_raw.get("min_training_rows", 120)),
        epochs=int(ml_raw.get("epochs", 400)),
        learning_rate=float(ml_raw.get("learning_rate", 0.08)),
        high_risk_probability=float(ml_raw.get("high_risk_probability", 0.65)),
        medium_risk_probability=float(ml_raw.get("medium_risk_probability", 0.45)),
        high_risk_trim_fraction=float(ml_raw.get("high_risk_trim_fraction", 0.10)),
        model_version=str(ml_raw.get("model_version", "logistic_price_risk_v1")),
    )

    execution = ExecutionConfig(
        mode=str(execution_raw.get("mode", "sandbox")),
        allow_live_brokerage=bool(execution_raw.get("allow_live_brokerage", False)),
    )

    _validate_weights(universe.positions, "positions")
    _validate_weights(universe.target_weights, "target_weights")
    _validate_config(indicators, rules, universe, ml, execution)

    return AppConfig(
        indicators=indicators,
        rules=rules,
        universe=universe,
        notifications=notifications,
        ml=ml,
        execution=execution,
    )


def _validate_weights(weights: dict[str, float], label: str) -> None:
    total = sum(weights.values())
    if not 0.95 <= total <= 1.05:
        raise ValueError(f"{label} should sum near 1.0; got {total:.4f}")
    if any(v < 0 for v in weights.values()):
        raise ValueError(f"{label} cannot contain negative values")
    if any(v > 1 for v in weights.values()):
        raise ValueError(f"{label} cannot contain weights above 1.0")


def _validate_config(
    indicators: IndicatorConfig,
    rules: RuleConfig,
    universe: UniverseConfig,
    ml: MLConfig,
    execution: ExecutionConfig,
) -> None:
    for name in (
        "ma_window",
        "trend_ma_window",
        "std_window",
        "z_window",
        "momentum_lookback_days",
        "volatility_window",
        "trailing_high_lookback_days",
    ):
        _validate_positive_int(getattr(indicators, name), f"indicators.{name}")

    for name in ("moderate_z", "extreme_z"):
        if getattr(indicators, name) <= 0:
            raise ValueError(f"indicators.{name} must be positive")
    if indicators.extreme_z < indicators.moderate_z:
        raise ValueError("indicators.extreme_z must be greater than or equal to moderate_z")

    _validate_positive_int(rules.min_history_days, "rules.min_history_days")
    for name in (
        "max_trim_fraction_per_position",
        "min_trade_weight",
        "overweight_trigger",
        "underweight_trigger",
        "max_single_position_weight",
        "max_sector_weight",
        "bear_market_trim_fraction",
        "loss_block_pct",
        "min_cash_weight",
        "defensive_cash_weight",
        "stop_loss_pct",
        "stop_trim_fraction",
        "trailing_stop_pct",
        "trailing_stop_trim_fraction",
    ):
        _validate_probability(getattr(rules, name), f"rules.{name}")
    if rules.defensive_cash_weight < rules.min_cash_weight:
        raise ValueError("rules.defensive_cash_weight must be greater than or equal to min_cash_weight")

    non_cash_tickers = {
        ticker
        for ticker in set(universe.positions) | set(universe.target_weights)
        if ticker != "CASH"
    }
    missing_sector = sorted(ticker for ticker in non_cash_tickers if ticker not in universe.ticker_sector)
    if missing_sector:
        raise ValueError(f"ticker_sector missing mappings for: {', '.join(missing_sector)}")

    missing_sector_etfs = sorted(
        sector for sector in set(universe.ticker_sector.values()) if sector not in universe.sector_etfs
    )
    if missing_sector_etfs:
        raise ValueError(f"sector_etfs missing proxies for sectors: {', '.join(missing_sector_etfs)}")

    _validate_positive_int(ml.horizon_days, "ml.horizon_days")
    _validate_positive_int(ml.min_training_rows, "ml.min_training_rows")
    _validate_positive_int(ml.epochs, "ml.epochs")
    if ml.learning_rate <= 0:
        raise ValueError("ml.learning_rate must be positive")
    for name in ("risk_event_threshold", "high_risk_probability", "medium_risk_probability", "high_risk_trim_fraction"):
        _validate_probability(getattr(ml, name), f"ml.{name}")
    if ml.high_risk_probability < ml.medium_risk_probability:
        raise ValueError("ml.high_risk_probability must be greater than or equal to medium_risk_probability")

    if execution.mode not in {"sandbox"}:
        raise ValueError("execution.mode must be sandbox")
    if execution.allow_live_brokerage:
        raise ValueError("execution.allow_live_brokerage must remain false")


def _validate_positive_int(value: int, label: str) -> None:
    if value <= 0:
        raise ValueError(f"{label} must be positive")


def _validate_probability(value: float, label: str) -> None:
    if not 0 <= value <= 1:
        raise ValueError(f"{label} must be between 0 and 1")
