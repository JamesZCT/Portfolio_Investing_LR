from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import TradeSuggestion


@dataclass
class TradeOrder:
    ticker: str
    side: str
    target_weight_delta: float
    reason: str
    rule_ids: tuple[str, ...]


@dataclass
class ExecutionResult:
    ticker: str
    side: str
    target_weight_delta: float
    status: str
    message: str
    timestamp: str


class ExecutionAdapter:
    def execute(self, orders: list[TradeOrder]) -> list[ExecutionResult]:
        raise NotImplementedError


class SandboxExecutionAdapter(ExecutionAdapter):
    def execute(self, orders: list[TradeOrder]) -> list[ExecutionResult]:
        now = datetime.utcnow().isoformat(timespec="seconds")
        return [
            ExecutionResult(
                ticker=order.ticker,
                side=order.side,
                target_weight_delta=order.target_weight_delta,
                status="simulated",
                message="sandbox only; no brokerage order was placed",
                timestamp=now,
            )
            for order in orders
        ]


class LiveBrokerageAdapter(ExecutionAdapter):
    def execute(self, orders: list[TradeOrder]) -> list[ExecutionResult]:
        raise RuntimeError(
            "Live brokerage execution is intentionally not implemented. "
            "Use SandboxExecutionAdapter until a broker-specific adapter is reviewed."
        )


def suggestions_to_orders(suggestions: list[TradeSuggestion]) -> list[TradeOrder]:
    orders: list[TradeOrder] = []
    for suggestion in suggestions:
        if suggestion.action == "block" or abs(suggestion.delta_weight) <= 0:
            continue
        if suggestion.action == "trim":
            side = "sell"
        elif suggestion.action == "add":
            side = "buy"
        elif suggestion.ticker == "CASH":
            side = "cash"
        else:
            side = "hold"

        orders.append(
            TradeOrder(
                ticker=suggestion.ticker,
                side=side,
                target_weight_delta=suggestion.delta_weight,
                reason=suggestion.reason,
                rule_ids=suggestion.rule_ids,
            )
        )
    return orders
