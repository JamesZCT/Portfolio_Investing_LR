from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.request import Request, urlopen
import csv
import io
import re
import xml.etree.ElementTree as ET


@dataclass
class InformationSign:
    title: str
    source: str
    source_tier: str
    published: str | None
    url: str
    category: str
    signal: str
    value: float | None
    unit: str | None
    why_it_matters: str
    decision_use: str = "information_only"
    portfolio_weight: float = 0.0


PUBLIC_FEEDS = (
    {
        "name": "Lance Roberts / RIA",
        "url": "https://realinvestmentadvice.com/feed/",
        "source_tier": "commentary",
        "category": "market commentary",
        "author_filter": "lance roberts",
        "max_items": 5,
    },
    {
        "name": "Federal Reserve",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "source_tier": "primary",
        "category": "monetary policy / regulation",
        "author_filter": None,
        "max_items": 4,
    },
)

FRED_SERIES = {
    "DGS10": {
        "title": "10-Year Treasury Yield",
        "unit": "%",
        "category": "rates / financial conditions",
        "why": "Long-term yields affect equity valuation, borrowing costs, and the relative appeal of bonds versus stocks.",
    },
    "DGS2": {
        "title": "2-Year Treasury Yield",
        "unit": "%",
        "category": "rates / policy expectations",
        "why": "The 2-year yield is sensitive to expected Federal Reserve policy and near-term financial conditions.",
    },
    "UNRATE": {
        "title": "US Unemployment Rate",
        "unit": "%",
        "category": "labor market",
        "why": "Labor-market cooling can affect earnings, consumer demand, recession risk, and the path of policy rates.",
    },
    "CPIAUCSL": {
        "title": "US CPI Year-over-Year",
        "unit": "% YoY",
        "category": "inflation",
        "why": "Inflation influences interest-rate expectations and the discount rate applied to future corporate earnings.",
    },
}


def build_information_signs_payload(market: str, mode: str = "real") -> dict[str, Any]:
    if mode == "sandbox":
        return _sandbox_payload(market)

    signs: list[InformationSign] = []
    source_status: list[dict[str, Any]] = []
    for feed in PUBLIC_FEEDS:
        rows, status = _fetch_feed(feed)
        signs.extend(rows)
        source_status.append(status)

    macro_signs, macro_status = _fetch_fred_signs()
    signs.extend(macro_signs)
    source_status.append(macro_status)

    commentary = [asdict(sign) for sign in signs if sign.source_tier == "commentary"]
    primary = [asdict(sign) for sign in signs if sign.source_tier == "primary"]
    successful_sources = sum(1 for item in source_status if item["status"] == "ok")
    status = "available" if successful_sources == len(source_status) else "partial" if signs else "unavailable"
    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": market,
        "source_mode": "public_information_only",
        "decision_policy": {
            "portfolio_weight": 0.0,
            "rule": (
                "Information signs may explain conditions and create review questions, but they do not change target weights, "
                "trade instructions, or risk limits. Any future influence must be explicit, bounded, and recorded with a reason."
            ),
        },
        "source_status": source_status,
        "primary_signs": primary[:10],
        "commentary_signs": commentary[:6],
        "sign_count": len(primary[:10]) + len(commentary[:6]),
    }


def _fetch_feed(feed: dict[str, Any]) -> tuple[list[InformationSign], dict[str, Any]]:
    request = Request(
        str(feed["url"]),
        headers={"User-Agent": "portfolio-investing-lab/1.0 (+public research RSS)"},
    )
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed public RSS sources only
            raw = response.read(1_200_000)
    except Exception as exc:
        return [], {"source": feed["name"], "url": feed["url"], "status": "unavailable", "detail": str(exc)[:180]}

    parsed = _parse_rss_items(raw, author_filter=feed.get("author_filter"))
    signs = [
        InformationSign(
            title=item["title"],
            source=str(feed["name"]),
            source_tier=str(feed["source_tier"]),
            published=item.get("published"),
            url=item.get("url", ""),
            category=str(feed["category"]),
            signal=_commentary_signal(item["title"], item.get("summary", "")) if feed["source_tier"] == "commentary" else "event",
            value=None,
            unit=None,
            why_it_matters=_why_feed_item_matters(str(feed["source_tier"]), item["title"], item.get("summary", "")),
        )
        for item in parsed[: int(feed["max_items"])]
    ]
    return signs, {
        "source": feed["name"],
        "url": feed["url"],
        "status": "ok" if signs else "empty",
        "item_count": len(signs),
        "latest_published": max((sign.published or "" for sign in signs), default=None),
    }


def _parse_rss_items(raw: bytes, author_filter: str | None = None) -> list[dict[str, str | None]]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    rows: list[dict[str, str | None]] = []
    for item in root.findall("./channel/item"):
        author = _node_text(item, "{http://purl.org/dc/elements/1.1/}creator") or _node_text(item, "author")
        if author_filter and author_filter not in author.lower():
            continue
        title = _clean_text(_node_text(item, "title"))
        if not title:
            continue
        summary = _clean_html(_node_text(item, "description"))
        rows.append(
            {
                "title": title[:220],
                "author": author,
                "published": _normalize_date(_node_text(item, "pubDate")),
                "url": _clean_text(_node_text(item, "link")),
                "summary": summary[:500],
            }
        )
    return rows


def _fetch_fred_signs() -> tuple[list[InformationSign], dict[str, Any]]:
    observations: dict[str, list[tuple[str, float]]] = {}
    failures: list[str] = []
    for series_id in FRED_SERIES:
        try:
            observations[series_id] = _fetch_fred_series(series_id)
        except Exception:
            failures.append(series_id)

    signs: list[InformationSign] = []
    for series_id in ("DGS10", "DGS2", "UNRATE"):
        rows = observations.get(series_id, [])
        if not rows:
            continue
        meta = FRED_SERIES[series_id]
        latest_date, latest = rows[-1]
        previous = rows[-2][1] if len(rows) > 1 else latest
        delta = latest - previous
        signs.append(
            InformationSign(
                title=str(meta["title"]),
                source="FRED / Federal Reserve Bank of St. Louis",
                source_tier="primary",
                published=latest_date,
                url=f"https://fred.stlouisfed.org/series/{series_id}",
                category=str(meta["category"]),
                signal=_direction(delta, threshold=0.005),
                value=round(latest, 3),
                unit=str(meta["unit"]),
                why_it_matters=f"{meta['why']} Latest change: {delta:+.2f} percentage points.",
            )
        )

    cpi_rows = observations.get("CPIAUCSL", [])
    if len(cpi_rows) >= 13:
        latest_date, latest = cpi_rows[-1]
        year_ago = cpi_rows[-13][1]
        yoy = (latest / year_ago - 1.0) * 100 if year_ago else 0.0
        meta = FRED_SERIES["CPIAUCSL"]
        signs.append(
            InformationSign(
                title=str(meta["title"]),
                source="FRED / U.S. Bureau of Labor Statistics",
                source_tier="primary",
                published=latest_date,
                url="https://fred.stlouisfed.org/series/CPIAUCSL",
                category=str(meta["category"]),
                signal="elevated" if yoy >= 3.0 else "moderating" if yoy < 2.5 else "near_target_range",
                value=round(yoy, 2),
                unit=str(meta["unit"]),
                why_it_matters=str(meta["why"]),
            )
        )

    ten_year = observations.get("DGS10", [])
    two_year = observations.get("DGS2", [])
    if ten_year and two_year:
        curve = ten_year[-1][1] - two_year[-1][1]
        signs.append(
            InformationSign(
                title="10Y minus 2Y Treasury Curve",
                source="FRED / U.S. Treasury",
                source_tier="primary",
                published=min(ten_year[-1][0], two_year[-1][0]),
                url="https://fred.stlouisfed.org/graph/?g=1K7YE",
                category="rates / growth expectations",
                signal="inverted" if curve < 0 else "positive",
                value=round(curve, 3),
                unit="percentage points",
                why_it_matters="The yield-curve shape is a macro context indicator for expected growth and policy, not a market-timing rule.",
            )
        )

    return signs, {
        "source": "FRED",
        "url": "https://fred.stlouisfed.org/",
        "status": "ok" if signs and not failures else "partial" if signs else "unavailable",
        "item_count": len(signs),
        "failed_series": failures,
    }


def _fetch_fred_series(series_id: str) -> list[tuple[str, float]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    request = Request(url, headers={"User-Agent": "portfolio-investing-lab/1.0 (+public macro research)"})
    with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed FRED endpoint only
        raw = response.read(800_000).decode("utf-8-sig", errors="replace")
    rows: list[tuple[str, float]] = []
    for row in csv.DictReader(io.StringIO(raw)):
        value = row.get(series_id)
        date = row.get("observation_date")
        if not date or value in (None, "", "."):
            continue
        try:
            rows.append((date, float(value)))
        except ValueError:
            continue
    return rows


def _commentary_signal(title: str, summary: str) -> str:
    text = f" {title} {summary} ".lower()
    risk_terms = ("risk", "warning", "overbought", "correction", "hawkish", "margin debt", "parabolic", "sell")
    constructive_terms = ("opportunity", "support held", "bull market", "breakout", "buy signal", "rally")
    risk_hits = sum(term in text for term in risk_terms)
    constructive_hits = sum(term in text for term in constructive_terms)
    if risk_hits > constructive_hits:
        return "cautionary"
    if constructive_hits > risk_hits:
        return "constructive"
    return "mixed"


def _why_feed_item_matters(source_tier: str, title: str, summary: str) -> str:
    if source_tier == "primary":
        return "Official releases can change rate, liquidity, regulatory, or economic expectations; review the underlying release before acting."
    text = f" {title} {summary} ".lower()
    if any(term in text for term in ("breadth", "moving average", "technical", "overbought", "support", "flow")):
        return "Technical and positioning commentary can identify conditions to test against current price trend, drawdown, and concentration rules."
    if any(term in text for term in ("fed", "inflation", "economy", "consumer", "debt", "yield")):
        return "Macro commentary provides a scenario to compare with primary economic data and the portfolio's rate sensitivity."
    return "Commentary supplies a research hypothesis and watch items; it is not independent evidence for changing portfolio weights."


def _direction(delta: float, threshold: float) -> str:
    if delta > threshold:
        return "rising"
    if delta < -threshold:
        return "falling"
    return "unchanged"


def _node_text(node: ET.Element, path: str) -> str:
    found = node.find(path)
    return found.text or "" if found is not None else ""


def _normalize_date(value: str) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        return value


def _clean_html(value: str) -> str:
    return _clean_text(re.sub(r"<[^>]+>", " ", value))


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def _sandbox_payload(market: str) -> dict[str, Any]:
    sign = InformationSign(
        title="Sandbox information sign",
        source="Sandbox",
        source_tier="primary",
        published=datetime.now(timezone.utc).date().isoformat(),
        url="",
        category="test",
        signal="unchanged",
        value=None,
        unit=None,
        why_it_matters="Validates the information-sign display without a network request.",
    )
    return {
        "status": "sandbox",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": market,
        "source_mode": "sandbox",
        "decision_policy": {"portfolio_weight": 0.0, "rule": "Sandbox signs never change portfolio decisions."},
        "source_status": [{"source": "Sandbox", "url": "", "status": "ok", "item_count": 1}],
        "primary_signs": [asdict(sign)],
        "commentary_signs": [],
        "sign_count": 1,
    }
