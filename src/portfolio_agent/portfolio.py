from __future__ import annotations

from collections import defaultdict

from .config import AppConfig
from .models import MarketRegime, RiskPrediction, SectorSignal, TradeSuggestion


def propose_rebalance(
    config: AppConfig,
    signals: list[SectorSignal],
    current_positions: dict[str, float] | None = None,
    latest_prices: dict[str, float] | None = None,
    trailing_highs: dict[str, float] | None = None,
    market_regime: MarketRegime | None = None,
    risk_predictions: dict[str, RiskPrediction] | None = None,
) -> list[TradeSuggestion]:
    positions = dict(current_positions) if current_positions is not None else dict(config.universe.positions)
    targets = config.universe.target_weights
    ticker_sector = config.universe.ticker_sector
    entry_prices = config.universe.entry_prices
    latest_prices = latest_prices or {}
    trailing_highs = trailing_highs or {}
    risk_predictions = risk_predictions or {}

    signal_by_sector = {s.sector: s for s in signals}
    hype_sectors = {s.sector for s in signals if s.status == "hyped"}
    undervalued_sectors = {s.sector for s in signals if s.status == "undervalued"}

    trim_by_ticker: dict[str, float] = defaultdict(float)
    trim_reasons: dict[str, list[str]] = defaultdict(list)
    trim_rule_ids: dict[str, set[str]] = defaultdict(set)
    blocked_adds: list[TradeSuggestion] = []
    is_bearish = (
        config.rules.trend_filter_enabled
        and market_regime is not None
        and market_regime.trend_state == "bearish"
    )

    for ticker, current_weight in positions.items():
        if ticker == "CASH":
            continue
        target_weight = targets.get(ticker, 0.0)
        sector = ticker_sector.get(ticker)
        signal = signal_by_sector.get(sector)

        overweight = current_weight - target_weight
        trim_for_overweight = max(0.0, overweight)

        trim_for_hype = 0.0
        if sector in hype_sectors and current_weight > 0:
            trim_for_hype = min(
                current_weight * config.rules.max_trim_fraction_per_position,
                max(0.0, current_weight - target_weight * 0.5),
            )

        trim_for_single_cap = max(0.0, current_weight - config.rules.max_single_position_weight)

        trim = max(trim_for_overweight, trim_for_hype, trim_for_single_cap)
        if trim >= config.rules.min_trade_weight:
            trim_by_ticker[ticker] = max(trim_by_ticker[ticker], trim)
            if trim_for_overweight >= config.rules.min_trade_weight:
                trim_reasons[ticker].append("over target weight")
                trim_rule_ids[ticker].add("OVER_TARGET")
            if trim_for_hype >= config.rules.min_trade_weight and signal is not None:
                trim_reasons[ticker].append(f"sector hyped (z={signal.z:.2f})")
                trim_rule_ids[ticker].add("SECTOR_HYPED")
            if trim_for_single_cap >= config.rules.min_trade_weight:
                trim_reasons[ticker].append("exceeds max single-name cap")
                trim_rule_ids[ticker].add("SINGLE_CAP")

        if is_bearish and current_weight > 0:
            defensive_trim = current_weight * config.rules.bear_market_trim_fraction
            if defensive_trim >= config.rules.min_trade_weight:
                trim_by_ticker[ticker] = max(trim_by_ticker[ticker], defensive_trim)
                trim_reasons[ticker].append(
                    f"benchmark trend bearish ({market_regime.benchmark} below MA{config.indicators.trend_ma_window})"
                )
                trim_rule_ids[ticker].add("TREND_FILTER")

        prediction = risk_predictions.get(ticker)
        if prediction is not None and prediction.risk_level == "high":
            ml_trim = current_weight * config.ml.high_risk_trim_fraction
            if ml_trim >= config.rules.min_trade_weight:
                trim_by_ticker[ticker] = max(trim_by_ticker[ticker], ml_trim)
                trim_reasons[ticker].append(
                    f"ML drawdown risk high (p={prediction.risk_probability:.2f})"
                )
                trim_rule_ids[ticker].add("ML_HIGH_RISK")

    _apply_sector_cap_trims(config, positions, ticker_sector, trim_by_ticker, trim_reasons, trim_rule_ids)
    _apply_stop_risk_trims(
        config=config,
        positions=positions,
        entry_prices=entry_prices,
        latest_prices=latest_prices,
        trailing_highs=trailing_highs,
        trim_by_ticker=trim_by_ticker,
        trim_reasons=trim_reasons,
        trim_rule_ids=trim_rule_ids,
    )

    suggestions: list[TradeSuggestion] = []
    freed_cash = 0.0

    post_trim_positions = dict(positions)
    for ticker, trim in trim_by_ticker.items():
        if trim < config.rules.min_trade_weight:
            continue
        bounded_trim = min(trim, positions.get(ticker, 0.0))
        if bounded_trim < config.rules.min_trade_weight:
            continue
        post_trim_positions[ticker] = max(0.0, positions.get(ticker, 0.0) - bounded_trim)
        freed_cash += bounded_trim
        reason = "; ".join(sorted(set(trim_reasons[ticker])))
        suggestions.append(
            TradeSuggestion(
                ticker=ticker,
                action="trim",
                delta_weight=-bounded_trim,
                reason=reason,
                rule_ids=tuple(sorted(trim_rule_ids[ticker])),
            )
        )

    buy_candidates: list[tuple[str, float, str]] = []
    for ticker, target_weight in targets.items():
        if ticker == "CASH" or ticker in trim_by_ticker:
            continue
        current_weight = post_trim_positions.get(ticker, 0.0)
        underweight = target_weight - current_weight
        if underweight <= config.rules.underweight_trigger:
            continue

        blocked_reason = _blocked_add_reason(
            ticker=ticker,
            entry_prices=entry_prices,
            latest_prices=latest_prices,
            risk_predictions=risk_predictions,
            is_bearish=is_bearish,
            config=config,
        )
        if blocked_reason:
            blocked_adds.append(
                TradeSuggestion(
                    ticker=ticker,
                    action="block",
                    delta_weight=0.0,
                    reason=blocked_reason,
                    rule_ids=("ADD_BLOCK",),
                )
            )
            continue

        sector = ticker_sector.get(ticker)
        if sector in undervalued_sectors:
            buy_candidates.append((ticker, underweight, "under target + sector undervalued"))
        else:
            buy_candidates.append((ticker, underweight * 0.5, "under target"))

    total_buy_score = sum(max(score, 0.0) for _, score, _ in buy_candidates)
    sector_weights = _sector_weights(post_trim_positions, ticker_sector)

    if freed_cash >= config.rules.min_trade_weight and total_buy_score > 0:
        for ticker, score, reason in buy_candidates:
            raw_alloc = freed_cash * (score / total_buy_score)
            cap_single = max(0.0, config.rules.max_single_position_weight - post_trim_positions.get(ticker, 0.0))
            sector = ticker_sector.get(ticker, "")
            cap_sector = max(0.0, config.rules.max_sector_weight - sector_weights.get(sector, 0.0))
            alloc = min(raw_alloc, cap_single, cap_sector)

            if alloc >= config.rules.min_trade_weight:
                post_trim_positions[ticker] = post_trim_positions.get(ticker, 0.0) + alloc
                sector_weights[sector] = sector_weights.get(sector, 0.0) + alloc
                suggestions.append(
                    TradeSuggestion(
                        ticker=ticker,
                        action="add",
                        delta_weight=alloc,
                        reason=reason,
                        rule_ids=("UNDER_TARGET",),
                    )
                )

    cash_weight = post_trim_positions.get("CASH", 0.0)
    target_cash = config.rules.defensive_cash_weight if is_bearish else config.rules.min_cash_weight
    cash_shortfall = max(0.0, target_cash - cash_weight)
    residual_cash = max(0.0, freed_cash - sum(s.delta_weight for s in suggestions if s.action == "add"))
    cash_delta = max(residual_cash, min(freed_cash, cash_shortfall))

    if cash_delta >= config.rules.min_trade_weight:
        suggestions.append(
            TradeSuggestion(
                ticker="CASH",
                action="hold",
                delta_weight=cash_delta,
                reason="raise or maintain cash buffer",
                rule_ids=("CASH_BUFFER",),
            )
        )

    suggestions.extend(blocked_adds)
    return sorted(suggestions, key=lambda x: (x.action, -abs(x.delta_weight), x.ticker))


def _apply_sector_cap_trims(
    config: AppConfig,
    positions: dict[str, float],
    ticker_sector: dict[str, str],
    trim_by_ticker: dict[str, float],
    trim_reasons: dict[str, list[str]],
    trim_rule_ids: dict[str, set[str]],
) -> None:
    sector_weights = _sector_weights(positions, ticker_sector)

    for sector, sector_weight in sector_weights.items():
        excess = sector_weight - config.rules.max_sector_weight
        if excess <= config.rules.min_trade_weight:
            continue

        members = [
            t
            for t, w in positions.items()
            if t != "CASH" and ticker_sector.get(t) == sector and w > config.rules.min_trade_weight
        ]
        total_member_weight = sum(positions[t] for t in members)
        if total_member_weight <= 0:
            continue

        for ticker in members:
            share = positions[ticker] / total_member_weight
            trim = excess * share
            trim_by_ticker[ticker] = max(trim_by_ticker.get(ticker, 0.0), trim)
            trim_reasons[ticker].append("sector exceeds max cap")
            trim_rule_ids[ticker].add("SECTOR_CAP")


def _apply_stop_risk_trims(
    config: AppConfig,
    positions: dict[str, float],
    entry_prices: dict[str, float],
    latest_prices: dict[str, float],
    trailing_highs: dict[str, float],
    trim_by_ticker: dict[str, float],
    trim_reasons: dict[str, list[str]],
    trim_rule_ids: dict[str, set[str]],
) -> None:
    for ticker, weight in positions.items():
        if ticker == "CASH":
            continue
        if weight <= config.rules.min_trade_weight:
            continue

        latest = latest_prices.get(ticker)
        if latest is None or latest <= 0:
            continue

        entry = entry_prices.get(ticker)
        if entry and entry > 0:
            drawdown_from_entry = (latest / entry) - 1.0
            if drawdown_from_entry <= -config.rules.stop_loss_pct:
                stop_trim = weight * config.rules.stop_trim_fraction
                trim_by_ticker[ticker] = max(trim_by_ticker.get(ticker, 0.0), stop_trim)
                trim_reasons[ticker].append("stop-loss triggered")
                trim_rule_ids[ticker].add("STOP_LOSS")

        high = trailing_highs.get(ticker)
        if high and high > 0:
            drawdown_from_peak = (latest / high) - 1.0
            if drawdown_from_peak <= -config.rules.trailing_stop_pct:
                trail_trim = weight * config.rules.trailing_stop_trim_fraction
                trim_by_ticker[ticker] = max(trim_by_ticker.get(ticker, 0.0), trail_trim)
                trim_reasons[ticker].append("trailing-stop triggered")
                trim_rule_ids[ticker].add("TRAILING_STOP")


def _sector_weights(positions: dict[str, float], ticker_sector: dict[str, str]) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for ticker, weight in positions.items():
        if ticker == "CASH":
            continue
        sector = ticker_sector.get(ticker, "")
        out[sector] += weight
    return dict(out)


def apply_trade_suggestions(
    positions: dict[str, float],
    suggestions: list[TradeSuggestion],
) -> dict[str, float]:
    updated = dict(positions)

    for suggestion in suggestions:
        if suggestion.action == "block":
            continue
        current = updated.get(suggestion.ticker, 0.0)
        updated[suggestion.ticker] = max(0.0, current + suggestion.delta_weight)

    total = sum(updated.values())
    if total <= 0:
        return updated
    return {k: v / total for k, v in updated.items()}


def _blocked_add_reason(
    ticker: str,
    entry_prices: dict[str, float],
    latest_prices: dict[str, float],
    risk_predictions: dict[str, RiskPrediction],
    is_bearish: bool,
    config: AppConfig,
) -> str:
    latest = latest_prices.get(ticker)
    entry = entry_prices.get(ticker)
    if latest is not None and entry is not None and entry > 0:
        loss = (latest / entry) - 1.0
        if loss <= -config.rules.loss_block_pct:
            return f"add blocked: position is down {100 * loss:.2f}% from entry without thesis override"

    prediction = risk_predictions.get(ticker)
    if prediction is not None and prediction.risk_level in {"medium", "high"}:
        return f"add blocked: ML drawdown risk {prediction.risk_level} (p={prediction.risk_probability:.2f})"

    if is_bearish and not config.rules.allow_countertrend_buys:
        return "add blocked: benchmark trend is bearish"

    return ""
