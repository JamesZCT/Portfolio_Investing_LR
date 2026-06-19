import type { Config, Context } from "@netlify/functions";

type Quote = {
  ticker: string;
  price: number;
  previous_close: number;
  change: number;
  change_pct: number;
  as_of: string;
  source: string;
};

const SNAPSHOT_BY_PATH: Record<string, string> = {
  "/api/dashboard": "dashboard.json",
  "/api/backtest": "backtest.json",
  "/api/strategies/compare": "strategies.json",
  "/api/rules": "rules.json",
  "/api/ohlc": "ohlc.json",
  "/api/news-sentiment": "sentiment.json"
};

export default async function handler(req: Request, context: Context) {
  if (req.method !== "GET") {
    return json({ detail: "Method not allowed" }, 405);
  }

  const url = new URL(req.url);
  if (url.pathname === "/api/health") {
    return json({
      status: "ok",
      runtime: "netlify-functions",
      deploy_id: context.deploy?.id ?? null
    });
  }

  if (url.pathname === "/api/quotes") {
    return quotesResponse(url);
  }

  if (url.pathname === "/api/bootstrap") {
    return bootstrapResponse(req);
  }

  const snapshotName = SNAPSHOT_BY_PATH[url.pathname];
  if (!snapshotName) {
    return json({ detail: `Unknown API route: ${url.pathname}` }, 404);
  }
  return snapshotResponse(req, snapshotName);
}

export const config: Config = {
  path: [
    "/api/health",
    "/api/dashboard",
    "/api/backtest",
    "/api/strategies/compare",
    "/api/rules",
    "/api/ohlc",
    "/api/news-sentiment",
    "/api/quotes",
    "/api/bootstrap"
  ],
  method: "GET"
};

async function bootstrapResponse(req: Request) {
  const market = marketFromRequest(req);
  const [dashboard, backtest, strategies, rules, ohlc, quotes, sentiment] = await Promise.all([
    readSnapshot(req, "dashboard.json", market),
    readSnapshot(req, "backtest.json", market),
    readSnapshot(req, "strategies.json", market),
    readSnapshot(req, "rules.json", market),
    readSnapshot(req, "ohlc.json", market),
    readSnapshot(req, "quotes.json", market),
    readSnapshot(req, "sentiment.json", market)
  ]);
  return json(
    {
      dashboard,
      backtest,
      strategyComparison: strategies,
      rules: rules.rules ?? [],
      ohlc: ohlc.ohlc ?? [],
      quotes: quotes.quotes ?? [],
      sentiment
    },
    200,
    {
      "Cache-Control": "public, max-age=60, stale-while-revalidate=300"
    }
  );
}

async function quotesResponse(url: URL) {
  const market = marketFromUrl(url);
  const tickers = (url.searchParams.get("tickers") ?? "SPY")
    .split(",")
    .map((ticker) => ticker.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, 20);

  try {
    const quotes = await Promise.all(tickers.map(fetchYahooQuote));
    return json({ quotes: quotes.filter(Boolean) }, 200, {
      "Cache-Control": "public, max-age=60, stale-while-revalidate=300"
    });
  } catch {
    return snapshotResponse(new Request(url), "quotes.json", market);
  }
}

async function fetchYahooQuote(ticker: string): Promise<Quote | null> {
  const response = await fetch(
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?range=5d&interval=1d`,
    { headers: { "User-Agent": "portfolio-investing-lab/1.0" } }
  );
  if (!response.ok) {
    throw new Error(`Quote request failed for ${ticker}: ${response.status}`);
  }

  const data = await response.json();
  const result = data?.chart?.result?.[0];
  const timestamps: number[] = result?.timestamp ?? [];
  const closes: Array<number | null> = result?.indicators?.quote?.[0]?.close ?? [];
  const points = timestamps
    .map((timestamp, index) => ({ timestamp, close: closes[index] }))
    .filter((point) => typeof point.close === "number") as Array<{ timestamp: number; close: number }>;

  if (!points.length) {
    return null;
  }

  const latest = points[points.length - 1];
  const previous = points.length > 1 ? points[points.length - 2].close : latest.close;
  const change = latest.close - previous;
  return {
    ticker,
    price: latest.close,
    previous_close: previous,
    change,
    change_pct: previous ? change / previous : 0,
    as_of: new Date(latest.timestamp * 1000).toISOString().slice(0, 10),
    source: "yahoo-chart"
  };
}

async function snapshotResponse(req: Request, snapshotName: string, market = marketFromRequest(req)) {
  const response = await fetch(snapshotUrl(req, snapshotName, market));
  if (!response.ok) {
    return json({ detail: `Snapshot unavailable: ${snapshotName}` }, response.status);
  }
  return new Response(response.body, {
    status: response.status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "public, max-age=60, stale-while-revalidate=300"
    }
  });
}

async function readSnapshot(req: Request, snapshotName: string, market = marketFromRequest(req)) {
  const response = await fetch(snapshotUrl(req, snapshotName, market));
  if (!response.ok) {
    throw new Error(`Snapshot unavailable: ${snapshotName}`);
  }
  return response.json();
}

function snapshotUrl(req: Request, snapshotName: string, market: string) {
  return new URL(`/data/${market}/${snapshotName}`, req.url);
}

function marketFromRequest(req: Request) {
  return marketFromUrl(new URL(req.url));
}

function marketFromUrl(url: URL) {
  const raw = (url.searchParams.get("market") ?? "us").toLowerCase();
  return raw === "hk" ? "hk" : "us";
}

function json(payload: unknown, status = 200, headers: Record<string, string> = {}) {
  return Response.json(payload, {
    status,
    headers: {
      "Cache-Control": "no-store",
      ...headers
    }
  });
}
