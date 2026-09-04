"""供定时器和 Next.js 调用的 Python 数据采集入口。"""
from __future__ import annotations

import argparse
import json

from .crawler import crawl_market
from .microcap import refresh_microcap, scheduled_microcap
from .sector import refresh_sectors, scheduled_sectors
from .trend import fetch_trend_kline, refresh_trend, scheduled_trend


def main() -> None:
    parser = argparse.ArgumentParser(description="投资工具箱 Python 采集任务")
    parser.add_argument("job", choices=["market", "microcap", "trend", "sector", "scheduled-microcap", "scheduled-trend", "scheduled-sector", "kline"])
    parser.add_argument("value", nargs="?")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.job == "market": result = crawl_market(force=args.force) or {"ok": True}
    elif args.job == "microcap": result = refresh_microcap(force=args.force)
    elif args.job == "trend": result = refresh_trend(force=args.force)
    elif args.job == "sector": result = refresh_sectors(force=args.force)
    elif args.job == "scheduled-microcap": result = scheduled_microcap()
    elif args.job == "scheduled-trend": result = scheduled_trend()
    elif args.job == "scheduled-sector": result = scheduled_sectors()
    else:
        if not args.value or len(args.value) != 6 or not args.value.isdigit(): raise SystemExit("股票代码必须是 6 位数字")
        result = {"code": args.value, "bars": fetch_trend_kline(args.value)}
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__": main()
