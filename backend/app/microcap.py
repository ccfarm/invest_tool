"""微盘股筛选模块。

=====================================================================
筛选逻辑设计（代码注释即设计文档）
=====================================================================

目标：每个交易日收盘后，选出全 A 股中总市值最低的 20 只"干净"股票，
并持久化快照，供页面按钮触发、历史下拉查看。

步骤：

1. 最近完整交易日（get_last_trade_date）
   - 用新浪日 K 线（sz000001）判断：有日 K 数据的日子即为交易日，
     天然覆盖周末与法定节假日，无需维护节假日表。
   - 若最后一根 K 线的日期 == 今天 且 当前时间 < 15:00（A 股收盘时间），
     说明今天的日 K 尚未完成，取倒数第二根 K 线的日期作为"最近完整交易日"；
     否则最后一根 K 线的日期即为最近完整交易日。

2. 拉取全 A 股列表（东方财富 push2delay 行情接口，按市值排序分页）
   - 取字段：f12（代码）、f14（名称）、f20（总市值，单位元）。
   - fs 只选沪深：沪主板（m:0+t:6）、科创板（m:0+t:80）、
     深主板/中小板（m:1+t:2）、创业板（m:1+t:23）——天然不含北交所。
   - 保留：沪市（600/601/603/605/688/689）、深市主板（000/001/002/003）、
     创业板（300/301）、科创板（688）——即覆盖"主板+中小板+创业板+科创板"。
   - 过滤：总市值缺失（"-"，多为已退市/PT 股）的直接跳过。

3. 基础排除（按名称）
   - 名称含 "ST" / "*ST" / "退" / "PT" 的股票直接排除，并写入黑名单
     （reason = "ST/退市名称"）。

4. 黑名单（百年内不需要重复判断）
   - microcap_blacklist 表按 code 唯一，含 reason 与入库时间。
   - 每次筛选先取黑名单集合，黑名单股票直接跳过，
     不再查公告、不再重复判断；"百年"= 永久生效（人工删除才解除）。

5. ST 风险评估（公告排查）
   - 对市值最低的候选池（默认前 100 只）逐只拉取最近公告
     （东方财富公告接口 np-anotice-stock.eastmoney.com），只匹配标题关键词：
       · 退市风险警示 / 其他风险警示 / 实施风险警示
       · 被立案调查 / 立案调查
       · 无法表示意见 / 保留意见（审计意见异常）
       · 可能被实施 / 存在退市风险 / 终止上市 / 退市整理
       · 净资产为负 / 连续亏损 / 扣非净利润为负
       · 股价低于面值 / 面值退市 / 重大违法
   - 命中任一关键词 → 加入黑名单（reason = "公告风险:<关键词>"），从候选移除。
   - 说明：公告标题匹配是"风险提示"近似方案，存在漏报可能；
     后续可扩展为读取公告正文或接入交易所风险名单。

6. 取结果与快照
   - 剩余候选按总市值升序，取前 20 只。
   - 快照按 trade_date 唯一写入 microcap_snapshots；
     同一天再次触发时直接复用已有快照，不重复计算（refresh_microcap 检查）。

7. 历史缺失补记（backfill_microcap）
   - 每 6 小时定时任务会检查近 10 个交易日是否有缺失快照；
   - 有缺失时按【历史市值】补齐：历史市值 = 当日收盘价（日K）× 总股本
     （总股本用当前值近似），对候选池逐日重算后取最低 20 只；
   - 保证历史下拉里的市值是"该交易日"的市值，而不是当前市值。
=====================================================================
"""
from __future__ import annotations

import json
import logging
import time as time_mod
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time
from zoneinfo import ZoneInfo

from .config import MICROCAP_BACKFILL_DAYS, MICROCAP_BACKFILL_POOL
from .crawler import USER_AGENT
from .db import (
    add_blacklist,
    get_blacklisted_codes,
    get_latest_microcap_snapshot,
    get_microcap_snapshot,
    save_microcap_snapshot,
)

logger = logging.getLogger(__name__)

KLINE_URL = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
CLIST_URL = "https://push2delay.eastmoney.com/api/qt/clist/get"
ANNOUNCE_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann"
CLOSE_HOUR = 15  # A 股收盘时间（Asia/Shanghai）

# 公告标题风险关键词（见模块头设计说明）
RISK_KEYWORDS = (
    "退市风险警示",
    "其他风险警示",
    "实施风险警示",
    "被立案调查",
    "立案调查",
    "无法表示意见",
    "保留意见",
    "可能被实施",
    "存在退市风险",
    "终止上市",
    "退市整理",
    "净资产为负",
    "连续亏损",
    "扣非净利润为负",
    "股价低于面值",
    "面值退市",
    "重大违法",
)


def _get(url: str, timeout: int = 30, retries: int = 3) -> str:
    """带重试的 GET：新浪限流（456/429）与临时错误时指数退避重试。"""
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://finance.sina.com.cn/",
    }
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="ignore").lstrip("\ufeff")
        except urllib.error.HTTPError as exc:
            if exc.code in (456, 429, 500, 502, 503, 504) and attempt < retries - 1:
                time_mod.sleep(2**attempt)
                continue
            raise
        except OSError:
            if attempt < retries - 1:
                time_mod.sleep(2**attempt)
                continue
            raise


def fetch_kline(symbol: str = "sz000001", datalen: int = 5) -> list[dict]:
    """新浪日 K 线（升序）。"""
    params = {"symbol": symbol, "scale": 240, "ma": "no", "datalen": datalen}
    url = f"{KLINE_URL}?{urllib.parse.urlencode(params)}"
    return json.loads(_get(url)) or []


def get_last_trade_date(now: datetime | None = None) -> str:
    """最近一个完整交易日（YYYY-MM-DD）。"""
    now = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    bars = fetch_kline(datalen=5)
    if not bars:
        raise RuntimeError("无法获取交易日历（新浪日 K 无数据）")
    last = bars[-1]
    today = now.date().isoformat()
    if last["day"] == today and now.time() < time(CLOSE_HOUR, 0):
        # 今日未收盘，日 K 未完成，取上一个交易日
        return bars[-2]["day"]
    return last["day"]


def fetch_market_stocks_with_cap() -> list[dict]:
    """全 A 股列表（沪深，含总市值 mktcap 与现价 price，单位元；按市值升序）。"""
    stocks: list[dict] = []
    page = 1
    while True:
        params = {
            "pn": page,
            "pz": 100,
            "po": 0,  # 市值升序
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f20",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f12,f13,f14,f2,f20",
        }
        url = f"{CLIST_URL}?{urllib.parse.urlencode(params)}"
        data = json.loads(_get(url)) or {}
        diff = (data.get("data") or {}).get("diff") or []
        for item in diff:
            cap = item.get("f20")
            if cap in (None, "-"):
                continue  # 无有效市值（多为已退市/PT 股）
            price = item.get("f2")
            if price in (None, "-"):
                price = None  # 停牌等无现价，补记时无法估算股本则跳过
            code = item["f12"]
            market = "SH" if code.startswith(("6", "9")) else "SZ"
            stocks.append(
                {
                    "code": code,
                    "name": item["f14"],
                    "market": market,
                    "mktcap": float(cap),
                    "price": float(price) if price else None,
                }
            )
        total = (data.get("data") or {}).get("total") or 0
        if not diff or page * 100 >= total:
            break
        page += 1
    return stocks


def fetch_daily_closes(code: str, datalen: int = 20) -> dict[str, float]:
    """某股票最近日 K 收盘价：{日期: 收盘价}。"""
    prefix = "sh" if code.startswith(("6", "9")) else "sz"
    bars = fetch_kline(symbol=f"{prefix}{code}", datalen=datalen)
    return {b["day"]: float(b["close"]) for b in bars}


def check_announcement_risk(code: str) -> str | None:
    """拉取最近公告标题，命中风险关键词则返回关键词，否则 None。"""
    params = {
        "sr": "-1",
        "page_size": 20,
        "page_index": 1,
        "ann_type": "A",
        "stock_list": code,
        "f_node": 0,
        "s_node": 0,
    }
    url = f"{ANNOUNCE_URL}?{urllib.parse.urlencode(params)}"
    data = json.loads(_get(url)) or {}
    for ann in (data.get("data") or {}).get("list") or []:
        title = ann.get("title") or ""
        for kw in RISK_KEYWORDS:
            if kw in title:
                return kw
    return None


def screen_microcap(pool_size: int = 100, top_n: int = 20) -> dict:
    """执行筛选（步骤 2~6），返回 {trade_date, items, blacklisted}。"""
    items, newly_blacklisted = _screen_items(pool_size, top_n)
    trade_date = get_last_trade_date()
    save_microcap_snapshot(trade_date, items)
    return {
        "trade_date": trade_date,
        "items": items,
        "blacklisted": newly_blacklisted,
    }


def _screen_items(pool_size: int = 100, top_n: int = 20) -> tuple[list[dict], list[dict]]:
    """筛选管线（不含交易日判定），返回 (items, newly_blacklisted)。"""
    stocks = fetch_market_stocks_with_cap()
    blacklist = get_blacklisted_codes()
    newly_blacklisted: list[dict] = []

    def exclude(code: str, name: str, reason: str) -> None:
        add_blacklist(code, name, reason)
        blacklist.add(code)
        newly_blacklisted.append({"code": code, "name": name, "reason": reason})

    candidates: list[dict] = []
    for s in stocks:
        if s["market"] == "BJ":
            continue  # 不含北交所
        if s["code"] in blacklist:
            continue  # 黑名单：百年内不重复判断
        if "ST" in s["name"].upper() or "退" in s["name"] or "PT" in s["name"].upper():
            exclude(s["code"], s["name"], "ST/退市名称")
            continue
        candidates.append(s)

    candidates.sort(key=lambda s: s["mktcap"])
    pool = candidates[:pool_size]

    # ST 风险：公告排查候选池
    for s in pool:
        if s["code"] in blacklist:
            continue
        try:
            kw = check_announcement_risk(s["code"])
        except (OSError, ValueError):
            logger.warning("公告排查失败：%s，按无风险处理", s["code"])
            continue
        if kw:
            exclude(s["code"], s["name"], f"公告风险:{kw}")

    results = [s for s in candidates if s["code"] not in blacklist][:top_n]
    items = [
        {
            "rank": i + 1,
            "code": s["code"],
            "name": s["name"],
            "mktcap_yi": round(s["mktcap"] / 1e8, 2),
        }
        for i, s in enumerate(results)
    ]
    return items, newly_blacklisted


def backfill_microcap(
    days: int = MICROCAP_BACKFILL_DAYS,
    pool_size: int = MICROCAP_BACKFILL_POOL,
) -> dict:
    """近 N 个交易日缺失检测：缺失则按【历史市值】补齐。

    历史市值 = 当日收盘价 × 总股本（总股本用当前值近似，短窗口内基本稳定）。
    流程：
    1. 取当前市值最低的前 pool_size 只作为候选池（10 天窗口内微盘股变动有限，覆盖足够）；
    2. 逐只拉取最近日 K 收盘价；
    3. 对每个缺失交易日，用当日收盘价×总股本计算历史市值，
       排除黑名单 / ST / 退 / PT 后取最低 20 只，存入该交易日快照。
    说明：ST 状态与股本按当前值近似；同日已存在则不覆盖。
    """
    bars = fetch_kline(datalen=days + 5)
    trade_dates = [b["day"] for b in bars][-days:]
    missing = [d for d in trade_dates if get_microcap_snapshot(d) is None]
    if not missing:
        return {"missing": [], "filled": []}

    stocks = fetch_market_stocks_with_cap()
    candidates = [s for s in stocks if s["price"]][:pool_size]
    blacklist = get_blacklisted_codes()

    closes_by_code: dict[str, dict[str, float]] = {}
    for s in candidates:
        try:
            closes_by_code[s["code"]] = fetch_daily_closes(s["code"])
        except (OSError, ValueError):
            continue

    filled: list[str] = []
    for d in missing:
        rows: list[dict] = []
        for s in candidates:
            if s["market"] == "BJ":
                continue  # 不含北交所
            close = closes_by_code.get(s["code"], {}).get(d)
            if close is None or s["code"] in blacklist:
                continue
            if "ST" in s["name"].upper() or "退" in s["name"] or "PT" in s["name"].upper():
                continue
            # 总股本 ≈ 当前总市值 / 当前价；历史市值 = 当日收盘价 × 总股本
            shares = s["mktcap"] / s["price"]
            rows.append(
                {"code": s["code"], "name": s["name"], "hist_cap": close * shares}
            )
        rows.sort(key=lambda r: r["hist_cap"])
        items = [
            {
                "rank": i + 1,
                "code": r["code"],
                "name": r["name"],
                "mktcap_yi": round(r["hist_cap"] / 1e8, 2),
            }
            for i, r in enumerate(rows[:20])
        ]
        save_microcap_snapshot(d, items)
        filled.append(d)
    logger.info("微盘股按历史市值补齐 %d 个缺失交易日：%s", len(filled), missing)
    return {"missing": missing, "filled": filled, "pool": len(candidates)}


def scheduled_microcap() -> dict:
    """每 6 小时定时任务：刷新最近完整交易日 + 补齐近 N 个交易日缺失。"""
    refreshed = refresh_microcap()
    backfilled = backfill_microcap()
    return {"refreshed": refreshed, "backfill": backfilled}


def refresh_microcap(force: bool = False) -> dict:
    """触发刷新：先判定交易日；同日期已有快照则直接复用，否则重新筛选。"""
    trade_date = get_last_trade_date()
    existing = get_microcap_snapshot(trade_date)
    if existing and not force:
        return {
            "trade_date": trade_date,
            "reused": True,
            "items": existing["items"],
            "blacklisted": [],
        }
    result = screen_microcap()
    save_microcap_snapshot(trade_date, result["items"])
    result["reused"] = False
    return result


def latest_microcap() -> dict | None:
    return get_latest_microcap_snapshot()
