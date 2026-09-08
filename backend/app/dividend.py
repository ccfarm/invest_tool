"""红利低波股票筛选。

口径：最近 5 个完整财年均实施现金分红，5 年平均股息率不低于 3%；
先按平均股息率取候选池，再按近 60 个交易日年化波动率从低到高精选。
页面行情指标均以最近完整交易日的未复权价格序列计算。
"""
from __future__ import annotations

import json
import logging
import math
import statistics
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import microcap
from .config import (
    DIVIDEND_CANDIDATE_POOL,
    DIVIDEND_CONCURRENCY,
    DIVIDEND_KLINE_DAYS,
    DIVIDEND_MIN_AVG_YIELD,
    DIVIDEND_TOP_N,
    DIVIDEND_YEARS,
)
from .db import (
    get_dividend_snapshot,
    get_latest_dividend_snapshot,
    save_dividend_snapshot,
)
from .oversold import calculate_rsi

logger = logging.getLogger(__name__)
DIVIDEND_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def fiscal_years(trade_date: str, count: int = DIVIDEND_YEARS) -> list[int]:
    """最近完整财年；例如 2026 年交易日对应 2021—2025。"""
    last = int(trade_date[:4]) - 1
    return list(range(last - count + 1, last + 1))


def _fetch_year(year: int) -> list[dict]:
    """拉取某年度已实施的年度现金分红方案。"""
    rows: list[dict] = []
    page = 1
    while True:
        params = {
            "reportName": "RPT_SHAREBONUS_DET",
            "columns": (
                "SECURITY_CODE,SECURITY_NAME_ABBR,REPORT_DATE,ASSIGN_PROGRESS,"
                "PRETAX_BONUS_RMB,DIVIDENT_RATIO"
            ),
            "pageNumber": page,
            "pageSize": 500,
            "filter": (
                f"(REPORT_DATE='{year}-12-31')"
                '(ASSIGN_PROGRESS="实施分配")(PRETAX_BONUS_RMB>0)'
            ),
            "source": "WEB",
            "client": "WEB",
        }
        data = json.loads(microcap._get(f"{DIVIDEND_URL}?{urllib.parse.urlencode(params)}"))
        result = data.get("result") or {}
        batch = result.get("data") or []
        rows.extend(batch)
        if page >= int(result.get("pages") or 0) or not batch:
            break
        page += 1
    return rows


def continuous_dividend_candidates(
    years: list[int], min_avg_yield: float = DIVIDEND_MIN_AVG_YIELD
) -> list[dict]:
    """返回每年均分红且 5 年平均股息率达标的沪深 A 股。"""
    by_code: dict[str, dict[int, dict]] = defaultdict(dict)
    for year in years:
        for row in _fetch_year(year):
            code = str(row.get("SECURITY_CODE") or "")
            name = str(row.get("SECURITY_NAME_ABBR") or "")
            ratio = row.get("DIVIDENT_RATIO")
            if len(code) != 6 or code[0] not in "036" or ratio in (None, "-"):
                continue
            if "ST" in name.upper() or "退" in name or "PT" in name.upper():
                continue
            dividend_yield = float(ratio) * 100
            previous = by_code[code].get(year)
            if previous is None or dividend_yield > previous["yield"]:
                by_code[code][year] = {"name": name, "yield": dividend_yield}

    candidates = []
    required = set(years)
    for code, annual in by_code.items():
        if set(annual) != required:
            continue
        yields = [annual[year]["yield"] for year in years]
        average = sum(yields) / len(yields)
        if average < min_avg_yield:
            continue
        candidates.append(
            {
                "code": code,
                "name": annual[years[-1]]["name"],
                "avg_dividend_yield": average,
                "annual_yields": yields,
            }
        )
    return sorted(candidates, key=lambda item: item["avg_dividend_yield"], reverse=True)


def percentile_rank(values: list[float], current: float) -> float:
    if not values:
        return 0.0
    return sum(value <= current for value in values) / len(values) * 100


def _change(closes: list[float], days: int) -> float:
    return (closes[-1] / closes[-1 - days] - 1) * 100


def evaluate_stock(stock: dict) -> dict | None:
    prefix = "sh" if stock["code"].startswith("6") else "sz"
    try:
        bars = microcap.fetch_kline(
            symbol=f"{prefix}{stock['code']}", datalen=DIVIDEND_KLINE_DAYS
        )
        closes = [float(bar["close"]) for bar in bars]
    except (OSError, ValueError, KeyError):
        logger.warning("红利低波日 K 获取失败：%s", stock["code"])
        return None
    if len(closes) < 252:
        return None
    rsi_values = calculate_rsi(closes, 14)
    if not rsi_values:
        return None
    returns = [math.log(current / previous) for previous, current in zip(closes[-61:-1], closes[-60:])]
    volatility = statistics.pstdev(returns) * math.sqrt(252) * 100
    return {
        **stock,
        "price": closes[-1],
        "change_day": _change(closes, 1),
        "change_20d": _change(closes, 20),
        "change_60d": _change(closes, 60),
        "rsi": rsi_values[-1],
        "rsi_percentile": percentile_rank(rsi_values[-250:], rsi_values[-1]),
        "price_percentile": percentile_rank(closes, closes[-1]),
        "volatility_60d": volatility,
    }


def screen_dividend(
    top_n: int = DIVIDEND_TOP_N,
    candidate_pool: int = DIVIDEND_CANDIDATE_POOL,
    concurrency: int = DIVIDEND_CONCURRENCY,
) -> dict:
    trade_date = microcap.get_last_trade_date()
    years = fiscal_years(trade_date)
    candidates = continuous_dividend_candidates(years)[:candidate_pool]
    evaluated: list[dict] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(evaluate_stock, stock): stock for stock in candidates}
        for future in as_completed(futures):
            result = future.result()
            if result:
                evaluated.append(result)
    evaluated.sort(key=lambda item: (item["volatility_60d"], -item["avg_dividend_yield"]))
    items = []
    for rank, item in enumerate(evaluated[:top_n], 1):
        items.append(
            {
                "rank": rank,
                "code": item["code"],
                "name": item["name"],
                "price": round(item["price"], 2),
                "avg_dividend_yield": round(item["avg_dividend_yield"], 2),
                "change_day": round(item["change_day"], 2),
                "change_20d": round(item["change_20d"], 2),
                "change_60d": round(item["change_60d"], 2),
                "rsi": round(item["rsi"], 2),
                "rsi_percentile": round(item["rsi_percentile"], 1),
                "price_percentile": round(item["price_percentile"], 1),
                "volatility_60d": round(item["volatility_60d"], 2),
            }
        )
    save_dividend_snapshot(trade_date, items)
    return {"trade_date": trade_date, "fiscal_years": years, "items": items}


def refresh_dividend(force: bool = False) -> dict:
    trade_date = microcap.get_last_trade_date()
    existing = get_dividend_snapshot(trade_date)
    if existing and not force:
        return {"trade_date": trade_date, "reused": True, "items": existing["items"]}
    result = screen_dividend()
    result["reused"] = False
    return result


def scheduled_dividend() -> dict:
    return refresh_dividend()


def latest_dividend() -> dict | None:
    return get_latest_dividend_snapshot()
