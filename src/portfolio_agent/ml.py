from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import AppConfig
from .indicators import moving_average, zscore
from .models import RiskPrediction


FEATURE_COLUMNS = [
    "ret_21",
    "ret_63",
    "ret_126",
    "ret_252",
    "ma_gap",
    "z_60",
    "vol_21",
    "vol_63",
    "drawdown_252",
]


def build_risk_predictions(prices: pd.DataFrame, tickers: list[str], config: AppConfig) -> dict[str, RiskPrediction]:
    if not config.ml.enabled:
        return {}

    frames: list[pd.DataFrame] = []
    latest_rows: dict[str, pd.Series] = {}

    for ticker in tickers:
        if ticker == "CASH" or ticker not in prices.columns:
            continue
        features = _build_feature_frame(prices[ticker].dropna(), config)
        if features.empty:
            continue
        features = features.replace([np.inf, -np.inf], np.nan)

        latest = features[FEATURE_COLUMNS].dropna().tail(1)
        if not latest.empty:
            latest_rows[ticker] = latest.iloc[0]

        train = features.dropna(subset=FEATURE_COLUMNS + ["target"])
        if not train.empty:
            frames.append(train)

    if not frames or not latest_rows:
        return {}

    training = pd.concat(frames, ignore_index=True)
    if len(training) < config.ml.min_training_rows:
        return _base_rate_predictions(training, latest_rows, config)

    x_train = training[FEATURE_COLUMNS].to_numpy(dtype=float)
    y_train = training["target"].to_numpy(dtype=float)
    finite_mask = np.isfinite(x_train).all(axis=1) & np.isfinite(y_train)
    x_train = x_train[finite_mask]
    y_train = y_train[finite_mask]
    if len(y_train) < config.ml.min_training_rows:
        return _base_rate_predictions(training, latest_rows, config)

    model = _fit_logistic_model(
        x_train,
        y_train,
        epochs=config.ml.epochs,
        learning_rate=config.ml.learning_rate,
    )

    predictions: dict[str, RiskPrediction] = {}
    for ticker, row in latest_rows.items():
        prob = _predict_probability(model, row.to_numpy(dtype=float))
        predictions[ticker] = RiskPrediction(
            ticker=ticker,
            risk_probability=prob,
            risk_level=_risk_level(prob, config),
            model_version=config.ml.model_version,
            features={name: float(row[name]) for name in FEATURE_COLUMNS},
        )
    return predictions


def _build_feature_frame(series: pd.Series, config: AppConfig) -> pd.DataFrame:
    if series.empty:
        return pd.DataFrame()

    frame = pd.DataFrame(index=series.index)
    frame["price"] = series
    frame["ret_21"] = series.pct_change(21)
    frame["ret_63"] = series.pct_change(63)
    frame["ret_126"] = series.pct_change(126)
    frame["ret_252"] = series.pct_change(252)

    ma = moving_average(series, config.indicators.trend_ma_window)
    frame["ma_gap"] = (series / ma) - 1.0
    frame["z_60"] = zscore(series, config.indicators.z_window)

    daily_returns = series.pct_change()
    frame["vol_21"] = daily_returns.rolling(21, min_periods=21).std(ddof=0) * math.sqrt(252.0)
    frame["vol_63"] = daily_returns.rolling(63, min_periods=63).std(ddof=0) * math.sqrt(252.0)
    trailing_high = series.rolling(252, min_periods=63).max()
    frame["drawdown_252"] = (series / trailing_high) - 1.0

    future_return = series.shift(-config.ml.horizon_days) / series - 1.0
    frame["target"] = (future_return <= -config.ml.risk_event_threshold).astype(float)
    frame.loc[future_return.isna(), "target"] = np.nan
    return frame


def _fit_logistic_model(x_raw: np.ndarray, y: np.ndarray, epochs: int, learning_rate: float) -> dict[str, np.ndarray | float]:
    means = x_raw.mean(axis=0)
    stds = x_raw.std(axis=0)
    stds = np.where(stds == 0.0, 1.0, stds)
    x = np.nan_to_num(np.clip((x_raw - means) / stds, -8.0, 8.0), nan=0.0, posinf=8.0, neginf=-8.0)

    weights = np.zeros(x.shape[1], dtype=float)
    bias = _logit(float(np.clip(y.mean(), 0.01, 0.99)))

    for _ in range(max(1, epochs)):
        logits = np.sum(x * weights, axis=1) + bias
        preds = 1.0 / (1.0 + np.exp(-np.clip(logits, -35, 35)))
        error = preds - y
        weights -= learning_rate * np.mean(x * error[:, np.newaxis], axis=0)
        weights = np.clip(weights, -10.0, 10.0)
        bias -= learning_rate * float(error.mean())
        bias = max(-10.0, min(10.0, bias))

    return {"weights": weights, "bias": float(bias), "means": means, "stds": stds}


def _predict_probability(model: dict[str, np.ndarray | float], row: np.ndarray) -> float:
    weights = model["weights"]
    means = model["means"]
    stds = model["stds"]
    bias = float(model["bias"])
    assert isinstance(weights, np.ndarray)
    assert isinstance(means, np.ndarray)
    assert isinstance(stds, np.ndarray)
    x = np.nan_to_num(np.clip((row - means) / stds, -8.0, 8.0), nan=0.0, posinf=8.0, neginf=-8.0)
    logit = float(np.sum(x * weights) + bias)
    return float(1.0 / (1.0 + math.exp(-max(-35.0, min(35.0, logit)))))


def _base_rate_predictions(
    training: pd.DataFrame,
    latest_rows: dict[str, pd.Series],
    config: AppConfig,
) -> dict[str, RiskPrediction]:
    base_rate = 0.0 if training.empty else float(training["target"].mean())
    return {
        ticker: RiskPrediction(
            ticker=ticker,
            risk_probability=base_rate,
            risk_level=_risk_level(base_rate, config),
            model_version=f"{config.ml.model_version}_base_rate",
            features={name: float(row[name]) for name in FEATURE_COLUMNS},
        )
        for ticker, row in latest_rows.items()
    }


def _risk_level(probability: float, config: AppConfig) -> str:
    if probability >= config.ml.high_risk_probability:
        return "high"
    if probability >= config.ml.medium_risk_probability:
        return "medium"
    return "low"


def _logit(probability: float) -> float:
    return math.log(probability / (1.0 - probability))
