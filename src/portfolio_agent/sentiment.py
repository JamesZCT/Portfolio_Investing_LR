from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
import json
import os
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import re
import xml.etree.ElementTree as ET

from .config import AppConfig
from .research_digest import build_research_overlay


@dataclass
class NewsArticle:
    ticker: str
    title: str
    source: str
    published: str | None
    link: str
    sentiment_score: float
    sentiment_label: str
    themes: list[str]
    matched_terms: list[str]


POSITIVE_TERMS = {
    "beat": 1.0,
    "beats": 1.0,
    "upgrade": 0.9,
    "upgraded": 0.9,
    "raises": 0.8,
    "raised": 0.8,
    "growth": 0.7,
    "surge": 0.9,
    "rally": 0.8,
    "record": 0.7,
    "profit": 0.6,
    "profits": 0.6,
    "strong": 0.7,
    "optimism": 0.7,
    "resilient": 0.6,
    "buyback": 0.6,
    "dividend": 0.5,
    "easing": 0.6,
    "stimulus": 0.6,
    "recovery": 0.6,
    "ai": 0.4,
}

NEGATIVE_TERMS = {
    "miss": -1.0,
    "misses": -1.0,
    "downgrade": -0.9,
    "downgraded": -0.9,
    "cuts": -0.8,
    "cut": -0.8,
    "falls": -0.8,
    "slumps": -0.9,
    "plunge": -1.0,
    "selloff": -0.9,
    "sell-off": -0.9,
    "weak": -0.7,
    "loss": -0.7,
    "losses": -0.7,
    "warning": -0.8,
    "probe": -0.7,
    "lawsuit": -0.7,
    "ban": -0.8,
    "tariff": -0.7,
    "inflation": -0.5,
    "recession": -0.8,
    "default": -0.9,
    "crackdown": -0.8,
    "risk": -0.4,
}

THEME_TERMS: dict[str, tuple[str, ...]] = {
    "AI / semiconductors": ("ai", "artificial intelligence", "chip", "semiconductor", "nvidia", "data center"),
    "rates / inflation": ("fed", "rate", "rates", "yield", "inflation", "cpi", "treasury"),
    "earnings": ("earnings", "revenue", "profit", "guidance", "margin", "forecast"),
    "China / policy": ("china", "hong kong", "beijing", "policy", "stimulus", "tariff"),
    "consumer demand": ("consumer", "retail", "spending", "demand", "sales"),
    "regulation / legal": ("regulator", "regulation", "probe", "lawsuit", "antitrust", "ban"),
    "macro risk": ("recession", "default", "geopolitical", "war", "slowdown", "liquidity"),
}

MARKET_QUERIES = {
    "us": ["US stock market", "S&P 500 market outlook", "Federal Reserve stocks"],
    "hk": ["Hong Kong stock market", "Hang Seng market outlook", "China internet stocks Hong Kong"],
}

TICKER_NAME_HINTS = {
    "AAPL": "Apple",
    "AVGO": "Broadcom",
    "COST": "Costco",
    "JNJ": "Johnson Johnson",
    "JPM": "JPMorgan",
    "MSFT": "Microsoft",
    "NVDA": "Nvidia",
    "SPY": "S&P 500 ETF",
    "UNH": "UnitedHealth",
    "V": "Visa",
    "XOM": "Exxon Mobil",
    "0001.HK": "CK Hutchison",
    "0005.HK": "HSBC Holdings Hong Kong",
    "0388.HK": "Hong Kong Exchanges HKEX",
    "0700.HK": "Tencent Holdings",
    "0823.HK": "Link REIT",
    "0939.HK": "China Construction Bank",
    "1299.HK": "AIA Group",
    "1810.HK": "Xiaomi",
    "2800.HK": "Tracker Fund of Hong Kong",
    "3690.HK": "Meituan",
    "9988.HK": "Alibaba Hong Kong",
}


def build_sentiment_payload(
    config: AppConfig,
    market: str,
    market_regime: Any | None = None,
    mode: str = "real",
    max_articles: int = 36,
) -> dict[str, Any]:
    tickers = _analysis_tickers(config)
    if mode == "sandbox":
        articles = _sandbox_articles(market, tickers)
        source_mode = "sandbox"
    else:
        articles = fetch_news_articles(market, tickers, max_articles=max_articles)
        source_mode = "rss" if articles else "unavailable"

    summary = summarize_sentiment(articles, market_regime)
    summary["source_mode"] = source_mode
    research_overlay = build_research_overlay(market, tickers)
    summary["research_overlay"] = research_overlay
    summary["ai_layer"] = _ai_layer_status(articles, summary, config)
    return {
        "market": market,
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "ticker_sentiment": ticker_sentiment(articles, tickers),
        "articles": [asdict(article) for article in articles[:max_articles]],
    }


def fetch_news_articles(market: str, tickers: list[str], max_articles: int = 36) -> list[NewsArticle]:
    queries = list(MARKET_QUERIES.get(market, MARKET_QUERIES["us"]))
    queries.extend(_ticker_query(ticker) for ticker in tickers[:10])

    seen: set[str] = set()
    articles: list[NewsArticle] = []
    for query in queries:
        for item in _fetch_google_news_rss(query):
            title = _clean_text(item.get("title", ""))
            if not title:
                continue
            key = re.sub(r"\W+", "", title).lower()
            if key in seen:
                continue
            seen.add(key)
            ticker = _match_ticker(title, tickers, fallback=_query_to_ticker(query, tickers))
            score, label, matched_terms = score_text(title)
            articles.append(
                NewsArticle(
                    ticker=ticker,
                    title=title,
                    source=item.get("source") or "Google News",
                    published=item.get("published"),
                    link=item.get("link", ""),
                    sentiment_score=score,
                    sentiment_label=label,
                    themes=themes_for_text(title),
                    matched_terms=matched_terms,
                )
            )
            if len(articles) >= max_articles:
                return articles
    return articles


def summarize_sentiment(articles: list[NewsArticle], market_regime: Any | None = None) -> dict[str, Any]:
    scores = [article.sentiment_score for article in articles]
    score = sum(scores) / len(scores) if scores else 0.0
    label = _label_for_score(score)
    positive_count = sum(1 for article in articles if article.sentiment_label == "positive")
    negative_count = sum(1 for article in articles if article.sentiment_label == "negative")
    neutral_count = len(articles) - positive_count - negative_count
    theme_counts: dict[str, int] = {}
    for article in articles:
        for theme in article.themes:
            theme_counts[theme] = theme_counts.get(theme, 0) + 1

    trend_state = getattr(market_regime, "trend_state", "unknown") if market_regime is not None else "unknown"
    momentum = float(getattr(market_regime, "momentum", 0.0) or 0.0) if market_regime is not None else 0.0
    drawdown = float(getattr(market_regime, "drawdown", 0.0) or 0.0) if market_regime is not None else 0.0
    market_bias = _market_bias(score, trend_state, momentum, drawdown)
    confidence = min(0.9, 0.3 + min(len(articles), 30) / 60 + min(abs(score), 1.0) * 0.15)
    return {
        "overall_score": score,
        "label": label,
        "confidence": confidence,
        "article_count": len(articles),
        "positive_count": positive_count,
        "negative_count": negative_count,
        "neutral_count": neutral_count,
        "top_themes": [
            {"theme": theme, "count": count}
            for theme, count in sorted(theme_counts.items(), key=lambda item: item[1], reverse=True)[:5]
        ],
        "forecast_bias": market_bias["forecast_bias"],
        "investment_posture": market_bias["investment_posture"],
        "recommended_action": market_bias["recommended_action"],
        "rationale": market_bias["rationale"],
    }


def ticker_sentiment(articles: list[NewsArticle], tickers: list[str]) -> list[dict[str, Any]]:
    rows = []
    for ticker in tickers:
        ticker_articles = [article for article in articles if article.ticker == ticker]
        if not ticker_articles:
            continue
        score = sum(article.sentiment_score for article in ticker_articles) / len(ticker_articles)
        rows.append(
            {
                "ticker": ticker,
                "score": score,
                "label": _label_for_score(score),
                "article_count": len(ticker_articles),
                "top_headlines": [article.title for article in ticker_articles[:3]],
            }
        )
    return sorted(rows, key=lambda row: (abs(float(row["score"])), int(row["article_count"])), reverse=True)


def score_text(text: str) -> tuple[float, str, list[str]]:
    lowered = f" {_normalize_text(text)} "
    matched: list[str] = []
    score = 0.0
    for term, weight in POSITIVE_TERMS.items():
        if _contains_term(lowered, term):
            score += weight
            matched.append(term)
    for term, weight in NEGATIVE_TERMS.items():
        if _contains_term(lowered, term):
            score += weight
            matched.append(term)
    clamped = max(-1.0, min(1.0, score / 2.5))
    return clamped, _label_for_score(clamped), matched[:8]


def themes_for_text(text: str) -> list[str]:
    lowered = _normalize_text(text)
    themes = [
        theme
        for theme, terms in THEME_TERMS.items()
        if any(_contains_term(f" {lowered} ", term) for term in terms)
    ]
    return themes or ["general market"]


def _fetch_google_news_rss(query: str) -> list[dict[str, str]]:
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    request = Request(url, headers={"User-Agent": "portfolio-investing-lab/1.0"})
    try:
        with urlopen(request, timeout=8) as response:  # noqa: S310 - public RSS feed only
            raw = response.read(700_000)
    except Exception:
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    items: list[dict[str, str]] = []
    for item in root.findall("./channel/item")[:8]:
        source_node = item.find("source")
        pub_date = item.findtext("pubDate") or ""
        items.append(
            {
                "title": item.findtext("title") or "",
                "link": item.findtext("link") or "",
                "source": source_node.text if source_node is not None else "",
                "published": _normalize_pub_date(pub_date),
            }
        )
    return items


def _analysis_tickers(config: AppConfig) -> list[str]:
    tickers = [config.universe.benchmark]
    tickers.extend(ticker for ticker in config.universe.positions if ticker != "CASH")
    deduped: list[str] = []
    for ticker in tickers:
        if ticker not in deduped:
            deduped.append(ticker)
    return deduped


def _ticker_query(ticker: str) -> str:
    return f"{TICKER_NAME_HINTS.get(ticker, ticker)} stock"


def _query_to_ticker(query: str, tickers: list[str]) -> str:
    for ticker in tickers:
        if TICKER_NAME_HINTS.get(ticker, ticker).lower() in query.lower():
            return ticker
    return "MARKET"


def _match_ticker(title: str, tickers: list[str], fallback: str) -> str:
    lowered = _normalize_text(title)
    for ticker in tickers:
        hint = TICKER_NAME_HINTS.get(ticker, ticker).lower()
        if _contains_term(f" {lowered} ", ticker.lower()) or hint.lower() in lowered:
            return ticker
    return fallback


def _market_bias(score: float, trend_state: str, momentum: float, drawdown: float) -> dict[str, Any]:
    bearish_trend = trend_state == "bearish"
    bullish_trend = trend_state == "bullish"
    if bearish_trend and score < -0.1:
        return {
            "forecast_bias": "risk_off",
            "investment_posture": "defensive",
            "recommended_action": "keep cash buffer high, trim stretched or high-risk holdings before adding exposure",
            "rationale": "News tone is negative while the benchmark trend is below its long moving average.",
        }
    if bearish_trend and score >= 0.15:
        return {
            "forecast_bias": "watch_for_bottoming",
            "investment_posture": "selective",
            "recommended_action": "avoid broad buying until price trend confirms; only consider phased adds to rule-approved names",
            "rationale": "News tone is improving, but trend rules have not confirmed a durable risk-on regime.",
        }
    if bullish_trend and score > 0.1 and momentum > 0:
        return {
            "forecast_bias": "risk_on",
            "investment_posture": "constructive",
            "recommended_action": "hold core exposure, add only where below target, and still trim concentration above caps",
            "rationale": "News tone and price trend both support risk exposure, subject to position-size discipline.",
        }
    if bullish_trend and score < -0.15:
        return {
            "forecast_bias": "late_cycle_caution",
            "investment_posture": "balanced",
            "recommended_action": "do not chase; tighten trims and review names with negative headlines",
            "rationale": "Price trend is positive, but news tone is deteriorating.",
        }
    if drawdown < -0.1:
        return {
            "forecast_bias": "fragile",
            "investment_posture": "defensive",
            "recommended_action": "prioritize liquidity and staged re-entry rules over one-shot buying",
            "rationale": "The benchmark remains in a meaningful drawdown even though news tone is mixed.",
        }
    return {
        "forecast_bias": "neutral",
        "investment_posture": "balanced",
        "recommended_action": "follow target weights and rule-based trims/adds; do not override price evidence with headlines alone",
        "rationale": "News and price evidence are mixed or not strong enough for a directional overlay.",
    }


def _ai_layer_status(articles: list[NewsArticle], summary: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    headlines = [article.title for article in articles[:10]]
    research_overlay = summary.get("research_overlay", {})
    research_notes = [
        {
            "title": note.get("title"),
            "source": note.get("source"),
            "stance": note.get("stance_label"),
            "themes": note.get("themes", []),
            "summary": note.get("summary"),
        }
        for note in research_overlay.get("notes", [])[:6]
        if isinstance(note, dict)
    ]
    prompt = (
        "You are a cautious portfolio research agent. Use the headlines, market-regime facts, "
        "private research notes when present, and rule-based portfolio constraints to explain market sentiment and produce a conditional, "
        "non-execution investment posture. Do not promise returns. Return JSON with sentiment, risks, "
        "watchlist, research-note conflicts, and recommended posture.\n\n"
        f"Benchmark: {config.universe.benchmark}\n"
        f"Rule engine posture: {summary['investment_posture']}\n"
        f"News score: {summary['overall_score']:.3f}\n"
        f"Private research overlay status: {research_overlay.get('status', 'unknown')}\n"
        f"Private research notes: {research_notes}\n"
        f"Headlines: {headlines}"
    )
    if os.getenv("LLM_SENTIMENT_ENABLED", "").lower() not in {"1", "true", "yes"}:
        return {
            "status": "heuristic_default",
            "provider": "none",
            "model": None,
            "analysis": None,
            "note": "LLM summarization is intentionally optional and currently disabled to avoid token costs.",
            "prompt_template": prompt,
        }

    model = os.getenv("LLM_SENTIMENT_MODEL")
    provider = os.getenv("LLM_SENTIMENT_PROVIDER", "ollama").lower()
    if not model:
        return {
            "status": "llm_not_configured",
            "provider": provider,
            "model": model,
            "analysis": None,
            "note": "Set LLM_SENTIMENT_MODEL before enabling LLM sentiment analysis.",
            "prompt_template": prompt,
        }

    if provider == "ollama":
        analysis = _call_ollama_model(prompt, model=model)
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return {
                "status": "llm_not_configured",
                "provider": "openai_compatible",
                "model": model,
                "analysis": None,
                "note": "Set OPENAI_API_KEY for the OpenAI-compatible provider, or use LLM_SENTIMENT_PROVIDER=ollama.",
                "prompt_template": prompt,
            }
        analysis = _call_openai_compatible_model(prompt, model=model, api_key=api_key)

    if analysis is None:
        return {
            "status": "llm_failed_fallback_to_heuristic",
            "provider": provider,
            "model": model,
            "analysis": None,
            "note": "The LLM call failed or returned an unsupported shape; heuristic analysis remains available.",
            "prompt_template": prompt,
        }
    return {
        "status": "llm_generated",
        "provider": provider,
        "model": model,
        "analysis": analysis,
        "note": "LLM output is a research overlay and should not override rule, risk, and price evidence by itself.",
        "prompt_template": prompt,
    }


def _call_ollama_model(prompt: str, model: str) -> str | None:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    timeout = float(os.getenv("LLM_SENTIMENT_TIMEOUT_SECONDS", "45"))
    payload = {
        "model": model,
        "stream": False,
        "think": os.getenv("LLM_SENTIMENT_THINK", "false").lower() in {"1", "true", "yes"},
        "messages": [
            {
                "role": "system",
                "content": "You produce cautious public-equity research commentary. Never present investment outcomes as guaranteed.",
            },
            {"role": "user", "content": prompt},
        ],
        "options": {
            "temperature": 0.2,
            "num_ctx": int(os.getenv("LLM_SENTIMENT_CONTEXT_TOKENS", "4096")),
            "num_predict": int(os.getenv("LLM_SENTIMENT_MAX_TOKENS", "700")),
        },
    }
    request = Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "portfolio-investing-lab/1.0"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - user-configured local endpoint
            data = json.loads(response.read(500_000))
    except Exception:
        return None
    content = data.get("message", {}).get("content")
    return content if isinstance(content, str) and content.strip() else None


def _call_openai_compatible_model(prompt: str, model: str, api_key: str) -> str | None:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    timeout = float(os.getenv("LLM_SENTIMENT_TIMEOUT_SECONDS", "45"))
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": "You produce cautious public-equity research commentary. Never present investment outcomes as guaranteed.",
            },
            {"role": "user", "content": prompt},
        ],
        "max_output_tokens": 700,
    }
    request = Request(
        f"{base_url}/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "portfolio-investing-lab/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - user-configured API endpoint
            data = json.loads(response.read(500_000))
    except Exception:
        return None

    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    output = data.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            for content in item.get("content", []) if isinstance(item, dict) else []:
                if isinstance(content, dict) and isinstance(content.get("text"), str):
                    parts.append(content["text"])
        return "\n".join(parts) if parts else None
    return None


def _sandbox_articles(market: str, tickers: list[str]) -> list[NewsArticle]:
    benchmark = tickers[0] if tickers else "MARKET"
    samples = [
        (benchmark, "Market breadth improves as investors weigh rates and earnings", 0.2),
        (benchmark, "Investors remain cautious after volatility and policy uncertainty", -0.25),
        (tickers[1] if len(tickers) > 1 else benchmark, "Analysts debate growth outlook after recent rally", 0.1),
        (tickers[2] if len(tickers) > 2 else benchmark, "Shares slip as traders watch guidance and margins", -0.2),
    ]
    return [
        NewsArticle(
            ticker=ticker,
            title=title,
            source="sandbox",
            published=datetime.now(timezone.utc).date().isoformat(),
            link="",
            sentiment_score=score,
            sentiment_label=_label_for_score(score),
            themes=themes_for_text(title),
            matched_terms=[],
        )
        for ticker, title, score in samples
    ]


def _label_for_score(score: float) -> str:
    if score >= 0.15:
        return "positive"
    if score <= -0.15:
        return "negative"
    return "neutral"


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text).lower()).strip()


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", text) is not None


def _normalize_pub_date(value: str) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except Exception:
        return value
