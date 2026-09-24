"""A 股低价小盘稳健榜：每日按可解释规则筛选并保存前 10 名。"""
from __future__ import annotations

import json
import logging
import urllib.parse

from .db import (
    get_latest_valuecap_snapshot,
    get_valuecap_snapshot,
    save_valuecap_snapshot,
)
from .microcap import CLIST_URL, _get, check_announcement_risk, get_last_trade_date

logger = logging.getLogger(__name__)

MIN_PRICE = 2.0
MAX_PRICE = 15.0
MIN_CAP = 2_000_000_000.0
MAX_CAP = 10_000_000_000.0
MIN_AMOUNT = 30_000_000.0
TOP_N = 10
RISK_POOL = 60


def _number(value) -> float | None:
    if value in (None, "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_market_candidates() -> list[dict]:
    """获取沪深 A 股行情指标；北交所暂不纳入榜单。"""
    rows: list[dict] = []
    page = 1
    while True:
        params = {
            "pn": page,
            "pz": 200,
            "po": 0,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f20",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f2,f3,f6,f9,f12,f14,f20,f23",
        }
        data = json.loads(_get(f"{CLIST_URL}?{urllib.parse.urlencode(params)}")) or {}
        payload = data.get("data") or {}
        diff = payload.get("diff") or []
        for item in diff:
            rows.append(
                {
                    "code": str(item.get("f12") or ""),
                    "name": str(item.get("f14") or ""),
                    "price": _number(item.get("f2")),
                    "change_pct": _number(item.get("f3")),
                    "amount": _number(item.get("f6")),
                    "pe": _number(item.get("f9")),
                    "mktcap": _number(item.get("f20")),
                    "pb": _number(item.get("f23")),
                }
            )
        total = int(payload.get("total") or 0)
        if not diff or page * 200 >= total:
            break
        page += 1
    return rows


def exclusion_reason(stock: dict) -> str | None:
    name = stock["name"].upper()
    if "ST" in name or "退" in name or "PT" in name:
        return "风险警示股票"
    price, cap, amount = stock["price"], stock["mktcap"], stock["amount"]
    if price is None or not MIN_PRICE <= price <= MAX_PRICE:
        return "股价不在2—15元"
    if cap is None or not MIN_CAP <= cap <= MAX_CAP:
        return "市值不在20—100亿元"
    if amount is None or amount < MIN_AMOUNT:
        return "成交额不足3000万元"
    return None


def score_stock(stock: dict) -> tuple[float, dict[str, float]]:
    """100 分：低价25、小盘25、面值安全20、流动性15、估值质量15。"""
    price = stock["price"]
    cap = stock["mktcap"]
    amount = stock["amount"]
    price_score = 25 * (MAX_PRICE - price) / (MAX_PRICE - MIN_PRICE)
    cap_score = 25 * (MAX_CAP - cap) / (MAX_CAP - MIN_CAP)
    safety_score = 20 * min(1.0, max(0.0, (price - 1.0) / 4.0))
    liquidity_score = 15 * min(1.0, amount / 200_000_000.0)
    quality_score = 0.0
    if stock["pe"] is not None and 0 < stock["pe"] <= 60:
        quality_score += 7.5
    if stock["pb"] is not None and 0 < stock["pb"] <= 5:
        quality_score += 7.5
    parts = {
        "low_price": round(price_score, 2),
        "small_cap": round(cap_score, 2),
        "price_safety": round(safety_score, 2),
        "liquidity": round(liquidity_score, 2),
        "valuation_quality": round(quality_score, 2),
    }
    return round(sum(parts.values()), 2), parts


def build_ranking(stocks: list[dict], top_n: int = TOP_N) -> list[dict]:
    candidates = []
    for stock in stocks:
        if exclusion_reason(stock) is not None:
            continue
        score, parts = score_stock(stock)
        candidates.append({**stock, "score": score, "score_parts": parts})
    candidates.sort(key=lambda row: (-row["score"], row["code"]))

    winners = []
    for stock in candidates[:RISK_POOL]:
        try:
            risk = check_announcement_risk(stock["code"])
        except (OSError, ValueError, KeyError):
            logger.warning("低价稳健榜公告排查失败：%s", stock["code"])
            continue  # 无法完成风险核验时宁可不入选
        if risk:
            continue
        winners.append(
            {
                "rank": len(winners) + 1,
                "code": stock["code"],
                "name": stock["name"],
                "score": stock["score"],
                "price": stock["price"],
                "mktcap_yi": round(stock["mktcap"] / 1e8, 2),
                "amount_wan": round(stock["amount"] / 1e4, 2),
                "change_pct": stock["change_pct"],
                "pe": stock["pe"],
                "pb": stock["pb"],
                "score_parts": stock["score_parts"],
            }
        )
        if len(winners) >= top_n:
            break
    return winners


def refresh_valuecap(force: bool = False) -> dict:
    trade_date = get_last_trade_date()
    existing = get_valuecap_snapshot(trade_date)
    if existing and not force:
        return {**existing, "reused": True}
    items = build_ranking(fetch_market_candidates())
    save_valuecap_snapshot(trade_date, items)
    return {"trade_date": trade_date, "items": items, "reused": False}


def latest_valuecap() -> dict | None:
    return get_latest_valuecap_snapshot()


def scheduled_valuecap() -> dict:
    return refresh_valuecap()
