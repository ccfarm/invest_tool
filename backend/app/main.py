from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .auth import verify_password
from .config import (
    AUTH_PASSWORD,
    AUTH_USERNAME,
    BASE_DIR,
    MICROCAP_INTERVAL,
    SCHEDULE_INTERVAL,
    TOKEN_TTL_SECONDS,
)
from .crawler import crawl_market
from .db import (
    create_session,
    delete_session,
    find_session_username,
    get_microcap_snapshot,
    get_password_hash,
    get_pv,
    init_auth_user,
    list_microcap_dates,
    record_pv,
    search,
)
from .microcap import latest_microcap, refresh_microcap, scheduled_microcap

FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
logger = logging.getLogger(__name__)
bearer = HTTPBearer(auto_error=False)


def require_auth_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    """校验并返回 token 明文（登出用）。"""
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    if find_session_username(credentials.credentials) is None:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return credentials.credentials


def require_auth(token: str = Depends(require_auth_token)) -> str:
    """受保护接口的鉴权依赖：返回用户名，无效则 401。"""
    return find_session_username(token)


def _run_scheduled_crawl(stop_event: threading.Event) -> None:
    """服务进程内的增量爬虫：启动立即执行一次，之后按间隔循环。"""
    logger.info(
        "增量爬虫线程已启动：立即执行一次，之后每 %d 秒（%.1f 小时）执行",
        SCHEDULE_INTERVAL,
        SCHEDULE_INTERVAL / 3600,
    )
    while not stop_event.is_set():
        try:
            crawl_market()
        except Exception:
            logger.exception("增量爬取失败，等待下一轮重试")
        stop_event.wait(SCHEDULE_INTERVAL)


def _run_scheduled_microcap(stop_event: threading.Event) -> None:
    """服务进程内的微盘股定时任务：启动立即执行一次，之后每 6 小时执行。"""
    logger.info(
        "微盘股定时任务已启动：立即执行一次，之后每 %d 秒（%.1f 小时）执行",
        MICROCAP_INTERVAL,
        MICROCAP_INTERVAL / 3600,
    )
    while not stop_event.is_set():
        try:
            scheduled_microcap()
        except Exception:
            logger.exception("微盘股定时拉取失败，等待下一轮重试")
        stop_event.wait(MICROCAP_INTERVAL)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_auth_user(AUTH_USERNAME, AUTH_PASSWORD)
    stop_event = threading.Event()
    if os.getenv("ENABLE_SCHEDULED_CRAWL", "1") == "1":
        thread = threading.Thread(
            target=_run_scheduled_crawl,
            args=(stop_event,),
            daemon=True,
            name="incremental-crawler",
        )
        thread.start()
    else:
        logger.info("内置增量爬虫已禁用（ENABLE_SCHEDULED_CRAWL=0）")
    if os.getenv("ENABLE_SCHEDULED_MICROCAP", "1") == "1":
        thread = threading.Thread(
            target=_run_scheduled_microcap,
            args=(stop_event,),
            daemon=True,
            name="microcap-scheduler",
        )
        thread.start()
    else:
        logger.info("微盘股定时任务已禁用（ENABLE_SCHEDULED_MICROCAP=0）")
    yield
    stop_event.set()


app = FastAPI(title="股东查询工具 API", version="0.1.0", lifespan=lifespan)

# 开发阶段允许前端本地访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


class SearchItem(BaseModel):
    stock_code: str
    stock_name: str
    holder_name: str
    hold_num: int
    hold_num_ratio: float | None
    change: int | None
    change_text: str | None
    end_date: str


class SearchResponse(BaseModel):
    query: str
    page: int
    page_size: int
    total: int
    items: list[SearchItem]


class PvResponse(BaseModel):
    today: int
    total: int


class MicrocapItem(BaseModel):
    rank: int
    code: str
    name: str
    mktcap_yi: float


class MicrocapRefreshResponse(BaseModel):
    trade_date: str
    reused: bool
    items: list[MicrocapItem]
    blacklisted: list[dict]


class MicrocapSnapshotResponse(BaseModel):
    trade_date: str | None
    created_at: str | None
    items: list[MicrocapItem]


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    username: str


class MeResponse(BaseModel):
    username: str


@app.get("/api/search", response_model=SearchResponse)
def search_holdings(
    q: str = Query(..., min_length=1, max_length=100, description="股东姓名或 A 股代码"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """按股东姓名或 A 股代码查询持股记录，按披露时间从新到旧。"""
    return search(q, page, page_size)


@app.post("/api/pv", response_model=PvResponse)
def add_pv():
    """PV +1（前端每次页面访问调用）。"""
    return record_pv()


@app.get("/api/pv", response_model=PvResponse)
def read_pv():
    """查询 PV 统计（今日 / 累计）。"""
    return get_pv()


@app.post("/api/microcap/refresh", response_model=MicrocapRefreshResponse)
def microcap_refresh(force: bool = False):
    """触发微盘股筛选：同交易日已存在结果时直接复用，不重复计算。"""
    return refresh_microcap(force=force)


@app.get("/api/microcap/latest", response_model=MicrocapSnapshotResponse)
def microcap_latest():
    """默认展示：最新一次微盘股筛选结果。"""
    snap = latest_microcap()
    if not snap:
        return {"trade_date": None, "created_at": None, "items": []}
    return snap


@app.get("/api/microcap/dates")
def microcap_dates():
    """近 20 次触发日期（含触发时间）。"""
    return {"dates": list_microcap_dates(limit=20)}


@app.get("/api/microcap/history", response_model=MicrocapSnapshotResponse)
def microcap_history(date: str):
    """按触发日期查看历史筛选结果。"""
    snap = get_microcap_snapshot(date)
    if not snap:
        return JSONResponse({"detail": f"未找到 {date} 的快照"}, status_code=404)
    return snap


@app.post("/api/auth/login", response_model=TokenResponse)
def login(body: LoginRequest):
    """登录：校验密码哈希，成功返回会话 token。"""
    stored = get_password_hash(body.username)
    if stored is None or not verify_password(body.password, stored):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token, _expires = create_session(body.username, TOKEN_TTL_SECONDS)
    return {"token": token, "username": body.username}


@app.get("/api/auth/me", response_model=MeResponse)
def me(username: str = Depends(require_auth)):
    """校验当前 token 是否有效。"""
    return {"username": username}


@app.post("/api/auth/logout")
def logout(token: str = Depends(require_auth_token)):
    """登出：使当前 token 失效。"""
    delete_session(token)
    return {"ok": True}


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    """托管前端构建产物（frontend/dist），未命中时回退到 index.html。"""
    if not FRONTEND_DIST.exists():
        return JSONResponse({"detail": "前端未构建，请先运行 npm run build"}, status_code=404)
    target = FRONTEND_DIST / full_path
    if full_path and target.is_file():
        return FileResponse(target)
    return FileResponse(FRONTEND_DIST / "index.html")
