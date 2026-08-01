"""东方财富数据中心爬虫：抓取 A 股十大股东持股数据并入库。"""
from __future__ import annotations

import argparse
import json
import logging
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from .config import CONCURRENCY, CRAWL_INTERVAL, MARKET_PAGE_LIMIT, TRACK_STOCKS
from .db import (
    get_stock_crawled_at,
    set_stock_crawled_at,
    upsert_holdings,
    upsert_stocks,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
REPORT_NAME = "RPT_F10_EH_HOLDERS"
COLUMNS = (
    "SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,END_DATE,HOLDER_NAME,"
    "HOLD_NUM,HOLD_NUM_RATIO,HOLD_NUM_CHANGE,HOLDER_RANK"
)
PAGE_SIZE = 100
PAGE_LIMIT = 5  # 每只股票最多抓取 5 页（约最近 50 个披露期）
CLIST_URL = "https://push2delay.eastmoney.com/api/qt/clist/get"
MARKET_PAGE_SIZE = 100
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def _secucode(code: str) -> str:
    """A 股代码转证券代码，如 600519 -> 600519.SH。"""
    code = code.strip().upper()
    if "." in code:
        return code
    if code.startswith(("92", "4", "8")):
        return f"{code}.BJ"
    if code.startswith(("6", "9")):
        return f"{code}.SH"
    if code.startswith(("0", "3")):
        return f"{code}.SZ"
    return f"{code}.BJ"


def _request(filter_: str, page: int) -> dict:
    params = {
        "reportName": REPORT_NAME,
        "columns": COLUMNS,
        "filter": filter_,
        "pageNumber": page,
        "pageSize": PAGE_SIZE,
        "sortColumns": "END_DATE",
        "sortTypes": "-1",
        "source": "HSF10",
        "client": "PC",
    }
    url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Referer": "https://data.eastmoney.com/"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _fetch_pages(filter_: str, page_limit: int = PAGE_LIMIT) -> list[dict]:
    items: list[dict] = []
    for page in range(1, page_limit + 1):
        result = (_request(filter_, page) or {}).get("result") or {}
        data = result.get("data") or []
        items.extend(data)
        total = result.get("count") or 0
        if not data or page * PAGE_SIZE >= total:
            break
    return items


def fetch_stock(code: str, page_limit: int = PAGE_LIMIT) -> list[dict]:
    """按 A 股代码抓取十大股东记录。"""
    return _fetch_pages(f'(SECUCODE="{_secucode(code)}")', page_limit=page_limit)


def fetch_holder(name: str) -> list[dict]:
    """按股东姓名跨市场抓取持股记录。"""
    return _fetch_pages(f'(HOLDER_NAME="{name}")', page_limit=PAGE_LIMIT)


def fetch_market_stocks() -> list[dict]:
    """全 A 股列表（东方财富行情接口，沪深，分页拉取）。"""
    stocks: list[dict] = []
    page = 1
    while True:
        params = {
            "pn": page,
            "pz": MARKET_PAGE_SIZE,
            "po": 0,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f20",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f12,f13,f14",
        }
        url = f"{CLIST_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        diff = (data.get("data") or {}).get("diff") or []
        for item in diff:
            code = item["f12"]
            market = "SH" if code.startswith(("6", "9")) else "SZ"
            stocks.append({"code": code, "name": item["f14"], "market": market})
        total = (data.get("data") or {}).get("total") or 0
        if not diff or page * MARKET_PAGE_SIZE >= total:
            break
        page += 1

    seen: set[str] = set()
    unique: list[dict] = []
    for s in stocks:
        if s["code"] not in seen:
            seen.add(s["code"])
            unique.append(s)
    return unique


def _to_row(item: dict) -> dict:
    return {
        "stock_code": item["SECURITY_CODE"],
        "stock_name": item["SECURITY_NAME_ABBR"],
        "market": item["SECUCODE"].split(".")[-1],
        "holder_name": item["HOLDER_NAME"],
        "hold_num": int(item["HOLD_NUM"] or 0),
        "hold_num_ratio": item.get("HOLD_NUM_RATIO"),
        "change_text": item.get("HOLD_NUM_CHANGE"),
        "end_date": (item["END_DATE"] or "")[:10],
        "holder_rank": item.get("HOLDER_RANK"),
    }


def is_stale(code: str) -> bool:
    """该股票是否已超过爬取间隔（无记录视为需要抓取）。"""
    last = get_stock_crawled_at(code)
    if not last:
        return True
    last_dt = datetime.fromisoformat(last)
    return (datetime.now(timezone.utc) - last_dt).total_seconds() >= CRAWL_INTERVAL


def crawl_stock(code: str, force: bool = False, page_limit: int = PAGE_LIMIT) -> int:
    if not force and not is_stale(code):
        logger.info("股票 %s：间隔内已抓取，跳过（--force 可强制重抓）", code)
        return 0
    rows = [_to_row(i) for i in fetch_stock(code, page_limit=page_limit)]
    saved = upsert_holdings(rows)
    set_stock_crawled_at(code)
    logger.info("股票 %s：抓取 %d 条，入库 %d 条", code, len(rows), saved)
    return saved


def crawl_holder(name: str) -> int:
    rows = [_to_row(i) for i in fetch_holder(name)]
    saved = upsert_holdings(rows)
    logger.info("股东 %s：抓取 %d 条，入库 %d 条", name, len(rows), saved)
    return saved


def crawl_all(force: bool = False) -> None:
    for code in TRACK_STOCKS:
        try:
            crawl_stock(code, force=force)
        except Exception:
            logger.exception("爬取 %s 失败，跳过", code)


def crawl_market(force: bool = False, limit: int | None = None) -> None:
    """全 A 股抓取：首次为全量，之后自动增量（跳过间隔内已抓取的股票）。"""
    stocks = fetch_market_stocks()
    if limit:
        stocks = stocks[:limit]
    upsert_stocks(stocks)
    codes = [s["code"] for s in stocks]
    logger.info("全市场共 %d 只 A 股，开始抓取（并发 %d，每只 %d 页）...", len(codes), CONCURRENCY, MARKET_PAGE_LIMIT)

    done = skipped = failed = 0
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = {pool.submit(crawl_stock, code, force, MARKET_PAGE_LIMIT): code for code in codes}
        for fut in as_completed(futures):
            code = futures[fut]
            try:
                if fut.result() == 0:
                    skipped += 1
            except Exception:
                failed += 1
                logger.exception("股票 %s 抓取失败", code)
            done += 1
            if done % 100 == 0:
                logger.info("进度：%d / %d（成功 %d，跳过 %d，失败 %d）", done, len(codes), done - skipped - failed, skipped, failed)
    logger.info("全市场抓取结束：成功 %d，跳过 %d，失败 %d", done - skipped - failed, skipped, failed)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = argparse.ArgumentParser(description="股东持股数据爬虫")
    parser.add_argument("--stock", help="按 A 股代码抓取，如 600519")
    parser.add_argument("--holder", help="按股东姓名抓取，如 贵州茅台")
    parser.add_argument("--once", action="store_true", help="只跑一次股票池")
    parser.add_argument("--loop", action="store_true", help="每小时循环爬取股票池")
    parser.add_argument("--market", action="store_true", help="全 A 股抓取（断点续传，每日增量）")
    parser.add_argument("--daily", action="store_true", help="同 --market（每日增量更新）")
    parser.add_argument("--limit", type=int, help="只抓前 N 只（调试用）")
    parser.add_argument("--force", action="store_true", help="忽略断点，强制重新抓取")
    args = parser.parse_args()

    if args.stock:
        crawl_stock(args.stock, force=True)
    elif args.holder:
        crawl_holder(args.holder)
    elif args.once:
        crawl_all(force=args.force)
    elif args.market or args.daily:
        crawl_market(force=args.force, limit=args.limit)
    elif args.loop:
        while True:
            crawl_all(force=args.force)
            time.sleep(CRAWL_INTERVAL)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
