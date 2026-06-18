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
import { BacktestPayload, DashboardPayload, SectorSignal, fetchBacktest, fetchDashboard } from "./api";
import "./styles.css";

function App() {
  const [mode, setMode] = useState("real");
  const [lookbackDays, setLookbackDays] = useState(900);
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [backtest, setBacktest] = useState<BacktestPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [dash, bt] = await Promise.all([
        fetchDashboard(mode, lookbackDays),
        fetchBacktest(mode, Math.max(lookbackDays, 900))
      ]);
      setDashboard(dash);
      setBacktest(bt);
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

          <section className="dashboard-grid">
            <Panel title="Benchmark Path" icon={<Activity size={18} />} className="wide-panel">
              <LineChart points={dashboard.benchmark_series} />
            </Panel>

            <Panel title="Backtest Snapshot" icon={<BarChart3 size={18} />}>
              {backtest ? <BacktestMetrics backtest={backtest} /> : <EmptyState label="Run backtest to compare." />}
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

function LineChart({ points }: { points: Array<{ date: string; value: number }> }) {
  if (points.length < 2) return <EmptyState label="No benchmark series available." />;
  const width = 680;
  const height = 220;
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(0.0001, max - min);
  const path = points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * width;
      const y = height - ((point.value - min) / range) * height;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Benchmark price line">
        <path className="area-path" d={`${path} L${width},${height} L0,${height} Z`} />
        <path className="line-path" d={path} />
      </svg>
      <div className="chart-axis">
        <span>{points[0].date}</span>
        <span>{money(points[points.length - 1].value)}</span>
        <span>{points[points.length - 1].date}</span>
      </div>
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
