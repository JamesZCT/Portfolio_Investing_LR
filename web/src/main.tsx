import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Brain,
  FlaskConical,
  Gauge,
  Newspaper,
  RefreshCw,
  RotateCcw,
  Save,
  ShieldCheck,
  TrendingUp
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  BacktestPayload,
  DashboardPayload,
  LatestQuote,
  MarketProfile,
  OhlcPoint,
  SectorSignal,
  SentimentPayload,
  StrategyComparisonPayload,
  StrategyRule,
  fetchBacktest,
  fetchBootstrap,
  fetchDashboard,
  fetchLatestQuotes,
  fetchOhlc,
  fetchRules,
  fetchSentiment,
  fetchStrategyComparison
} from "./api";
import "./styles.css";

type MarketProfileInfo = {
  label: string;
  benchmarkName: string;
  currency: string;
  tickerConvention: string;
  dataTruth: string;
  portfolioTruth: string;
  instruments: Record<string, string>;
};

const MARKET_INFO: Record<MarketProfile, MarketProfileInfo> = {
  us: {
    label: "US Stocks",
    benchmarkName: "SPDR S&P 500 ETF Trust",
    currency: "USD",
    tickerConvention: "US exchange tickers use ordinary symbols such as AAPL, MSFT, SPY.",
    dataTruth: "Prices and history are real market data fetched through yfinance/Yahoo and published as API/static snapshots.",
    portfolioTruth: "The current holdings are an example research portfolio until you enter your own positions.",
    instruments: {
      AAPL: "Apple",
      AVGO: "Broadcom",
      COST: "Costco",
      JNJ: "Johnson & Johnson",
      JPM: "JPMorgan Chase",
      MSFT: "Microsoft",
      NVDA: "NVIDIA",
      SPY: "S&P 500 ETF",
      UNH: "UnitedHealth",
      V: "Visa",
      XOM: "Exxon Mobil",
      CASH: "Cash reserve",
      XLB: "Materials Select Sector SPDR",
      XLC: "Communication Services Select Sector SPDR",
      XLE: "Energy Select Sector SPDR",
      XLF: "Financials Select Sector SPDR",
      XLI: "Industrials Select Sector SPDR",
      XLK: "Technology Select Sector SPDR",
      XLP: "Consumer Staples Select Sector SPDR",
      XLRE: "Real Estate Select Sector SPDR",
      XLU: "Utilities Select Sector SPDR",
      XLV: "Health Care Select Sector SPDR",
      XLY: "Consumer Discretionary Select Sector SPDR"
    }
  },
  hk: {
    label: "Hong Kong",
    benchmarkName: "Tracker Fund of Hong Kong",
    currency: "HKD",
    tickerConvention: "HKEX tickers are numeric locally; yfinance/Yahoo writes them with a .HK suffix, for example 0700.HK.",
    dataTruth: "Prices and history are real Hong Kong market data fetched through yfinance/Yahoo and published as API/static snapshots.",
    portfolioTruth: "The portfolio weights are a sandbox/example HK portfolio, not your actual brokerage holdings.",
    instruments: {
      "0001.HK": "CK Hutchison Holdings",
      "0005.HK": "HSBC Holdings",
      "0388.HK": "Hong Kong Exchanges and Clearing",
      "0700.HK": "Tencent Holdings",
      "0823.HK": "Link REIT",
      "0939.HK": "China Construction Bank",
      "1299.HK": "AIA Group",
      "1810.HK": "Xiaomi",
      "2800.HK": "Tracker Fund of Hong Kong",
      "3690.HK": "Meituan",
      "9988.HK": "Alibaba Group",
      CASH: "Cash reserve"
    }
  }
};

function App() {
  const [market, setMarket] = useState<MarketProfile>("us");
  const [mode, setMode] = useState("real");
  const [lookbackDays, setLookbackDays] = useState(900);
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [backtest, setBacktest] = useState<BacktestPayload | null>(null);
  const [strategyComparison, setStrategyComparison] = useState<StrategyComparisonPayload | null>(null);
  const [rules, setRules] = useState<StrategyRule[]>([]);
  const [ohlc, setOhlc] = useState<OhlcPoint[]>([]);
  const [quotes, setQuotes] = useState<LatestQuote[]>([]);
  const [sentiment, setSentiment] = useState<SentimentPayload | null>(null);
  const [researchPositions, setResearchPositions] = useState<Record<string, number>>({});
  const [hoverCandle, setHoverCandle] = useState<OhlcPoint | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function applyResearchPositions(defaultPositions: Record<string, number>) {
    setResearchPositions(loadSavedPortfolio(market, defaultPositions));
  }

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const bootstrap = await tryBootstrap();
      if (bootstrap) {
        setDashboard(bootstrap.dashboard);
        setBacktest(bootstrap.backtest);
        setStrategyComparison(bootstrap.strategyComparison);
        setRules(bootstrap.rules);
        setOhlc(bootstrap.ohlc);
        setQuotes(bootstrap.quotes);
        setSentiment(bootstrap.sentiment);
        applyResearchPositions(bootstrap.dashboard.positions);
        setHoverCandle(null);
        return;
      }

      const [dash, bt, comparison] = await Promise.all([
        fetchDashboard(mode, lookbackDays, market),
        fetchBacktest(mode, Math.max(lookbackDays, 900), market),
        fetchStrategyComparison(mode, Math.max(lookbackDays, 900), market)
      ]);
      const quoteTickers = [dash.universe.benchmark, ...dash.universe.tickers].slice(0, 12);
      const [ruleList, ohlcRows, quoteRows] = await Promise.all([
        fetchRules(market),
        fetchOhlc(mode, Math.min(lookbackDays, 900), dash.universe.benchmark, market),
        fetchLatestQuotes(quoteTickers, market)
      ]);
      const sentimentPayload = await fetchSentiment(market);
      setDashboard(dash);
      setBacktest(bt);
      setStrategyComparison(comparison);
      setRules(ruleList);
      setOhlc(ohlcRows);
      setQuotes(quoteRows);
      setSentiment(sentimentPayload);
      applyResearchPositions(dash.positions);
      setHoverCandle(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function tryBootstrap() {
    if (mode !== "real" || lookbackDays !== 900) return null;
    try {
      return await fetchBootstrap(market);
    } catch {
      return null;
    }
  }

  useEffect(() => {
    void load();
  }, [market]);

  const topRisks = useMemo(
    () => [...(dashboard?.risk_predictions ?? [])].sort((a, b) => b.risk_probability - a.risk_probability).slice(0, 6),
    [dashboard]
  );
  const marketInfo = MARKET_INFO[market];

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Portfolio Investing Lab</p>
          <h1>Rules, risk, and historical evidence</h1>
        </div>
        <div className="controls">
          <label>
            <span>Market</span>
            <select value={market} onChange={(event) => setMarket(event.target.value as MarketProfile)}>
              <option value="us">US Stocks</option>
              <option value="hk">Hong Kong</option>
            </select>
          </label>
          <label>
            <span>Data</span>
            <select value={mode} onChange={(event) => setMode(event.target.value)}>
              <option value="real">Real historical</option>
              <option value="sandbox">Sandbox</option>
            </select>
          </label>
          <label>
            <span>Lookback</span>
            <select value={lookbackDays} onChange={(event) => setLookbackDays(Number(event.target.value))}>
              <option value={500}>500 days</option>
              <option value={900}>900 days</option>
              <option value={1200}>1200 days</option>
              <option value={1800}>1800 days</option>
            </select>
          </label>
          <button className="primary-button" onClick={() => void load()} disabled={loading}>
            <RefreshCw size={16} />
            {loading ? "Running" : "Refresh"}
          </button>
        </div>
      </header>

      {error ? (
        <section className="error-band">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </section>
      ) : null}

      {dashboard ? (
        <>
          <MarketTruthBanner marketInfo={marketInfo} dashboard={dashboard} quotes={quotes} />

          <section className="metric-grid">
            <MetricCard
              icon={<Gauge size={19} />}
              label="Market Regime"
              value={dashboard.market_regime.trend_state}
              detail={`${tickerLabel(dashboard.market_regime.benchmark, market)} ${money(dashboard.market_regime.price)} vs MA ${money(
                dashboard.market_regime.trend_ma
              )}`}
            />
            <MetricCard
              icon={<TrendingUp size={19} />}
              label="Momentum"
              value={percent(dashboard.market_regime.momentum)}
              detail={`Drawdown ${percent(dashboard.market_regime.drawdown)}`}
            />
            <MetricCard
              icon={<Brain size={19} />}
              label="ML Risk"
              value={`${topRisks.filter((item) => item.risk_level === "high").length} high`}
              detail={topRisks[0] ? `${tickerLabel(topRisks[0].ticker, market)}: ${percent(topRisks[0].risk_probability)}` : "No predictions"}
            />
            <MetricCard
              icon={<ShieldCheck size={19} />}
              label="Recommendations"
              value={String(dashboard.suggestions.length)}
              detail={`As of ${dashboard.price_as_of ?? "unknown"}`}
            />
          </section>

          <section className="conclusion-grid">
            <Panel title="Key Takeaways" icon={<ShieldCheck size={18} />}>
              <TakeawayList items={dashboard.advisor_summary} />
            </Panel>
            <Panel title="Suggested Portfolio Distribution" icon={<Gauge size={18} />} className="wide-panel">
              <DistributionTable rows={dashboard.recommended_distribution} market={market} />
            </Panel>
          </section>

          <section className="conclusion-grid">
            <Panel title="My Research Portfolio" icon={<Save size={18} />}>
              <PortfolioEditor
                market={market}
                positions={researchPositions}
                defaultPositions={dashboard.positions}
                onChange={setResearchPositions}
              />
            </Panel>
            <Panel title="Personalized Action Gap" icon={<Gauge size={18} />} className="wide-panel">
              <PersonalizedGapTable positions={researchPositions} rows={dashboard.recommended_distribution} market={market} />
            </Panel>
          </section>

          <section className="dashboard-grid">
            <Panel title="News Sentiment & AI Readout" icon={<Newspaper size={18} />} className="wide-panel">
              {sentiment ? <SentimentPanel sentiment={sentiment} market={market} /> : <EmptyState label="News sentiment loading." />}
            </Panel>

            <Panel title="Benchmark Path" icon={<Activity size={18} />} className="wide-panel">
              <BenchmarkArea points={dashboard.benchmark_series} />
            </Panel>

            <Panel title="Backtest Snapshot" icon={<BarChart3 size={18} />}>
              {backtest ? <BacktestMetrics backtest={backtest} /> : <EmptyState label="Run backtest to compare." />}
            </Panel>

            <Panel title="Latest Market Data" icon={<Activity size={18} />}>
              <QuotesTable quotes={quotes} market={market} />
            </Panel>

            <Panel title={`${tickerLabel(dashboard.universe.benchmark, market)} K-Line`} icon={<Activity size={18} />} className="wide-panel">
              <CandlestickChart rows={ohlc} hover={hoverCandle} setHover={setHoverCandle} />
            </Panel>

            <Panel title="Allocation Pie" icon={<Gauge size={18} />}>
              <AllocationPie positions={dashboard.positions} market={market} />
            </Panel>

            <Panel title="Strategy Comparison" icon={<BarChart3 size={18} />} className="wide-panel">
              {strategyComparison ? <StrategyComparison comparison={strategyComparison} /> : <EmptyState label="Strategy comparison loading." />}
            </Panel>

            <Panel title="Strategy Metrics" icon={<Gauge size={18} />}>
              {strategyComparison ? <StrategyMetrics comparison={strategyComparison} /> : <EmptyState label="No comparison metrics." />}
            </Panel>

            <Panel title="Rule Recommendations" icon={<ShieldCheck size={18} />} className="wide-panel">
              <RecommendationTable suggestions={dashboard.suggestions} market={market} />
            </Panel>

            <Panel title="ML Risk Ranking" icon={<Brain size={18} />}>
              <RiskList risks={topRisks} market={market} />
            </Panel>

            <Panel title="Sector Signals" icon={<FlaskConical size={18} />} className="wide-panel">
              <SectorTable signals={dashboard.signals} market={market} />
            </Panel>

            <Panel title="Allocation Drift" icon={<Gauge size={18} />}>
              <AllocationBars positions={dashboard.positions} targets={dashboard.target_weights} market={market} />
            </Panel>

            <Panel title="Instrument Guide" icon={<Activity size={18} />} className="wide-panel">
              <InstrumentGuide dashboard={dashboard} market={market} quotes={quotes} />
            </Panel>

            <Panel title="Strategy Rule Book" icon={<ShieldCheck size={18} />} className="wide-panel">
              <RulesTable rules={rules} />
            </Panel>
          </section>
        </>
      ) : (
        <section className="loading-surface">Loading portfolio lab...</section>
      )}
    </main>
  );
}

function MarketTruthBanner({
  marketInfo,
  dashboard,
  quotes
}: {
  marketInfo: MarketProfileInfo;
  dashboard: DashboardPayload;
  quotes: LatestQuote[];
}) {
  const quoteSource = quotes[0]?.source ?? "snapshot/API";
  return (
    <section className="truth-banner">
      <div>
        <strong>{marketInfo.label}</strong>
        <span>{marketInfo.tickerConvention}</span>
      </div>
      <div>
        <strong>Market data is real</strong>
        <span>
          {marketInfo.dataTruth} Latest quote source: {quoteSource}; price date: {dashboard.price_as_of ?? "unknown"}.
        </span>
      </div>
      <div>
        <strong>Portfolio is editable research input</strong>
        <span>{marketInfo.portfolioTruth}</span>
      </div>
    </section>
  );
}

function MetricCard({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string; detail: string }) {
  return (
    <article className="metric-card">
      <div className="metric-icon">{icon}</div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        <span>{detail}</span>
      </div>
    </article>
  );
}

function Panel({
  title,
  icon,
  children,
  className = ""
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div className="panel-title">
          {icon}
          <h2>{title}</h2>
        </div>
      </div>
      {children}
    </section>
  );
}

function BenchmarkArea({ points }: { points: Array<{ date: string; value: number }> }) {
  if (points.length < 2) return <EmptyState label="No benchmark series available." />;

  return (
    <div className="chart-wrap">
      <ResponsiveContainer width="100%" height={240}>
        <AreaChart data={points} margin={{ top: 8, right: 14, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="benchmarkGradient" x1="0" x2="0" y1="0" y2="1">
              <stop offset="5%" stopColor="#1f6f5b" stopOpacity={0.35} />
              <stop offset="95%" stopColor="#1f6f5b" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#e6ecef" vertical={false} />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={34} />
          <YAxis domain={["dataMin", "dataMax"]} tick={{ fontSize: 11 }} width={48} />
          <Tooltip content={<ChartTooltip />} />
          <Area dataKey="value" name="Close" type="monotone" stroke="#1f6f5b" fill="url(#benchmarkGradient)" strokeWidth={2.5} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function CandlestickChart({
  rows,
  hover,
  setHover
}: {
  rows: OhlcPoint[];
  hover: OhlcPoint | null;
  setHover: (row: OhlcPoint | null) => void;
}) {
  const visible = rows.slice(-120);
  if (visible.length < 2) return <EmptyState label="No OHLC data available." />;

  const width = 720;
  const height = 260;
  const pad = 16;
  const lows = visible.map((row) => row.low);
  const highs = visible.map((row) => row.high);
  const min = Math.min(...lows);
  const max = Math.max(...highs);
  const range = Math.max(0.001, max - min);
  const candleWidth = Math.max(2, (width - pad * 2) / visible.length * 0.55);
  const y = (value: number) => height - pad - ((value - min) / range) * (height - pad * 2);

  return (
    <div className="kline-wrap">
      <div className="kline-meta">
        {hover ? (
          <>
            <strong>{hover.date}</strong>
            <span>O {money(hover.open)}</span>
            <span>H {money(hover.high)}</span>
            <span>L {money(hover.low)}</span>
            <span>C {money(hover.close)}</span>
          </>
        ) : (
          <span>Hover over candles for OHLC detail</span>
        )}
      </div>
      <svg className="kline-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Candlestick chart">
        {visible.map((row, index) => {
          const x = pad + (index / Math.max(1, visible.length - 1)) * (width - pad * 2);
          const up = row.close >= row.open;
          const bodyTop = y(Math.max(row.open, row.close));
          const bodyHeight = Math.max(1.5, Math.abs(y(row.open) - y(row.close)));
          return (
            <g
              key={`${row.date}-${index}`}
              onMouseEnter={() => setHover(row)}
              onMouseLeave={() => setHover(null)}
              className={up ? "candle up" : "candle down"}
            >
              <line x1={x} x2={x} y1={y(row.high)} y2={y(row.low)} />
              <rect x={x - candleWidth / 2} y={bodyTop} width={candleWidth} height={bodyHeight} rx={1} />
              <rect className="hitbox" x={x - candleWidth} y={0} width={candleWidth * 2} height={height} />
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function BacktestMetrics({ backtest }: { backtest: BacktestPayload }) {
  return (
    <div className="metric-list">
      <Row label="Final value" value={backtest.metrics.final_value.toFixed(3)} />
      <Row label="CAGR" value={percent(backtest.metrics.cagr)} />
      <Row label="Volatility" value={percent(backtest.metrics.annualized_volatility)} />
      <Row label="Sharpe" value={backtest.metrics.sharpe.toFixed(2)} />
      <Row label="Max drawdown" value={percent(backtest.metrics.max_drawdown)} />
    </div>
  );
}

function QuotesTable({ quotes, market }: { quotes: LatestQuote[]; market: MarketProfile }) {
  if (!quotes.length) return <EmptyState label="Latest market data unavailable." />;
  const marketInfo = MARKET_INFO[market];
  return (
    <div className="table-wrap compact-table">
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Price ({marketInfo.currency})</th>
            <th>Change</th>
            <th>As of</th>
          </tr>
        </thead>
        <tbody>
          {quotes.slice(0, 8).map((quote) => (
            <tr key={quote.ticker} title={`Source: ${quote.source}`}>
              <td>
                <TickerCell ticker={quote.ticker} market={market} />
              </td>
              <td>{money(quote.price)}</td>
              <td className={quote.change >= 0 ? "positive" : "negative"}>
                {quote.change >= 0 ? "+" : ""}
                {money(quote.change)} / {percent(quote.change_pct)}
              </td>
              <td>{quote.as_of}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AllocationPie({ positions, market }: { positions: Record<string, number>; market: MarketProfile }) {
  const colors = ["#1f6f5b", "#4c88a3", "#dc8f2d", "#9b6aab", "#557a38", "#b5533f", "#456990", "#c49a2c"];
  const data = Object.entries(positions)
    .filter(([, value]) => value > 0)
    .map(([name, value]) => ({ name, label: tickerLabel(name, market), value }));
  return (
    <div className="pie-wrap">
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="label" innerRadius="48%" outerRadius="80%" paddingAngle={1}>
            {data.map((entry, index) => (
              <Cell key={entry.name} fill={colors[index % colors.length]} />
            ))}
          </Pie>
          <Tooltip content={<PieTooltip />} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

function StrategyComparison({ comparison }: { comparison: StrategyComparisonPayload }) {
  const merged = mergeEquityCurves(comparison);
  const names = comparison.strategies.map((strategy) => strategy.name);
  const colors = ["#1f6f5b", "#4c88a3", "#dc8f2d", "#9b6aab", "#b5533f", "#557a38"];
  return (
    <div className="strategy-comparison">
      <ResponsiveContainer width="100%" height={270}>
        <AreaChart data={merged} margin={{ top: 8, right: 18, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#e6ecef" vertical={false} />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={34} />
          <YAxis tick={{ fontSize: 11 }} width={48} />
          <Tooltip content={<ChartTooltip />} />
          {names.map((name, index) => (
            <Area
              key={name}
              dataKey={name}
              name={name}
              type="monotone"
              stroke={colors[index % colors.length]}
              fill={colors[index % colors.length]}
              fillOpacity={0.08}
              strokeWidth={2}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
      <div className="strategy-legend">
        {comparison.strategies.map((strategy, index) => (
          <span key={strategy.name}>
            <i style={{ background: colors[index % colors.length] }} />
            {strategy.name}
          </span>
        ))}
      </div>
    </div>
  );
}

function StrategyMetrics({ comparison }: { comparison: StrategyComparisonPayload }) {
  const data = comparison.strategies.map((strategy) => ({
    name: strategy.name,
    cagr: strategy.metrics.cagr,
    sharpe: strategy.metrics.sharpe,
    drawdown: Math.abs(strategy.metrics.max_drawdown),
    final: strategy.metrics.final_value
  }));
  return (
    <div className="strategy-metrics">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} layout="vertical" margin={{ top: 8, right: 12, left: 24, bottom: 0 }}>
          <CartesianGrid stroke="#e6ecef" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 11 }} />
          <YAxis dataKey="name" type="category" width={112} tick={{ fontSize: 11 }} />
          <Tooltip content={<PercentTooltip />} />
          <Bar dataKey="cagr" name="CAGR" fill="#1f6f5b" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <div className="table-wrap compact-table">
        <table>
          <thead>
            <tr>
              <th>Strategy</th>
              <th>CAGR</th>
              <th>Sharpe</th>
              <th>Max DD</th>
            </tr>
          </thead>
          <tbody>
            {comparison.strategies.map((strategy) => (
              <tr key={strategy.name} title={strategy.description}>
                <td>{strategy.name}</td>
                <td>{percent(strategy.metrics.cagr)}</td>
                <td>{strategy.metrics.sharpe.toFixed(2)}</td>
                <td>{percent(strategy.metrics.max_drawdown)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RecommendationTable({ suggestions, market }: { suggestions: DashboardPayload["suggestions"]; market: MarketProfile }) {
  if (!suggestions.length) return <EmptyState label="No recommendations met thresholds." />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Action</th>
            <th>Delta</th>
            <th>Rules</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {suggestions.map((item) => (
            <tr key={`${item.ticker}-${item.action}-${item.reason}`}>
              <td>
                <TickerCell ticker={item.ticker} market={market} />
              </td>
              <td>
                <span className={`badge ${item.action}`}>{item.action}</span>
              </td>
              <td>{percent(item.delta_weight)}</td>
              <td>{item.rule_ids.join(", ") || "-"}</td>
              <td>{item.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TakeawayList({ items }: { items: DashboardPayload["advisor_summary"] }) {
  if (!items.length) return <EmptyState label="No conclusions available." />;
  return (
    <div className="takeaway-list">
      {items.map((item) => (
        <article className={`takeaway ${item.severity}`} key={`${item.rank}-${item.title}`}>
          <div className="takeaway-rank">{item.rank}</div>
          <div>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
            <span>{item.rule_ids.join(", ")}</span>
          </div>
        </article>
      ))}
    </div>
  );
}

function DistributionTable({ rows, market }: { rows: DashboardPayload["recommended_distribution"]; market: MarketProfile }) {
  const visible = rows.filter((row) => row.current_weight > 0 || row.recommended_weight > 0).slice(0, 14);
  return (
    <div className="table-wrap distribution-table">
      <table>
        <thead>
          <tr>
            <th>Priority</th>
            <th>Ticker</th>
            <th>Action</th>
            <th>Current</th>
            <th>Target</th>
            <th>Suggested</th>
            <th>Delta</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((row, index) => (
            <tr key={row.ticker} title={`Rules: ${row.rule_ids.join(", ") || "none"}`}>
              <td>{index + 1}</td>
              <td>
                <strong>{row.ticker}</strong>
                <span>{instrumentName(row.ticker, market)}</span>
                <span>{row.sector}</span>
              </td>
              <td>
                <span className={`badge ${row.action}`}>{row.action}</span>
              </td>
              <td>{percent(row.current_weight)}</td>
              <td>{percent(row.target_weight)}</td>
              <td>
                <strong>{percent(row.recommended_weight)}</strong>
              </td>
              <td className={row.delta_weight >= 0 ? "positive" : "negative"}>{percent(row.delta_weight)}</td>
              <td>{row.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PortfolioEditor({
  market,
  positions,
  defaultPositions,
  onChange
}: {
  market: MarketProfile;
  positions: Record<string, number>;
  defaultPositions: Record<string, number>;
  onChange: (positions: Record<string, number>) => void;
}) {
  const tickers = Object.keys({ ...defaultPositions, ...positions }).sort((a, b) => (a === "CASH" ? -1 : b === "CASH" ? 1 : a.localeCompare(b)));
  const total = tickers.reduce((sum, ticker) => sum + (positions[ticker] ?? 0), 0);
  const normalized = normalizeWeights(positions);

  function updateTicker(ticker: string, value: string) {
    const pct = Number(value);
    if (!Number.isFinite(pct)) return;
    onChange({ ...positions, [ticker]: Math.max(0, pct / 100) });
  }

  return (
    <div className="portfolio-editor">
      <div className="editor-actions">
        <span className={Math.abs(total - 1) <= 0.01 ? "total-ok" : "total-warn"}>Total {percent(total)}</span>
        <button type="button" onClick={() => onChange(normalized)}>
          Normalize
        </button>
        <button type="button" onClick={() => savePortfolio(market, positions)}>
          <Save size={14} />
          Save
        </button>
        <button
          type="button"
          onClick={() => {
            clearPortfolio(market);
            onChange(defaultPositions);
          }}
        >
          <RotateCcw size={14} />
          Reset
        </button>
      </div>
      <div className="portfolio-input-grid">
        {tickers.map((ticker) => (
          <label key={ticker}>
            <span>
              <strong>{ticker}</strong>
              {instrumentName(ticker, market)}
            </span>
            <input
              type="number"
              min="0"
              max="100"
              step="0.1"
              value={((positions[ticker] ?? 0) * 100).toFixed(1)}
              onChange={(event) => updateTicker(ticker, event.target.value)}
            />
          </label>
        ))}
      </div>
    </div>
  );
}

function PersonalizedGapTable({
  positions,
  rows,
  market
}: {
  positions: Record<string, number>;
  rows: DashboardPayload["recommended_distribution"];
  market: MarketProfile;
}) {
  const visible = rows
    .map((row) => {
      const current = positions[row.ticker] ?? 0;
      const gap = row.recommended_weight - current;
      return { ...row, current, gap, personalizedAction: actionForGap(gap) };
    })
    .filter((row) => row.current > 0 || row.recommended_weight > 0 || row.ticker === "CASH")
    .sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap))
    .slice(0, 14);

  return (
    <div className="table-wrap distribution-table">
      <table>
        <thead>
          <tr>
            <th>Priority</th>
            <th>Holding</th>
            <th>Action</th>
            <th>Mine</th>
            <th>Model</th>
            <th>Gap</th>
            <th>Why</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((row, index) => (
            <tr key={row.ticker}>
              <td>{index + 1}</td>
              <td>
                <TickerCell ticker={row.ticker} market={market} />
              </td>
              <td>
                <span className={`badge ${row.personalizedAction}`}>{row.personalizedAction}</span>
              </td>
              <td>{percent(row.current)}</td>
              <td>{percent(row.recommended_weight)}</td>
              <td className={row.gap >= 0 ? "positive" : "negative"}>{percent(row.gap)}</td>
              <td>{row.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SentimentPanel({ sentiment, market }: { sentiment: SentimentPayload; market: MarketProfile }) {
  const summary = sentiment.summary;
  return (
    <div className="sentiment-panel">
      <div className="sentiment-summary">
        <div>
          <span>Forecast Bias</span>
          <strong className={`sentiment-${summary.forecast_bias}`}>{summary.forecast_bias.replaceAll("_", " ")}</strong>
        </div>
        <div>
          <span>News Tone</span>
          <strong>{summary.label}</strong>
        </div>
        <div>
          <span>Confidence</span>
          <strong>{percent(summary.confidence)}</strong>
        </div>
        <div>
          <span>Articles</span>
          <strong>{summary.article_count}</strong>
        </div>
      </div>
      <p className="sentiment-callout">
        {summary.recommended_action}. {summary.rationale}
      </p>
      <div className="sentiment-columns">
        <div>
          <h3>Themes</h3>
          <div className="theme-list">
            {summary.top_themes.length ? (
              summary.top_themes.map((theme) => (
                <span key={theme.theme}>
                  {theme.theme} <strong>{theme.count}</strong>
                </span>
              ))
            ) : (
              <span>No dominant theme</span>
            )}
          </div>
        </div>
        <div>
          <h3>Ticker Sentiment</h3>
          <div className="ticker-sentiment-list">
            {sentiment.ticker_sentiment.slice(0, 5).map((row) => (
              <div key={row.ticker}>
                <TickerCell ticker={row.ticker} market={market} />
                <span className={`badge ${row.label}`}>{row.label}</span>
                <strong>{percent(row.score)}</strong>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="headline-list">
        {sentiment.articles.slice(0, 6).map((article) => (
          <a key={`${article.title}-${article.source}`} href={article.link || "#"} target="_blank" rel="noreferrer">
            <span className={`dot ${article.sentiment_label}`} />
            <strong>{article.title}</strong>
            <em>{article.source}</em>
          </a>
        ))}
      </div>
      <div className="ai-note">
        AI layer: {summary.ai_layer.status}. {summary.ai_layer.note}
      </div>
      {summary.ai_layer.analysis ? <pre className="ai-analysis">{summary.ai_layer.analysis}</pre> : null}
    </div>
  );
}

function RiskList({ risks, market }: { risks: DashboardPayload["risk_predictions"]; market: MarketProfile }) {
  if (!risks.length) return <EmptyState label="ML model needs more data." />;
  return (
    <div className="risk-list">
      {risks.map((risk) => (
        <div className="risk-row" key={risk.ticker}>
          <div>
            <strong>{risk.ticker}</strong>
            <span>{instrumentName(risk.ticker, market)}</span>
            <span>{risk.risk_level}</span>
          </div>
          <meter min={0} max={1} value={risk.risk_probability} />
          <em>{percent(risk.risk_probability)}</em>
        </div>
      ))}
    </div>
  );
}

function SectorTable({ signals, market }: { signals: SectorSignal[]; market: MarketProfile }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Sector</th>
            <th>ETF</th>
            <th>Status</th>
            <th>Trend</th>
            <th>Z</th>
            <th>Momentum</th>
            <th>Vol</th>
          </tr>
        </thead>
        <tbody>
          {[...signals].sort((a, b) => b.z - a.z).map((signal) => (
            <tr key={signal.sector}>
              <td>{signal.sector}</td>
              <td>
                <TickerCell ticker={signal.etf} market={market} />
              </td>
              <td>
                <span className={`badge ${signal.status}`}>{signal.status}</span>
              </td>
              <td>{signal.trend_state}</td>
              <td>{signal.z.toFixed(2)}</td>
              <td>{percent(signal.momentum)}</td>
              <td>{percent(signal.realized_vol)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RulesTable({ rules }: { rules: StrategyRule[] }) {
  if (!rules.length) return <EmptyState label="Rule catalog unavailable." />;
  return (
    <div className="table-wrap rules-table">
      <table>
        <thead>
          <tr>
            <th>Rule</th>
            <th>Category</th>
            <th>Formula</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((rule) => (
            <tr key={rule.rule_id} title={`${rule.rationale} Evidence: ${rule.evidence}`}>
              <td>
                <strong>{rule.rule_id}</strong>
                <span>{rule.name}</span>
              </td>
              <td>{rule.category}</td>
              <td>
                <code>{rule.formula}</code>
              </td>
              <td>
                <span className={`badge ${rule.implementation_status}`}>{rule.implementation_status}</span>
              </td>
              <td>{rule.action}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AllocationBars({ positions, targets, market }: { positions: Record<string, number>; targets: Record<string, number>; market: MarketProfile }) {
  const tickers = Object.keys({ ...positions, ...targets }).filter((ticker) => ticker !== "CASH");
  return (
    <div className="allocation-list">
      {tickers.map((ticker) => {
        const current = positions[ticker] ?? 0;
        const target = targets[ticker] ?? 0;
        return (
          <div className="allocation-row" key={ticker}>
            <div className="allocation-label">
              <strong>{ticker}</strong>
              <span>{instrumentName(ticker, market)}</span>
              <span>{percent(current - target)} drift</span>
            </div>
            <div className="bar-track">
              <span className="bar-current" style={{ width: `${Math.min(100, current * 500)}%` }} />
              <i style={{ left: `${Math.min(100, target * 500)}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function InstrumentGuide({ dashboard, market, quotes }: { dashboard: DashboardPayload; market: MarketProfile; quotes: LatestQuote[] }) {
  const marketInfo = MARKET_INFO[market];
  const quoteMap = new Map(quotes.map((quote) => [quote.ticker, quote]));
  const tickers = [dashboard.universe.benchmark, ...dashboard.universe.tickers, "CASH"].filter(
    (ticker, index, all) => all.indexOf(ticker) === index
  );

  return (
    <div className="instrument-guide">
      <p>
        {marketInfo.benchmarkName} is the benchmark for this profile. Prices are shown in {marketInfo.currency}; weights are portfolio percentages.
      </p>
      <div className="table-wrap compact-table">
        <table>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Name</th>
              <th>Current weight</th>
              <th>Latest price</th>
              <th>Data status</th>
            </tr>
          </thead>
          <tbody>
            {tickers.map((ticker) => {
              const quote = quoteMap.get(ticker);
              return (
                <tr key={ticker}>
                  <td>
                    <strong>{ticker}</strong>
                  </td>
                  <td>{instrumentName(ticker, market)}</td>
                  <td>{percent(dashboard.positions[ticker] ?? 0)}</td>
                  <td>{quote ? `${money(quote.price)} ${marketInfo.currency}` : ticker === "CASH" ? "-" : "not in latest quote set"}</td>
                  <td>{ticker === "CASH" ? "portfolio input" : quote ? `real snapshot, ${quote.as_of}` : "historical data only"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TickerCell({ ticker, market }: { ticker: string; market: MarketProfile }) {
  return (
    <span className="ticker-cell">
      <strong>{ticker}</strong>
      <span>{instrumentName(ticker, market)}</span>
    </span>
  );
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      {payload.map((item: any) => (
        <span key={item.dataKey}>
          {item.name}: {money(Number(item.value))}
        </span>
      ))}
    </div>
  );
}

function PieTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const item = payload[0];
  return (
    <div className="chart-tooltip">
      <strong>{item.name}</strong>
      <span>{percent(Number(item.value))}</span>
    </div>
  );
}

function PercentTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      {payload.map((item: any) => (
        <span key={item.dataKey}>
          {item.name}: {percent(Number(item.value))}
        </span>
      ))}
    </div>
  );
}

function mergeEquityCurves(comparison: StrategyComparisonPayload) {
  const rows = new Map<string, Record<string, string | number>>();
  for (const strategy of comparison.strategies) {
    for (const point of strategy.equity_curve) {
      const row = rows.get(point.date) ?? { date: point.date };
      row[strategy.name] = point.portfolio_value;
      rows.set(point.date, row);
    }
  }
  return Array.from(rows.values()).sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return <div className="empty-state">{label}</div>;
}

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function money(value: number) {
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function instrumentName(ticker: string, market: MarketProfile) {
  return MARKET_INFO[market].instruments[ticker] ?? ticker;
}

function tickerLabel(ticker: string, market: MarketProfile) {
  const name = instrumentName(ticker, market);
  return name === ticker ? ticker : `${ticker} ${name}`;
}

function portfolioStorageKey(market: MarketProfile) {
  return `portfolio-investing-lab:${market}:research-positions`;
}

function loadSavedPortfolio(market: MarketProfile, fallback: Record<string, number>) {
  try {
    const raw = window.localStorage.getItem(portfolioStorageKey(market));
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Record<string, number>;
    const cleaned = Object.fromEntries(
      Object.entries(parsed).filter(([, value]) => typeof value === "number" && Number.isFinite(value) && value >= 0)
    );
    return Object.keys(cleaned).length ? { ...fallback, ...cleaned } : fallback;
  } catch {
    return fallback;
  }
}

function savePortfolio(market: MarketProfile, positions: Record<string, number>) {
  window.localStorage.setItem(portfolioStorageKey(market), JSON.stringify(positions));
}

function clearPortfolio(market: MarketProfile) {
  window.localStorage.removeItem(portfolioStorageKey(market));
}

function normalizeWeights(positions: Record<string, number>) {
  const total = Object.values(positions).reduce((sum, value) => sum + Math.max(0, value), 0);
  if (total <= 0) return positions;
  return Object.fromEntries(Object.entries(positions).map(([ticker, value]) => [ticker, Math.max(0, value) / total]));
}

function actionForGap(gap: number) {
  if (gap > 0.01) return "add";
  if (gap < -0.01) return "trim";
  return "hold";
}

createRoot(document.getElementById("root")!).render(<App />);
