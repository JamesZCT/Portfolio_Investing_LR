# Research Sources Integration

This project keeps market data, rule outputs, and private research inputs separate.

## Current Source Layers

1. Price, quote, and backtest data
- Source: yfinance/Yahoo through the Python snapshot exporter.
- Role: primary quantitative evidence.
- Output: `dashboard.json`, `backtest.json`, `ohlc.json`, `quotes.json`, `strategies.json`.

2. Public RSS/news sentiment
- Source: Google News RSS queries.
- Role: broad headline tone and theme detection.
- Output: `sentiment.json`.

3. Optional local LLM overlay
- Source: Ollama or an OpenAI-compatible local/private endpoint.
- Role: summarize and reconcile price evidence, headlines, and research notes.
- Default: local Ollama, no cloud token spend.

4. Private research overlay
- Source: local normalized exports from Gmail, Substack, PDFs, or notes.
- Role: investor color, questions, watchlist emphasis, and risk posture.
- Output: compact metadata only inside `sentiment.json`; raw emails should never be committed.

## Lance Roberts / RIA Workflow

Lance Roberts and Real Investment Advice are best used as a technical and macro-risk overlay, not as an automatic trade signal.

Recommended use:

- Extract newsletter subject, date, source, URL, short summary, and selected body text into a private local folder.
- Set `RESEARCH_DIGEST_DIR` to that folder before the scheduled snapshot run.
- Let the exporter score the notes for risk-on/risk-off stance and themes such as technical trend, risk management, rates/macro, breadth/positioning, and AI/semiconductors.
- Let the local LLM compare those notes against price trend, portfolio rules, concentration limits, and current drawdown.

Avoid:

- Committing raw email bodies, paid newsletter content, or private Substack content to the public repo.
- Treating any single commentator as the final decision rule.
- Letting commentary override position-size caps, stop rules, liquidity constraints, or trend evidence.

## Private Digest File Format

Put `.json`, `.md`, or `.txt` files in a private ignored folder such as:

```powershell
mkdir C:\portfolio-research-digest
$env:RESEARCH_DIGEST_DIR="C:\portfolio-research-digest"
```

The self-hosted GitHub Actions workflow defaults to `C:\portfolio-research-digest`. You can override it with a repository variable named `RESEARCH_DIGEST_DIR`.

Preferred JSON shape:

```json
[
  {
    "title": "Daily market commentary title",
    "source": "Lance Roberts / RIA",
    "published": "2026-07-14T12:00:00Z",
    "url": "https://example.com/original-post",
    "summary": "Short private summary or snippet you are comfortable processing locally.",
    "body": "Optional fuller private text. Do not commit this file."
  }
]
```

The public output keeps only compact fields: title, source, published date, link, summary excerpt, themes, stance label, and matched tickers.

## Gmail Ingestion Plan

The current Codex session does not expose callable Gmail search/read tools, so the safest immediate path is local export:

1. In Gmail, search for relevant sender/newsletter terms:
   - `from:(lance OR realinvestmentadvice) newer_than:30d`
   - `("Lance Roberts" OR "Real Investment Advice" OR "RIA") newer_than:30d`
2. Export or copy the selected messages into normalized JSON files in `private/research_digest`.
3. The scheduled 3090 Ti workflow reads that private folder via `RESEARCH_DIGEST_DIR`.

When Gmail connector tools become available, the next upgrade is a private local script that searches Gmail daily, normalizes the latest matching emails, writes them to `private/research_digest`, then runs the existing snapshot exporter. That should live in a private repo or local-only automation, not the public demo repo.

## Other Reputable Source Candidates

Use multiple sources with different biases and time horizons:

- Yardeni Research: macro, earnings, and market-indicator charts.
- A Wealth of Common Sense / Ben Carlson: behavioral and asset-allocation perspective.
- JPMorgan Guide to the Markets: broad macro and allocation reference.
- Schwab Market Perspective: retail-accessible macro and sector commentary.
- BlackRock Investment Institute: asset allocation and macro regime framing.
- FRED / Federal Reserve data: primary macro time series.
- BLS, BEA, Treasury, and SEC filings: primary economic and company data.

The best project design is not to ask one source for a final answer. Use source disagreement as a feature:

- Price/rules decide risk limits.
- Primary data confirms macro and fundamentals.
- News and newsletters explain narratives and watch items.
- Local LLM summarizes conflicts and generates questions.
