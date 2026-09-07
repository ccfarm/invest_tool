"""在无数据库的采集节点生成超跌板块快照 JSON。"""
from __future__ import annotations

import json
import sys

from app import oversold


def main() -> None:
    oversold.save_oversold_snapshot = lambda trade_date, items: None
    json.dump(oversold.screen_oversold(), sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
