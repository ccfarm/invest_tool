"""行业 RSI 历史低分位筛选。"""
from __future__ import annotations

import logging
import threading
import time as time_mod
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time
from zoneinfo import ZoneInfo

from .config import (
    OVERSOLD_LOOKBACK,
    OVERSOLD_PERCENTILE,
    OVERSOLD_RSI_PERIOD,
    SECTOR_CONCURRENCY,
)
from .db import get_latest_oversold_snapshot, get_oversold_snapshot, save_oversold_snapshot
from .microcap import get_last_trade_date
from .sector import UT, _json_get, fetch_industry_boards

logger = logging.getLogger(__name__)
KLINE_HOSTS = ("7", "33", "63", "91")
KLINE_PATH = "/api/qt/stock/kline/get"
KLINE_REQUEST_INTERVAL = 0.5
_kline_lock = threading.Lock()
_last_kline_request = 0.0


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    return 100 * avg_gain / (avg_gain + avg_loss)


def fetch_board_closes(board_code: str, limit: int) -> list[float]:
    """获取东方财富行业板块日线收盘价。"""
    global _last_kline_request
    with _kline_lock:
        wait = KLINE_REQUEST_INTERVAL - (time_mod.monotonic() - _last_kline_request)
        if wait > 0:
            time_mod.sleep(wait)
        _last_kline_request = time_mod.monotonic()
    params = {
        "secid": f"90.{board_code}", "ut": UT, "klt": 101, "fqt": 0,
        "lmt": limit, "end": "20500101", "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    }
    query = urllib.parse.urlencode(params)
    start = int(board_code.removeprefix("BK")) % len(KLINE_HOSTS)
    last_error: Exception | None = None
    for offset in range(len(KLINE_HOSTS)):
        host = KLINE_HOSTS[(start + offset) % len(KLINE_HOSTS)]
        url = f"http://{host}.push2his.eastmoney.com{KLINE_PATH}?{query}"
        try:
            data = _json_get(url)
            rows = (data.get("data") or {}).get("klines") or []
            if rows:
                return [float(row.split(",")[2]) for row in rows]
        except (OSError, ValueError, KeyError) as exc:
            last_error = exc
    if last_error:
        raise last_error
    return []


def calculate_rsi(closes: list[float], period: int = OVERSOLD_RSI_PERIOD) -> list[float]:
    """Wilder RSI，与国内行情软件常用的 RSI(14) 平滑方式一致。"""
    if len(closes) <= period:
        return []
    changes = [current - previous for previous, current in zip(closes, closes[1:])]
    avg_gain = sum(max(change, 0.0) for change in changes[:period]) / period
    avg_loss = sum(max(-change, 0.0) for change in changes[:period]) / period
    values = [_rsi_value(avg_gain, avg_loss)]
    for change in changes[period:]:
        avg_gain = (avg_gain * (period - 1) + max(change, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0.0)) / period
        values.append(_rsi_value(avg_gain, avg_loss))
    return values


def percentile(values: list[float], percent: float) -> float:
    """线性插值百分位数。"""
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def evaluate_board(
    board: dict,
    period: int = OVERSOLD_RSI_PERIOD,
    lookback: int = OVERSOLD_LOOKBACK,
    percent: float = OVERSOLD_PERCENTILE,
) -> dict | None:
    closes = fetch_board_closes(board["code"], lookback + period * 5)
    rsi_values = calculate_rsi(closes, period)
    if len(rsi_values) < lookback:
        return None
    window = rsi_values[-lookback:]
    current = window[-1]
    threshold = percentile(window, percent)
    if current > threshold:
        return None
    rank_percentile = sum(value <= current for value in window) / len(window) * 100
    return {
        "code": board["code"], "name": board["name"],
        "stock_count": board["stock_count"], "rsi": round(current, 2),
        "threshold": round(threshold, 2), "percentile": round(rank_percentile, 1),
        "url": f"https://quote.eastmoney.com/bk/90.{board['code']}.html",
    }


def screen_oversold(concurrency: int = SECTOR_CONCURRENCY) -> dict:
    trade_date = get_last_trade_date()
    boards = fetch_industry_boards()
    items: list[dict] = []
    evaluated = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(evaluate_board, board): board for board in boards}
        for future in as_completed(futures):
            try:
                result = future.result()
            except (OSError, ValueError, KeyError):
                logger.warning("超跌板块日 K 获取失败：%s", futures[future]["code"])
                continue
            if result:
                items.append(result)
            evaluated += 1
    required = max(1, (len(boards) * 4 + 4) // 5)
    if evaluated < required:
        raise RuntimeError("超跌板块有效行业数据不足，本次不保存快照")
    items.sort(key=lambda item: (item["percentile"], item["rsi"]))
    for rank, item in enumerate(items, 1):
        item["rank"] = rank
    save_oversold_snapshot(trade_date, items)
    return {"trade_date": trade_date, "items": items}


def refresh_oversold(force: bool = False) -> dict:
    trade_date = get_last_trade_date()
    existing = get_oversold_snapshot(trade_date)
    if existing and not force:
        return {"trade_date": trade_date, "reused": True, "items": existing["items"]}
    result = screen_oversold()
    result["reused"] = False
    return result


def scheduled_oversold() -> dict:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.weekday() < 5 and now.time() < time(15, 10):
        return {"skipped": True, "reason": "等待当日收盘数据"}
    return refresh_oversold()


def latest_oversold() -> dict | None:
    return get_latest_oversold_snapshot()
