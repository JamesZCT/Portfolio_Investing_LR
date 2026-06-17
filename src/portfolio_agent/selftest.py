from __future__ import annotations

from .config import load_config
from .models import SectorSignal
from .notifier import send_notifications
from .portfolio import propose_rebalance


def main() -> int:
    cfg = load_config("config.yaml")

    signals = [
        SectorSignal("Technology", "XLK", 200.0, 180.0, 8.0, 3.2, 0.11, "hyped"),
        SectorSignal("Financials", "XLF", 40.0, 44.0, 1.5, -2.4, -0.09, "cool"),
        SectorSignal("Healthcare", "XLV", 130.0, 145.0, 3.0, -3.3, -0.10, "undervalued"),
        SectorSignal("Energy", "XLE", 90.0, 88.0, 2.5, 0.8, 0.02, "neutral"),
        SectorSignal("ConsumerStaples", "XLP", 80.0, 81.0, 1.1, -0.5, -0.01, "neutral"),
    ]

    latest_prices = {
        "AAPL": 175.0,
        "MSFT": 370.0,
        "NVDA": 110.0,
        "JPM": 178.0,
        "XOM": 112.0,
        "JNJ": 142.0,
        "V": 268.0,
        "COST": 805.0,
        "UNH": 498.0,
        "AVGO": 1320.0,
    }
    trailing_highs = {
        "AAPL": 230.0,
        "MSFT": 430.0,
        "NVDA": 145.0,
        "JPM": 198.0,
        "XOM": 124.0,
        "JNJ": 170.0,
        "V": 290.0,
        "COST": 890.0,
        "UNH": 580.0,
        "AVGO": 1750.0,
    }

    suggestions = propose_rebalance(
        config=cfg,
        signals=signals,
        current_positions=cfg.universe.positions,
        latest_prices=latest_prices,
        trailing_highs=trailing_highs,
    )

    print("SELFTEST: suggestions")
    for item in suggestions:
        print(f"- {item.action.upper()} {item.ticker}: {item.delta_weight:+.4f} ({item.reason})")

    note_results = send_notifications(
        config=cfg.notifications,
        subject="Portfolio Agent selftest",
        body=f"Generated {len(suggestions)} suggestions.",
    )
    print("SELFTEST: notifications")
    for line in note_results:
        print(f"- {line}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
