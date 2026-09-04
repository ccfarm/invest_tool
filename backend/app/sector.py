"""东方财富行业板块强度计算。

每天针对最近完整交易日生成一次快照：
1. 拉取东方财富全部行业板块及最近 11 根日 K；
2. 按第 11 根收盘价 / 第 1 根收盘价 - 1 计算近 10 个交易日涨幅，取前 20；
3. 拉取这 20 个板块的 A 股成分股，计算 MA5 > MA10 > MA20 的个股占比；
4. 最终按强势占比降序，近 10 日涨幅作为同占比时的次排序键。
"""
from __future__ import annotations

import json
import logging
import threading
import time as time_mod
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time
from zoneinfo import ZoneInfo

from .config import SECTOR_CONCURRENCY, SECTOR_MIN_STOCKS, SECTOR_TOP_N
from .db import get_latest_sector_snapshot, get_sector_snapshot, save_sector_snapshot
from .microcap import _get, fetch_kline, get_last_trade_date

logger = logging.getLogger(__name__)

CLIST_URL = "https://push2delay.eastmoney.com/api/qt/clist/get"
UT = "bd1d9ddb04089700cf9c27f6f7426281"
REQUEST_INTERVAL = 0.2
_request_lock = threading.Lock()
_last_request = 0.0


def _json_get(url: str) -> dict:
    global _last_request
    # 东方财富会主动断开高频连接；限制全进程请求起始速率，线程仅用于隐藏网络延迟。
    with _request_lock:
        wait = REQUEST_INTERVAL - (time_mod.monotonic() - _last_request)
        if wait > 0:
            time_mod.sleep(wait)
        _last_request = time_mod.monotonic()
    return json.loads(_get(url)) or {}


def fetch_industry_boards() -> list[dict]:
    """东方财富行业板块列表；m:90+t:2 为行业板块，排除概念板块。"""
    boards: list[dict] = []
    page = 1
    while True:
        params = {
            "pn": page, "pz": 100, "po": 1, "np": 1, "ut": UT, "fltt": 2,
            "invt": 2, "fid": "f3", "fs": "m:90+t:2+f:!50",
            "fields": "f12,f14,f104,f105,f106,f160",
        }
        data = _json_get(f"{CLIST_URL}?{urllib.parse.urlencode(params)}")
        payload = data.get("data") or {}
        rows = payload.get("diff") or []
        for row in rows:
            stock_count = sum(int(row.get(field) or 0) for field in ("f104", "f105", "f106"))
            if (
                row.get("f12")
                and row.get("f14")
                and row.get("f160") not in (None, "-")
                and stock_count > SECTOR_MIN_STOCKS
            ):
                boards.append({
                    "code": row["f12"], "name": row["f14"],
                    "return_10d": float(row["f160"]), "stock_count": stock_count,
                })
        if not rows or page * 100 >= (payload.get("total") or 0):
            break
        page += 1
    return boards


def fetch_board_members(board_code: str) -> list[dict]:
    """板块成分股，仅保留沪深 A 股。"""
    members: list[dict] = []
    page = 1
    while True:
        params = {
            "pn": page, "pz": 100, "po": 1, "np": 1, "ut": UT, "fltt": 2,
            "invt": 2, "fid": "f3", "fs": f"b:{board_code}+f:!50",
            "fields": "f12,f13,f14",
        }
        data = _json_get(f"{CLIST_URL}?{urllib.parse.urlencode(params)}")
        payload = data.get("data") or {}
        rows = payload.get("diff") or []
        for row in rows:
            code = str(row.get("f12") or "")
            market = row.get("f13")
            if len(code) == 6 and code.isdigit() and market in (0, 1):
                members.append({"code": code, "market": market})
        if not rows or page * 100 >= (payload.get("total") or 0):
            break
        page += 1
    return members


def is_strong(closes: list[float]) -> bool:
    """最近一个交易日满足 MA5 > MA10 > MA20。"""
    if len(closes) < 20:
        return False
    ma5 = sum(closes[-5:]) / 5
    ma10 = sum(closes[-10:]) / 10
    ma20 = sum(closes[-20:]) / 20
    return ma5 > ma10 > ma20


def fetch_stock_closes(code: str) -> list[float]:
    """复用项目已稳定运行的新浪个股日 K，避免东方财富个股日 K 高频断连。"""
    prefix = "sh" if code.startswith(("6", "9")) else "sz"
    return [float(bar["close"]) for bar in fetch_kline(f"{prefix}{code}", datalen=20)]


def _member_strong(member: dict) -> bool | None:
    try:
        closes = fetch_stock_closes(member["code"])
    except (OSError, ValueError, KeyError):
        return None
    return is_strong(closes) if len(closes) >= 20 else None


def _board_strength(board: dict, concurrency: int) -> dict:
    try:
        members = fetch_board_members(board["code"])
    except (OSError, ValueError, KeyError):
        logger.warning("板块成分股获取失败：%s", board["code"])
        members = []
    strong_count = valid_count = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for result in pool.map(_member_strong, members):
            if result is None:
                continue
            valid_count += 1
            strong_count += int(result)
    ratio = strong_count / valid_count * 100 if valid_count else 0.0
    return {
        "code": board["code"], "name": board["name"],
        "return_10d": round(board["return_10d"], 2),
        "strong_count": strong_count, "valid_count": valid_count,
        "stock_count": board["stock_count"],
        "strong_ratio": round(ratio, 1),
        "url": f"https://quote.eastmoney.com/bk/90.{board['code']}.html",
    }


def screen_sectors(top_n: int = SECTOR_TOP_N, concurrency: int = SECTOR_CONCURRENCY) -> dict:
    trade_date = get_last_trade_date()
    boards = fetch_industry_boards()
    leaders = sorted(boards, key=lambda item: item["return_10d"], reverse=True)[:top_n]
    # 板块逐个处理以控制东方财富并发量；板块内部并发拉取个股日 K。
    items = [_board_strength(board, concurrency) for board in leaders]
    if len(items) != top_n or any(item["valid_count"] == 0 for item in items):
        raise RuntimeError("强势板块有效成分股数据不完整，本次不保存快照")
    items.sort(key=lambda item: (item["strong_ratio"], item["return_10d"]), reverse=True)
    for rank, item in enumerate(items, 1):
        item["rank"] = rank
    save_sector_snapshot(trade_date, items)
    return {"trade_date": trade_date, "items": items}


def refresh_sectors(force: bool = False) -> dict:
    trade_date = get_last_trade_date()
    existing = get_sector_snapshot(trade_date)
    valid_existing = (
        existing
        and len(existing["items"]) == SECTOR_TOP_N
        and all(
            item.get("valid_count", 0) > 0
            and item.get("stock_count", 0) > SECTOR_MIN_STOCKS
            for item in existing["items"]
        )
    )
    if valid_existing and not force:
        return {"trade_date": trade_date, "reused": True, "items": existing["items"]}
    result = screen_sectors()
    result["reused"] = False
    return result


def scheduled_sectors() -> dict:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.weekday() < 5 and now.time() < time(15, 10):
        return {"skipped": True, "reason": "等待当日收盘数据"}
    return refresh_sectors()


def latest_sectors() -> dict | None:
    return get_latest_sector_snapshot()
