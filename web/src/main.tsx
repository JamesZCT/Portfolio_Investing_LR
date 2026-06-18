import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Brain,
  FlaskConical,
  Gauge,
  RefreshCw,
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
  OhlcPoint,
  SectorSignal,
  StrategyComparisonPayload,
  StrategyRule,
  fetchBacktest,
  fetchDashboard,
  fetchLatestQuotes,
  fetchOhlc,
  fetchRules,
  fetchStrategyComparison
} from "./api";
import "./styles.css";

function App() {
  const [mode, setMode] = useState("real");
  const [lookbackDays, setLookbackDays] = useState(900);
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [backtest, setBacktest] = useState<BacktestPayload | null>(null);
  const [strategyComparison, setStrategyComparison] = useState<StrategyComparisonPayload | null>(null);
  const [rules, setRules] = useState<StrategyRule[]>([]);
  const [ohlc, setOhlc] = useState<OhlcPoint[]>([]);
  const [quotes, setQuotes] = useState<LatestQuote[]>([]);
  const [hoverCandle, setHoverCandle] = useState<OhlcPoint | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [dash, bt, comparison] = await Promise.all([
        fetchDashboard(mode, lookbackDays),
        fetchBacktest(mode, Math.max(lookbackDays, 900)),
        fetchStrategyComparison(mode, Math.max(lookbackDays, 900))
      ]);
      const quoteTickers = [dash.universe.benchmark, ...dash.universe.tickers].slice(0, 12);
      const [ruleList, ohlcRows, quoteRows] = await Promise.all([
        fetchRules(),
        fetchOhlc(mode, Math.min(lookbackDays, 900), dash.universe.benchmark),
        fetchLatestQuotes(quoteTickers)
      ]);
      setDashboard(dash);
      setBacktest(bt);
      setStrategyComparison(comparison);
      setRules(ruleList);
      setOhlc(ohlcRows);
      setQuotes(quoteRows);
      setHoverCandle(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const topRisks = useMemo(
    () => [...(dashboard?.risk_predictions ?? [])].sort((a, b) => b.risk_probability - a.risk_probability).slice(0, 6),
    [dashboard]
  );

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Portfolio Investing Lab</p>
          <h1>Rules, risk, and historical evidence</h1>
        </div>
        <div className="controls">
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
          <section className="metric-grid">
            <MetricCard
              icon={<Gauge size={19} />}
              label="Market Regime"
              value={dashboard.market_regime.trend_state}
              detail={`${dashboard.market_regime.benchmark} ${money(dashboard.market_regime.price)} vs MA ${money(
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
              detail={topRisks[0] ? `${topRisks[0].ticker}: ${percent(topRisks[0].risk_probability)}` : "No predictions"}
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
              <DistributionTable rows={dashboard.recommended_distribution} />
            </Panel>
          </section>

          <section className="dashboard-grid">
            <Panel title="Benchmark Path" icon={<Activity size={18} />} className="wide-panel">
              <BenchmarkArea points={dashboard.benchmark_series} />
            </Panel>

            <Panel title="Backtest Snapshot" icon={<BarChart3 size={18} />}>
              {backtest ? <BacktestMetrics backtest={backtest} /> : <EmptyState label="Run backtest to compare." />}
            </Panel>

            <Panel title="Latest Market Data" icon={<Activity size={18} />}>
              <QuotesTable quotes={quotes} />
            </Panel>

            <Panel title={`${dashboard.universe.benchmark} K-Line`} icon={<Activity size={18} />} className="wide-panel">
              <CandlestickChart rows={ohlc} hover={hoverCandle} setHover={setHoverCandle} />
            </Panel>

            <Panel title="Allocation Pie" icon={<Gauge size={18} />}>
              <AllocationPie positions={dashboard.positions} />
            </Panel>

            <Panel title="Strategy Comparison" icon={<BarChart3 size={18} />} className="wide-panel">
              {strategyComparison ? <StrategyComparison comparison={strategyComparison} /> : <EmptyState label="Strategy comparison loading." />}
            </Panel>

            <Panel title="Strategy Metrics" icon={<Gauge size={18} />}>
              {strategyComparison ? <StrategyMetrics comparison={strategyComparison} /> : <EmptyState label="No comparison metrics." />}
            </Panel>

            <Panel title="Rule Recommendations" icon={<ShieldCheck size={18} />} className="wide-panel">
              <RecommendationTable suggestions={dashboard.suggestions} />
            </Panel>

            <Panel title="ML Risk Ranking" icon={<Brain size={18} />}>
              <RiskList risks={topRisks} />
            </Panel>

            <Panel title="Sector Signals" icon={<FlaskConical size={18} />} className="wide-panel">
              <SectorTable signals={dashboard.signals} />
            </Panel>

            <Panel title="Allocation Drift" icon={<Gauge size={18} />}>
              <AllocationBars positions={dashboard.positions} targets={dashboard.target_weights} />
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

function QuotesTable({ quotes }: { quotes: LatestQuote[] }) {
  if (!quotes.length) return <EmptyState label="Latest market data unavailable." />;
  return (
    <div className="table-wrap compact-table">
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Price</th>
            <th>Change</th>
            <th>As of</th>
          </tr>
        </thead>
        <tbody>
          {quotes.slice(0, 8).map((quote) => (
            <tr key={quote.ticker} title={`Source: ${quote.source}`}>
              <td>
                <strong>{quote.ticker}</strong>
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

function AllocationPie({ positions }: { positions: Record<string, number> }) {
  const colors = ["#1f6f5b", "#4c88a3", "#dc8f2d", "#9b6aab", "#557a38", "#b5533f", "#456990", "#c49a2c"];
  const data = Object.entries(positions)
    .filter(([, value]) => value > 0)
    .map(([name, value]) => ({ name, value }));
  return (
    <div className="pie-wrap">
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius="48%" outerRadius="80%" paddingAngle={1}>
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

function RecommendationTable({ suggestions }: { suggestions: DashboardPayload["suggestions"] }) {
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
              <td>{item.ticker}</td>
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

function DistributionTable({ rows }: { rows: DashboardPayload["recommended_distribution"] }) {
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

function RiskList({ risks }: { risks: DashboardPayload["risk_predictions"] }) {
  if (!risks.length) return <EmptyState label="ML model needs more data." />;
  return (
    <div className="risk-list">
      {risks.map((risk) => (
        <div className="risk-row" key={risk.ticker}>
          <div>
            <strong>{risk.ticker}</strong>
            <span>{risk.risk_level}</span>
          </div>
          <meter min={0} max={1} value={risk.risk_probability} />
          <em>{percent(risk.risk_probability)}</em>
        </div>
      ))}
    </div>
  );
}

function SectorTable({ signals }: { signals: SectorSignal[] }) {
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
              <td>{signal.etf}</td>
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

function AllocationBars({ positions, targets }: { positions: Record<string, number>; targets: Record<string, number> }) {
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

createRoot(document.getElementById("root")!).render(<App />);
