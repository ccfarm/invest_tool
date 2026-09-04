"""应用配置（可用环境变量覆盖）。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "shareholders.db")))
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://invest_tool:invest_tool@127.0.0.1:5432/invest_tool"
)

# 定时爬取的股票池（东方财富十大股东）
TRACK_STOCKS = [
    s.strip()
    for s in os.getenv("TRACK_STOCKS", "600519,000858,002594,300750").split(",")
    if s.strip()
]

# 爬取间隔（秒），默认 1 小时
CRAWL_INTERVAL = int(os.getenv("CRAWL_INTERVAL", "3600"))

# 全市场抓取并发数
CONCURRENCY = int(os.getenv("CONCURRENCY", "6"))

# 全市场模式下每只股票抓取的页数（每页约 100 条，即约 10 个披露期）
MARKET_PAGE_LIMIT = int(os.getenv("MARKET_PAGE_LIMIT", "2"))

# 服务内置增量爬虫的执行间隔（秒），默认 24 小时
SCHEDULE_INTERVAL = int(os.getenv("SCHEDULE_INTERVAL", "86400"))

# 登录账号（唯一账号，密码明文仅用于首次生成哈希，DB 中只存哈希）
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "test")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "test")

# 登录 token 有效期（秒），默认 7 天
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", str(7 * 24 * 3600)))

# 微盘股自动拉取间隔（秒），默认 6 小时
MICROCAP_INTERVAL = int(os.getenv("MICROCAP_INTERVAL", "21600"))

# 微盘股每个板块的入选数量
MICROCAP_TOP_N_PER_BOARD = int(os.getenv("MICROCAP_TOP_N_PER_BOARD", "10"))

# 微盘股自动补记：检查最近 N 个交易日，缺失则补一次
MICROCAP_BACKFILL_DAYS = int(os.getenv("MICROCAP_BACKFILL_DAYS", "10"))

# 补记时按历史市值筛选的候选池大小（当前市值最低的前 N 只）
MICROCAP_BACKFILL_POOL = int(os.getenv("MICROCAP_BACKFILL_POOL", "300"))

# 趋势向上自动拉取间隔（秒），默认 6 小时
TREND_INTERVAL = int(os.getenv("TREND_INTERVAL", "21600"))

# MA20 需要连续上行的交易日数
TREND_UP_DAYS = int(os.getenv("TREND_UP_DAYS", "10"))

# 入选数量：按换手率升序取前 N 只
TREND_TOP_N = int(os.getenv("TREND_TOP_N", "30"))

# 筛选与悬停 K 线使用的日 K 根数（约 3 个自然月）
TREND_KLINE_DAYS = int(os.getenv("TREND_KLINE_DAYS", "75"))

# 悬停 K 线内存缓存有效期（秒）
TREND_KLINE_TTL = int(os.getenv("TREND_KLINE_TTL", "300"))

# 趋势筛选并发拉取日 K 的线程数
TREND_CONCURRENCY = int(os.getenv("TREND_CONCURRENCY", "8"))

# 强势板块：先按近 10 个交易日涨幅取前 20 个行业，再按均线多头个股占比排序
SECTOR_INTERVAL = int(os.getenv("SECTOR_INTERVAL", "3600"))
SECTOR_TOP_N = int(os.getenv("SECTOR_TOP_N", "20"))
SECTOR_CONCURRENCY = int(os.getenv("SECTOR_CONCURRENCY", "12"))
