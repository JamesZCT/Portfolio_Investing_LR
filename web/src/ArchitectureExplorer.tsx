import { useMemo, useState } from "react";
import {
  ArrowRight,
  BrainCircuit,
  Calculator,
  Cloud,
  Database,
  FileCode2,
  GitBranch,
  Server,
  ShieldCheck,
  Workflow
} from "lucide-react";

type Language = "en" | "zh";
type Lane = "data" | "financial" | "ai" | "delivery";

type ArchitectureNode = {
  id: string;
  stage: string;
  lane: Lane;
  title: [string, string];
  summary: [string, string];
  input: [string, string];
  output: [string, string];
  guardrail: [string, string];
  files: string[];
};

const REPOSITORY = "https://github.com/JamesZCT/Portfolio_Investing_LR/blob/main/";

const NODES: ArchitectureNode[] = [
  {
    id: "scheduler", stage: "collect", lane: "delivery", title: ["Scheduled orchestration", "定时编排"],
    summary: ["Runs pre-open information refreshes, post-close market computation, weekly validation, and GitHub Pages delivery.", "运行盘前信息刷新、盘后市场计算、每周验证与 GitHub Pages 发布。"],
    input: ["New York market schedule and manual dispatch", "纽约市场时间与手动触发"], output: ["A reproducible Windows runner job", "可复现的 Windows runner 作业"],
    guardrail: ["Concurrency and time-zone gates prevent duplicate refreshes.", "并发与时区门控避免重复刷新。"], files: [".github/workflows/refresh-web-snapshot-local-llm.yml", ".github/workflows/weekly-historical-validation.yml"]
  },
  {
    id: "market-data", stage: "collect", lane: "data", title: ["Market data adapters", "市场数据适配器"],
    summary: ["Downloads adjusted prices and OHLC history, or reads a local CSV for an offline reproducible run.", "下载复权价格与 OHLC 历史，或读取本地 CSV 进行可复现的离线运行。"],
    input: ["Ticker universe and lookback window", "股票池与回看窗口"], output: ["Aligned pandas price frames", "对齐的 pandas 价格表"],
    guardrail: ["Missing and stale observations remain visible in snapshot health.", "缺失与过期数据会在快照健康状态中明确显示。"], files: ["src/portfolio_agent/data.py", "src/portfolio_agent/config.py"]
  },
  {
    id: "public-research", stage: "collect", lane: "data", title: ["Public research ingestion", "公开研究采集"],
    summary: ["Collects RSS headlines, Lance/RIA commentary signs, Federal Reserve context, Yahoo screen fields, and SEC filings.", "采集 RSS 标题、Lance/RIA 评论信号、美联储信息、Yahoo 筛选字段和 SEC 申报。"],
    input: ["Public feeds and filings", "公开信息源与申报"], output: ["Source-dated research records", "带来源与日期的研究记录"],
    guardrail: ["Public commentary has zero portfolio-decision weight.", "公开评论对组合决策的权重为零。"], files: ["src/portfolio_agent/information_signs.py", "src/portfolio_agent/market_screener.py", "src/portfolio_agent/sec_fundamentals.py"]
  },
  {
    id: "signals", stage: "analyze", lane: "financial", title: ["Trend and sector signals", "趋势与行业信号"],
    summary: ["Calculates market regime, moving averages, momentum, volatility, drawdown, z-scores, and sector extension.", "计算市场状态、均线、动量、波动、回撤、z-score 与行业延伸程度。"],
    input: ["Adjusted close history", "复权收盘历史"], output: ["Deterministic market and sector states", "确定性的市场与行业状态"],
    guardrail: ["Configured windows and formulas are published in the rule book.", "窗口与公式均在规则手册中公开。"], files: ["src/portfolio_agent/indicators.py", "src/portfolio_agent/signals.py"]
  },
  {
    id: "timing", stage: "analyze", lane: "financial", title: ["DCA and tactical timing", "定投与战术择时"],
    summary: ["Separates scheduled investing from staged adds, no-chase holds, and confirmed tactical risk reduction.", "将长期定投与分批增持、不追高持有及确认后的战术减仓分开。"],
    input: ["SPY, QQQ, VTI, VXUS and sector ETF history", "SPY、QQQ、VTI、VXUS 与行业 ETF 历史"], output: ["50/200-day, RSI, weekly MACD, breadth and cross evidence", "50/200 日均线、RSI、周 MACD、宽度与交叉证据"],
    guardrail: ["It is a public-rule proxy, not RIA's proprietary model.", "这是公开规则代理，并非 RIA 的专有模型。"], files: ["src/portfolio_agent/market_timing.py"]
  },
  {
    id: "fundamentals", stage: "analyze", lane: "financial", title: ["Fundamental and earnings research", "基本面与财报研究"],
    summary: ["Applies sector-aware quality, valuation, balance-sheet, cash-flow, and earnings gates to the visible shortlist.", "对可见候选名单应用行业适配的质量、估值、资产负债、现金流和财报门槛。"],
    input: ["SEC facts, filings, prices and estimates", "SEC 数据、申报、价格与预期"], output: ["Research-qualified, wait, specialist-review, or avoid labels", "研究合格、等待、专业复核或回避标签"],
    guardrail: ["Banks, insurers, REITs, software, and energy use different lenses.", "银行、保险、REIT、软件和能源采用不同评估框架。"], files: ["src/portfolio_agent/sec_fundamentals.py"]
  },
  {
    id: "portfolio", stage: "decide", lane: "financial", title: ["Portfolio rules and optimizer", "组合规则与优化器"],
    summary: ["Applies target gaps, concentration caps, stops, risk limits, and constrained defensive, balanced, and aggressive allocations.", "应用目标差距、集中度上限、止损、风险限制以及防守、平衡、进取型约束配置。"],
    input: ["Positions, targets, signals, prices and risk estimates", "持仓、目标、信号、价格与风险估计"], output: ["Traceable ADD, TRIM, HOLD and cash-gap research actions", "可追溯的增持、减持、持有和现金差距研究动作"],
    guardrail: ["Long-only, unlevered, capped, and sandbox execution only.", "仅做多、无杠杆、有上限且只允许沙盒执行。"], files: ["src/portfolio_agent/portfolio.py", "src/portfolio_agent/optimization.py", "src/portfolio_agent/execution.py"]
  },
  {
    id: "ml-risk", stage: "analyze", lane: "ai", title: ["Transparent ML risk", "透明机器学习风险"],
    summary: ["Fits a small local logistic model to price features and estimates forward drawdown-event probability.", "使用价格特征训练轻量本地逻辑模型，估计未来回撤事件概率。"],
    input: ["Rolling price-derived features", "滚动价格特征"], output: ["Per-holding low, medium, or high risk probability", "每个持仓的低、中、高风险概率"],
    guardrail: ["The model can constrain sizing; it cannot place an order.", "模型可以限制仓位，但不能下单。"], files: ["src/portfolio_agent/ml.py"]
  },
  {
    id: "llm", stage: "analyze", lane: "ai", title: ["Local LLM commentary", "本地大模型解读"],
    summary: ["Ollama qwen3:14b summarizes sourced news and explains conflicts between headlines and price evidence.", "Ollama qwen3:14b 总结有来源的新闻，并解释标题与价格证据的冲突。"],
    input: ["Bounded headline and information-sign digest", "受限的标题与信息信号摘要"], output: ["Plain-language commentary and watch questions", "自然语言解读与观察问题"],
    guardrail: ["Zero target-weight authority; no paid OpenAI token is required.", "目标权重决策权为零；不需要付费 OpenAI token。"], files: ["src/portfolio_agent/sentiment.py", "src/portfolio_agent/research_digest.py"]
  },
  {
    id: "validation", stage: "validate", lane: "financial", title: ["Backtest and bias controls", "回测与偏差控制"],
    summary: ["Runs next-day-effective, transaction-cost-aware walk-forward tests with point-in-time membership and explicit data gaps.", "运行次日生效、计入交易成本、使用当时成分股并披露数据缺口的滚动回测。"],
    input: ["Rules fixed before each evaluation window", "每个评估窗口前固定的规则"], output: ["CAGR, Sharpe, drawdown, turnover, coverage and bias audits", "CAGR、Sharpe、回撤、换手、覆盖率与偏差审计"],
    guardrail: ["Future prices cannot alter earlier signals; survivorship limitations remain disclosed.", "未来价格不能改变过去信号；幸存者偏差限制持续披露。"], files: ["src/portfolio_agent/backtest.py", "src/portfolio_agent/historical_validation.py", "src/portfolio_agent/point_in_time.py", "src/portfolio_agent/strategy_comparison.py"]
  },
  {
    id: "snapshot", stage: "publish", lane: "data", title: ["Snapshot data contract", "快照数据契约"],
    summary: ["Composes dashboard, timing, sentiment, opportunity, validation, health, and history JSON from one run.", "一次运行生成仪表盘、择时、情绪、机会、验证、健康与历史 JSON。"],
    input: ["All deterministic and commentary outputs", "所有确定性与解读输出"], output: ["Versionable static JSON and API-compatible payloads", "可版本化静态 JSON 与 API 兼容数据"],
    guardrail: ["Dates, source mode, example-config status, and failures travel with the output.", "日期、来源模式、示例配置状态和失败信息随输出一起发布。"], files: ["src/portfolio_agent/engine.py", "scripts/export_web_snapshot.py", "src/portfolio_agent/api.py"]
  },
  {
    id: "frontend", stage: "publish", lane: "delivery", title: ["Dashboard and public hosting", "仪表盘与公开托管"],
    summary: ["React renders the same snapshot contract locally, through an API, or as a public GitHub Pages site.", "React 使用同一快照契约在本地、API 或公开 GitHub Pages 中展示。"],
    input: ["Typed JSON payloads", "类型化 JSON 数据"], output: ["Responsive bilingual research dashboard", "响应式双语研究仪表盘"],
    guardrail: ["The public repository contains demonstration data only and no brokerage connection.", "公开仓库仅包含演示数据，不连接券商。"], files: ["web/src/api.ts", "web/src/main.tsx", "web/src/styles.css", ".github/workflows/deploy-github-pages.yml"]
  }
];

const STAGES = ["collect", "analyze", "decide", "validate", "publish"];
const STAGE_LABELS: Record<string, [string, string]> = {
  collect: ["1. Collect", "1. 采集"], analyze: ["2. Analyze", "2. 分析"], decide: ["3. Decide", "3. 决策"],
  validate: ["4. Validate", "4. 验证"], publish: ["5. Publish", "5. 发布"]
};

export function ArchitectureExplorer({ language }: { language: Language }) {
  const [selectedId, setSelectedId] = useState("timing");
  const selected = NODES.find((node) => node.id === selectedId) ?? NODES[0];
  const grouped = useMemo(() => STAGES.map((stage) => ({ stage, nodes: NODES.filter((node) => node.stage === stage) })), []);
  const text = (pair: [string, string]) => pair[language === "zh" ? 1 : 0];

  return (
    <div className="architecture-explorer">
      <div className="architecture-legend" aria-label={language === "zh" ? "模块类别" : "Module categories"}>
        <span className="data"><Database size={14} />{language === "zh" ? "数据工程" : "Data engineering"}</span>
        <span className="financial"><Calculator size={14} />{language === "zh" ? "金融分析" : "Financial analysis"}</span>
        <span className="ai"><BrainCircuit size={14} />{language === "zh" ? "AI / ML" : "AI / ML"}</span>
        <span className="delivery"><Cloud size={14} />{language === "zh" ? "自动化与交付" : "Automation & delivery"}</span>
      </div>
      <div className="architecture-flow">
        {grouped.map((group, index) => (
          <div className="architecture-stage-wrap" key={group.stage}>
            <section className="architecture-stage">
              <header>{text(STAGE_LABELS[group.stage])}</header>
              <div>
                {group.nodes.map((node) => (
                  <button
                    type="button"
                    className={`architecture-node ${node.lane} ${selected.id === node.id ? "active" : ""}`}
                    aria-pressed={selected.id === node.id}
                    onClick={() => setSelectedId(node.id)}
                    onMouseEnter={() => setSelectedId(node.id)}
                    onFocus={() => setSelectedId(node.id)}
                    key={node.id}
                  >
                    {laneIcon(node.lane)}
                    <span>{text(node.title)}</span>
                  </button>
                ))}
              </div>
            </section>
            {index < grouped.length - 1 ? <ArrowRight className="architecture-arrow" size={20} aria-hidden="true" /> : null}
          </div>
        ))}
      </div>

      <article className={`architecture-inspector ${selected.lane}`} aria-live="polite">
        <header>
          <span>{laneIcon(selected.lane)}</span>
          <div><small>{text(STAGE_LABELS[selected.stage])}</small><strong>{text(selected.title)}</strong></div>
        </header>
        <p>{text(selected.summary)}</p>
        <div className="architecture-io">
          <span><GitBranch size={15} /><small>{language === "zh" ? "输入" : "Input"}</small><strong>{text(selected.input)}</strong></span>
          <span><Workflow size={15} /><small>{language === "zh" ? "输出" : "Output"}</small><strong>{text(selected.output)}</strong></span>
          <span><ShieldCheck size={15} /><small>{language === "zh" ? "保护边界" : "Guardrail"}</small><strong>{text(selected.guardrail)}</strong></span>
        </div>
        <div className="architecture-files">
          <span>{language === "zh" ? "相关代码" : "Source files"}</span>
          <div>{selected.files.map((file) => <a href={`${REPOSITORY}${file}`} target="_blank" rel="noreferrer" key={file}><FileCode2 size={14} />{file}</a>)}</div>
        </div>
      </article>
    </div>
  );
}

function laneIcon(lane: Lane) {
  if (lane === "data") return <Database size={16} aria-hidden="true" />;
  if (lane === "financial") return <Calculator size={16} aria-hidden="true" />;
  if (lane === "ai") return <BrainCircuit size={16} aria-hidden="true" />;
  return <Server size={16} aria-hidden="true" />;
}
