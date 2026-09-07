"""把可信采集节点生成的超跌板块快照导入生产数据库。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.db import init_db, save_oversold_snapshot


def main() -> None:
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    items = payload["items"]
    if any(item.get("stock_count", 0) <= 10 for item in items):
        raise ValueError("快照包含成分股数量不超过 10 的行业")
    if any(item["rsi"] > item["threshold"] for item in items):
        raise ValueError("快照包含未进入历史倒数 5% 分位的行业")
    init_db()
    save_oversold_snapshot(payload["trade_date"], items)


if __name__ == "__main__":
    main()
