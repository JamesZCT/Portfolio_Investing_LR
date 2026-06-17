from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SectorSignal:
    sector: str
    etf: str
    price: float
    ma: float
    std: float
    z: float
    pct_from_ma: float
    status: str
    trend_state: str = "unknown"
    trend_ma: float = 0.0
    momentum: float = 0.0
    realized_vol: float = 0.0


@dataclass
class MarketRegime:
    benchmark: str
    price: float
    trend_ma: float
    trend_state: str
    z: float
    momentum: float
    realized_vol: float
    drawdown: float


@dataclass
class RiskPrediction:
    ticker: str
    risk_probability: float
    risk_level: str
    model_version: str
    features: dict[str, float] = field(default_factory=dict)


@dataclass
class TradeSuggestion:
    ticker: str
    action: str
    delta_weight: float
    reason: str
    rule_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
