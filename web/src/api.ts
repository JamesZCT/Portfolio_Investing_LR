export type MarketRegime = {
  benchmark: string;
  price: number;
  trend_ma: number;
  trend_state: string;
  z: number;
  momentum: number;
  realized_vol: number;
  drawdown: number;
};

export type SectorSignal = {
  sector: string;
  etf: string;
  price: number;
  ma: number;
  std: number;
  z: number;
  pct_from_ma: number;
  status: string;
  trend_state: string;
  trend_ma: number;
  momentum: number;
  realized_vol: number;
};

export type Suggestion = {
  ticker: string;
  action: string;
  delta_weight: number;
  reason: string;
  rule_ids: string[];
};

export type RiskPrediction = {
  ticker: string;
  risk_probability: number;
  risk_level: string;
  model_version: string;
  features: Record<string, number>;
};

export type SeriesPoint = {
  date: string;
  value: number;
};

export type OptimizationRow = {
  priority: number;
  ticker: string;
  group: string;
  asset_type: string;
  action: "ADD" | "TRIM" | "HOLD";
  current_weight: number;
  target_weight: number;
  delta_weight: number;
  reason_en: string;
  reason_zh: string;
  rule_ids: string[];
};

export type OptimizationProfile = {
  id: string;
  name_en: string;
  name_zh: string;
  risk_level: "low" | "medium" | "high" | string;
  objective: string;
  objective_en: string;
  objective_zh: string;
  status: "optimized" | "fallback";
  fallback_reason: string | null;
  cash_weight: number;
  metrics: {
    annualized_return: number | null;
    annualized_volatility: number | null;
    sharpe_ratio: number | null;
    max_drawdown: number | null;
    turnover: number;
    estimated_transaction_cost: number;
  };
  rows: OptimizationRow[];
  missing_assets: string[];
  constraints: {
    long_only: boolean;
    max_single_weight: number;
    max_fund_weight: number;
    max_group_weight: number;
    group_constraints: string[];
    leverage: number;
  };
  evidence: {
    start_date: string | null;
    end_date: string | null;
    observations: number;
    basis_en: string;
    basis_zh: string;
  };
};

export type OptimizationPayload = {
  status: string;
  data_as_of?: string | null;
  lookback_days?: number;
  min_history_days?: number;
  transaction_cost_bps?: number;
  methodology: string;
  methodology_zh?: string;
  profiles: OptimizationProfile[];
};

export type DashboardPayload = {
  mode: string;
  lookback_days: number;
  price_as_of: string | null;
  snapshot?: {
    generated_at?: string;
    config_name?: string;
    is_example_config?: boolean;
    mode?: string;
    lookback_days?: number;
  };
  market_regime: MarketRegime;
  signals: SectorSignal[];
  suggestions: Suggestion[];
  risk_predictions: RiskPrediction[];
  positions: Record<string, number>;
  target_weights: Record<string, number>;
  sector_weights: Record<string, number>;
  advisor_summary: Array<{
    rank: number;
    severity: string;
    title: string;
    detail: string;
    rule_ids: string[];
  }>;
  recommended_distribution: Array<{
    ticker: string;
    sector: string;
    current_weight: number;
    target_weight: number;
    recommended_weight: number;
    delta_weight: number;
    action: string;
    reason: string;
    rule_ids: string[];
    priority: number;
  }>;
  optimization: OptimizationPayload;
  benchmark_series: SeriesPoint[];
  universe: {
    benchmark: string;
    sector_etfs: Record<string, string>;
    tickers: string[];
  };
};

export type BacktestPayload = {
  mode: string;
  lookback_days: number;
  metrics: Record<string, number>;
  equity_curve: Array<{ date: string; portfolio_value: number; daily_return: number }>;
  trades: Array<Record<string, string | number>>;
};

export type StrategyComparisonPayload = {
  mode: string;
  lookback_days: number;
  strategies: Array<{
    name: string;
    description: string;
    metrics: Record<string, number>;
    turnover: number;
    equity_curve: Array<{ date: string; portfolio_value: number; daily_return: number }>;
  }>;
};

export type StrategyRule = {
  rule_id: string;
  name: string;
  category: string;
  formula: string;
  action: string;
  rationale: string;
  evidence: string;
  implementation_status: string;
  source_url: string;
};

export type OhlcPoint = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type LatestQuote = {
  ticker: string;
  price: number;
  previous_close: number;
  change: number;
  change_pct: number;
  as_of: string;
  source: string;
};

export type SentimentPayload = {
  market: MarketProfile;
  mode: string;
  generated_at: string;
  summary: {
    overall_score: number;
    label: string;
    confidence: number;
    article_count: number;
    positive_count: number;
    negative_count: number;
    neutral_count: number;
    top_themes: Array<{ theme: string; count: number }>;
    forecast_bias: string;
    investment_posture: string;
    recommended_action: string;
    rationale: string;
    source_mode: string;
    ai_layer: {
      status: string;
      provider: string;
      model: string | null;
      analysis: string | null;
      note: string;
      prompt_template: string;
    };
    research_overlay?: ResearchOverlay;
    information_signs?: InformationSignsPayload;
  };
  ticker_sentiment: Array<{
    ticker: string;
    score: number;
    label: string;
    article_count: number;
    top_headlines: string[];
  }>;
  articles: Array<{
    ticker: string;
    title: string;
    source: string;
    published: string | null;
    link: string;
    sentiment_score: number;
    sentiment_label: string;
    themes: string[];
    matched_terms: string[];
  }>;
};

export type InformationSign = {
  title: string;
  source: string;
  source_tier: "primary" | "commentary" | string;
  published: string | null;
  url: string;
  category: string;
  signal: string;
  value: number | null;
  unit: string | null;
  why_it_matters: string;
  decision_use: "information_only" | string;
  portfolio_weight: number;
};

export type InformationSignsPayload = {
  status: string;
  generated_at: string;
  market: MarketProfile;
  source_mode: string;
  decision_policy: {
    portfolio_weight: number;
    rule: string;
  };
  source_status: Array<{
    source: string;
    url: string;
    status: string;
    item_count?: number;
    latest_published?: string | null;
    failed_series?: string[];
  }>;
  primary_signs: InformationSign[];
  commentary_signs: InformationSign[];
  sign_count: number;
};

export type MarketOpportunity = {
  ticker: string;
  name: string;
  exchange: string;
  action: "buy_candidate" | "hold_watch" | "sell_avoid";
  score: number;
  price: number;
  return_1y_pct: number;
  distance_ma50_pct: number;
  distance_ma200_pct: number;
  range_position: number;
  market_cap: number | null;
  average_volume_3m: number | null;
  trailing_pe: number | null;
  forward_pe?: number | null;
  price_to_book?: number | null;
  eps_ttm?: number | null;
  eps_forward?: number | null;
  eps_forward_growth_pct?: number | null;
  profitable?: boolean;
  next_earnings_date?: string | null;
  earnings_date_is_estimate?: boolean;
  analyst_rating?: string | null;
  range_width_pct: number;
  reason: string;
  research?: {
    status: "sec_fundamentals" | "quote_only";
    decision: string;
    decision_label: string;
    decision_score: number | null;
    confidence: "high" | "medium" | "low";
    sector: string;
    industry: string;
    business_model: string;
    valuation_model: string;
    scorecard: {
      quality: number | null;
      value: number | null;
      financial_strength: number | null;
      earnings: number | null;
      trend: number | null;
    };
    earnings: {
      assessment: string;
      latest_report_form: string | null;
      filed_at: string | null;
      period_end: string | null;
      report_url?: string | null;
      revenue_growth_yoy_pct: number | null;
      net_income_growth_yoy_pct: number | null;
      next_earnings_date: string | null;
    };
    metrics?: Record<string, number | null>;
    key_takeaways: string[];
    risks: string[];
    source: { name: string; url: string; as_of?: string | null };
    methodology_note?: string;
  };
};

export type MarketOpportunitiesPayload = {
  status: string;
  generated_at: string;
  market: MarketProfile;
  note?: string;
  source: { name: string; url: string; note?: string };
  universe: {
    definition: string;
    eligible_total: number;
    fetched_count: number;
    analyzed_count: number;
    coverage_ratio: number;
    latest_price_date: string | null;
  };
  methodology: {
    summary?: string;
    buy_rule?: string;
    sell_rule?: string;
    policy: string;
    sector_models?: Record<string, string>;
  };
  deep_research?: {
    status: string;
    researched_count: number;
    failed_count: number;
    note: string;
  };
  action_counts: Record<"buy_candidate" | "hold_watch" | "sell_avoid", number>;
  buy_candidates: MarketOpportunity[];
  hold_watch: MarketOpportunity[];
  sell_avoid: MarketOpportunity[];
};

export type ResearchOverlay = {
  status: string;
  source_mode: string;
  generated_at: string;
  note_count: number;
  overall_stance_score: number;
  overall_stance_label: string;
  top_themes: Array<{ theme: string; count: number }>;
  notes: Array<{
    title: string;
    source: string;
    published: string | null;
    url: string;
    summary: string;
    stance_score: number;
    stance_label: string;
    themes: string[];
    tickers: string[];
  }>;
  note?: string;
  decision_use: string;
};

export type HealthPayload = {
  generated_at: string;
  market: MarketProfile;
  mode: string;
  lookback_days: number;
  config_name: string;
  is_example_config: boolean;
  price_as_of: string | null;
  days_since_price: number | null;
  stale_price: boolean;
  quote_latest_as_of: string | null;
  news_article_count: number;
  sentiment_label: string;
  investment_posture: string;
  forecast_bias: string;
  llm_status: string;
  llm_provider: string;
  llm_model: string | null;
  research_overlay_status: string;
  research_overlay_note_count: number;
  information_signs_status: string;
  information_sign_count: number;
  market_screen_status: string;
  market_screen_analyzed_count: number;
  pipeline: Record<string, string>;
};

export type HistoryPayload = {
  generated_at: string;
  market: MarketProfile;
  retention_runs: number;
  runs: Array<{
    generated_at: string;
    market: string;
    price_as_of: string | null;
    sentiment_label: string;
    investment_posture: string;
    forecast_bias: string;
    news_article_count: number;
    llm_status: string;
    research_overlay_status: string;
    research_overlay_note_count: number;
    information_signs_status: string;
    information_sign_count: number;
    top_themes: Array<{ theme: string; count: number }>;
  }>;
};

export type HistoricalTrack = {
  id: string;
  name_en: string;
  name_zh: string;
  description_en: string;
  description_zh: string;
  metrics: {
    final_value: number;
    cagr: number;
    annualized_volatility: number;
    sharpe: number;
    max_drawdown: number;
    excess_cagr_vs_benchmark: number;
    drawdown_improvement_vs_benchmark: number;
  };
  turnover: number;
  rebalance_count: number;
  latest_holdings: string[];
  equity_curve: Array<{ date: string; portfolio_value: number; daily_return: number }>;
  selection_history?: Array<{
    date: string;
    reason: string;
    membership_count: number;
    price_eligible_count: number;
    selected: Array<{
      ticker: string;
      score: number;
      return_1y: number;
      distance_ma200: number;
    }>;
    market_regime: string;
    cash_weight: number;
  }>;
};

export type HistoricalValidationPayload = {
  status: "exploratory" | string;
  requested_years: number;
  source_start_date: string;
  evaluation_start_date: string;
  evaluation_end_date: string;
  data_as_of: string;
  benchmark: string;
  transaction_cost_bps: number;
  tracks: HistoricalTrack[];
  universe: {
    tickers: string[];
    size: number;
    definition_en: string;
    definition_zh: string;
  };
  integrity: {
    lookahead_protection: string;
    lookahead_protection_zh: string;
    transaction_costs_included: boolean;
    fundamental_layer_included: boolean;
    survivorship_bias: boolean;
    delisted_securities_included: boolean;
    claim_level: string;
  };
  limitations_en: string[];
  limitations_zh: string[];
  point_in_time_experiment?: {
    status: string;
    error?: string;
    evaluation_start_date?: string;
    evaluation_end_date?: string;
    benchmark?: string;
    transaction_cost_bps?: number;
    tracks?: HistoricalTrack[];
    bias_effect?: {
      survivor_minus_historical_cagr: number;
      survivor_minus_historical_sharpe: number;
    };
    universe_audit?: {
      membership_source: string;
      membership_source_url: string;
      membership_source_commit: string;
      membership_license: string;
      membership_is_official: boolean;
      membership_start_date: string;
      membership_end_date: string;
      unique_historical_members: number;
      final_members: number;
      removed_members_included: number;
      removed_members_with_price_history: number;
      rebalance_member_observations: number;
      price_eligible_observations: number;
      rebalance_price_coverage: number;
      requested_tickers?: number;
      tickers_with_any_price?: number;
      ticker_price_coverage?: number;
      downloaded_tickers?: number;
    };
    integrity?: Record<string, boolean | string>;
    limitations_en?: string[];
    limitations_zh?: string[];
  };
  academic_factor_evidence?: {
    status: string;
    error?: string;
    evaluation_start_date?: string;
    evaluation_end_date?: string;
    tracks?: Array<{
      id: string;
      name_en: string;
      name_zh: string;
      description_en: string;
      description_zh: string;
      metrics: {
        final_value: number;
        cagr: number;
        annualized_volatility: number;
        sharpe: number;
        max_drawdown: number;
        excess_cagr_vs_market: number;
      };
      equity_curve: Array<{ date: string; portfolio_value: number; daily_return: number }>;
    }>;
    source?: {
      name: string;
      url: string;
      momentum_portfolios_url: string;
      five_factors_url: string;
    };
    construction?: {
      rule_en: string;
      rule_zh: string;
      survivorship_bias_control: string;
    };
    limitations_en?: string[];
    limitations_zh?: string[];
  };
};

export type BootstrapPayload = {
  dashboard: DashboardPayload;
  backtest: BacktestPayload;
  strategyComparison: StrategyComparisonPayload;
  rules: StrategyRule[];
  ohlc: OhlcPoint[];
  quotes: LatestQuote[];
  sentiment: SentimentPayload;
};

export type MarketProfile = "us" | "hk";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";
const DATA_MODE = import.meta.env.VITE_DATA_MODE ?? "api";
const APP_BASE = import.meta.env.BASE_URL ?? "/";
export const IS_STATIC_DATA_MODE = DATA_MODE === "static";

export async function fetchDashboard(mode: string, lookbackDays: number, market: MarketProfile): Promise<DashboardPayload> {
  const params = new URLSearchParams({ mode, lookback_days: String(lookbackDays), market });
  return fetchJson<DashboardPayload>(`${API_BASE}/api/dashboard?${params.toString()}`, `/data/${market}/dashboard.json`);
}

export async function fetchBacktest(mode: string, lookbackDays: number, market: MarketProfile): Promise<BacktestPayload> {
  const params = new URLSearchParams({ mode, lookback_days: String(lookbackDays), market });
  return fetchJson<BacktestPayload>(`${API_BASE}/api/backtest?${params.toString()}`, `/data/${market}/backtest.json`);
}

export async function fetchStrategyComparison(
  mode: string,
  lookbackDays: number,
  market: MarketProfile
): Promise<StrategyComparisonPayload> {
  const params = new URLSearchParams({ mode, lookback_days: String(Math.max(lookbackDays, 900)), market });
  return fetchJson<StrategyComparisonPayload>(`${API_BASE}/api/strategies/compare?${params.toString()}`, `/data/${market}/strategies.json`);
}

export async function fetchRules(market: MarketProfile): Promise<StrategyRule[]> {
  const params = new URLSearchParams({ market });
  const data = await fetchJson<{ rules: StrategyRule[] }>(`${API_BASE}/api/rules?${params.toString()}`, `/data/${market}/rules.json`);
  return data.rules;
}

export async function fetchOhlc(mode: string, lookbackDays: number, ticker: string, market: MarketProfile): Promise<OhlcPoint[]> {
  const params = new URLSearchParams({ mode, lookback_days: String(Math.min(lookbackDays, 1200)), ticker, market });
  const data = await fetchJson<{ ohlc: OhlcPoint[] }>(`${API_BASE}/api/ohlc?${params.toString()}`, `/data/${market}/ohlc.json`);
  return data.ohlc;
}

export async function fetchLatestQuotes(tickers: string[], market: MarketProfile): Promise<LatestQuote[]> {
  const params = new URLSearchParams({ tickers: tickers.join(","), market });
  const data = await fetchJson<{ quotes: LatestQuote[] }>(`${API_BASE}/api/quotes?${params.toString()}`, `/data/${market}/quotes.json`);
  return data.quotes;
}

export async function fetchSentiment(market: MarketProfile): Promise<SentimentPayload> {
  const params = new URLSearchParams({ market });
  return fetchJson<SentimentPayload>(`${API_BASE}/api/news-sentiment?${params.toString()}`, `/data/${market}/sentiment.json`);
}

export async function fetchBootstrap(market: MarketProfile): Promise<BootstrapPayload> {
  const params = new URLSearchParams({ market });
  return fetchJson<BootstrapPayload>(`${API_BASE}/api/bootstrap?${params.toString()}`, `/data/${market}/bootstrap.json`);
}

export async function fetchHealth(market: MarketProfile): Promise<HealthPayload> {
  return fetchSnapshot<HealthPayload>(`/data/${market}/health.json`);
}

export async function fetchHistory(market: MarketProfile): Promise<HistoryPayload> {
  return fetchSnapshot<HistoryPayload>(`/data/${market}/history.json`);
}

export async function fetchMarketOpportunities(market: MarketProfile): Promise<MarketOpportunitiesPayload> {
  return fetchSnapshot<MarketOpportunitiesPayload>(`/data/${market}/market_opportunities.json`);
}

export async function fetchHistoricalValidation(market: MarketProfile): Promise<HistoricalValidationPayload> {
  const params = new URLSearchParams({ market, years: "10", mode: "real" });
  return fetchJson<HistoricalValidationPayload>(
    `${API_BASE}/api/historical-validation?${params.toString()}`,
    `/data/${market}/historical_validation.json`
  );
}

async function fetchJson<T>(apiUrl: string, snapshotUrl: string): Promise<T> {
  if (IS_STATIC_DATA_MODE) {
    return fetchSnapshot<T>(snapshotUrl);
  }

  try {
    const response = await fetch(apiUrl);
    if (!response.ok) {
      throw new Error(await readError(response));
    }
    return response.json();
  } catch (error) {
    try {
      return await fetchSnapshot<T>(snapshotUrl);
    } catch {
      throw error;
    }
  }
}

async function fetchSnapshot<T>(snapshotUrl: string): Promise<T> {
  const response = await fetch(resolveSnapshotUrl(snapshotUrl));
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

function resolveSnapshotUrl(snapshotUrl: string): string {
  if (/^https?:\/\//.test(snapshotUrl)) {
    return snapshotUrl;
  }
  const base = APP_BASE.endsWith("/") ? APP_BASE : `${APP_BASE}/`;
  return `${base}${snapshotUrl.replace(/^\/+/, "")}`;
}

async function readError(response: Response): Promise<string> {
  try {
    const data = await response.json();
    return data.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
}
