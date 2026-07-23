import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Brain,
  FileText,
  FlaskConical,
  Gauge,
  Languages,
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
  HealthPayload,
  HistoricalValidationPayload,
  HistoryPayload,
  LatestQuote,
  MarketOpportunitiesPayload,
  MarketProfile,
  OhlcPoint,
  SectorSignal,
  SentimentPayload,
  StrategyComparisonPayload,
  StrategyRule,
  fetchBacktest,
  fetchBootstrap,
  fetchDashboard,
  fetchHealth,
  fetchHistoricalValidation,
  fetchHistory,
  fetchMarketOpportunities,
  fetchLatestQuotes,
  fetchOhlc,
  fetchRules,
  fetchSentiment,
  fetchStrategyComparison,
  IS_STATIC_DATA_MODE
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

type ModelPortfolio = {
  id: string;
  name: string;
  risk: string;
  coverage: string;
  description: string;
  keywords: string[];
  weights: Record<string, number>;
};

type Language = "en" | "zh";

type I18nContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  tr: (english: string, mandarin: string) => string;
};

const LANGUAGE_STORAGE_KEY = "portfolio-investing-lab:language";
const I18nContext = createContext<I18nContextValue | null>(null);

function I18nProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>(() => {
    try {
      return window.localStorage.getItem(LANGUAGE_STORAGE_KEY) === "zh" ? "zh" : "en";
    } catch {
      return "en";
    }
  });

  function setLanguage(nextLanguage: Language) {
    setLanguageState(nextLanguage);
    try {
      window.localStorage.setItem(LANGUAGE_STORAGE_KEY, nextLanguage);
    } catch {
      // The language still changes for this session when storage is unavailable.
    }
  }

  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
    document.title = language === "zh" ? "投资组合研究室" : "Portfolio Investing Lab";
  }, [language]);

  const value = useMemo<I18nContextValue>(
    () => ({ language, setLanguage, tr: (english, mandarin) => (language === "zh" ? mandarin : english) }),
    [language]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

function useI18n() {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used inside I18nProvider");
  return context;
}

const ZH_LABELS: Record<string, string> = {
  add: "增持",
  aggressive: "进取",
  available: "可用",
  balanced: "平衡",
  bearish: "看空",
  bullish: "看多",
  buy: "买入",
  "buy candidate": "买入候选",
  cautious: "谨慎",
  custom: "自定义",
  defensive: "防守",
  empty: "无内容",
  fresh: "正常",
  high: "高",
  hold: "持有",
  "hold / watch": "持有 / 观察",
  "hold watch": "持有观察",
  "information only": "仅供参考",
  "llm generated": "本地模型已生成",
  low: "低",
  mixed: "中性",
  moderate: "中等",
  neutral: "中性",
  pending: "等待中",
  positive: "积极",
  negative: "消极",
  "quote only": "仅报价筛选",
  reduce: "减持",
  "research buy": "研究买入",
  "rules only": "仅规则分析",
  sell: "卖出",
  "sell / avoid": "卖出 / 回避",
  "sell avoid": "卖出回避",
  stale: "需更新",
  strong: "强",
  trim: "减持",
  uptrend: "上升趋势",
  downtrend: "下降趋势",
  unknown: "未知",
  weak: "弱"
};

function localizeLabel(value: string | null | undefined, language: Language, fallback = "unknown") {
  const display = (value || fallback).replaceAll("_", " ");
  return language === "zh" ? ZH_LABELS[display.toLowerCase()] ?? display : display;
}

function localizeReason(value: string, language: Language) {
  const englishByChinese: Record<string, string> = {
    "当前没有规则触发明显调整。": "No rule currently triggers a material adjustment."
  };
  if (language === "en") return englishByChinese[value] ?? value.replaceAll("：", ": ");

  const phrases: Record<string, string> = {
    "exceeds max single-name cap": "超过单一个股上限",
    "over target weight": "高于目标权重",
    "raise or maintain cash buffer": "提高或维持现金缓冲",
    "sector exceeds max cap": "板块超过上限",
    "stop-loss triggered": "触发止损",
    "trailing-stop triggered": "触发移动止损",
    "No rule currently triggers a material adjustment.": "当前没有规则触发明显调整。"
  };
  return value
    .split("; ")
    .map((phrase) => phrases[phrase] ?? phrase.replace("sector hyped", "板块偏热"))
    .join("；");
}

function localizedTakeaway(item: DashboardPayload["advisor_summary"][number], language: Language) {
  const actionMatch = item.detail.match(/^(TRIM|ADD|HOLD)\s+(\S+)/);
  const ticker = actionMatch?.[2] ?? "";
  const isBearish = item.title.includes("降低风险") || item.detail.includes("低于 MA");
  const isTrend = item.rule_ids.includes("TREND_200DMA");
  const isRisk = item.rule_ids.includes("ML_DRAWDOWN_RISK");

  if (language === "en") {
    if (isTrend) {
      return {
        title: isBearish ? "Reduce risk exposure first" : "Trend still supports holding risk assets",
        detail: isBearish
          ? "The benchmark is below its long-term moving average, so the rules favor more cash or lower-risk positioning."
          : "The benchmark is above its long-term moving average, while position and sector caps still call for concentration review."
      };
    }
    if (isRisk) return { title: "ML risk model flags a review", detail: item.detail };
    if (actionMatch) {
      const action = actionMatch[1];
      const title = ticker === "CASH"
        ? "Raise the cash buffer"
        : action === "TRIM"
          ? `Prioritize trimming ${ticker}`
          : action === "ADD"
            ? `Consider adding ${ticker}`
            : `Maintain ${ticker}`;
      const parts = item.detail.split("：");
      return { title, detail: `${parts[0]}: ${localizeReason(parts.slice(1).join("："), language)}` };
    }
    return { title: item.title, detail: localizeReason(item.detail, language) };
  }

  if (isTrend) {
    return {
      title: isBearish ? "先降低风险敞口" : "趋势仍支持持有风险资产",
      detail: isBearish
        ? "基准低于长期移动平均线，规则系统倾向提高现金或减少高风险仓位。"
        : "基准高于长期移动平均线，但仍需按个股和板块上限复查集中度。"
    };
  }
  if (isRisk) return { title: "机器学习风险模型提示需复查", detail: item.detail };
  if (actionMatch) {
    const action = actionMatch[1];
    const title = ticker === "CASH" ? "建议提高现金缓冲" : action === "TRIM" ? `优先减持 ${ticker}` : action === "ADD" ? `可以考虑增持 ${ticker}` : `维持 ${ticker}`;
    const detail = item.detail.replaceAll("：", ": ");
    const separator = detail.indexOf(": ");
    return { title, detail: separator >= 0 ? `${detail.slice(0, separator)}：${localizeReason(detail.slice(separator + 2), language)}` : detail };
  }
  return { title: item.title, detail: localizeReason(item.detail, language) };
}

function localizeBusinessModel(value: string | null | undefined, language: Language, fallback: string) {
  if (!value) return fallback;
  const display = value.replaceAll("_", " ");
  if (language === "en") return display;
  const labels: Record<string, string> = {
    bank: "银行",
    energy: "能源",
    financial: "金融",
    industrial: "工业",
    insurance: "保险",
    reit: "房地产投资信托",
    software: "软件",
    technology: "科技"
  };
  return labels[display.toLowerCase()] ?? display;
}

function localizeStrategyName(value: string, language: Language) {
  if (language === "en") return value;
  const labels: Record<string, string> = {
    "Buy & Hold": "买入并持有",
    "Rule Engine": "规则引擎",
    "Trend Filter": "趋势过滤"
  };
  return labels[value] ?? value;
}

const ZH_MODEL_COPY: Record<string, Omit<ModelPortfolio, "id" | "weights">> = {
  "total-us": {
    name: "美国全市场",
    risk: "市场风险",
    coverage: "美国全市值股票",
    description: "广泛覆盖美国股票，可作为加入主动观点前的实用基准。",
    keywords: ["美国", "广泛覆盖", "指数型", "股票"]
  },
  "sp500-core": {
    name: "标普 500 核心",
    risk: "市场风险",
    coverage: "美国大型股",
    description: "覆盖美国大型公司，降低单一个股决策风险。",
    keywords: ["美国", "大型股", "标普 500", "简洁"]
  },
  "balanced-growth": {
    name: "均衡增长",
    risk: "中等",
    coverage: "美国、国际、债券",
    description: "以美国股票为核心，并用国际股票、债券和现金降低波动。",
    keywords: ["美国", "国际", "债券", "现金"]
  },
  "growth-tech": {
    name: "科技增长倾斜",
    risk: "进取",
    coverage: "美国增长、科技、少量国际",
    description: "保留美国市场核心，同时主动提高纳斯达克风格的增长敞口。",
    keywords: ["科技", "增长", "美国", "较高波动"]
  },
  defensive: {
    name: "防守型配置",
    risk: "较低波动",
    coverage: "美国、国际、债券、现金",
    description: "更保守的研究组合，重视回撤控制并保留可投资现金。",
    keywords: ["防守", "债券", "现金", "较低回撤"]
  },
  "core-satellite": {
    name: "核心 + AI 龙头",
    risk: "进取",
    coverage: "美国指数核心及精选大型科技股",
    description: "在指数投资和个股研究之间建立实用的核心卫星组合。",
    keywords: ["美国", "科技", "个股", "主动倾斜"]
  },
  "hk-tracker": {
    name: "香港指数核心",
    risk: "市场风险",
    coverage: "香港市场指数",
    description: "通过盈富基金获得简洁的香港市场基准敞口。",
    keywords: ["香港", "指数", "简洁"]
  },
  "hk-balanced": {
    name: "香港均衡核心",
    risk: "中等",
    coverage: "香港指数、金融、互联网、现金",
    description: "以指数为锚，加入适量主动敞口和现金缓冲。",
    keywords: ["香港", "核心", "现金", "主动"]
  },
  "hk-defensive": {
    name: "香港防守型",
    risk: "较低波动",
    coverage: "香港指数、银行、房托、现金",
    description: "现金储备较高、更重视防守的香港市场研究组合。",
    keywords: ["香港", "防守", "现金", "收益"]
  }
};

function localizedModelPortfolio(portfolio: ModelPortfolio, language: Language): ModelPortfolio {
  return language === "zh" && ZH_MODEL_COPY[portfolio.id] ? { ...portfolio, ...ZH_MODEL_COPY[portfolio.id] } : portfolio;
}

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
      BND: "Vanguard Total Bond Market ETF",
      QQQ: "Invesco QQQ Trust",
      SPY: "S&P 500 ETF",
      SGOV: "0-3 Month Treasury Bill ETF",
      UNH: "UnitedHealth",
      V: "Visa",
      VTI: "Vanguard Total Stock Market ETF",
      VXUS: "Vanguard Total International Stock ETF",
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

const MODEL_PORTFOLIOS: Record<MarketProfile, ModelPortfolio[]> = {
  us: [
    {
      id: "total-us",
      name: "Total US Market",
      risk: "Market beta",
      coverage: "US all-cap stocks",
      description: "Broad US equity baseline, useful as the practical default before adding active views.",
      keywords: ["US", "broad", "index-like", "equity"],
      weights: { VTI: 1 }
    },
    {
      id: "sp500-core",
      name: "S&P 500 Core",
      risk: "Market beta",
      coverage: "US large cap",
      description: "Large-company US benchmark exposure with less single-stock decision risk.",
      keywords: ["US", "large-cap", "S&P 500", "simple"],
      weights: { SPY: 1 }
    },
    {
      id: "balanced-growth",
      name: "Balanced Growth",
      risk: "Moderate",
      coverage: "US, international, bonds",
      description: "A steadier research starting point with US equity as the core and ballast from bonds and cash.",
      keywords: ["US", "international", "bonds", "cash"],
      weights: { VTI: 0.55, QQQ: 0.15, VXUS: 0.15, BND: 0.1, CASH: 0.05 }
    },
    {
      id: "growth-tech",
      name: "Growth Tech Tilt",
      risk: "Aggressive",
      coverage: "US growth, tech, light international",
      description: "Keeps a broad US core but deliberately leans toward Nasdaq-style growth exposure.",
      keywords: ["tech", "growth", "US", "higher volatility"],
      weights: { VTI: 0.55, QQQ: 0.25, VXUS: 0.1, SGOV: 0.05, CASH: 0.05 }
    },
    {
      id: "defensive",
      name: "Defensive Allocator",
      risk: "Lower volatility",
      coverage: "US, international, bonds, cash",
      description: "A more conservative sandbox for drawdown control and dry powder.",
      keywords: ["defensive", "bonds", "cash", "lower drawdown"],
      weights: { VTI: 0.35, QQQ: 0.05, VXUS: 0.15, BND: 0.35, CASH: 0.1 }
    },
    {
      id: "core-satellite",
      name: "Core + AI Leaders",
      risk: "Aggressive",
      coverage: "US index core plus selected mega-cap tech",
      description: "A practical bridge between index investing and single-stock experimentation.",
      keywords: ["US", "tech", "single stocks", "active tilt"],
      weights: { VTI: 0.4, SPY: 0.15, QQQ: 0.15, AAPL: 0.05, MSFT: 0.05, NVDA: 0.05, AVGO: 0.03, VXUS: 0.07, CASH: 0.05 }
    }
  ],
  hk: [
    {
      id: "hk-tracker",
      name: "HK Tracker Core",
      risk: "Market beta",
      coverage: "Hong Kong index",
      description: "Simple Hong Kong benchmark exposure through the tracker fund.",
      keywords: ["HK", "index", "simple"],
      weights: { "2800.HK": 1 }
    },
    {
      id: "hk-balanced",
      name: "HK Balanced Core",
      risk: "Moderate",
      coverage: "HK index, financials, internet, cash",
      description: "Uses the tracker as the anchor with modest active exposure and a cash buffer.",
      keywords: ["HK", "core", "cash", "active"],
      weights: { "2800.HK": 0.55, "0700.HK": 0.15, "1299.HK": 0.1, "0005.HK": 0.1, CASH: 0.1 }
    },
    {
      id: "hk-defensive",
      name: "HK Defensive",
      risk: "Lower volatility",
      coverage: "HK index, bank, REIT, cash",
      description: "A more defensive Hong Kong research mix with a larger cash reserve.",
      keywords: ["HK", "defensive", "cash", "income"],
      weights: { "2800.HK": 0.45, "0005.HK": 0.15, "0823.HK": 0.15, CASH: 0.25 }
    }
  ]
};

const US_SINGLE_STOCKS = new Set(["AAPL", "AVGO", "COST", "JNJ", "JPM", "MSFT", "NVDA", "UNH", "V", "XOM"]);
const US_CORE_FUNDS = new Set(["SPY", "VTI", "QQQ"]);
const TECH_TILT_TICKERS = new Set(["AAPL", "AVGO", "MSFT", "NVDA", "QQQ", "XLK"]);
const INTERNATIONAL_TICKERS = new Set(["VXUS"]);
const BOND_TICKERS = new Set(["BND"]);
const CASH_TICKERS = new Set(["CASH", "SGOV"]);

function App() {
  const { language, setLanguage, tr } = useI18n();
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
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [historicalValidation, setHistoricalValidation] = useState<HistoricalValidationPayload | null>(null);
  const [history, setHistory] = useState<HistoryPayload | null>(null);
  const [marketOpportunities, setMarketOpportunities] = useState<MarketOpportunitiesPayload | null>(null);
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
        const [healthPayload, historyPayload, opportunitiesPayload, validationPayload] = await fetchOptionalRunStatus(market);
        setHealth(healthPayload);
        setHistory(historyPayload);
        setMarketOpportunities(opportunitiesPayload);
        setHistoricalValidation(validationPayload);
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
      const [healthPayload, historyPayload, opportunitiesPayload, validationPayload] = await fetchOptionalRunStatus(market);
      setDashboard(dash);
      setBacktest(bt);
      setStrategyComparison(comparison);
      setRules(ruleList);
      setOhlc(ohlcRows);
      setQuotes(quoteRows);
      setSentiment(sentimentPayload);
      setHealth(healthPayload);
      setHistory(historyPayload);
      setMarketOpportunities(opportunitiesPayload);
      setHistoricalValidation(validationPayload);
      applyResearchPositions(dash.positions);
      setHoverCandle(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function tryBootstrap() {
    if (IS_STATIC_DATA_MODE) return null;
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
          <p className="eyebrow">{tr("Portfolio Investing Lab", "投资组合研究室")}</p>
          <h1>{tr("Rules, risk, and historical evidence", "规则、风险与历史证据")}</h1>
        </div>
        <div className="controls">
          <label>
            <span>{tr("Market", "市场")}</span>
            <select value={market} onChange={(event) => setMarket(event.target.value as MarketProfile)}>
              <option value="us">{tr("US Stocks", "美国股票")}</option>
              <option value="hk">{tr("Hong Kong", "香港市场")}</option>
            </select>
          </label>
          <label>
            <span>{tr("Data", "数据")}</span>
            <select value={mode} onChange={(event) => setMode(event.target.value)}>
              <option value="real">{tr("Real historical", "真实历史数据")}</option>
              <option value="sandbox">{tr("Sandbox", "沙盒")}</option>
            </select>
          </label>
          <label>
            <span>{tr("Lookback", "回看区间")}</span>
            <select value={lookbackDays} onChange={(event) => setLookbackDays(Number(event.target.value))}>
              <option value={500}>500 {tr("days", "天")}</option>
              <option value={900}>900 {tr("days", "天")}</option>
              <option value={1200}>1200 {tr("days", "天")}</option>
              <option value={1800}>1800 {tr("days", "天")}</option>
            </select>
          </label>
          <div className="language-control" role="group" aria-label={tr("Interface language", "界面语言")}>
            <Languages size={16} aria-hidden="true" />
            <button type="button" className={language === "en" ? "active" : ""} aria-pressed={language === "en"} onClick={() => setLanguage("en")}>EN</button>
            <button type="button" className={language === "zh" ? "active" : ""} aria-pressed={language === "zh"} onClick={() => setLanguage("zh")}>中文</button>
          </div>
          <button className="primary-button" onClick={() => void load()} disabled={loading}>
            <RefreshCw size={16} />
            {loading ? tr("Running", "更新中") : tr("Refresh", "刷新")}
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

          <RunHealthPanel health={health} history={history} sentiment={sentiment} />

          {market === "us" && marketOpportunities ? <MarketOpportunityPanel payload={marketOpportunities} /> : null}

          <section className="metric-grid">
            <MetricCard
              icon={<Gauge size={19} />}
              label={tr("Market Regime", "市场状态")}
              value={localizeLabel(dashboard.market_regime.trend_state, language)}
              detail={`${tickerLabel(dashboard.market_regime.benchmark, market)} ${money(dashboard.market_regime.price)} ${tr("vs MA", "对比均线")} ${money(
                dashboard.market_regime.trend_ma
              )}`}
            />
            <MetricCard
              icon={<TrendingUp size={19} />}
              label={tr("Momentum", "动量")}
              value={percent(dashboard.market_regime.momentum)}
              detail={`${tr("Drawdown", "回撤")} ${percent(dashboard.market_regime.drawdown)}`}
            />
            <MetricCard
              icon={<Brain size={19} />}
              label={tr("ML Risk", "机器学习风险")}
              value={`${topRisks.filter((item) => item.risk_level === "high").length} ${tr("high", "高风险")}`}
              detail={topRisks[0] ? `${tickerLabel(topRisks[0].ticker, market)}: ${percent(topRisks[0].risk_probability)}` : tr("No predictions", "暂无预测")}
            />
            <MetricCard
              icon={<ShieldCheck size={19} />}
              label={tr("Recommendations", "建议")}
              value={String(dashboard.suggestions.length)}
              detail={`${tr("As of", "截至")} ${dashboard.price_as_of ?? tr("unknown", "未知")}`}
            />
          </section>

          <section className="conclusion-grid">
            <Panel title={tr("Key Takeaways", "核心结论")} icon={<ShieldCheck size={18} />}>
              <TakeawayList items={dashboard.advisor_summary} />
            </Panel>
            <Panel title={tr("Suggested Portfolio Distribution", "建议投资组合配置")} icon={<Gauge size={18} />} className="wide-panel">
              <DistributionTable rows={dashboard.recommended_distribution} market={market} />
            </Panel>
          </section>

          <section className="conclusion-grid">
            <Panel title={tr("My Research Portfolio", "我的研究组合")} icon={<Save size={18} />} className="portfolio-panel">
              <PortfolioEditor
                market={market}
                positions={researchPositions}
                defaultPositions={dashboard.positions}
                onChange={setResearchPositions}
              />
            </Panel>
            <Panel title={tr("Personalized Action Gap", "个性化调整差距")} icon={<Gauge size={18} />} className="wide-panel">
              <PersonalizedGapTable positions={researchPositions} rows={dashboard.recommended_distribution} market={market} />
            </Panel>
          </section>

          {dashboard.optimization?.profiles.length ? (
            <section className="portfolio-comparison-row">
              <Panel title={tr("Portfolio Optimizer & Action Plan", "组合优化与行动计划")} icon={<Gauge size={18} />} className="wide-panel">
                <OptimizationPanel optimization={dashboard.optimization} market={market} />
              </Panel>
            </section>
          ) : null}

          <section className="portfolio-comparison-row">
            <Panel title={tr("Selected Portfolio vs Indexes", "所选组合与指数对比")} icon={<BarChart3 size={18} />} className="wide-panel">
              <PortfolioComparison positions={researchPositions} targetWeights={dashboard.target_weights} market={market} />
            </Panel>
          </section>

          {historicalValidation ? (
            <section className="portfolio-comparison-row">
              <Panel title={tr("10-Year Walk-Forward Validation", "十年滚动历史验证")} icon={<BarChart3 size={18} />} className="wide-panel">
                <HistoricalValidationPanel validation={historicalValidation} />
              </Panel>
            </section>
          ) : null}

          <section className="dashboard-grid">
            <Panel title={tr("News Sentiment & AI Readout", "新闻情绪与 AI 解读")} icon={<Newspaper size={18} />} className="wide-panel">
              {sentiment ? <SentimentPanel sentiment={sentiment} market={market} /> : <EmptyState label={tr("News sentiment loading.", "正在加载新闻情绪。")} />}
            </Panel>

            <Panel title={tr("Benchmark Path", "基准走势")} icon={<Activity size={18} />} className="wide-panel">
              <BenchmarkArea points={dashboard.benchmark_series} />
            </Panel>

            <Panel title={tr("Backtest Snapshot", "回测摘要")} icon={<BarChart3 size={18} />}>
              {backtest ? <BacktestMetrics backtest={backtest} /> : <EmptyState label={tr("Run backtest to compare.", "运行回测后进行比较。")} />}
            </Panel>

            <Panel title={tr("Latest Market Data", "最新市场数据")} icon={<Activity size={18} />}>
              <QuotesTable quotes={quotes} market={market} />
            </Panel>

            <Panel title={`${tickerLabel(dashboard.universe.benchmark, market)} ${tr("K-Line", "K 线")}`} icon={<Activity size={18} />} className="wide-panel">
              <CandlestickChart rows={ohlc} hover={hoverCandle} setHover={setHoverCandle} />
            </Panel>

            <Panel title={tr("Allocation Pie", "配置比例")} icon={<Gauge size={18} />}>
              <AllocationPie positions={dashboard.positions} market={market} />
            </Panel>

            <Panel title={tr("Strategy Comparison", "策略对比")} icon={<BarChart3 size={18} />} className="wide-panel">
              {strategyComparison ? <StrategyComparison comparison={strategyComparison} /> : <EmptyState label={tr("Strategy comparison loading.", "正在加载策略对比。")} />}
            </Panel>

            <Panel title={tr("Strategy Metrics", "策略指标")} icon={<Gauge size={18} />}>
              {strategyComparison ? <StrategyMetrics comparison={strategyComparison} /> : <EmptyState label={tr("No comparison metrics.", "暂无对比指标。")} />}
            </Panel>

            <Panel title={tr("Rule Recommendations", "规则建议")} icon={<ShieldCheck size={18} />} className="wide-panel">
              <RecommendationTable suggestions={dashboard.suggestions} market={market} />
            </Panel>

            <Panel title={tr("ML Risk Ranking", "机器学习风险排名")} icon={<Brain size={18} />}>
              <RiskList risks={topRisks} market={market} />
            </Panel>

            <Panel title={tr("Sector Signals", "板块信号")} icon={<FlaskConical size={18} />} className="wide-panel">
              <SectorTable signals={dashboard.signals} market={market} />
            </Panel>

            <Panel title={tr("Allocation Drift", "配置偏离")} icon={<Gauge size={18} />}>
              <AllocationBars positions={dashboard.positions} targets={dashboard.target_weights} market={market} />
            </Panel>

            <Panel title={tr("Instrument Guide", "标的说明")} icon={<Activity size={18} />} className="wide-panel">
              <InstrumentGuide dashboard={dashboard} market={market} quotes={quotes} />
            </Panel>

            <Panel title={tr("Strategy Rule Book", "策略规则手册")} icon={<ShieldCheck size={18} />} className="wide-panel">
              <RulesTable rules={rules} />
            </Panel>
          </section>
        </>
      ) : (
        <section className="loading-surface">{tr("Loading portfolio lab...", "正在加载投资组合研究室...")}</section>
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
  const { language, tr } = useI18n();
  const quoteSource = quotes[0]?.source ?? tr("snapshot/API", "快照/API");
  const refreshedAt = dashboard.snapshot?.generated_at ? formatDateTime(dashboard.snapshot.generated_at, language) : tr("unknown", "未知");
  const tickerConvention = tr(
    marketInfo.tickerConvention,
    marketInfo.currency === "USD"
      ? "美国交易所股票使用 AAPL、MSFT、SPY 等普通代码。"
      : "港交所本地代码为数字；yfinance/Yahoo 使用 .HK 后缀，例如 0700.HK。"
  );
  const dataTruth = tr(
    marketInfo.dataTruth,
    marketInfo.currency === "USD"
      ? "价格和历史数据来自 yfinance/Yahoo 的真实市场数据，并通过 API/静态快照发布。"
      : "价格和历史数据来自 yfinance/Yahoo 的真实香港市场数据，并通过 API/静态快照发布。"
  );
  const portfolioTruth = tr(
    marketInfo.portfolioTruth,
    marketInfo.currency === "USD"
      ? "在您输入自己的持仓前，当前持仓仅为研究示例组合。"
      : "组合权重为香港市场沙盒示例，并非您的真实券商持仓。"
  );
  return (
    <section className="truth-banner">
      <div>
        <strong>{tr(marketInfo.label, marketInfo.currency === "USD" ? "美国股票" : "香港市场")}</strong>
        <span>{tickerConvention}</span>
      </div>
      <div>
        <strong>{tr("Market data is real", "市场数据真实有效")}</strong>
        <span>
          {dataTruth} {tr("Latest quote source", "最新报价来源")}: {quoteSource}; {tr("market price date", "市场价格日期")}: {dashboard.price_as_of ?? tr("unknown", "未知")}; {tr("snapshot refreshed", "快照刷新时间")}: {refreshedAt}.
        </span>
      </div>
      <div>
        <strong>{tr("Portfolio is editable research input", "投资组合是可编辑的研究输入")}</strong>
        <span>{portfolioTruth}</span>
      </div>
    </section>
  );
}

async function fetchOptionalRunStatus(
  market: MarketProfile
): Promise<[HealthPayload | null, HistoryPayload | null, MarketOpportunitiesPayload | null, HistoricalValidationPayload | null]> {
  const [healthResult, historyResult, opportunitiesResult, validationResult] = await Promise.allSettled([
    fetchHealth(market),
    fetchHistory(market),
    fetchMarketOpportunities(market),
    fetchHistoricalValidation(market)
  ]);
  return [
    healthResult.status === "fulfilled" ? healthResult.value : null,
    historyResult.status === "fulfilled" ? historyResult.value : null,
    opportunitiesResult.status === "fulfilled" ? opportunitiesResult.value : null,
    validationResult.status === "fulfilled" ? validationResult.value : null
  ];
}

function MarketOpportunityPanel({ payload }: { payload: MarketOpportunitiesPayload }) {
  const { language, tr } = useI18n();
  const groups = [
    { key: "buy", title: tr("Best research setups", "最佳研究机会"), rows: payload.buy_candidates, count: payload.action_counts.buy_candidate },
    { key: "hold", title: tr("Hold / watch", "持有 / 观察"), rows: payload.hold_watch, count: payload.action_counts.hold_watch },
    { key: "sell", title: tr("Sell / avoid review", "卖出 / 回避审查"), rows: payload.sell_avoid, count: payload.action_counts.sell_avoid }
  ];
  const deepResearch = payload.deep_research;

  return (
    <section className="market-opportunities" aria-label={tr("Broad market opportunity screen", "广泛市场机会筛选")}>
      <header>
        <div>
          <span>{tr("Broad US Market Screen", "美国市场广泛筛选")}</span>
          <h2>{tr("High-level opportunity map", "高层机会图")}</h2>
        </div>
        <div className="market-coverage">
          <strong>{payload.universe.analyzed_count.toLocaleString()} / {payload.universe.eligible_total.toLocaleString()}</strong>
          <span>{tr("eligible stocks analyzed", "符合条件股票已分析")} | {tr("prices", "价格日期")} {payload.universe.latest_price_date ?? tr("unknown", "未知")}</span>
          <small className={`research-status ${deepResearch?.status ?? "quote-only"}`}>
            {deepResearch?.researched_count ?? 0} {tr("SEC filing reviews", "份 SEC 申报审查")} | {localizeLabel(deepResearch?.status, language, "quote only")}
          </small>
        </div>
      </header>
      {payload.status === "available" ? (
        <>
          <div className="opportunity-groups">
            {groups.map((group) => (
              <section className={`opportunity-group ${group.key}`} key={group.key}>
                <header>
                  <strong>{group.title}</strong>
                  <span>{group.count} {tr("in universe", "个股票池标的")}</span>
                </header>
                <div>
                  {group.rows.slice(0, 4).map((row) => {
                    const research = row.research;
                    const scorecard = research?.scorecard;
                    const decision = research?.decision ?? row.action;
                    const evidence = research?.key_takeaways?.[0] ?? row.reason;
                    const report = research?.earnings;
                    return (
                      <article className={`decision-card ${decision}`} key={row.ticker} title={row.reason}>
                        <div className="decision-heading">
                          <div>
                            <strong>{row.ticker}</strong>
                            <span>{row.name}</span>
                          </div>
                          <span className={`decision-badge ${decision}`}>
                            {research?.decision_label ? localizeLabel(research.decision_label, language) : group.title}
                          </span>
                        </div>
                        <div className="decision-context">
                          <span>{research?.sector ?? row.exchange}</span>
                          <span>{localizeLabel(research?.confidence, language, "low")} {tr("confidence", "置信度")}</span>
                          <span>{localizeBusinessModel(research?.business_model, language, tr("trend screen", "趋势筛选"))}</span>
                        </div>
                        <p>{evidence}</p>
                        {research?.risks?.[0] ? <small className="decision-risk">{research.risks[0]}</small> : null}
                        <div className="decision-scores" aria-label={`${row.ticker} ${tr("research scorecard", "研究评分卡")}`}>
                          <ScoreChip label={tr("Quality", "质量")} value={scorecard?.quality} />
                          <ScoreChip label={tr("Value", "估值")} value={scorecard?.value} />
                          <ScoreChip label={tr("Earnings", "盈利")} value={scorecard?.earnings} />
                          <ScoreChip label={tr("Trend", "趋势")} value={scorecard?.trend ?? row.score} />
                        </div>
                        <div className="earnings-line">
                          {report?.report_url ? (
                            <a href={report.report_url} target="_blank" rel="noreferrer" title={tr("Open SEC earnings filing", "打开 SEC 盈利申报")}>
                              <FileText size={13} aria-hidden="true" />
                              <span>{report.latest_report_form} {tr("filed", "申报于")} {report.filed_at ?? tr("date unknown", "日期未知")}</span>
                            </a>
                          ) : (
                            <span>{tr("Forward P/E", "预期市盈率")} {row.forward_pe?.toFixed(1) ?? tr("n/a", "不适用")}</span>
                          )}
                          <strong>{research?.decision_score?.toFixed(0) ?? row.score.toFixed(0)}</strong>
                        </div>
                      </article>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
          <footer>
            <span>{payload.universe.definition}</span>
            <span>{deepResearch?.note ?? payload.methodology.policy}</span>
            <a href={payload.source.url} target="_blank" rel="noreferrer">{payload.source.name}</a>
          </footer>
        </>
      ) : (
        <p className="market-screen-unavailable">{payload.note ?? tr("The broad-market screen is unavailable for this snapshot.", "此快照暂时无法使用广泛市场筛选。")}</p>
      )}
    </section>
  );
}

function ScoreChip({ label, value }: { label: string; value: number | null | undefined }) {
  const { tr } = useI18n();
  const status = value == null ? "unknown" : value >= 67 ? "strong" : value >= 45 ? "mixed" : "weak";
  return (
    <div className={status} title={`${label}: ${value == null ? tr("pending", "等待中") : value.toFixed(0) + "/100"}`}>
      <span>{label.slice(0, 1)}</span>
      <strong>{value == null ? "-" : value.toFixed(0)}</strong>
    </div>
  );
}

function RunHealthPanel({
  health,
  history,
  sentiment
}: {
  health: HealthPayload | null;
  history: HistoryPayload | null;
  sentiment: SentimentPayload | null;
}) {
  const { language, tr } = useI18n();
  const research = sentiment?.summary.research_overlay;
  const informationSigns = sentiment?.summary.information_signs;
  const latestRuns = history?.runs.slice(0, 5) ?? [];
  const status = health?.stale_price ? "stale" : "fresh";
  return (
    <section className="run-health">
      <div className={`run-health-summary ${status}`}>
        <div>
          <span>{tr("Scheduler Health", "调度器状态")}</span>
          <strong>{health ? (health.stale_price ? tr("Needs review", "需要检查") : tr("Fresh", "正常")) : tr("Pending", "等待中")}</strong>
          <small>{tr("Snapshot", "快照")} {health ? formatDateTime(health.generated_at, language) : tr("not loaded", "尚未加载")}</small>
        </div>
        <div>
          <span>{tr("Market Data", "市场数据")}</span>
          <strong>{health?.price_as_of ?? tr("unknown", "未知")}</strong>
          <small>{tr("price date is", "价格日期距今")} {health?.days_since_price ?? "?"} {tr("days old", "天")}</small>
        </div>
        <div>
          <span>{tr("Local AI Layer", "本地 AI 层")}</span>
          <strong>{localizeLabel(health?.llm_status, language)}</strong>
          <small>{[health?.llm_provider, health?.llm_model].filter(Boolean).join(" / ") || tr("no model", "无模型")}</small>
        </div>
        <div>
          <span>{tr("Research Overlay", "研究叠加层")}</span>
          <strong>{localizeLabel(research?.status ?? health?.research_overlay_status, language)}</strong>
          <small>{research?.note_count ?? health?.research_overlay_note_count ?? 0} {tr("private notes applied", "条私人笔记已应用")}</small>
        </div>
        <div>
          <span>{tr("Public Information", "公开信息")}</span>
          <strong>{localizeLabel(informationSigns?.status ?? health?.information_signs_status, language)}</strong>
          <small>{informationSigns?.sign_count ?? health?.information_sign_count ?? 0} {tr("sourced signs, decision weight 0", "条有来源信号，决策权重为 0")}</small>
        </div>
      </div>
      {latestRuns.length ? (
        <div className="run-history">
          {latestRuns.map((run) => (
            <div key={`${run.market}-${run.generated_at}`}>
              <span>{formatShortDateTime(run.generated_at, language)}</span>
              <strong>{run.price_as_of ?? tr("unknown", "未知")}</strong>
              <em>{localizeLabel(run.investment_posture, language)}</em>
              <small>{localizeLabel(run.llm_status, language)}</small>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function formatDateTime(value: string, language: Language = "en") {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString(language === "zh" ? "zh-CN" : "en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short"
  });
}

function formatShortDateTime(value: string, language: Language = "en") {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString(language === "zh" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
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
  const { tr } = useI18n();
  if (points.length < 2) return <EmptyState label={tr("No benchmark series available.", "暂无基准序列。")}/>;

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
          <Area dataKey="value" name={tr("Close", "收盘")} type="monotone" stroke="#1f6f5b" fill="url(#benchmarkGradient)" strokeWidth={2.5} />
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
  const { tr } = useI18n();
  const visible = rows.slice(-120);
  if (visible.length < 2) return <EmptyState label={tr("No OHLC data available.", "暂无开高低收数据。")}/>;

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
          <span>{tr("Hover over candles for OHLC detail", "将鼠标移到 K 线上查看开高低收详情")}</span>
        )}
      </div>
      <svg className="kline-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={tr("Candlestick chart", "K 线图")}>
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

function OptimizationPanel({
  optimization,
  market
}: {
  optimization: DashboardPayload["optimization"];
  market: MarketProfile;
}) {
  const { language, tr } = useI18n();
  const [profileId, setProfileId] = useState(optimization.profiles[0]?.id ?? "");
  const profile = optimization.profiles.find((item) => item.id === profileId) ?? optimization.profiles[0];

  useEffect(() => {
    setProfileId(optimization.profiles[0]?.id ?? "");
  }, [optimization]);

  if (!profile) return <EmptyState label={tr("No optimizer profile is available.", "暂无可用优化组合。")} />;
  const metric = (value: number | null) => (value == null ? "-" : percent(value));
  const materialRows = profile.rows
    .filter((row) => Math.abs(row.delta_weight) >= 0.005 || row.action === "HOLD")
    .slice(0, 14);

  return (
    <div className="optimizer-panel">
      <div className="profile-tabs" role="tablist" aria-label={tr("Risk profile", "风险档位")}>
        {optimization.profiles.map((item) => (
          <button
            type="button"
            role="tab"
            aria-selected={item.id === profile.id}
            className={item.id === profile.id ? "active" : ""}
            key={item.id}
            onClick={() => setProfileId(item.id)}
          >
            <strong>{language === "zh" ? item.name_zh : item.name_en}</strong>
            <span>{localizeLabel(item.risk_level, language)}</span>
          </button>
        ))}
      </div>

      <div className="optimizer-summary">
        <div>
          <span>{tr("Trailing return", "历史年化收益")}</span>
          <strong>{metric(profile.metrics.annualized_return)}</strong>
        </div>
        <div>
          <span>{tr("Volatility", "年化波动率")}</span>
          <strong>{metric(profile.metrics.annualized_volatility)}</strong>
        </div>
        <div>
          <span>{tr("Sharpe", "夏普比率")}</span>
          <strong>{profile.metrics.sharpe_ratio == null ? "-" : profile.metrics.sharpe_ratio.toFixed(2)}</strong>
        </div>
        <div>
          <span>{tr("Max drawdown", "最大回撤")}</span>
          <strong>{metric(profile.metrics.max_drawdown)}</strong>
        </div>
        <div>
          <span>{tr("Estimated turnover", "预计换手率")}</span>
          <strong>{percent(profile.metrics.turnover)}</strong>
        </div>
      </div>

      <div className={`optimizer-explainer ${profile.status}`}>
        <div>
          <strong>{language === "zh" ? profile.objective_zh : profile.objective_en}</strong>
          <span>
            {tr("Long-only, no leverage; trailing diagnostics through", "只做多、不加杠杆；历史诊断截至")}{" "}
            {optimization.data_as_of ?? profile.evidence.end_date ?? "-"}
          </span>
        </div>
        <small>
          {profile.status === "fallback"
            ? `${tr("Fallback used", "已使用保守回退方案")}: ${profile.fallback_reason}`
            : language === "zh"
              ? profile.evidence.basis_zh
              : profile.evidence.basis_en}
        </small>
      </div>

      <div className="table-wrap optimizer-table">
        <table>
          <thead>
            <tr>
              <th>{tr("Priority", "优先级")}</th>
              <th>{tr("Holding", "标的")}</th>
              <th>{tr("Action", "操作")}</th>
              <th>{tr("Current", "当前")}</th>
              <th>{tr("Target", "目标")}</th>
              <th>{tr("Gap", "差额")}</th>
              <th>{tr("Why this allocation", "为什么这样配置")}</th>
            </tr>
          </thead>
          <tbody>
            {materialRows.map((row) => (
              <tr key={`${profile.id}-${row.ticker}`}>
                <td>{row.priority}</td>
                <td><TickerCell ticker={row.ticker} market={market} /></td>
                <td><span className={`badge ${row.action.toLowerCase()}`}>{localizeLabel(row.action, language)}</span></td>
                <td>{percent(row.current_weight)}</td>
                <td>{percent(row.target_weight)}</td>
                <td className={row.delta_weight >= 0 ? "positive" : "negative"}>{formatSignedPercent(row.delta_weight)}</td>
                <td>
                  {language === "zh" ? row.reason_zh : row.reason_en}
                  <small className="rule-trace">{row.rule_ids.join(" · ")}</small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="methodology-note">
        {language === "zh" ? optimization.methodology_zh : optimization.methodology}
      </p>
    </div>
  );
}

function HistoricalValidationPanel({ validation }: { validation: HistoricalValidationPayload }) {
  const { language, tr } = useI18n();
  const colors = ["#526168", "#1f6f5b", "#3a73a8", "#d0962f", "#9b5c72"];
  const merged = mergeValidationCurves(validation);
  const limitations = language === "zh" ? validation.limitations_zh : validation.limitations_en;
  return (
    <div className="historical-validation">
      <div className="validation-header">
        <div>
          <strong>
            {validation.evaluation_start_date} - {validation.evaluation_end_date}
          </strong>
          <span>
            {tr("Signals at close t; first return exposure on t+1", "t 日收盘计算信号；最早从 t+1 日承担收益")}
          </span>
        </div>
        <span className="validation-status">{tr("Exploratory, not production proof", "探索性结果，不是实盘有效性证明")}</span>
      </div>

      <div className="validation-chart">
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={merged} margin={{ top: 8, right: 18, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#e6ecef" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={42} />
            <YAxis tick={{ fontSize: 11 }} width={54} />
            <Tooltip content={<ChartTooltip />} />
            {validation.tracks.map((track, index) => (
              <Area
                key={track.id}
                dataKey={track.id}
                name={language === "zh" ? track.name_zh : track.name_en}
                type="monotone"
                stroke={colors[index % colors.length]}
                fill={colors[index % colors.length]}
                fillOpacity={0.04}
                strokeWidth={track.id === "benchmark" ? 2 : 2.4}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="strategy-legend">
        {validation.tracks.map((track, index) => (
          <span key={track.id}>
            <i style={{ background: colors[index % colors.length] }} />
            {language === "zh" ? track.name_zh : track.name_en}
          </span>
        ))}
      </div>

      <div className="table-wrap validation-table">
        <table>
          <thead>
            <tr>
              <th>{tr("Model", "模型")}</th>
              <th>CAGR</th>
              <th>{tr("vs benchmark", "相对基准")}</th>
              <th>{tr("Sharpe", "夏普")}</th>
              <th>{tr("Max drawdown", "最大回撤")}</th>
              <th>{tr("Turnover", "累计换手")}</th>
              <th>{tr("Rebalances", "调仓次数")}</th>
            </tr>
          </thead>
          <tbody>
            {validation.tracks.map((track) => (
              <tr key={track.id} title={language === "zh" ? track.description_zh : track.description_en}>
                <td>{language === "zh" ? track.name_zh : track.name_en}</td>
                <td>{percent(track.metrics.cagr)}</td>
                <td className={track.metrics.excess_cagr_vs_benchmark >= 0 ? "positive" : "negative"}>
                  {formatSignedPercent(track.metrics.excess_cagr_vs_benchmark)}
                </td>
                <td>{track.metrics.sharpe.toFixed(2)}</td>
                <td>{percent(track.metrics.max_drawdown)}</td>
                <td>{percent(track.turnover)}</td>
                <td>{track.rebalance_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="validation-limitations">
        <strong>{tr("What this test does not prove", "这项测试尚不能证明什么")}</strong>
        <ul>
          {limitations.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </div>
    </div>
  );
}

function mergeValidationCurves(validation: HistoricalValidationPayload) {
  const rows = new Map<string, Record<string, string | number>>();
  for (const track of validation.tracks) {
    const step = Math.max(1, Math.floor(track.equity_curve.length / 600));
    track.equity_curve.forEach((point, index) => {
      if (index % step !== 0 && index !== track.equity_curve.length - 1) return;
      const row = rows.get(point.date) ?? { date: point.date };
      row[track.id] = point.portfolio_value;
      rows.set(point.date, row);
    });
  }
  return Array.from(rows.values()).sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

function BacktestMetrics({ backtest }: { backtest: BacktestPayload }) {
  const { tr } = useI18n();
  return (
    <div className="metric-list">
      <Row label={tr("Final value", "期末价值")} value={backtest.metrics.final_value.toFixed(3)} />
      <Row label="CAGR" value={percent(backtest.metrics.cagr)} />
      <Row label={tr("Volatility", "波动率")} value={percent(backtest.metrics.annualized_volatility)} />
      <Row label={tr("Sharpe", "夏普比率")} value={backtest.metrics.sharpe.toFixed(2)} />
      <Row label={tr("Max drawdown", "最大回撤")} value={percent(backtest.metrics.max_drawdown)} />
    </div>
  );
}

function QuotesTable({ quotes, market }: { quotes: LatestQuote[]; market: MarketProfile }) {
  const { tr } = useI18n();
  if (!quotes.length) return <EmptyState label={tr("Latest market data unavailable.", "最新市场数据不可用。")}/>;
  const marketInfo = MARKET_INFO[market];
  return (
    <div className="table-wrap compact-table">
      <table>
        <thead>
          <tr>
            <th>{tr("Ticker", "代码")}</th>
            <th>{tr("Price", "价格")} ({marketInfo.currency})</th>
            <th>{tr("Change", "涨跌")}</th>
            <th>{tr("As of", "截至")}</th>
          </tr>
        </thead>
        <tbody>
          {quotes.slice(0, 8).map((quote) => (
            <tr key={quote.ticker} title={`${tr("Source", "来源")}: ${quote.source}`}>
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
  const { language } = useI18n();
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
              name={localizeStrategyName(name, language)}
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
            {localizeStrategyName(strategy.name, language)}
          </span>
        ))}
      </div>
    </div>
  );
}

function StrategyMetrics({ comparison }: { comparison: StrategyComparisonPayload }) {
  const { language, tr } = useI18n();
  const data = comparison.strategies.map((strategy) => ({
    name: localizeStrategyName(strategy.name, language),
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
              <th>{tr("Strategy", "策略")}</th>
              <th>CAGR</th>
              <th>{tr("Sharpe", "夏普")}</th>
              <th>{tr("Max DD", "最大回撤")}</th>
            </tr>
          </thead>
          <tbody>
            {comparison.strategies.map((strategy) => (
              <tr key={strategy.name} title={strategy.description}>
                <td>{localizeStrategyName(strategy.name, language)}</td>
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
  const { language, tr } = useI18n();
  if (!suggestions.length) return <EmptyState label={tr("No recommendations met thresholds.", "暂无建议达到阈值。")}/>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{tr("Ticker", "代码")}</th>
            <th>{tr("Action", "操作")}</th>
            <th>{tr("Delta", "差值")}</th>
            <th>{tr("Rules", "规则")}</th>
            <th>{tr("Reason", "原因")}</th>
          </tr>
        </thead>
        <tbody>
          {suggestions.map((item) => (
            <tr key={`${item.ticker}-${item.action}-${item.reason}`}>
              <td>
                <TickerCell ticker={item.ticker} market={market} />
              </td>
              <td>
                <span className={`badge ${item.action}`}>{localizeLabel(item.action, language)}</span>
              </td>
              <td>{percent(item.delta_weight)}</td>
              <td>{item.rule_ids.join(", ") || "-"}</td>
              <td>{localizeReason(item.reason, language)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TakeawayList({ items }: { items: DashboardPayload["advisor_summary"] }) {
  const { language, tr } = useI18n();
  if (!items.length) return <EmptyState label={tr("No conclusions available.", "暂无结论。")}/>;
  return (
    <div className="takeaway-list">
      {items.map((item) => {
        const localized = localizedTakeaway(item, language);
        return (
          <article className={`takeaway ${item.severity}`} key={`${item.rank}-${item.title}`}>
            <div className="takeaway-rank">{item.rank}</div>
            <div>
              <strong>{localized.title}</strong>
              <p>{localized.detail}</p>
              <span>{item.rule_ids.join(", ")}</span>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function DistributionTable({ rows, market }: { rows: DashboardPayload["recommended_distribution"]; market: MarketProfile }) {
  const { language, tr } = useI18n();
  const visible = rows.filter((row) => row.current_weight > 0 || row.recommended_weight > 0).slice(0, 14);
  return (
    <div className="table-wrap distribution-table">
      <table>
        <thead>
          <tr>
            <th>{tr("Priority", "优先级")}</th>
            <th>{tr("Ticker", "代码")}</th>
            <th>{tr("Action", "操作")}</th>
            <th>{tr("Current", "当前")}</th>
            <th>{tr("Target", "目标")}</th>
            <th>{tr("Suggested", "建议")}</th>
            <th>{tr("Delta", "差值")}</th>
            <th>{tr("Reason", "原因")}</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((row, index) => (
            <tr key={row.ticker} title={`${tr("Rules", "规则")}: ${row.rule_ids.join(", ") || tr("none", "无")}`}>
              <td>{index + 1}</td>
              <td>
                <strong>{row.ticker}</strong>
                <span>{instrumentName(row.ticker, market)}</span>
                <span>{row.sector}</span>
              </td>
              <td>
                <span className={`badge ${row.action}`}>{localizeLabel(row.action, language)}</span>
              </td>
              <td>{percent(row.current_weight)}</td>
              <td>{percent(row.target_weight)}</td>
              <td>
                <strong>{percent(row.recommended_weight)}</strong>
              </td>
              <td className={row.delta_weight >= 0 ? "positive" : "negative"}>{percent(row.delta_weight)}</td>
              <td>{localizeReason(row.reason, language)}</td>
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
  const { language, tr } = useI18n();
  const templates = MODEL_PORTFOLIOS[market].map((template) => localizedModelPortfolio(template, language));
  const [templateId, setTemplateId] = useState(templates[0]?.id ?? "");
  const selectedTemplate = templates.find((template) => template.id === templateId) ?? templates[0];
  const templateTickers = Object.fromEntries(templates.flatMap((template) => Object.keys(template.weights)).map((ticker) => [ticker, 0]));
  const tickers = Object.keys({ ...templateTickers, ...defaultPositions, ...positions }).sort((a, b) =>
    a === "CASH" ? -1 : b === "CASH" ? 1 : a.localeCompare(b)
  );
  const total = tickers.reduce((sum, ticker) => sum + (positions[ticker] ?? 0), 0);
  const normalized = normalizeWeights(positions);

  useEffect(() => {
    const nextTemplates = MODEL_PORTFOLIOS[market];
    setTemplateId(nextTemplates[0]?.id ?? "");
  }, [market]);

  function updateTicker(ticker: string, value: string) {
    const pct = Number(value);
    if (!Number.isFinite(pct)) return;
    onChange({ ...positions, [ticker]: Math.max(0, pct / 100) });
  }

  return (
    <div className="portfolio-editor">
      {selectedTemplate ? (
        <div className="template-selector">
          <label>
            <span>{tr("Starting portfolio", "起始组合")}</span>
            <select value={selectedTemplate.id} onChange={(event) => setTemplateId(event.target.value)}>
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </select>
          </label>
          <button type="button" onClick={() => onChange(selectedTemplate.weights)}>
            {tr("Use", "使用")}
          </button>
          <div className="template-summary">
            <strong>{selectedTemplate.name}</strong>
            <p>{selectedTemplate.description}</p>
            <div className="keyword-list">
              <span>{selectedTemplate.risk}</span>
              <span>{selectedTemplate.coverage}</span>
              {selectedTemplate.keywords.map((keyword) => (
                <span key={keyword}>{keyword}</span>
              ))}
            </div>
          </div>
        </div>
      ) : null}
      <div className="editor-actions">
        <span className={Math.abs(total - 1) <= 0.01 ? "total-ok" : "total-warn"}>{tr("Total", "合计")} {percent(total)}</span>
        <button type="button" onClick={() => onChange(normalized)}>
          {tr("Normalize", "归一化")}
        </button>
        <button type="button" onClick={() => savePortfolio(market, positions)}>
          <Save size={14} />
          {tr("Save", "保存")}
        </button>
        <button
          type="button"
          onClick={() => {
            clearPortfolio(market);
            onChange(defaultPositions);
          }}
        >
          <RotateCcw size={14} />
          {tr("Reset", "重置")}
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

function PortfolioComparison({
  positions,
  targetWeights,
  market
}: {
  positions: Record<string, number>;
  targetWeights: Record<string, number>;
  market: MarketProfile;
}) {
  const { tr } = useI18n();
  const benchmarkRows: Array<{ id: string; name: string; risk: string; coverage: string; weights: Record<string, number> }> =
    market === "us"
      ? [
          { id: "selected", name: tr("Selected Portfolio", "所选组合"), risk: tr("Custom", "自定义"), coverage: tr("Your current editor weights", "当前编辑器权重"), weights: positions },
          { id: "vti", name: tr("Total US Market", "美国全市场"), risk: tr("Market beta", "市场风险"), coverage: tr("US all-cap stocks", "美国全市值股票"), weights: { VTI: 1 } },
          { id: "spy", name: "S&P 500", risk: tr("Market beta", "市场风险"), coverage: tr("US large cap", "美国大型股"), weights: { SPY: 1 } },
          { id: "qqq", name: tr("Nasdaq 100", "纳斯达克 100"), risk: tr("Aggressive", "进取"), coverage: tr("US growth and tech-heavy", "美国增长及科技股为主"), weights: { QQQ: 1 } },
          { id: "rule-target", name: tr("Current Rule Target", "当前规则目标"), risk: tr("Rule model", "规则模型"), coverage: tr("App target weights", "应用目标权重"), weights: targetWeights }
        ]
      : [
          { id: "selected", name: tr("Selected Portfolio", "所选组合"), risk: tr("Custom", "自定义"), coverage: tr("Your current editor weights", "当前编辑器权重"), weights: positions },
          { id: "tracker", name: tr("HK Tracker", "香港指数"), risk: tr("Market beta", "市场风险"), coverage: tr("Hong Kong index", "香港市场指数"), weights: { "2800.HK": 1 } },
          { id: "rule-target", name: tr("Current Rule Target", "当前规则目标"), risk: tr("Rule model", "规则模型"), coverage: tr("App target weights", "应用目标权重"), weights: targetWeights }
        ];
  const profiles = benchmarkRows.map((row) => ({ ...row, profile: portfolioProfile(row.weights, market) }));
  const selected = profiles[0].profile;
  const marketBaseline = profiles[1]?.profile ?? selected;
  const equityLabel = market === "us" ? tr("US equity exposure", "美国股票敞口") : tr("Local equity exposure", "本地股票敞口");

  return (
    <div className="portfolio-comparison">
      <div className="comparison-summary">
        <div>
          <span>{equityLabel}</span>
          <strong>{percent(selected.usEquity)}</strong>
          <small>{formatSignedPercent(selected.usEquity - marketBaseline.usEquity)} {tr("vs", "对比")} {profiles[1]?.name ?? tr("baseline", "基准")}</small>
        </div>
        <div>
          <span>{tr("Tech and growth tilt", "科技与增长倾斜")}</span>
          <strong>{percent(selected.techTilt)}</strong>
          <small>{formatSignedPercent(selected.techTilt - marketBaseline.techTilt)} {tr("vs", "对比")} {profiles[1]?.name ?? tr("baseline", "基准")}</small>
        </div>
        <div>
          <span>{tr("Bonds and cash", "债券与现金")}</span>
          <strong>{percent(selected.defensive)}</strong>
          <small>{formatSignedPercent(selected.defensive - marketBaseline.defensive)} {tr("vs", "对比")} {profiles[1]?.name ?? tr("baseline", "基准")}</small>
        </div>
        <div>
          <span>{tr("Top five concentration", "前五大持仓集中度")}</span>
          <strong>{percent(selected.topFive)}</strong>
          <small>{tr("Largest holding", "最大持仓")} {selected.largestTicker ? `${selected.largestTicker} ${percent(selected.largestWeight)}` : tr("none", "无")}</small>
        </div>
      </div>
      <div className="table-wrap compact-table">
        <table>
          <thead>
            <tr>
              <th>{tr("Portfolio", "组合")}</th>
              <th>{tr("Risk / Coverage", "风险 / 覆盖")}</th>
              <th>{market === "us" ? tr("US Equity", "美国股票") : tr("Local Equity", "本地股票")}</th>
              <th>{tr("Tech Tilt", "科技倾斜")}</th>
              <th>{tr("International", "国际")}</th>
              <th>{tr("Bonds + Cash", "债券 + 现金")}</th>
              <th>{tr("Top 5", "前五大")}</th>
              <th>{tr("Largest Holding", "最大持仓")}</th>
            </tr>
          </thead>
          <tbody>
            {profiles.map((row) => (
              <tr key={row.id}>
                <td>
                  <strong>{row.name}</strong>
                  <span>{row.id === "selected" ? tr("active research mix", "当前研究组合") : tr("comparison baseline", "对比基准")}</span>
                </td>
                <td>
                  <span className="badge neutral">{row.risk}</span>
                  <span>{row.coverage}</span>
                </td>
                <td>{percent(row.profile.usEquity)}</td>
                <td>{percent(row.profile.techTilt)}</td>
                <td>{percent(row.profile.international)}</td>
                <td>{percent(row.profile.defensive)}</td>
                <td>{percent(row.profile.topFive)}</td>
                <td>{row.profile.largestTicker ? `${row.profile.largestTicker} ${percent(row.profile.largestWeight)}` : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
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
  const { language, tr } = useI18n();
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
            <th>{tr("Priority", "优先级")}</th>
            <th>{tr("Holding", "持仓")}</th>
            <th>{tr("Action", "操作")}</th>
            <th>{tr("Mine", "我的")}</th>
            <th>{tr("Model", "模型")}</th>
            <th>{tr("Gap", "差距")}</th>
            <th>{tr("Why", "原因")}</th>
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
                <span className={`badge ${row.personalizedAction}`}>{localizeLabel(row.personalizedAction, language)}</span>
              </td>
              <td>{percent(row.current)}</td>
              <td>{percent(row.recommended_weight)}</td>
              <td className={row.gap >= 0 ? "positive" : "negative"}>{percent(row.gap)}</td>
              <td>{localizeReason(row.reason, language)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SentimentPanel({ sentiment, market }: { sentiment: SentimentPayload; market: MarketProfile }) {
  const { language, tr } = useI18n();
  const summary = sentiment.summary;
  const research = summary.research_overlay;
  const informationSigns = summary.information_signs;
  return (
    <div className="sentiment-panel">
      <div className="sentiment-summary">
        <div>
          <span>{tr("Forecast Bias", "预测倾向")}</span>
          <strong className={`sentiment-${summary.forecast_bias}`}>{localizeLabel(summary.forecast_bias, language)}</strong>
        </div>
        <div>
          <span>{tr("News Tone", "新闻基调")}</span>
          <strong className={`sentiment-tone-${summary.label}`}>{localizeLabel(summary.label, language)}</strong>
        </div>
        <div>
          <span>{tr("Confidence", "置信度")}</span>
          <strong className={`sentiment-confidence-${summary.confidence >= 0.65 ? "high" : summary.confidence >= 0.4 ? "medium" : "low"}`}>
            {percent(summary.confidence)}
          </strong>
        </div>
        <div>
          <span>{tr("Articles", "文章")}</span>
          <strong>{summary.article_count}</strong>
        </div>
      </div>
      <p className="sentiment-callout">
        {summary.recommended_action}. {summary.rationale}
      </p>
      {research ? (
        <div className="research-overlay">
          <div>
            <span>{tr("Private Research Overlay", "私人研究叠加层")}</span>
            <strong>{localizeLabel(research.status, language)}</strong>
            <small>{research.decision_use}</small>
          </div>
          {research.notes.slice(0, 3).map((note) => (
            <a key={`${note.source}-${note.title}`} href={note.url || "#"} target="_blank" rel="noreferrer">
              <span className={`badge ${note.stance_label}`}>{localizeLabel(note.stance_label, language)}</span>
              <strong>{note.title}</strong>
              <em>{note.source}</em>
            </a>
          ))}
          {!research.notes.length && research.note ? <p>{research.note}</p> : null}
        </div>
      ) : null}
      {informationSigns ? (
        <section className="information-signs">
          <header>
            <div>
              <span>{tr("Public Information Signs", "公开信息信号")}</span>
              <strong>{localizeLabel(informationSigns.status, language)}</strong>
            </div>
            <small>{tr("Portfolio decision weight", "组合决策权重")}: {informationSigns.decision_policy.portfolio_weight}</small>
          </header>
          <p>{informationSigns.decision_policy.rule}</p>
          <div className="information-sign-list">
            {[...informationSigns.commentary_signs.slice(0, 3), ...informationSigns.primary_signs.slice(0, 5)].map((sign) => (
              <a key={`${sign.source}-${sign.title}-${sign.published ?? "latest"}`} href={sign.url || "#"} target="_blank" rel="noreferrer">
                <div>
                  <span>{sign.source_tier} · {sign.source}</span>
                  <strong>{sign.title}</strong>
                  <em>{sign.category} · {sign.signal.replaceAll("_", " ")}{sign.value !== null ? ` · ${sign.value}${sign.unit ? ` ${sign.unit}` : ""}` : ""}</em>
                </div>
                <p><b>{tr("Why", "原因")}:</b> {sign.why_it_matters}</p>
                <time>{sign.published ? formatShortDateTime(sign.published, language) : tr("date unavailable", "日期不可用")}</time>
              </a>
            ))}
          </div>
        </section>
      ) : null}
      <div className="sentiment-columns">
        <div>
          <h3>{tr("Themes", "主题")}</h3>
          <div className="theme-list">
            {summary.top_themes.length ? (
              summary.top_themes.map((theme) => (
                <span key={theme.theme}>
                  {theme.theme} <strong>{theme.count}</strong>
                </span>
              ))
            ) : (
              <span>{tr("No dominant theme", "无主导主题")}</span>
            )}
          </div>
        </div>
        <div>
          <h3>{tr("Ticker Sentiment", "个股情绪")}</h3>
          <div className="ticker-sentiment-list">
            {sentiment.ticker_sentiment.slice(0, 5).map((row) => (
              <div key={row.ticker}>
                <TickerCell ticker={row.ticker} market={market} />
                <span className={`badge ${row.label}`}>{localizeLabel(row.label, language)}</span>
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
        {tr("AI layer", "AI 层")}: {localizeLabel(summary.ai_layer.status, language)}. {summary.ai_layer.note}
      </div>
      {summary.ai_layer.analysis ? <pre className="ai-analysis">{summary.ai_layer.analysis}</pre> : null}
    </div>
  );
}

function RiskList({ risks, market }: { risks: DashboardPayload["risk_predictions"]; market: MarketProfile }) {
  const { language, tr } = useI18n();
  if (!risks.length) return <EmptyState label={tr("ML model needs more data.", "机器学习模型需要更多数据。")}/>;
  return (
    <div className="risk-list">
      {risks.map((risk) => (
        <div className="risk-row" key={risk.ticker}>
          <div>
            <strong>{risk.ticker}</strong>
            <span>{instrumentName(risk.ticker, market)}</span>
            <span>{localizeLabel(risk.risk_level, language)}</span>
          </div>
          <meter min={0} max={1} value={risk.risk_probability} />
          <em>{percent(risk.risk_probability)}</em>
        </div>
      ))}
    </div>
  );
}

function SectorTable({ signals, market }: { signals: SectorSignal[]; market: MarketProfile }) {
  const { language, tr } = useI18n();
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{tr("Sector", "板块")}</th>
            <th>ETF</th>
            <th>{tr("Status", "状态")}</th>
            <th>{tr("Trend", "趋势")}</th>
            <th>Z</th>
            <th>{tr("Momentum", "动量")}</th>
            <th>{tr("Vol", "波动")}</th>
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
                <span className={`badge ${signal.status}`}>{localizeLabel(signal.status, language)}</span>
              </td>
              <td>{localizeLabel(signal.trend_state, language)}</td>
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
  const { language, tr } = useI18n();
  if (!rules.length) return <EmptyState label={tr("Rule catalog unavailable.", "规则目录不可用。")}/>;
  return (
    <div className="table-wrap rules-table">
      <table>
        <thead>
          <tr>
            <th>{tr("Rule", "规则")}</th>
            <th>{tr("Category", "类别")}</th>
            <th>{tr("Formula", "公式")}</th>
            <th>{tr("Status", "状态")}</th>
            <th>{tr("Action", "操作")}</th>
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
                <span className={`badge ${rule.implementation_status}`}>{localizeLabel(rule.implementation_status, language)}</span>
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
  const { tr } = useI18n();
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
              <span>{percent(current - target)} {tr("drift", "偏离")}</span>
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
  const { tr } = useI18n();
  const marketInfo = MARKET_INFO[market];
  const quoteMap = new Map(quotes.map((quote) => [quote.ticker, quote]));
  const tickers = [dashboard.universe.benchmark, ...dashboard.universe.tickers, "CASH"].filter(
    (ticker, index, all) => all.indexOf(ticker) === index
  );

  return (
    <div className="instrument-guide">
      <p>
        {tr(`${marketInfo.benchmarkName} is the benchmark for this profile. Prices are shown in ${marketInfo.currency}; weights are portfolio percentages.`,
          `${marketInfo.benchmarkName} 是此市场配置的基准。价格以 ${marketInfo.currency} 显示；权重为投资组合百分比。`)}
      </p>
      <div className="table-wrap compact-table">
        <table>
          <thead>
            <tr>
              <th>{tr("Ticker", "代码")}</th>
              <th>{tr("Name", "名称")}</th>
              <th>{tr("Current weight", "当前权重")}</th>
              <th>{tr("Latest price", "最新价格")}</th>
              <th>{tr("Data status", "数据状态")}</th>
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
                  <td>{quote ? `${money(quote.price)} ${marketInfo.currency}` : ticker === "CASH" ? "-" : tr("not in latest quote set", "不在最新报价集中")}</td>
                  <td>{ticker === "CASH" ? tr("portfolio input", "组合输入") : quote ? `${tr("real snapshot", "真实快照")}, ${quote.as_of}` : tr("historical data only", "仅历史数据")}</td>
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

function portfolioProfile(weights: Record<string, number>, market: MarketProfile) {
  const normalized = normalizeWeights(weights);
  const entries = Object.entries(normalized)
    .filter(([, weight]) => weight > 0)
    .sort((a, b) => b[1] - a[1]);
  const profile = {
    usEquity: 0,
    techTilt: 0,
    international: 0,
    defensive: 0,
    topFive: entries.slice(0, 5).reduce((sum, [, weight]) => sum + weight, 0),
    largestTicker: entries[0]?.[0] ?? "",
    largestWeight: entries[0]?.[1] ?? 0
  };

  for (const [ticker, weight] of entries) {
    if (TECH_TILT_TICKERS.has(ticker)) profile.techTilt += weight;
    if (market === "us" && (INTERNATIONAL_TICKERS.has(ticker) || ticker.endsWith(".HK"))) profile.international += weight;
    if (BOND_TICKERS.has(ticker) || CASH_TICKERS.has(ticker)) profile.defensive += weight;
    if (market === "us" && (US_CORE_FUNDS.has(ticker) || US_SINGLE_STOCKS.has(ticker))) profile.usEquity += weight;
    if (market === "hk" && ticker.endsWith(".HK")) profile.usEquity += weight;
  }

  return profile;
}

function formatSignedPercent(value: number) {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${percent(value)}`;
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

createRoot(document.getElementById("root")!).render(
  <I18nProvider>
    <App />
  </I18nProvider>
);
