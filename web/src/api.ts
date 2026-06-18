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

export type DashboardPayload = {
  mode: string;
  lookback_days: number;
  price_as_of: string | null;
  market_regime: MarketRegime;
  signals: SectorSignal[];
  suggestions: Suggestion[];
  risk_predictions: RiskPrediction[];
  positions: Record<string, number>;
  target_weights: Record<string, number>;
  sector_weights: Record<string, number>;
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

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export async function fetchDashboard(mode: string, lookbackDays: number): Promise<DashboardPayload> {
  const params = new URLSearchParams({ mode, lookback_days: String(lookbackDays) });
  const response = await fetch(`${API_BASE}/api/dashboard?${params.toString()}`);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function fetchBacktest(mode: string, lookbackDays: number): Promise<BacktestPayload> {
  const params = new URLSearchParams({ mode, lookback_days: String(lookbackDays) });
  const response = await fetch(`${API_BASE}/api/backtest?${params.toString()}`);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function fetchStrategyComparison(mode: string, lookbackDays: number): Promise<StrategyComparisonPayload> {
  const params = new URLSearchParams({ mode, lookback_days: String(Math.max(lookbackDays, 900)) });
  const response = await fetch(`${API_BASE}/api/strategies/compare?${params.toString()}`);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function fetchRules(): Promise<StrategyRule[]> {
  const response = await fetch(`${API_BASE}/api/rules`);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  const data = await response.json();
  return data.rules;
}

export async function fetchOhlc(mode: string, lookbackDays: number, ticker: string): Promise<OhlcPoint[]> {
  const params = new URLSearchParams({ mode, lookback_days: String(Math.min(lookbackDays, 1200)), ticker });
  const response = await fetch(`${API_BASE}/api/ohlc?${params.toString()}`);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  const data = await response.json();
  return data.ohlc;
}

async function readError(response: Response): Promise<string> {
  try {
    const data = await response.json();
    return data.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
}
