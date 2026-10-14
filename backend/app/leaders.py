"""全 A 股月度强势与五年收盘新高；统一使用前复权日线。"""
from __future__ import annotations

import logging
import math
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from . import microcap
from .db import _get_snapshot, _save_snapshot
from .sector import CLIST_URL, UT, _json_get

logger = logging.getLogger(__name__)
TABLES = {"strong": "strong_snapshots", "newhigh": "newhigh_snapshots"}


def years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def fetch_universe() -> list[dict]:
    stocks = []
    page = 1
    while True:
        params = {
            "pn": page, "pz": 100, "po": 1, "np": 1, "ut": UT, "fltt": 2,
            "fid": "f12", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
            "fields": "f12,f13,f14,f100,f26",
        }
        payload = _json_get(f"{CLIST_URL}?{urllib.parse.urlencode(params)}").get("data")
        if not payload or "diff" not in payload:
            raise RuntimeError("A 股列表获取失败，不保存快照")
        rows = payload["diff"]
        for row in rows:
            code = str(row["f12"])
            if len(code) == 6 and code.isdigit():
                stocks.append({"code": code, "name": row["f14"], "market": row["f13"],
                               "industry": row.get("f100"), "listing_date": str(row.get("f26"))})
        if page * 100 >= payload["total"]:
            break
        if not rows:
            raise RuntimeError("A 股列表分页不完整")
        page += 1
    if not stocks:
        raise RuntimeError("A 股列表为空")
    return stocks


def fetch_history(stock: dict, trade_date: str, long: bool) -> list[dict]:
    day = date.fromisoformat(trade_date)
    begin = years_before(day, 5).strftime("%Y%m%d") if long else "0"
    params = {
        "secid": f"{stock['market']}.{stock['code']}", "ut": UT, "klt": 101, "fqt": 1,
        "beg": begin, "end": trade_date.replace("-", ""), "lmt": 2000 if long else 40,
        "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56",
    }
    payload = _json_get(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get?"
        + urllib.parse.urlencode(params)
    ).get("data")
    if payload is None or "klines" not in payload:
        raise RuntimeError(f"{stock['code']} 日线获取失败")
    bars = []
    for row in payload["klines"]:
        fields = row.split(",")
        close = float(fields[2])
        if not math.isfinite(close) or close <= 0:
            raise ValueError("无效收盘价")
        if fields[0] <= trade_date:
            bars.append({"date": fields[0], "close": close})
    return sorted(bars, key=lambda bar: bar["date"])


def evaluate(stock: dict, trade_date: str, kind: str) -> dict | None:
    day = date.fromisoformat(trade_date)
    if kind == "newhigh":
        try:
            listed = datetime.strptime(stock["listing_date"], "%Y%m%d").replace(
                tzinfo=ZoneInfo("Asia/Shanghai")
            ).date()
        except (ValueError, TypeError):
            raise RuntimeError(f"{stock['code']} 上市日期缺失")
        if listed > years_before(day, 3):
            return None
    bars = fetch_history(stock, trade_date, kind == "newhigh")
    if len(bars) < 21 or bars[-1]["date"] != trade_date:
        return None  # 停牌或上市不足一个月
    if kind == "newhigh":
        window_start = years_before(day, 5).isoformat()
        window = [bar for bar in bars[:-1] if bar["date"] >= window_start]
        if not window or bars[-1]["close"] <= max(bar["close"] for bar in window):
            return None
    change = (bars[-1]["close"] / bars[-21]["close"] - 1) * 100
    return {**stock, "month_change_pct": change, "price": bars[-1]["close"]}


def enrich(item: dict) -> dict:
    try:
        concepts = microcap.fetch_ths_concepts(item["code"])
    except (OSError, ValueError):
        logger.warning("概念获取失败：%s", item["code"])
        concepts = []
    return {**item, "board": microcap.board_for_code(item["code"]) or "北交所",
            "main_concepts": concepts[:3], "themes": concepts,
            "month_change_pct": round(item["month_change_pct"], 2)}


def refresh_leaders(kind: str, force: bool = False, concurrency: int = 4) -> dict:
    table = TABLES[kind]
    trade_date = microcap.get_last_trade_date()
    existing = _get_snapshot(table, trade_date)
    if existing and not force:
        return {**existing, "reused": True}
    stocks = fetch_universe()
    # 任何行情请求失败均中止，防止不完整股票池产生错误的全市场排名。
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        items = list(pool.map(lambda stock: evaluate(stock, trade_date, kind), stocks))
    winners = sorted((item for item in items if item),
                     key=lambda item: (-item["month_change_pct"], item["code"]))
    if kind == "strong":
        if len(winners) < 20:
            raise RuntimeError("有效股票不足 20 只，不保存强势快照")
        winners = winners[:20]
    items = [{**enrich(item), "rank": rank} for rank, item in enumerate(winners, 1)]
    _save_snapshot(table, trade_date, items)
    return {"trade_date": trade_date, "items": items, "reused": False}


def scheduled_leaders(kind: str) -> dict:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.weekday() < 5 and now.time() < time(15, 10):
        return {"skipped": True, "reason": "等待当日收盘数据"}
    return refresh_leaders(kind)
