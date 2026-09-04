"""PostgreSQL 存储层：供 Python 数据采集器使用。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://invest_tool:invest_tool@127.0.0.1:5432/invest_tool"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS stocks(code TEXT PRIMARY KEY,name TEXT NOT NULL,market TEXT);
CREATE TABLE IF NOT EXISTS shareholders(id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS holdings(
  id BIGSERIAL PRIMARY KEY,
  stock_code TEXT NOT NULL REFERENCES stocks(code),
  shareholder_id BIGINT NOT NULL REFERENCES shareholders(id),
  hold_num BIGINT NOT NULL,hold_num_ratio DOUBLE PRECISION,change_text TEXT,
  end_date TEXT NOT NULL,holder_rank INTEGER,updated_at TEXT NOT NULL,
  UNIQUE(stock_code,shareholder_id,end_date)
);
CREATE INDEX IF NOT EXISTS idx_holdings_end_date ON holdings(end_date DESC);
CREATE INDEX IF NOT EXISTS idx_holdings_shareholder ON holdings(shareholder_id);
CREATE INDEX IF NOT EXISTS idx_holdings_shareholder_date ON holdings(shareholder_id,end_date DESC);
CREATE TABLE IF NOT EXISTS crawl_state(stock_code TEXT PRIMARY KEY,last_crawled_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pv_stats(date TEXT PRIMARY KEY,count BIGINT NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS microcap_blacklist(code TEXT PRIMARY KEY,name TEXT,reason TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS microcap_snapshots(id BIGSERIAL PRIMARY KEY,trade_date TEXT UNIQUE,created_at TEXT,items TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trend_snapshots(id BIGSERIAL PRIMARY KEY,trade_date TEXT UNIQUE,created_at TEXT,items TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sector_snapshots(id BIGSERIAL PRIMARY KEY,trade_date TEXT UNIQUE,created_at TEXT,items TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(id BIGSERIAL PRIMARY KEY,username TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,created_at TEXT);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,username TEXT NOT NULL,created_at TEXT,expires_at TEXT);
"""


def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(SCHEMA)


def upsert_holdings(rows: list[dict]) -> int:
    init_db()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    saved = 0
    with get_conn() as conn:
        for row in rows:
            conn.execute(
                "INSERT INTO stocks(code,name,market) VALUES(%s,%s,%s) ON CONFLICT(code) DO NOTHING",
                (row["stock_code"], row["stock_name"], row.get("market")),
            )
            shareholder = conn.execute(
                "INSERT INTO shareholders(name) VALUES(%s) ON CONFLICT(name) DO UPDATE SET name=EXCLUDED.name RETURNING id",
                (row["holder_name"],),
            ).fetchone()
            conn.execute(
                """INSERT INTO holdings(stock_code,shareholder_id,hold_num,hold_num_ratio,change_text,end_date,holder_rank,updated_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(stock_code,shareholder_id,end_date) DO UPDATE SET
                hold_num=EXCLUDED.hold_num,hold_num_ratio=EXCLUDED.hold_num_ratio,
                change_text=EXCLUDED.change_text,holder_rank=EXCLUDED.holder_rank,updated_at=EXCLUDED.updated_at""",
                (row["stock_code"], shareholder["id"], row["hold_num"], row.get("hold_num_ratio"),
                 row.get("change_text"), row["end_date"], row.get("holder_rank"), now),
            )
            saved += 1
    return saved


def upsert_stocks(rows: list[dict]) -> int:
    init_db()
    with get_conn() as conn:
        before = sum(conn.execute(
            "INSERT INTO stocks(code,name,market) VALUES(%s,%s,%s) ON CONFLICT(code) DO NOTHING",
            (row["code"], row["name"], row.get("market")),
        ).rowcount for row in rows)
    return before


def get_stock_crawled_at(code: str) -> str | None:
    init_db()
    with get_conn() as conn:
        row = conn.execute("SELECT last_crawled_at FROM crawl_state WHERE stock_code=%s", (code,)).fetchone()
    return row["last_crawled_at"] if row else None


def set_stock_crawled_at(code: str, at: str | None = None) -> None:
    init_db(); at = at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute("INSERT INTO crawl_state(stock_code,last_crawled_at) VALUES(%s,%s) ON CONFLICT(stock_code) DO UPDATE SET last_crawled_at=EXCLUDED.last_crawled_at", (code, at))


def _today() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def record_pv() -> dict:
    init_db(); day = _today()
    with get_conn() as conn:
        conn.execute("INSERT INTO pv_stats(date,count) VALUES(%s,1) ON CONFLICT(date) DO UPDATE SET count=pv_stats.count+1", (day,))
    return get_pv()


def get_pv() -> dict:
    init_db(); day = _today()
    with get_conn() as conn:
        total = conn.execute("SELECT COALESCE(SUM(count),0) AS n FROM pv_stats").fetchone()["n"]
        current = conn.execute("SELECT COALESCE(SUM(count),0) AS n FROM pv_stats WHERE date=%s", (day,)).fetchone()["n"]
    return {"today": int(current), "total": int(total)}


def add_blacklist(code: str, name: str, reason: str) -> None:
    init_db(); now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute("INSERT INTO microcap_blacklist(code,name,reason,created_at) VALUES(%s,%s,%s,%s) ON CONFLICT(code) DO NOTHING", (code,name,reason,now))


def get_blacklisted_codes() -> set[str]:
    init_db()
    with get_conn() as conn: rows = conn.execute("SELECT code FROM microcap_blacklist").fetchall()
    return {row["code"] for row in rows}


def _save_snapshot(table: str, trade_date: str, items: list[dict]) -> None:
    init_db(); now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(f"INSERT INTO {table}(trade_date,created_at,items) VALUES(%s,%s,%s) ON CONFLICT(trade_date) DO UPDATE SET created_at=EXCLUDED.created_at,items=EXCLUDED.items", (trade_date,now,json.dumps(items,ensure_ascii=False)))


def _get_snapshot(table: str, trade_date: str | None = None) -> dict | None:
    init_db()
    with get_conn() as conn:
        row = conn.execute(f"SELECT trade_date,created_at,items FROM {table} WHERE trade_date=%s", (trade_date,)).fetchone() if trade_date else conn.execute(f"SELECT trade_date,created_at,items FROM {table} ORDER BY trade_date DESC LIMIT 1").fetchone()
    return {**row, "items": json.loads(row["items"])} if row else None


def _list_dates(table: str, limit: int) -> list[dict]:
    init_db()
    with get_conn() as conn: return list(conn.execute(f"SELECT trade_date,created_at FROM {table} ORDER BY trade_date DESC LIMIT %s", (limit,)).fetchall())


def save_microcap_snapshot(trade_date: str, items: list[dict]) -> None: _save_snapshot("microcap_snapshots",trade_date,items)
def get_microcap_snapshot(trade_date: str) -> dict | None: return _get_snapshot("microcap_snapshots",trade_date)
def get_latest_microcap_snapshot() -> dict | None: return _get_snapshot("microcap_snapshots")
def list_microcap_dates(limit: int = 20) -> list[dict]: return _list_dates("microcap_snapshots",limit)
def save_trend_snapshot(trade_date: str, items: list[dict]) -> None: _save_snapshot("trend_snapshots",trade_date,items)
def get_trend_snapshot(trade_date: str) -> dict | None: return _get_snapshot("trend_snapshots",trade_date)
def get_latest_trend_snapshot() -> dict | None: return _get_snapshot("trend_snapshots")
def list_trend_dates(limit: int = 20) -> list[dict]: return _list_dates("trend_snapshots",limit)
def save_sector_snapshot(trade_date: str, items: list[dict]) -> None: _save_snapshot("sector_snapshots",trade_date,items)
def get_sector_snapshot(trade_date: str) -> dict | None: return _get_snapshot("sector_snapshots",trade_date)
def get_latest_sector_snapshot() -> dict | None: return _get_snapshot("sector_snapshots")


def init_auth_user(username: str, password: str) -> None:
    from .auth import hash_password
    init_db(); now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES(%s,%s,%s) ON CONFLICT(username) DO NOTHING", (username,hash_password(password),now))


def get_password_hash(username: str) -> str | None:
    init_db()
    with get_conn() as conn: row = conn.execute("SELECT password_hash FROM users WHERE username=%s", (username,)).fetchone()
    return row["password_hash"] if row else None


def create_session(username: str, ttl_seconds: int) -> tuple[str, str]:
    from .auth import generate_token, hash_token
    init_db(); token=generate_token(); now=datetime.now(timezone.utc); expires=now+timedelta(seconds=ttl_seconds)
    with get_conn() as conn:
        conn.execute("INSERT INTO sessions(token_hash,username,created_at,expires_at) VALUES(%s,%s,%s,%s)", (hash_token(token),username,now.isoformat(timespec="seconds"),expires.isoformat(timespec="seconds")))
    return token, expires.isoformat(timespec="seconds")


def find_session_username(token: str) -> str | None:
    from .auth import hash_token
    init_db(); now=datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_conn() as conn: row=conn.execute("SELECT username FROM sessions WHERE token_hash=%s AND expires_at>%s", (hash_token(token),now)).fetchone()
    return row["username"] if row else None


def delete_session(token: str) -> None:
    from .auth import hash_token
    init_db()
    with get_conn() as conn: conn.execute("DELETE FROM sessions WHERE token_hash=%s", (hash_token(token),))


def search(q: str, page: int = 1, page_size: int = 20) -> dict:
    init_db(); q=q.strip()
    if not q: return {"query":q,"page":page,"page_size":page_size,"total":0,"items":[]}
    numeric=q.isdigit(); param=q if numeric else f"%{q}%"
    where="h.stock_code=%s" if numeric else "h.shareholder_id IN (SELECT id FROM shareholders WHERE name LIKE %s)"
    with get_conn() as conn:
        total=conn.execute(f"SELECT COUNT(*) AS n FROM holdings h WHERE {where}",(param,)).fetchone()["n"]
        rows=conn.execute(f"""SELECT h.stock_code,s.name AS stock_name,h.shareholder_id,sh.name AS holder_name,
          h.hold_num,h.hold_num_ratio,h.change_text,h.end_date,
          h.hold_num-LAG(h.hold_num) OVER(PARTITION BY h.stock_code,h.shareholder_id ORDER BY h.end_date) AS change
          FROM holdings h JOIN stocks s ON s.code=h.stock_code JOIN shareholders sh ON sh.id=h.shareholder_id
          WHERE {where} ORDER BY h.end_date DESC LIMIT %s OFFSET %s""",(param,page_size,(page-1)*page_size)).fetchall()
    return {"query":q,"page":page,"page_size":page_size,"total":int(total),"items":list(rows)}
