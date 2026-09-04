"""独立采集调度进程；Web 服务重启不会中断采集配置。"""
from __future__ import annotations

import logging
import threading

from .config import MICROCAP_INTERVAL, SCHEDULE_INTERVAL, SECTOR_INTERVAL, TREND_INTERVAL
from .crawler import crawl_market
from .microcap import scheduled_microcap
from .sector import scheduled_sectors
from .trend import scheduled_trend

logger = logging.getLogger(__name__)

def loop(name: str, task, interval: int, delay: int) -> None:
    stop = threading.Event()
    stop.wait(delay)
    while True:
        try: task()
        except Exception: logger.exception("%s 采集失败", name)
        stop.wait(interval)

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    jobs=(("全市场股东",crawl_market,SCHEDULE_INTERVAL,60),("微盘股",scheduled_microcap,MICROCAP_INTERVAL,30),("趋势",scheduled_trend,TREND_INTERVAL,45),("强势板块",scheduled_sectors,SECTOR_INTERVAL,75))
    threads=[threading.Thread(target=loop,args=job,daemon=True,name=job[0]) for job in jobs]
    for thread in threads: thread.start()
    for thread in threads: thread.join()

if __name__ == "__main__": main()
