import { Activity, CalendarClock, ChevronRight, ShieldCheck, TrendingUp } from "lucide-react";

import type { MarketTimingPayload, MarketTimingRow } from "./api";

type Language = "en" | "zh";

const ACTIONS: Record<string, [string, string]> = {
  continue_core_dca: ["Continue core DCA", "继续核心定投"],
  staged_add: ["Staged tactical add", "分批战术增持"],
  hold_no_chase: ["Hold; do not chase", "持有，不追高"],
  hold_core: ["Hold core exposure", "持有核心仓位"],
  wait_for_50dma_reclaim: ["Wait for 50-day reclaim", "等待重回 50 日均线"],
  wait_for_confirmation: ["Wait for confirmation", "等待确认"],
  reduce_tactical: ["Reduce tactical sleeve", "降低战术仓位"],
  review_data: ["Review data", "检查数据"]
};

const REGIMES: Record<string, [string, string]> = {
  bullish_pullback: ["Bullish pullback", "多头回调"],
  bullish_extended: ["Bullish, extended", "多头但偏高"],
  bullish: ["Bullish", "多头"],
  caution: ["Caution", "谨慎"],
  defensive_watch: ["Defensive watch", "防守观察"],
  risk_off: ["Risk off", "风险规避"],
  mixed: ["Mixed", "混合"],
  unknown: ["Unknown", "未知"]
};

export function MarketTimingPanel({ payload, language }: { payload: MarketTimingPayload; language: Language }) {
  const tr = (english: string, mandarin: string) => (language === "zh" ? mandarin : english);
  const breadth = payload.breadth;

  if (payload.status !== "available") {
    return <p className="timing-empty">{tr("Timing history is not sufficient yet.", "当前历史数据不足以生成择时判断。")}</p>;
  }

  return (
    <div className="market-timing-panel">
      <div className="timing-summary">
        <div>
          <span>{tr("Long-term plan", "长期计划")}</span>
          <strong><CalendarClock size={17} /> {actionLabel(payload.summary.dca_action, language)}</strong>
          <small>{tr("Moving averages do not automatically stop scheduled investing.", "均线信号不会自动停止长期定投。")}</small>
        </div>
        <div className={`timing-summary-action ${payload.summary.tactical_action}`}>
          <span>{tr("Tactical posture", "战术仓位")}</span>
          <strong><ShieldCheck size={17} /> {actionLabel(payload.summary.tactical_action, language)}</strong>
          <small>{localizeHeadline(payload.summary.headline, language)}</small>
        </div>
        <div>
          <span>{tr("Sector breadth", "行业宽度")}</span>
          <strong><Activity size={17} /> {formatOptionalPercent(breadth.above_200dma_pct)}</strong>
          <small>{tr("configured sector ETFs above their 200-day average", "已配置行业 ETF 位于 200 日均线上方")}</small>
        </div>
      </div>

      <div className="timing-card-grid">
        {payload.rows.map((row) => <TimingCard key={row.ticker} row={row} language={language} />)}
      </div>

      <div className="timing-method">
        <TrendingUp size={17} aria-hidden="true" />
        <div>
          <strong>{tr("How the decision is bounded", "判断边界")}</strong>
          <span>{tr(payload.methodology.tactical_policy, "只有在上升趋势中确认 50 日均线支撑，才允许分批增持；跌破 200 日均线还需要多个确认，才降低战术仓位。")}</span>
          <small>{tr(payload.methodology.decision_authority, "只有确定性的价格规则能改变判断；新闻和本地大模型的决策权重为零。")}</small>
        </div>
      </div>
    </div>
  );
}

function TimingCard({ row, language }: { row: MarketTimingRow; language: Language }) {
  const tr = (english: string, mandarin: string) => (language === "zh" ? mandarin : english);
  return (
    <article className={`timing-card ${row.tactical_action}`}>
      <header>
        <div>
          <strong>{row.ticker}</strong>
          <span>{row.as_of}</span>
        </div>
        <span className={`timing-regime ${row.regime}`}>{regimeLabel(row.regime, language)}</span>
      </header>
      <p>{localizeHeadline(row.headline, language)}</p>
      <div className="timing-actions">
        <span>{tr("DCA", "定投")}<strong>{actionLabel(row.dca_action, language)}</strong></span>
        <ChevronRight size={16} aria-hidden="true" />
        <span>{tr("Tactical", "战术")}<strong>{actionLabel(row.tactical_action, language)}</strong></span>
      </div>
      <div className="timing-metrics">
        <span>{tr("vs 50-day", "距 50 日线")}<strong>{signedPercent(row.distance_ma50_pct)}</strong></span>
        <span>{tr("vs 200-day", "距 200 日线")}<strong>{signedPercent(row.distance_ma200_pct)}</strong></span>
        <span>RSI(14)<strong>{row.rsi14.toFixed(1)}</strong></span>
        <span>{tr("Bear confirms", "看空确认")}<strong>{row.bearish_confirmation_count}/4</strong></span>
      </div>
      <details>
        <summary>{tr("Evidence and moving averages", "证据与均线详情")}</summary>
        <div className="timing-average-row">
          <span>50 DMA <strong>{money(row.ma50)}</strong> <small>{signedPercent(row.ma50_slope_20d_pct)} {tr("slope", "斜率")}</small></span>
          <span>200 DMA <strong>{money(row.ma200)}</strong> <small>{signedPercent(row.ma200_slope_20d_pct)} {tr("slope", "斜率")}</small></span>
        </div>
        <ul>{row.evidence.map((item) => <li key={item}>{item}</li>)}</ul>
      </details>
    </article>
  );
}

function actionLabel(value: string, language: Language) {
  const labels = ACTIONS[value] ?? [value.replaceAll("_", " "), value.replaceAll("_", " ")];
  return labels[language === "zh" ? 1 : 0];
}

function regimeLabel(value: string, language: Language) {
  const labels = REGIMES[value] ?? [value.replaceAll("_", " "), value.replaceAll("_", " ")];
  return labels[language === "zh" ? 1 : 0];
}

function localizeHeadline(value: string, language: Language) {
  if (language === "en") return value;
  const headlines: Record<string, string> = {
    "Reduce tactical risk; keep long-term contributions tied to the written plan": "降低战术风险；长期投入仍按书面计划执行",
    "200-day support is broken, but confirmation is incomplete": "已跌破 200 日均线，但看空确认尚不完整",
    "Rising 50-day support held; a staged tactical add is eligible": "上升中的 50 日均线支撑有效，可考虑分批战术增持",
    "Trend is constructive, but price is extended; hold without chasing": "趋势仍好，但价格偏高；持有而不追高",
    "Trend supports holding core exposure": "趋势支持继续持有核心仓位",
    "Long trend remains intact; wait for short-trend confirmation": "长期趋势尚未破坏，等待短期趋势确认",
    "Evidence is mixed; avoid a one-shot timing decision": "证据混合，避免一次性押注择时",
    "Insufficient timing history": "择时历史数据不足"
  };
  return headlines[value] ?? value;
}

function signedPercent(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function formatOptionalPercent(value: number | null) {
  return value == null ? "n/a" : `${(value * 100).toFixed(0)}%`;
}

function money(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}
