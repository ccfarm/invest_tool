# 投资工具箱

一个以 Next.js 为 Web 全栈、Python 为数据采集器的 A 股工具箱。页面与 API 由
Next.js App Router 提供；股东、微盘股、趋势、红利低波和 K 线数据由 Python 抓取；两者通过
PostgreSQL 共享持久化数据。

桌面端使用左侧固定导航，手机端点击左上角“导航”展开左侧菜单；登录和主题切换位于菜单底部。

## 技术架构

```
浏览器 ──> Next.js 页面 / Route Handlers ──> PostgreSQL
                         │
                         └── 按需调用 Python（刷新、K 线）
Python 独立调度进程 ────────────────────────> PostgreSQL
```

- `frontend/app/`：Next.js 页面、SSR metadata、API Route Handlers
- `frontend/components/`：React 客户端交互组件
- `frontend/lib/db.js`：Node.js PostgreSQL 数据访问和登录会话
- `backend/app/crawler.py`：十大股东采集
- `backend/app/microcap.py`：微盘股采集
- `backend/app/trend.py`：趋势筛选与 K 线采集
- `backend/app/dividend.py`：连续分红与低波动股票筛选
- `backend/app/jobs.py`：单次采集命令入口
- `backend/app/scheduler.py`：独立常驻调度器

FastAPI 不再参与生产运行；历史 Python 测试和模块暂时保留，便于验证采集算法。

## 本地运行

需要 Node.js 22+ 与 Python 3.10+。

```bash
./start.sh
```

浏览器访问 <http://localhost:80>。开发模式：

```bash
cd frontend
npm install
PYTHON_BIN=../backend/.venv/bin/python npm run dev
```

开发服务默认端口是 3000。通过 `DATABASE_URL` 指定 PostgreSQL，例如
`postgresql://invest_tool:password@127.0.0.1:5432/invest_tool`。

## Python 数据采集

```bash
cd backend
source .venv/bin/activate

python -m app.crawler --stock 600519
python -m app.crawler --holder 贵州茅台
python -m app.jobs market
python -m app.jobs market --force
python -m app.jobs microcap
python -m app.jobs trend
python -m app.jobs dividend
python -m app.scheduler
```

微盘股快照除总市值外，还保存截至快照日近 20 个交易日的涨跌幅，以及同花顺 F10
中的常规概念和其他概念。页面展示概念数量，鼠标悬停或键盘聚焦后可查看完整列表。

`/valuecap` 为低价小盘稳健榜：每日从沪深 A 股中筛选股价 2—15 元、总市值
20—100 亿元、当日成交额不少于 3000 万元的股票，排除 ST、退市名称及近期公告
风险，按低价、小盘、面值安全、流动性和估值质量计算 100 分制得分并展示前 10 名。
公告接口暂时不可用时不会中断整份榜单，页面会将对应股票标为“待核验”。
结果按交易日保存，`VALUECAP_INTERVAL` 可配置定时检查间隔（默认 6 小时，同日复用）。

生产环境用 `invest-tool-crawler.service` 单独运行调度器。Web 服务和爬虫服务可以分别
重启与扩容，不再把耗时采集线程放进 Web 进程。

## API

- `GET /api/health`
- `GET /api/search?q=600519&page=1&page_size=20`
- `GET|POST /api/pv`
- `GET /api/microcap/latest|dates|history?date=YYYY-MM-DD`
- `POST /api/microcap/refresh`
- `GET /api/trend/latest|dates|history?date=YYYY-MM-DD`
- `POST /api/trend/refresh`
- `GET /api/trend/kline?code=600519`
- `GET /api/dividend/latest|dates|history?date=YYYY-MM-DD`
- `POST /api/dividend/refresh`
- `GET /api/sectors/latest`
- `POST /api/sectors/refresh`
- `GET /api/oversold/latest`
- `POST /api/oversold/refresh`
- `POST /api/auth/login|logout`、`GET /api/auth/me`

## 验证与部署

```bash
cd frontend && npm install && npm run build
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile backend/app/jobs.py backend/app/scheduler.py
./scripts/smoke_test.sh

docker build -t invest-tools .
docker run -p 80:80 -v invest-data:/app/backend/data invest-tools
```

服务器部署脚本会安装并初始化 PostgreSQL、从旧 SQLite 完成一次性数据导入，并注册两个 systemd 服务：`invest-tool.service`（Next.js）与
`invest-tool-crawler.service`（Python）。生产数据库默认位于
`/var/lib/postgresql/`；旧 SQLite 文件会保留作为回滚备份。

## 配置

常用环境变量：`DATABASE_URL`、`DB_PATH`（仅旧库迁移）、`DATA_DIR`、`PYTHON_BIN`、`SITE_URL`、
`AUTH_USERNAME`、`AUTH_PASSWORD`、`TOKEN_TTL_SECONDS`、`TRACK_STOCKS`、
`CONCURRENCY`、`MARKET_PAGE_LIMIT`、`CRAWL_INTERVAL`、`SCHEDULE_INTERVAL`、
`MICROCAP_INTERVAL`、`MICROCAP_TOP_N_PER_BOARD`（每板默认 10）、`TREND_INTERVAL`、`TREND_UP_DAYS`、`TREND_TOP_N`、
`TREND_KLINE_DAYS`、`TREND_CONCURRENCY`、`SECTOR_INTERVAL`、`SECTOR_TOP_N` 与
`SECTOR_CONCURRENCY`、`SECTOR_MIN_STOCKS`、`OVERSOLD_INTERVAL`、
`OVERSOLD_RSI_PERIOD`、`OVERSOLD_LOOKBACK` 与 `OVERSOLD_PERCENTILE`。

顶部导航“红利低波”筛选最近 5 个完整财年均实施现金分红、5 年平均股息率不低于
3% 的沪深 A 股；先按平均股息率取候选池，再按近 60 个交易日年化波动率从低到高
精选。页面同时展示当日、近 20 日、近 60 日涨幅、RSI(14)、近 250 日 RSI 分位和
近 5 年股价分位。相关参数可通过 `DIVIDEND_INTERVAL`、`DIVIDEND_YEARS`、
`DIVIDEND_MIN_AVG_YIELD`、`DIVIDEND_CANDIDATE_POOL`、`DIVIDEND_TOP_N`、
`DIVIDEND_KLINE_DAYS` 与 `DIVIDEND_CONCURRENCY` 调整。

顶部导航“右侧品种”每天针对最近完整交易日生成一次：先按东方财富行业板块近
10 个交易日涨幅取前 20（仅统计成分股数量大于 10 的行业），再按成分股中
`MA5 > MA10 > MA20` 的比例降序展示。

顶部导航“超跌板块”同样只统计成分股数量大于 10 的行业；计算 RSI(14)，筛选当前值
位于自身最近 200 个交易日 RSI 序列倒数 5% 分位的行业，每日收盘后生成快照。

## 最近强势与新高

- `/strong`：沪深北 A 股按前复权收盘价计算近20个交易日涨幅，降序取前20只。
- `/newhigh`：当日的前复权收盘价严格超过此前五年最高收盘价；排除上市未满
  三年的股票，上市三至五年按上市以来历史比较。结果按月涨幅降序展示。
- 两页展示交易板块、行业、主要概念（同花顺概念列表前三项）、题材（完整概念列表）
  和近1个月涨幅。概念获取失败时显示“暂无数据”，不生成推测题材。
- 月涨幅不足21根日线或当日无成交日线的股票不参与筛选；保留 ST 股票。
- `python -m app.jobs strong` / `python -m app.jobs newhigh` 手动采集，
  加 `--force` 重算同日快照。`GET /api/{strong,newhigh}/latest` 读取快照，
  `POST /api/{strong,newhigh}/refresh?force=true` 强制刷新。
- 独立调度器默认每6小时尝试刷新，交易日15:10前等待收盘；
  `ENABLE_SCHEDULED_STRONG=0`、`ENABLE_SCHEDULED_NEWHIGH=0` 可分别禁用。
  首次全市场扫描耗时较长；任何行情请求失败均不覆盖已有快照。
