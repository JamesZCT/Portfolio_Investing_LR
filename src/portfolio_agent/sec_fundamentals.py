from __future__ import annotations

import json
import os
import re
import statistics
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx


SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
PERIODIC_FORMS = ANNUAL_FORMS | {"10-Q", "10-Q/A", "8-K", "8-K/A"}

REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "Revenues",
)
NET_INCOME_TAGS = ("NetIncomeLoss", "ProfitLoss")
OPERATING_INCOME_TAGS = ("OperatingIncomeLoss",)
CFO_TAGS = (
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
)
CAPEX_TAGS = (
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsForAdditionsToPropertyPlantAndEquipment",
)
ASSET_TAGS = ("Assets",)
EQUITY_TAGS = (
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
)
CASH_TAGS = (
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
)
DEBT_CURRENT_TAGS = ("LongTermDebtCurrent", "ShortTermBorrowings")
DEBT_NONCURRENT_TAGS = ("LongTermDebtNoncurrent", "LongTermDebt")
TAX_TAGS = ("IncomeTaxExpenseBenefit",)
PRETAX_TAGS = ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",)


class SecFundamentalsClient:
    def __init__(
        self,
        *,
        user_agent: str | None = None,
        cache_dir: str | Path | None = None,
        request_interval_seconds: float = 0.15,
    ) -> None:
        self.user_agent = (user_agent or os.getenv("SEC_USER_AGENT", "")).strip()
        if not self.user_agent:
            raise ValueError("SEC_USER_AGENT is required and must include a monitored contact email.")
        self.cache_dir = Path(cache_dir or os.getenv("SEC_CACHE_DIR", "outputs/cache/sec"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.request_interval_seconds = request_interval_seconds
        self._last_request_at = 0.0
        self._lookup: dict[str, dict[str, Any]] | None = None

    def research_ticker(self, ticker: str, quote: dict[str, Any]) -> dict[str, Any]:
        company = self._company_lookup().get(_normalized_ticker(ticker))
        if not company:
            raise LookupError(f"No SEC CIK mapping found for {ticker}.")
        cik = int(company["cik"])
        submissions = self._cached_json(
            SEC_SUBMISSIONS_URL.format(cik=cik),
            f"submissions-{cik:010d}.json",
            ttl_hours=12,
        )
        company_facts = self._cached_json(
            SEC_COMPANY_FACTS_URL.format(cik=cik),
            f"companyfacts-{cik:010d}.json",
            ttl_hours=22,
        )
        return assess_company_facts(ticker, quote, submissions, company_facts)

    def _company_lookup(self) -> dict[str, dict[str, Any]]:
        if self._lookup is not None:
            return self._lookup
        payload = self._cached_json(SEC_TICKER_URL, "company-tickers-exchange.json", ttl_hours=168)
        fields = payload.get("fields", [])
        rows = payload.get("data", [])
        lookup: dict[str, dict[str, Any]] = {}
        for raw in rows:
            if not isinstance(raw, list) or len(raw) != len(fields):
                continue
            row = dict(zip(fields, raw))
            ticker = _normalized_ticker(str(row.get("ticker", "")))
            if ticker:
                lookup[ticker] = row
        self._lookup = lookup
        return self._lookup

    def _cached_json(self, url: str, filename: str, *, ttl_hours: int) -> dict[str, Any]:
        path = self.cache_dir / filename
        if path.exists() and time.time() - path.stat().st_mtime < ttl_hours * 3600:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    return payload
            except (OSError, json.JSONDecodeError):
                pass

        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.request_interval_seconds:
            time.sleep(self.request_interval_seconds - elapsed)
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        }
        contact = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", self.user_agent)
        if contact:
            headers["From"] = contact.group(0)
        with httpx.Client(headers=headers, timeout=40.0, follow_redirects=True) as client:
            response = client.get(url)
            self._last_request_at = time.monotonic()
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"SEC endpoint returned an unsupported payload for {url}")
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(path)
        return payload


def enrich_shortlist_with_sec(
    groups: list[list[dict[str, Any]]],
    *,
    limit_per_group: int = 5,
    client: SecFundamentalsClient | None = None,
) -> dict[str, Any]:
    if limit_per_group <= 0:
        return {"status": "disabled", "researched_count": 0, "failed_count": 0, "note": "SEC deep research is disabled."}
    try:
        sec = client or SecFundamentalsClient()
    except ValueError as exc:
        return {"status": "not_configured", "researched_count": 0, "failed_count": 0, "note": str(exc)}

    researched = 0
    failed = 0
    errors: list[str] = []
    seen: set[str] = set()
    for rows in groups:
        for row in rows[:limit_per_group]:
            ticker = str(row.get("ticker", "")).upper()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            try:
                row["research"] = sec.research_ticker(ticker, row)
                researched += 1
            except Exception as exc:
                failed += 1
                errors.append(f"{ticker}: {str(exc)[:100]}")
                row["research"] = quote_only_research(row, note="SEC filing facts were unavailable for this refresh.")

    status = "available" if researched and not failed else "partial" if researched else "unavailable"
    note = "Deterministic SEC filing analysis; no LLM is used to calculate scores."
    if errors:
        note += f" {failed} ticker(s) fell back to quote-only evidence."
    return {
        "status": status,
        "researched_count": researched,
        "failed_count": failed,
        "note": note,
        "errors": errors[:3],
    }


def quote_only_research(quote: dict[str, Any], *, note: str | None = None) -> dict[str, Any]:
    trend_score = _number(quote.get("score")) or 50.0
    trailing_pe = _positive(quote.get("trailing_pe"))
    forward_pe = _positive(quote.get("forward_pe"))
    eps_growth = _number(quote.get("eps_forward_growth_pct"))
    value_score = _average(
        [
            _score_low(trailing_pe, 10.0, 45.0),
            _score_low(forward_pe, 10.0, 40.0),
        ]
    )
    earnings_score = _average(
        [
            70.0 if quote.get("profitable") else 25.0,
            _score_high(eps_growth, -10.0, 25.0),
        ]
    )
    decision_score = _weighted_average(
        [(trend_score, 0.45), (value_score, 0.25), (earnings_score, 0.30)]
    )
    if quote.get("action") == "sell_avoid":
        decision = "avoid_review"
    elif quote.get("action") == "buy_candidate" and decision_score is not None and decision_score >= 62:
        decision = "research_buy"
    else:
        decision = "wait_watch"
    return {
        "status": "quote_only",
        "decision": decision,
        "decision_label": _decision_label(decision),
        "decision_score": _round(decision_score),
        "confidence": "low",
        "sector": "Unclassified",
        "industry": "SEC classification pending",
        "business_model": "quote_only",
        "valuation_model": "P/E and forward earnings; filing evidence pending",
        "scorecard": {
            "quality": None,
            "value": _round(value_score),
            "financial_strength": None,
            "earnings": _round(earnings_score),
            "trend": _round(trend_score),
        },
        "earnings": {
            "assessment": "Filing review pending",
            "latest_report_form": None,
            "filed_at": None,
            "period_end": None,
            "revenue_growth_yoy_pct": None,
            "net_income_growth_yoy_pct": None,
            "next_earnings_date": quote.get("next_earnings_date"),
        },
        "key_takeaways": [quote.get("reason") or "Price and trend evidence only."],
        "risks": [note or "Low-confidence decision until SEC filing facts are available."],
        "source": {"name": "Market quote snapshot", "url": "https://finance.yahoo.com/"},
    }


def assess_company_facts(
    ticker: str,
    quote: dict[str, Any],
    submissions: dict[str, Any],
    company_facts: dict[str, Any],
) -> dict[str, Any]:
    facts = company_facts.get("facts", {}).get("us-gaap", {})
    sic = int(submissions.get("sic") or 0)
    industry = str(submissions.get("sicDescription") or "Unclassified")
    business_model, sector, valuation_model = classify_business_model(sic, industry)

    annual_revenue = _annual_series(facts, REVENUE_TAGS)
    annual_income = _annual_series(facts, NET_INCOME_TAGS)
    annual_operating_income = _annual_series(facts, OPERATING_INCOME_TAGS)
    annual_cfo = _annual_series(facts, CFO_TAGS)
    annual_capex = _annual_series(facts, CAPEX_TAGS)
    annual_assets = _annual_series(facts, ASSET_TAGS)
    annual_equity = _annual_series(facts, EQUITY_TAGS)
    annual_cash = _annual_series(facts, CASH_TAGS)
    annual_debt_current = _annual_series(facts, DEBT_CURRENT_TAGS)
    annual_debt_noncurrent = _annual_series(facts, DEBT_NONCURRENT_TAGS)
    annual_tax = _annual_series(facts, TAX_TAGS)
    annual_pretax = _annual_series(facts, PRETAX_TAGS)

    revenue = _latest_value(annual_revenue)
    net_income = _latest_value(annual_income)
    operating_income = _latest_value(annual_operating_income)
    cfo = _latest_value(annual_cfo)
    capex = abs(_latest_value(annual_capex) or 0.0) if annual_capex else None
    assets = _latest_value(annual_assets)
    equity = _latest_value(annual_equity)
    cash = _latest_value(annual_cash) or 0.0
    debt = (_latest_value(annual_debt_current) or 0.0) + (_latest_value(annual_debt_noncurrent) or 0.0)
    market_cap = _positive(quote.get("market_cap"))

    fcf = cfo - capex if cfo is not None and capex is not None else None
    normalized_fcf = _median_fcf(annual_cfo, annual_capex)
    operating_margin = _ratio(operating_income, revenue)
    fcf_margin = _ratio(fcf, revenue)
    fcf_conversion = _ratio(cfo, net_income) if net_income and net_income > 0 else None
    roe = _ratio(net_income, equity) if equity and equity > 0 else None
    equity_to_assets = _ratio(equity, assets) if assets and assets > 0 else None
    debt_to_equity = _ratio(debt, equity) if equity and equity > 0 else None
    net_debt_to_fcf = _ratio(max(debt - cash, 0.0), fcf) if fcf and fcf > 0 else None
    fcf_yield = _ratio(fcf, market_cap)
    normalized_fcf_yield = _ratio(normalized_fcf, market_cap)
    tax_rate = _bounded_ratio(_latest_value(annual_tax), _latest_value(annual_pretax), 0.0, 0.35) or 0.21
    invested_capital = debt + (equity or 0.0) - cash
    roic_proxy = _ratio((operating_income or 0.0) * (1.0 - tax_rate), invested_capital) if invested_capital > 0 else None

    revenue_growth = _period_growth(facts, REVENUE_TAGS)
    income_growth = _period_growth(facts, NET_INCOME_TAGS)
    filing = _latest_earnings_filing(submissions)
    earnings_score = _earnings_score(revenue_growth, income_growth, filing, quote)
    quality_score = _quality_score(business_model, operating_margin, fcf_margin, fcf_conversion, roe, roic_proxy, revenue_growth)
    strength_score = _strength_score(
        business_model, debt_to_equity, net_debt_to_fcf, equity_to_assets, cash, debt
    )
    value_score = _value_score(
        business_model,
        _positive(quote.get("trailing_pe")),
        _positive(quote.get("forward_pe")),
        _positive(quote.get("price_to_book")),
        fcf_yield,
        normalized_fcf_yield,
    )
    trend_score = _number(quote.get("score")) or 50.0
    decision_score = _weighted_average(
        [
            (quality_score, 0.27),
            (value_score, 0.23),
            (strength_score, 0.17),
            (earnings_score, 0.18),
            (trend_score, 0.15),
        ]
    )
    decision = _research_decision(
        quote.get("action"),
        decision_score,
        quality_score,
        value_score,
        strength_score,
        earnings_score,
        business_model,
        revenue_growth is not None or income_growth is not None,
    )
    assessment = _earnings_assessment(revenue_growth, income_growth, net_income)
    days_since_filing = _days_since(filing.get("filed_at")) if filing else None
    specialist = business_model in {"bank", "insurance", "reit"}
    confidence = "high" if not specialist and days_since_filing is not None and days_since_filing <= 180 else "medium"
    if not annual_revenue or not annual_income or specialist:
        confidence = "medium" if annual_income else "low"

    metrics = {
        "operating_margin_pct": _percent(operating_margin),
        "fcf_margin_pct": _percent(fcf_margin),
        "fcf_yield_pct": _percent(fcf_yield),
        "normalized_fcf_yield_pct": _percent(normalized_fcf_yield),
        "roe_pct": _percent(roe),
        "roic_proxy_pct": _percent(roic_proxy),
        "debt_to_equity": _round(debt_to_equity, 2),
        "net_debt_to_fcf": _round(net_debt_to_fcf, 2),
        "equity_to_assets_pct": _percent(equity_to_assets),
    }
    takeaways = _takeaways(
        business_model, assessment, revenue_growth, income_growth, metrics, quote, valuation_model
    )
    risks = _risks(business_model, metrics, quote, assessment)
    return {
        "status": "sec_fundamentals",
        "decision": decision,
        "decision_label": _decision_label(decision),
        "decision_score": _round(decision_score),
        "confidence": confidence,
        "sector": sector,
        "industry": industry,
        "sic": sic,
        "business_model": business_model,
        "valuation_model": valuation_model,
        "scorecard": {
            "quality": _round(quality_score),
            "value": _round(value_score),
            "financial_strength": _round(strength_score),
            "earnings": _round(earnings_score),
            "trend": _round(trend_score),
        },
        "earnings": {
            "assessment": assessment,
            "latest_report_form": filing.get("form") if filing else None,
            "filed_at": filing.get("filed_at") if filing else None,
            "period_end": filing.get("period_end") if filing else None,
            "report_url": filing.get("url") if filing else None,
            "revenue_growth_yoy_pct": _round(revenue_growth),
            "net_income_growth_yoy_pct": _round(income_growth),
            "next_earnings_date": quote.get("next_earnings_date"),
        },
        "metrics": metrics,
        "key_takeaways": takeaways[:3],
        "risks": risks[:2],
        "source": {
            "name": "SEC EDGAR company facts and filings",
            "url": f"https://www.sec.gov/edgar/browse/?CIK={int(company_facts.get('cik') or 0):010d}",
            "as_of": filing.get("filed_at") if filing else None,
        },
        "methodology_note": "Scores use standardized filing facts and sector-aware thresholds; specialist bank, insurer, and REIT metrics remain review gates.",
    }


def classify_business_model(sic: int, industry: str = "") -> tuple[str, str, str]:
    description = industry.lower()
    if sic == 6798 or "real estate investment trust" in description:
        return "reit", "Real Estate", "P/FFO, AFFO growth, leverage and occupancy; SEC score is preliminary"
    if 6020 <= sic <= 6099 or "bank" in description:
        return "bank", "Financials", "P/B and P/E relative to ROE, credit quality and regulatory capital"
    if 6300 <= sic <= 6411 or "insurance" in description:
        return "insurance", "Financials", "P/B and earnings relative to ROE, reserves and underwriting quality"
    if 6000 <= sic <= 6799:
        return "financial", "Financials", "P/B, P/E, ROE and balance-sheet resilience"
    if 7370 <= sic <= 7379 or "software" in description:
        return "software", "Technology", "Revenue growth, FCF margin and forward P/E; dilution remains a review gate"
    if 3570 <= sic <= 3579 or 3670 <= sic <= 3679:
        return "technology", "Technology", "ROIC, margins, FCF yield, growth and forward P/E"
    if 1300 <= sic <= 1399 or sic == 2911 or 4610 <= sic <= 4619 or "petroleum" in description or "oil" in description:
        return "energy", "Energy", "Normalized multi-year FCF yield, balance sheet and cycle resilience"
    if 4900 <= sic <= 4999:
        return "utility", "Utilities", "Earnings stability, leverage, dividend capacity and rate-base economics"
    if 2830 <= sic <= 2836 or 3840 <= sic <= 3851 or 8000 <= sic <= 8099:
        return "healthcare", "Healthcare", "Pipeline/product durability, margins, FCF and balance-sheet runway"
    return "operating_company", "Other", "ROIC, FCF yield, margins, growth and balance-sheet resilience"


def _annual_series(facts: dict[str, Any], tags: tuple[str, ...]) -> list[dict[str, Any]]:
    for tag in tags:
        units = facts.get(tag, {}).get("units", {})
        values = units.get("USD") or units.get("shares") or []
        candidates: dict[str, dict[str, Any]] = {}
        for row in values:
            if row.get("form") not in ANNUAL_FORMS or row.get("fp") != "FY" or not row.get("end"):
                continue
            if row.get("start"):
                try:
                    duration = (date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])).days
                except ValueError:
                    continue
                if duration < 250:
                    continue
            existing = candidates.get(row["end"])
            if existing is None or str(row.get("filed", "")) > str(existing.get("filed", "")):
                candidates[row["end"]] = row
        if candidates:
            return sorted(candidates.values(), key=lambda item: item["end"], reverse=True)[:5]
    return []


def _period_growth(facts: dict[str, Any], tags: tuple[str, ...]) -> float | None:
    frame_pattern = re.compile(r"^CY(\d{4})(Q[1-4])?$")
    for tag in tags:
        values = facts.get(tag, {}).get("units", {}).get("USD", [])
        by_frame: dict[str, dict[str, Any]] = {}
        for row in values:
            frame = str(row.get("frame") or "")
            match = frame_pattern.match(frame)
            if not match or row.get("form") not in PERIODIC_FORMS:
                continue
            if row.get("start"):
                try:
                    duration = (date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])).days
                except (KeyError, ValueError):
                    continue
                if match.group(2) and not 60 <= duration <= 120:
                    continue
                if not match.group(2) and duration < 250:
                    continue
            existing = by_frame.get(frame)
            if existing is None or str(row.get("filed", "")) > str(existing.get("filed", "")):
                by_frame[frame] = row
        if not by_frame:
            continue
        latest_frame = max(by_frame, key=lambda frame: str(by_frame[frame].get("end", "")))
        match = frame_pattern.match(latest_frame)
        if not match:
            continue
        prior_frame = f"CY{int(match.group(1)) - 1}{match.group(2) or ''}"
        current = _number(by_frame[latest_frame].get("val"))
        previous = _number(by_frame.get(prior_frame, {}).get("val"))
        if current is not None and previous is not None and previous > 0:
            return (current / previous - 1.0) * 100.0
    return None


def _latest_earnings_filing(submissions: dict[str, Any]) -> dict[str, Any]:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    candidates: list[dict[str, Any]] = []
    for index, form in enumerate(forms):
        items = _at(recent.get("items", []), index) or ""
        is_earnings_8k = form in {"8-K", "8-K/A"} and "2.02" in items
        if form not in ANNUAL_FORMS | {"10-Q", "10-Q/A"} and not is_earnings_8k:
            continue
        accession = str(_at(recent.get("accessionNumber", []), index) or "")
        document = str(_at(recent.get("primaryDocument", []), index) or "")
        cik = int(submissions.get("cik") or 0)
        accession_path = accession.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_path}/{document}" if accession and document else None
        candidates.append(
            {
                "form": form,
                "filed_at": _at(recent.get("filingDate", []), index),
                "period_end": _at(recent.get("reportDate", []), index),
                "url": url,
            }
        )
    return max(candidates, key=lambda item: str(item.get("filed_at", ""))) if candidates else {}


def _quality_score(
    model: str,
    operating_margin: float | None,
    fcf_margin: float | None,
    fcf_conversion: float | None,
    roe: float | None,
    roic: float | None,
    revenue_growth: float | None,
) -> float | None:
    if model in {"bank", "insurance", "financial"}:
        return _average([_score_high(_percent(roe), 4.0, 18.0), _score_high(revenue_growth, -5.0, 15.0)])
    if model == "software":
        return _average(
            [
                _score_high(_percent(fcf_margin), -5.0, 30.0),
                _score_high(_percent(operating_margin), -10.0, 30.0),
                _score_high(revenue_growth, 0.0, 25.0),
                _score_high(_percent(roic), 0.0, 25.0),
            ]
        )
    return _average(
        [
            _score_high(_percent(operating_margin), 0.0, 25.0),
            _score_high(_percent(fcf_margin), 0.0, 20.0),
            _score_high(fcf_conversion, 0.5, 1.5),
            _score_high(_percent(roic), 0.0, 20.0),
        ]
    )


def _strength_score(
    model: str,
    debt_to_equity: float | None,
    net_debt_to_fcf: float | None,
    equity_to_assets: float | None,
    cash: float,
    debt: float,
) -> float | None:
    if model in {"bank", "insurance", "financial"}:
        return _average([_score_high(_percent(equity_to_assets), 4.0, 14.0)])
    return _average(
        [
            _score_low(debt_to_equity, 0.2, 2.2),
            _score_low(net_debt_to_fcf, 0.0, 4.0),
            _score_high(_ratio(cash, debt) if debt > 0 else 2.0, 0.1, 1.2),
        ]
    )


def _value_score(
    model: str,
    trailing_pe: float | None,
    forward_pe: float | None,
    price_to_book: float | None,
    fcf_yield: float | None,
    normalized_fcf_yield: float | None,
) -> float | None:
    if model in {"bank", "insurance", "financial"}:
        return _average([_score_low(trailing_pe, 8.0, 28.0), _score_low(price_to_book, 0.8, 3.5)])
    yield_input = normalized_fcf_yield if model == "energy" else fcf_yield
    pe_high = 55.0 if model in {"software", "technology"} else 35.0
    return _average(
        [
            _score_low(forward_pe, 12.0, pe_high),
            _score_low(trailing_pe, 10.0, pe_high + 10.0),
            _score_high(_percent(yield_input), 1.0, 7.0),
        ]
    )


def _earnings_score(
    revenue_growth: float | None,
    income_growth: float | None,
    filing: dict[str, Any],
    quote: dict[str, Any],
) -> float | None:
    recency = _days_since(filing.get("filed_at")) if filing else None
    recency_score = 85.0 if recency is not None and recency <= 120 else 65.0 if recency is not None and recency <= 220 else 40.0
    return _average(
        [
            _score_high(revenue_growth, -10.0, 20.0),
            _score_high(income_growth, -25.0, 30.0),
            _score_high(_number(quote.get("eps_forward_growth_pct")), -10.0, 25.0),
            recency_score,
        ]
    )


def _research_decision(
    action: Any,
    decision_score: float | None,
    quality: float | None,
    value: float | None,
    strength: float | None,
    earnings: float | None,
    model: str,
    has_comparable_earnings: bool,
) -> str:
    if action == "sell_avoid" or (decision_score is not None and decision_score < 40):
        return "avoid_review"
    if model in {"bank", "insurance", "reit"} and action == "buy_candidate":
        return "specialist_review"
    if action == "buy_candidate" and not has_comparable_earnings:
        return "wait_for_earnings"
    if (
        action == "buy_candidate"
        and (decision_score or 0) >= 66
        and (quality or 0) >= 55
        and (value or 0) >= 40
        and (strength or 0) >= 45
        and (earnings or 0) >= 50
    ):
        return "research_buy"
    if (quality or 0) >= 60 and (value or 0) < 40:
        return "wait_for_value"
    if (earnings or 0) < 40:
        return "wait_for_earnings"
    return "hold_watch"


def _earnings_assessment(revenue_growth: float | None, income_growth: float | None, net_income: float | None) -> str:
    if net_income is not None and net_income < 0:
        return "Loss-making; thesis requires stronger evidence"
    if revenue_growth is None and income_growth is None:
        return "Insufficient comparable filing history"
    if (revenue_growth or 0) >= 5 and (income_growth or 0) >= 5:
        return "Growth and earnings improved"
    if (revenue_growth or 0) < 0 and (income_growth or 0) < 0:
        return "Revenue and earnings weakened"
    return "Mixed earnings report"


def _takeaways(
    model: str,
    assessment: str,
    revenue_growth: float | None,
    income_growth: float | None,
    metrics: dict[str, Any],
    quote: dict[str, Any],
    valuation_model: str,
) -> list[str]:
    rows = [assessment]
    growth_parts = []
    if revenue_growth is not None:
        growth_parts.append(f"revenue {revenue_growth:+.1f}% YoY")
    if income_growth is not None:
        growth_parts.append(f"net income {income_growth:+.1f}% YoY")
    if growth_parts:
        rows.append("Latest comparable period: " + ", ".join(growth_parts) + ".")
    if model in {"bank", "insurance", "financial"}:
        roe = metrics.get("roe_pct")
        pb = _positive(quote.get("price_to_book"))
        if roe is not None or pb is not None:
            rows.append(f"Financial lens: ROE {roe if roe is not None else 'n/a'}%, P/B {pb if pb is not None else 'n/a'}x.")
    else:
        fcf_yield = metrics.get("normalized_fcf_yield_pct") if model == "energy" else metrics.get("fcf_yield_pct")
        roic = metrics.get("roic_proxy_pct")
        if fcf_yield is not None or roic is not None:
            rows.append(f"Cash-return lens: FCF yield {fcf_yield if fcf_yield is not None else 'n/a'}%, ROIC proxy {roic if roic is not None else 'n/a'}%.")
    if len(rows) < 3:
        rows.append(valuation_model + ".")
    return rows


def _risks(model: str, metrics: dict[str, Any], quote: dict[str, Any], assessment: str) -> list[str]:
    risks: list[str] = []
    if model == "bank":
        risks.append("Confirm CET1 capital, charge-offs and deposit funding before acting.")
    elif model == "insurance":
        risks.append("Confirm reserve adequacy and combined ratio before acting.")
    elif model == "reit":
        risks.append("Confirm FFO/AFFO, occupancy and debt maturities before acting.")
    elif model == "software":
        risks.append("Confirm stock-based compensation, dilution and recurring-revenue durability.")
    elif model == "energy":
        risks.append("Low P/E can reflect peak-cycle commodity earnings; normalized cash flow controls the decision.")
    pe = _positive(quote.get("forward_pe")) or _positive(quote.get("trailing_pe"))
    if pe is not None and pe > 45:
        risks.append(f"Valuation is demanding at approximately {pe:.1f}x earnings.")
    debt_to_equity = metrics.get("debt_to_equity")
    if debt_to_equity is not None and debt_to_equity > 2:
        risks.append(f"Debt-to-equity is elevated at {debt_to_equity:.1f}x.")
    if "weakened" in assessment.lower():
        risks.append("Do not treat the price decline as a dip until operating deterioration stabilizes.")
    if not risks:
        risks.append("Review company-specific competition, management and concentration before sizing a position.")
    return risks


def _median_fcf(cfo: list[dict[str, Any]], capex: list[dict[str, Any]]) -> float | None:
    cfo_by_end = {row["end"]: _number(row.get("val")) for row in cfo}
    capex_by_end = {row["end"]: abs(_number(row.get("val")) or 0.0) for row in capex}
    values = [value - capex_by_end[end] for end, value in cfo_by_end.items() if value is not None and end in capex_by_end]
    return statistics.median(values[:3]) if values else None


def _decision_label(decision: str) -> str:
    return {
        "research_buy": "Research buy",
        "hold_watch": "Hold / watch",
        "wait_watch": "Wait / watch",
        "wait_for_value": "Wait for value",
        "wait_for_earnings": "Wait for earnings",
        "specialist_review": "Specialist review",
        "avoid_review": "Avoid / sell review",
    }.get(decision, "Needs review")


def _normalized_ticker(ticker: str) -> str:
    return ticker.strip().upper().replace(".", "-")


def _latest_value(series: list[dict[str, Any]]) -> float | None:
    return _number(series[0].get("val")) if series else None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in {None, 0}:
        return None
    return numerator / denominator


def _bounded_ratio(numerator: float | None, denominator: float | None, low: float, high: float) -> float | None:
    value = _ratio(numerator, denominator)
    return min(max(value, low), high) if value is not None else None


def _score_high(value: float | None, low: float, high: float) -> float | None:
    if value is None:
        return None
    if high <= low:
        return 50.0
    return min(max((value - low) / (high - low) * 100.0, 0.0), 100.0)


def _score_low(value: float | None, low: float, high: float) -> float | None:
    score = _score_high(value, low, high)
    return 100.0 - score if score is not None else None


def _average(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None


def _weighted_average(values: list[tuple[float | None, float]]) -> float | None:
    present = [(value, weight) for value, weight in values if value is not None]
    weight_sum = sum(weight for _, weight in present)
    return sum(value * weight for value, weight in present) / weight_sum if weight_sum else None


def _positive(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in {float("inf"), float("-inf")} else None


def _round(value: float | None, digits: int = 1) -> float | None:
    return round(value, digits) if value is not None else None


def _percent(value: float | None) -> float | None:
    return _round(value * 100.0) if value is not None else None


def _days_since(value: Any) -> int | None:
    if not value:
        return None
    try:
        return (datetime.now(timezone.utc).date() - date.fromisoformat(str(value))).days
    except ValueError:
        return None


def _at(values: list[Any], index: int) -> Any:
    return values[index] if index < len(values) else None
