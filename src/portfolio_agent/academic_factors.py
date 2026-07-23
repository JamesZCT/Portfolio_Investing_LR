from __future__ import annotations

from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pandas as pd

from .backtest import compute_metrics, downsample_equity_curve


MOMENTUM_PORTFOLIOS_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "10_Portfolios_Prior_12_2_Daily_CSV.zip"
)
FIVE_FACTORS_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"
)
KEN_FRENCH_LIBRARY_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html"
)


def build_academic_factor_evidence(
    *,
    years: int = 10,
    cache_dir: str | Path | None = None,
) -> dict[str, Any]:
    momentum_text = _download_zip_text(
        MOMENTUM_PORTFOLIOS_URL,
        "momentum-portfolios.zip",
        cache_dir,
    )
    factors_text = _download_zip_text(
        FIVE_FACTORS_URL,
        "five-factors.zip",
        cache_dir,
    )
    momentum = parse_ken_french_daily_table(momentum_text, "Lo PRIOR")
    factors = parse_ken_french_daily_table(factors_text, "Mkt-RF")
    common = momentum.index.intersection(factors.index)
    if common.empty:
        raise RuntimeError("Ken French momentum and market series do not overlap")
    end = common.max()
    start = end - pd.DateOffset(years=years)
    dates = common[common >= start]

    returns = {
        "academic_market": (factors.loc[dates, "Mkt-RF"] + factors.loc[dates, "RF"])
        / 100.0,
        "academic_high_momentum": momentum.loc[dates, "Hi PRIOR"] / 100.0,
        "academic_low_momentum": momentum.loc[dates, "Lo PRIOR"] / 100.0,
    }
    labels = {
        "academic_market": (
            "CRSP U.S. market",
            "CRSP 美国市场",
            "Value-weight U.S. market return from the Fama/French research factors.",
            "Fama/French 研究因子中的美国市场价值加权收益。",
        ),
        "academic_high_momentum": (
            "High prior-return decile",
            "高动量十分位组",
            "Long-only highest prior 2-12 month return decile, re-formed daily.",
            "只做多过去 2-12 个月收益最高的十分位组，并每日动态重建。",
        ),
        "academic_low_momentum": (
            "Low prior-return decile",
            "低动量十分位组",
            "Long-only lowest prior 2-12 month return decile, re-formed daily.",
            "只做多过去 2-12 个月收益最低的十分位组，并每日动态重建。",
        ),
    }
    tracks = []
    market_cagr = 0.0
    for track_id, series in returns.items():
        series = series.replace([-99.99, -999.0], pd.NA).dropna().astype(float)
        equity = (1.0 + series).cumprod()
        curve = pd.DataFrame(
            {
                "date": series.index.strftime("%Y-%m-%d"),
                "portfolio_value": equity.values,
                "daily_return": series.values,
            }
        )
        metrics = compute_metrics(curve)
        published_curve = downsample_equity_curve(curve)
        if track_id == "academic_market":
            market_cagr = metrics["cagr"]
        name_en, name_zh, description_en, description_zh = labels[track_id]
        tracks.append(
            {
                "id": track_id,
                "name_en": name_en,
                "name_zh": name_zh,
                "description_en": description_en,
                "description_zh": description_zh,
                "metrics": metrics,
                "equity_curve": published_curve.to_dict(orient="records"),
            }
        )
    for track in tracks:
        track["metrics"]["excess_cagr_vs_market"] = (
            track["metrics"]["cagr"] - market_cagr
        )

    return {
        "status": "available",
        "evaluation_start_date": str(dates.min().date()),
        "evaluation_end_date": str(dates.max().date()),
        "tracks": tracks,
        "source": {
            "name": "Kenneth R. French Data Library / CRSP",
            "url": KEN_FRENCH_LIBRARY_URL,
            "momentum_portfolios_url": MOMENTUM_PORTFOLIOS_URL,
            "five_factors_url": FIVE_FACTORS_URL,
        },
        "construction": {
            "rule_en": (
                "The high-momentum portfolio holds the top NYSE-breakpoint decile by "
                "prior 2-12 month return; portfolios are formed daily from eligible "
                "NYSE, AMEX, and Nasdaq stocks."
            ),
            "rule_zh": (
                "高动量组合按照过去 2-12 个月收益及 NYSE 分位点选择最高十分位；"
                "每天使用当时符合条件的 NYSE、AMEX 和 Nasdaq 股票重新构建。"
            ),
            "survivorship_bias_control": (
                "CRSP research returns use the historical listed-security universe rather "
                "than today's surviving ticker list."
            ),
        },
        "limitations_en": [
            "These are academic portfolio returns, not this application's exact stock picks.",
            "Trading costs, taxes, and implementation shortfall are not deducted here.",
            "A factor can outperform over one decade and underperform for long future periods.",
        ],
        "limitations_zh": [
            "这是学术组合收益，不是本应用逐只股票的完全相同选股。",
            "这里没有扣除交易成本、税费和实际成交偏差。",
            "因子在某十年跑赢，并不代表未来长时间仍会跑赢。",
        ],
    }


def parse_ken_french_daily_table(text: str, header_contains: str) -> pd.DataFrame:
    lines = text.splitlines()
    header_index = next(
        (index for index, line in enumerate(lines) if header_contains in line),
        None,
    )
    if header_index is None:
        raise ValueError(f"Ken French table is missing header containing {header_contains}")
    rows = []
    for line in lines[header_index + 1 :]:
        first = line.split(",", 1)[0].strip()
        if len(first) != 8 or not first.isdigit():
            break
        rows.append(line)
    if not rows:
        raise ValueError(f"Ken French table {header_contains} contains no daily rows")

    frame = pd.read_csv(StringIO("\n".join([lines[header_index], *rows])), index_col=0)
    frame.index = pd.to_datetime(frame.index.astype(str), format="%Y%m%d")
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame.apply(pd.to_numeric, errors="coerce").sort_index()


def _download_zip_text(
    url: str,
    filename: str,
    cache_dir: str | Path | None,
) -> str:
    cache_root = (
        Path(cache_dir).expanduser()
        if cache_dir is not None
        else Path.home() / ".cache" / "portfolio_agent" / "academic_factors"
    )
    cache_root.mkdir(parents=True, exist_ok=True)
    archive_path = cache_root / filename
    if archive_path.exists():
        content = archive_path.read_bytes()
    else:
        import httpx

        response = httpx.get(url, follow_redirects=True, timeout=60)
        response.raise_for_status()
        content = response.content
        archive_path.write_bytes(content)
    with ZipFile(BytesIO(content)) as archive:
        member = archive.namelist()[0]
        return archive.read(member).decode("latin-1")
