"""趋势向上筛选模块。

=====================================================================
筛选逻辑设计（代码注释即设计文档）
=====================================================================

目标：每个交易日收盘后，选出全 A 股中 MA20 连续 10 个交易日上行、
且换手率最低的 30 只股票，持久化快照供页面回看；鼠标悬停代码可查看
近 3 个月的日 K 线（含 MA20）。

步骤：

1. 最近完整交易日：复用微盘股模块的判定（新浪日 K，15:00 前取上一日）。

2. 拉取全 A 股列表（东方财富 push2delay 行情接口，按换手率升序分页）
   - 取字段：f12（代码）、f14（名称）、f2（现价）、f8（换手率）。
   - fs 只选沪深主板/中小板/创业板/科创板，天然不含北交所。
   - 过滤：无有效现价或换手率（"-"）、换手率 <= 0（停牌/退市）的跳过；
     名称含 ST / *ST / 退 / PT 的跳过。

3. MA20 上行判定（is_ma20_rising）
   - 逐只拉取最近 TREND_KLINE_DAYS（默认 75）根日 K（新浪，升序）。
   - 收盘价不足 20 + up_days 根（次新股）直接跳过。
   - 计算最近 up_days + 1 个交易日的 MA20，要求严格逐日递增：
     MA20(t-10) < MA20(t-9) < ... < MA20(t)。
   - "持续上行"按字面实现为逐日抬升，调整 TREND_UP_DAYS 可放宽/收紧。

4. 取结果
   - 行情列表本身按换手率升序返回，因此按扫描顺序取前 top_n 只通过
     的股票，即为"换手率最低的 top_n"，命中后即停止拉取 K 线；
     拉取按 TREND_CONCURRENCY 批量并发以缩短耗时。

5. 快照与复用：同交易日再次触发直接复用已有快照（refresh_trend）。

6. 悬停 K 线（fetch_trend_kline）
   - 返回最近 TREND_KLINE_DAYS 个交易日的 OHLC + MA20，供前端绘图；
   - 内存缓存 TREND_KLINE_TTL 秒，筛选时顺手预热入选股票的 K 线，
     首次悬停无需再次请求行情接口。
=====================================================================
"""
from __future__ import annotations

import json
import logging
import time as time_mod
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from . import microcap
from .config import (
    TREND_CONCURRENCY,
    TREND_KLINE_DAYS,
    TREND_KLINE_TTL,
    TREND_TOP_N,
    TREND_UP_DAYS,
)
from .db import (
    get_latest_trend_snapshot,
    get_trend_snapshot,
    save_trend_snapshot,
)

logger = logging.getLogger(__name__)

CLIST_URL = "https://push2delay.eastmoney.com/api/qt/clist/get"
CLIST_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"  # 沪深主板/科创板/中小板/创业板

# 悬停 K 线内存缓存：code -> (时间戳, bars)
_KLINE_CACHE: dict[str, tuple[float, list[dict]]] = {}


def fetch_market_stocks_with_turnover() -> list[dict]:
    """全 A 股列表（沪深，含现价与换手率，按换手率升序）。"""
    stocks: list[dict] = []
    page = 1
    while True:
        params = {
            "pn": page,
            "pz": 100,
            "po": 0,  # 换手率升序
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f8",
            "fs": CLIST_FS,
            "fields": "f12,f14,f2,f8",
        }
        url = f"{CLIST_URL}?{urllib.parse.urlencode(params)}"
        data = json.loads(microcap._get(url)) or {}
        diff = (data.get("data") or {}).get("diff") or []
        for item in diff:
            price = item.get("f2")
            turnover = item.get("f8")
            if price in (None, "-") or turnover in (None, "-") or turnover <= 0:
                continue  # 停牌/退市/无有效换手率
            name = item["f14"]
            if "ST" in name.upper() or "退" in name or "PT" in name.upper():
                continue
            code = item["f12"]
            market = "SH" if code.startswith(("6", "9")) else "SZ"
            stocks.append(
                {
                    "code": code,
                    "name": name,
                    "market": market,
                    "price": float(price),
                    "turnover": float(turnover),
                }
            )
        total = (data.get("data") or {}).get("total") or 0
        if not diff or page * 100 >= total:
            break
        page += 1
    return stocks


def _ma(values: list[float], n: int, i: int) -> float:
    """values 升序排列，返回第 i 个位置的 n 日均值。"""
    return sum(values[i - n + 1 : i + 1]) / n


def is_ma20_rising(closes: list[float], up_days: int = TREND_UP_DAYS) -> bool:
    """MA20 在过去 up_days 个交易日严格逐日上行。"""
    if len(closes) < 20 + up_days:
        return False
    prev = None
    for k in range(up_days, -1, -1):
        value = _ma(closes, 20, len(closes) - 1 - k)
        if prev is not None and value <= prev:
            return False
        prev = value
    return True


def _format_bars(bars: list[dict]) -> list[dict]:
    """原始新浪日 K 转前端绘图字段（升序，含 MA20）。"""
    closes = [float(b["close"]) for b in bars]
    return [
        {
            "date": b["day"],
            "open": float(b["open"]),
            "high": float(b["high"]),
            "low": float(b["low"]),
            "close": float(b["close"]),
            "ma20": round(_ma(closes, 20, i), 2) if i >= 19 else None,
        }
        for i, b in enumerate(bars)
    ]


def fetch_trend_kline(code: str) -> list[dict]:
    """近 3 个月日 K（含 MA20），带内存缓存，失败时抛错。"""
    cached = _KLINE_CACHE.get(code)
    if cached and time_mod.time() - cached[0] < TREND_KLINE_TTL:
        return cached[1]
    prefix = "sh" if code.startswith(("6", "9")) else "sz"
    bars = microcap.fetch_kline(symbol=f"{prefix}{code}", datalen=TREND_KLINE_DAYS)
    formatted = _format_bars(bars)
    _KLINE_CACHE[code] = (time_mod.time(), formatted)
    return formatted


def _evaluate_trend(stock: dict, up_days: int = TREND_UP_DAYS) -> dict | None:
    """判断单只股票是否入选，入选返回 {ma20, bars}，否则 None。"""
    prefix = "sh" if stock["code"].startswith(("6", "9")) else "sz"
    try:
        bars = microcap.fetch_kline(
            symbol=f"{prefix}{stock['code']}", datalen=TREND_KLINE_DAYS
        )
    except (OSError, ValueError):
        logger.warning("趋势筛选 K 线获取失败：%s，跳过", stock["code"])
        return None
    closes = [float(b["close"]) for b in bars]
    if not is_ma20_rising(closes, up_days):
        return None
    return {"ma20": _ma(closes, 20, len(closes) - 1), "bars": bars}


def _find_passing(
    stocks: list[dict],
    top_n: int = TREND_TOP_N,
    up_days: int = TREND_UP_DAYS,
    concurrency: int = TREND_CONCURRENCY,
) -> list[dict]:
    """按换手率升序批量并发扫描，返回前 top_n 只入选股票（保持顺序）。"""
    passing: list[dict] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for start in range(0, len(stocks), concurrency):
            batch = stocks[start : start + concurrency]
            futures = [pool.submit(_evaluate_trend, s, up_days) for s in batch]
            for s, fut in zip(batch, futures):
                result = fut.result()
                if result is None:
                    continue
                s["_ma20"] = result["ma20"]
                s["_bars"] = result["bars"]
                passing.append(s)
                if len(passing) >= top_n:
                    return passing[:top_n]
    return passing


def screen_trend(top_n: int = TREND_TOP_N, up_days: int = TREND_UP_DAYS) -> dict:
    """执行筛选：MA20 连续 up_days 日上行，按换手率升序取前 top_n。"""
    trade_date = microcap.get_last_trade_date()
    stocks = fetch_market_stocks_with_turnover()
    winners = _find_passing(stocks, top_n, up_days)
    items = [
        {
            "rank": i + 1,
            "code": s["code"],
            "name": s["name"],
            "price": round(s["price"], 2),
            "turnover": round(s["turnover"], 2),
            "ma20": round(s["_ma20"], 2),
        }
        for i, s in enumerate(winners)
    ]
    # 预热悬停 K 线缓存：入选股票的日 K 已拉取过，直接复用
    now = time_mod.time()
    for s in winners:
        _KLINE_CACHE[s["code"]] = (now, _format_bars(s["_bars"]))
    save_trend_snapshot(trade_date, items)
    return {"trade_date": trade_date, "items": items}


def refresh_trend(force: bool = False) -> dict:
    """触发刷新：同交易日已有快照直接复用，否则重新筛选。"""
    trade_date = microcap.get_last_trade_date()
    existing = get_trend_snapshot(trade_date)
    if existing and not force:
        return {
            "trade_date": trade_date,
            "reused": True,
            "items": existing["items"],
        }
    result = screen_trend()
    save_trend_snapshot(trade_date, result["items"])
    result["reused"] = False
    return result


def scheduled_trend() -> dict:
    """每 6 小时定时任务：刷新最近完整交易日的趋势快照。"""
    return refresh_trend()


def latest_trend() -> dict | None:
    """最新一次趋势向上快照，无数据返回 None。"""
    return get_latest_trend_snapshot()

