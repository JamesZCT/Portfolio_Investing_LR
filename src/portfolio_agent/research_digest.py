from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from email import policy
from email.parser import BytesParser
from html import unescape
from pathlib import Path
from typing import Any
import json
import mailbox
import os
import re


@dataclass
class ResearchNote:
    title: str
    source: str
    published: str | None
    url: str
    summary: str
    stance_score: float
    stance_label: str
    themes: list[str]
    tickers: list[str]


SOURCE_HINTS = {
    "lance": "Lance Roberts / RIA",
    "realinvestmentadvice": "Real Investment Advice",
    "ria": "Real Investment Advice",
    "substack": "Substack",
}

RISK_ON_TERMS = {
    "buy signal": 0.7,
    "risk on": 0.7,
    "breadth improves": 0.6,
    "earnings growth": 0.5,
    "support held": 0.5,
    "breakout": 0.5,
    "uptrend": 0.4,
    "constructive": 0.4,
}

RISK_OFF_TERMS = {
    "sell signal": -0.7,
    "risk off": -0.7,
    "overbought": -0.5,
    "divergence": -0.5,
    "breakdown": -0.6,
    "recession": -0.5,
    "bearish": -0.5,
    "trim": -0.4,
    "hedge": -0.4,
    "raise cash": -0.6,
}

THEME_TERMS = {
    "technical trend": ("moving average", "macd", "rsi", "overbought", "oversold", "support", "resistance"),
    "risk management": ("trim", "hedge", "stop", "cash", "rebalance", "risk"),
    "earnings": ("earnings", "margins", "guidance", "profits", "revenue"),
    "rates / macro": ("fed", "rates", "treasury", "inflation", "cpi", "jobs"),
    "breadth / positioning": ("breadth", "sentiment", "positioning", "flows", "crowded"),
    "AI / semiconductors": ("ai", "nvidia", "semiconductor", "chips", "data center"),
}


def build_research_overlay(market: str, tickers: list[str], max_items: int = 12) -> dict[str, Any]:
    directory = os.getenv("RESEARCH_DIGEST_DIR")
    if not directory:
        return _empty_overlay("not_configured", "Set RESEARCH_DIGEST_DIR to a private folder of normalized Gmail/Substack exports.")

    root = Path(directory).expanduser()
    if not root.exists():
        return _empty_overlay("missing_directory", f"Research digest directory not found: {root}")

    notes = load_research_notes(root, tickers=tickers, max_items=max_items)
    if not notes:
        return _empty_overlay("empty", "No supported research notes were found in the configured directory.")

    score = sum(note.stance_score for note in notes) / len(notes)
    theme_counts: dict[str, int] = {}
    for note in notes:
        for theme in note.themes:
            theme_counts[theme] = theme_counts.get(theme, 0) + 1

    return {
        "status": "available",
        "source_mode": "private_digest",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": market,
        "note_count": len(notes),
        "overall_stance_score": score,
        "overall_stance_label": _label_for_score(score),
        "top_themes": [
            {"theme": theme, "count": count}
            for theme, count in sorted(theme_counts.items(), key=lambda item: item[1], reverse=True)[:6]
        ],
        "notes": [asdict(note) for note in notes],
        "decision_use": (
            "Use as a research overlay for questions, risk posture, and watchlist emphasis. "
            "Do not let newsletter commentary override price trend, position-size, liquidity, or risk controls."
        ),
    }


def load_research_notes(root: Path, tickers: list[str], max_items: int = 12) -> list[ResearchNote]:
    candidates = sorted(
        [path for path in root.rglob("*") if path.suffix.lower() in {".json", ".md", ".txt", ".eml", ".mbox"}],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    notes: list[ResearchNote] = []
    for path in candidates:
        for item in _records_from_file(path):
            note = _note_from_record(item, path, tickers)
            if note is not None:
                notes.append(note)
            if len(notes) >= max_items:
                return notes
    return notes


def _records_from_file(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".eml":
        try:
            message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        except (OSError, ValueError):
            return []
        return [_record_from_email(message)]

    if path.suffix.lower() == ".mbox":
        try:
            messages = mailbox.mbox(path, create=False)
            return [
                _record_from_email(BytesParser(policy=policy.default).parsebytes(message.as_bytes()))
                for message in messages
            ]
        except (OSError, ValueError, mailbox.Error):
            return []

    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("messages", "emails", "posts", "items", "notes"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [data]
        return []

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    title = path.stem.replace("_", " ").replace("-", " ").strip()
    return [{"title": title, "body": text, "source": _source_from_text(f"{path} {text[:300]}")}]


def _record_from_email(message: Any) -> dict[str, Any]:
    body = ""
    try:
        preferred = message.get_body(preferencelist=("plain", "html"))
        if preferred is not None:
            body = preferred.get_content()
    except (AttributeError, KeyError, LookupError, UnicodeDecodeError):
        body = ""
    if not body:
        payload = message.get_payload(decode=True)
        if isinstance(payload, bytes):
            body = payload.decode(message.get_content_charset() or "utf-8", errors="replace")
    content_type = str(message.get_content_type() or "")
    if content_type == "text/html" or "<html" in body.lower():
        body = re.sub(r"<[^>]+>", " ", body)
    first_url = re.search(r"https?://[^\s<>\"]+", body)
    return {
        "title": str(message.get("Subject") or "Untitled email"),
        "sender": str(message.get("From") or "Email export"),
        "published": str(message.get("Date") or ""),
        "body": _clean_text(body),
        "url": first_url.group(0).rstrip(".,)") if first_url else "",
    }


def _note_from_record(record: dict[str, Any], path: Path, tickers: list[str]) -> ResearchNote | None:
    title = _clean_text(str(_first(record, "title", "subject", "headline") or path.stem))
    body = _clean_text(str(_first(record, "summary", "snippet", "body", "content", "text") or ""))
    if not title and not body:
        return None

    source = _clean_text(str(_first(record, "source", "sender", "from", "author", "publisher") or ""))
    source = source or _source_from_text(f"{title} {body} {path}")
    published = _normalize_date(_first(record, "published", "date", "received_at", "created_at"))
    url = _clean_text(str(_first(record, "url", "link", "permalink") or ""))
    combined = f"{title}. {body}"
    score = _score_research_text(combined)
    return ResearchNote(
        title=title[:180],
        source=source[:90],
        published=published,
        url=url,
        summary=_truncate(body or title, 260),
        stance_score=score,
        stance_label=_label_for_score(score),
        themes=_themes_for_text(combined),
        tickers=_tickers_for_text(combined, tickers),
    )


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _score_research_text(text: str) -> float:
    lowered = f" {_normalize(text)} "
    score = 0.0
    for term, weight in RISK_ON_TERMS.items():
        if _contains(lowered, term):
            score += weight
    for term, weight in RISK_OFF_TERMS.items():
        if _contains(lowered, term):
            score += weight
    return max(-1.0, min(1.0, score / 1.5))


def _themes_for_text(text: str) -> list[str]:
    lowered = _normalize(text)
    themes = [
        theme
        for theme, terms in THEME_TERMS.items()
        if any(_contains(f" {lowered} ", term) for term in terms)
    ]
    return themes or ["general research"]


def _tickers_for_text(text: str, tickers: list[str]) -> list[str]:
    lowered = f" {_normalize(text)} "
    matched = [ticker for ticker in tickers if _contains(lowered, ticker.lower())]
    return matched[:8]


def _source_from_text(text: str) -> str:
    lowered = text.lower()
    for hint, source in SOURCE_HINTS.items():
        if hint in lowered:
            return source
    return "Private research digest"


def _empty_overlay(status: str, note: str) -> dict[str, Any]:
    return {
        "status": status,
        "source_mode": "none",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note_count": 0,
        "overall_stance_score": 0.0,
        "overall_stance_label": "neutral",
        "top_themes": [],
        "notes": [],
        "note": note,
        "decision_use": "No private research overlay was applied.",
    }


def _label_for_score(score: float) -> str:
    if score >= 0.15:
        return "risk_on"
    if score <= -0.15:
        return "risk_off"
    return "neutral"


def _normalize_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            return None
    raw = str(value)
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        return raw


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _normalize(text: str) -> str:
    return _clean_text(text).lower()


def _contains(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", text) is not None


def _truncate(text: str, limit: int) -> str:
    clean = _clean_text(text)
    return clean if len(clean) <= limit else f"{clean[: limit - 1].rstrip()}..."
