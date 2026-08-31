import os
import tempfile
from pathlib import Path

# 测试使用独立临时数据库，避免污染真实数据
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
# 测试不启动内置增量爬虫（避免联网）
os.environ["ENABLE_SCHEDULED_CRAWL"] = "0"
# 测试不启动微盘股定时任务（避免联网）
os.environ["ENABLE_SCHEDULED_MICROCAP"] = "0"
# 与 test_api.py 中登录用例保持一致（默认值可被外部环境变量覆盖）
os.environ.setdefault("AUTH_USERNAME", "ccfarm")
os.environ.setdefault("AUTH_PASSWORD", "5800969q")

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import AUTH_PASSWORD, AUTH_USERNAME, TOKEN_TTL_SECONDS
from app.db import create_session, init_auth_user, upsert_holdings
from app.main import app

# 测试使用最小前端产物，保证 SPA 路由/爬虫快照测试不依赖仓库内是否已构建
_FAKE_DIST = Path(tempfile.mkdtemp())
_FAKE_DIST.joinpath("index.html").write_text(
    '<!doctype html><html><head><title>股东查询 - A股股东持股记录</title></head>'
    '<body><div id="app"></div></body></html>',
    encoding="utf-8",
)
main_module.FRONTEND_DIST = _FAKE_DIST


@pytest.fixture(autouse=True)
def seed_db():
    init_auth_user(AUTH_USERNAME, AUTH_PASSWORD)
    upsert_holdings(
        [
            {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "market": "SH",
                "holder_name": "张三",
                "hold_num": 1250000,
                "hold_num_ratio": 0.1,
                "change_text": "增加",
                "end_date": "2026-06-30",
                "holder_rank": 5,
            },
            {
                "stock_code": "000858",
                "stock_name": "五粮液",
                "market": "SZ",
                "holder_name": "张三",
                "hold_num": 890000,
                "hold_num_ratio": 0.2,
                "change_text": "减少",
                "end_date": "2026-06-30",
                "holder_rank": 6,
            },
            {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "market": "SH",
                "holder_name": "张三",
                "hold_num": 1200000,
                "hold_num_ratio": 0.1,
                "change_text": "增加",
                "end_date": "2025-12-31",
                "holder_rank": 5,
            },
        ]
    )


@pytest.fixture()
def auth_headers():
    token, _ = create_session("ccfarm", TOKEN_TTL_SECONDS)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
