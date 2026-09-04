# 投资工具箱

一个以 Next.js 为 Web 全栈、Python 为数据采集器的 A 股工具箱。页面与 API 由
Next.js App Router 提供；股东、微盘股、趋势和 K 线数据由 Python 抓取；两者通过
PostgreSQL 共享持久化数据。

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
python -m app.scheduler
```

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
`MICROCAP_INTERVAL`、`TREND_INTERVAL`、`TREND_UP_DAYS`、`TREND_TOP_N`、
`TREND_KLINE_DAYS` 与 `TREND_CONCURRENCY`。
