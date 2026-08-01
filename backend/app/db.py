"""SQLite 存储层：股票、股东、持股记录。"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import DB_PATH


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS stocks (
                code   TEXT PRIMARY KEY,
                name   TEXT NOT NULL,
                market TEXT
            );

            CREATE TABLE IF NOT EXISTS shareholders (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS holdings (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_code     TEXT NOT NULL REFERENCES stocks(code),
                shareholder_id INTEGER NOT NULL REFERENCES shareholders(id),
                hold_num       INTEGER NOT NULL,
                hold_num_ratio REAL,
                change_text    TEXT,
                end_date       TEXT NOT NULL,
                holder_rank    INTEGER,
                updated_at     TEXT NOT NULL,
                UNIQUE (stock_code, shareholder_id, end_date)
            );

            CREATE INDEX IF NOT EXISTS idx_holdings_end_date
                ON holdings (end_date DESC);

            CREATE INDEX IF NOT EXISTS idx_holdings_shareholder
                ON holdings (shareholder_id);

            CREATE INDEX IF NOT EXISTS idx_holdings_shareholder_date
                ON holdings (shareholder_id, end_date DESC);

            CREATE TABLE IF NOT EXISTS crawl_state (
                stock_code      TEXT PRIMARY KEY,
                last_crawled_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pv_stats (
                date  TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS microcap_blacklist (
                code       TEXT PRIMARY KEY,
                name       TEXT,
                reason     TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS microcap_snapshots (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT UNIQUE,
                created_at TEXT,
                items      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at    TEXT
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                username   TEXT NOT NULL,
                created_at TEXT,
                expires_at TEXT
            );
            """
        )


def upsert_holdings(rows: list[dict]) -> int:
    """写入持股记录，按（股票、股东、披露期）去重更新。"""
    init_db()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    saved = 0
    with get_conn() as conn:
        for row in rows:
            conn.execute(
                "INSERT OR IGNORE INTO stocks (code, name, market) VALUES (?, ?, ?)",
                (row["stock_code"], row["stock_name"], row.get("market")),
            )
            conn.execute(
                "INSERT OR IGNORE INTO shareholders (name) VALUES (?)",
                (row["holder_name"],),
            )
            shareholder_id = conn.execute(
                "SELECT id FROM shareholders WHERE name = ?", (row["holder_name"],)
            ).fetchone()["id"]
            cur = conn.execute(
                """
                INSERT INTO holdings (
                    stock_code, shareholder_id, hold_num, hold_num_ratio,
                    change_text, end_date, holder_rank, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (stock_code, shareholder_id, end_date) DO UPDATE SET
                    hold_num       = excluded.hold_num,
                    hold_num_ratio = excluded.hold_num_ratio,
                    change_text    = excluded.change_text,
                    holder_rank    = excluded.holder_rank,
                    updated_at     = excluded.updated_at
                """,
                (
                    row["stock_code"],
                    shareholder_id,
                    row["hold_num"],
                    row.get("hold_num_ratio"),
                    row.get("change_text"),
                    row["end_date"],
                    row.get("holder_rank"),
                    now,
                ),
            )
            saved += cur.rowcount
    return saved


def upsert_stocks(rows: list[dict]) -> int:
    """写入股票列表（新股票插入，已有忽略）。"""
    init_db()
    saved = 0
    with get_conn() as conn:
        for row in rows:
            cur = conn.execute(
                "INSERT OR IGNORE INTO stocks (code, name, market) VALUES (?, ?, ?)",
                (row["code"], row["name"], row.get("market")),
            )
            saved += cur.rowcount
    return saved


def get_stock_crawled_at(code: str) -> str | None:
    """查询股票最近一次成功抓取时间（无记录返回 None）。"""
    init_db()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT last_crawled_at FROM crawl_state WHERE stock_code = ?",
            (code,),
        ).fetchone()
    return row["last_crawled_at"] if row else None


def set_stock_crawled_at(code: str, at: str | None = None) -> None:
    """记录股票成功抓取时间（默认当前 UTC 时间）。"""
    init_db()
    at = at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO crawl_state (stock_code, last_crawled_at)
            VALUES (?, ?)
            ON CONFLICT (stock_code) DO UPDATE SET
                last_crawled_at = excluded.last_crawled_at
            """,
            (code, at),
        )


def _today() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def record_pv() -> dict:
    """今日 PV +1，返回今日与累计次数。"""
    init_db()
    today = _today()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO pv_stats (date, count) VALUES (?, 1)
            ON CONFLICT (date) DO UPDATE SET count = count + 1
            """,
            (today,),
        )
    return get_pv()


def get_pv() -> dict:
    """查询今日与累计 PV。"""
    init_db()
    today = _today()
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COALESCE(SUM(count), 0) FROM pv_stats"
        ).fetchone()[0]
        today_count = conn.execute(
            "SELECT COALESCE(SUM(count), 0) FROM pv_stats WHERE date = ?",
            (today,),
        ).fetchone()[0]
    return {"today": today_count, "total": total}


def add_blacklist(code: str, name: str, reason: str) -> None:
    """加入微盘股黑名单（百年内不再重复判断，除非人工删除）。"""
    init_db()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO microcap_blacklist (code, name, reason, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (code) DO NOTHING
            """,
            (code, name, reason, now),
        )


def get_blacklisted_codes() -> set[str]:
    init_db()
    with get_conn() as conn:
        rows = conn.execute("SELECT code FROM microcap_blacklist").fetchall()
    return {r["code"] for r in rows}


def save_microcap_snapshot(trade_date: str, items: list[dict]) -> None:
    """保存某交易日微盘股结果快照（同日期覆盖）。"""
    init_db()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO microcap_snapshots (trade_date, created_at, items)
            VALUES (?, ?, ?)
            ON CONFLICT (trade_date) DO UPDATE SET
                created_at = excluded.created_at,
                items      = excluded.items
            """,
            (trade_date, now, json.dumps(items, ensure_ascii=False)),
        )


def get_microcap_snapshot(trade_date: str) -> dict | None:
    init_db()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT trade_date, created_at, items FROM microcap_snapshots WHERE trade_date = ?",
            (trade_date,),
        ).fetchone()
    if not row:
        return None
    return {
        "trade_date": row["trade_date"],
        "created_at": row["created_at"],
        "items": json.loads(row["items"]),
    }


def get_latest_microcap_snapshot() -> dict | None:
    init_db()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT trade_date, created_at, items FROM microcap_snapshots ORDER BY trade_date DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return {
        "trade_date": row["trade_date"],
        "created_at": row["created_at"],
        "items": json.loads(row["items"]),
    }


def list_microcap_dates(limit: int = 20) -> list[dict]:
    """最近 N 次微盘股触发日期（含触发时间，倒序）。"""
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT trade_date, created_at FROM microcap_snapshots ORDER BY trade_date DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"trade_date": r["trade_date"], "created_at": r["created_at"]} for r in rows
    ]


def init_auth_user(username: str, password: str) -> None:
    """首次启动创建唯一账号（已存在则跳过），只存密码哈希。"""
    from .auth import hash_password

    init_db()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, hash_password(password), now),
        )


def get_password_hash(username: str) -> str | None:
    init_db()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    return row["password_hash"] if row else None


def create_session(username: str, ttl_seconds: int) -> tuple[str, str]:
    """创建会话，返回 (明文 token, 过期时间)；DB 只存 token 哈希。"""
    from .auth import generate_token, hash_token

    init_db()
    token = generate_token()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=ttl_seconds)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (
                hash_token(token),
                username,
                now.isoformat(timespec="seconds"),
                expires.isoformat(timespec="seconds"),
            ),
        )
    return token, expires.isoformat(timespec="seconds")


def find_session_username(token: str) -> str | None:
    """校验 token：有效则返回用户名，无效/过期返回 None。"""
    from .auth import hash_token

    init_db()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT username, expires_at FROM sessions WHERE token_hash = ?",
            (hash_token(token),),
        ).fetchone()
    if not row or row["expires_at"] < now:
        return None
    return row["username"]


def delete_session(token: str) -> None:
    from .auth import hash_token

    init_db()
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),)
        )


def _previous_hold_num(conn: sqlite3.Connection, stock_code: str, shareholder_id: int, end_date: str):
    """查同一股票同一股东上一披露期的持股数（走唯一索引）。"""
    row = conn.execute(
        """
        SELECT hold_num FROM holdings
        WHERE stock_code = ? AND shareholder_id = ? AND end_date < ?
        ORDER BY end_date DESC LIMIT 1
        """,
        (stock_code, shareholder_id, end_date),
    ).fetchone()
    return row["hold_num"] if row else None


def search(q: str, page: int = 1, page_size: int = 20) -> dict:
    """按股东姓名（模糊）或 A 股代码（精确）查询持股记录。"""
    init_db()
    q = q.strip()
    if not q:
        return {"query": q, "page": page, "page_size": page_size, "total": 0, "items": []}

    if q.isdigit():
        where, param = "h.stock_code = ?", q
    else:
        # 先在小表 shareholders 上做模糊匹配，再按命中 ID 走索引关联大表
        where = "h.shareholder_id IN (SELECT id FROM shareholders WHERE name LIKE ?)"
        param = f"%{q}%"

    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM holdings h WHERE {where}",
            (param,),
        ).fetchone()[0]

        page_rows = conn.execute(
            f"""
            SELECT h.stock_code, s.name AS stock_name, h.shareholder_id,
                   h.hold_num, h.hold_num_ratio, h.change_text, h.end_date
            FROM holdings h
            JOIN stocks s       ON s.code = h.stock_code
            WHERE {where}
            ORDER BY h.end_date DESC
            LIMIT ? OFFSET ?
            """,
            (param, page_size, (page - 1) * page_size),
        ).fetchall()

        holder_names = {}
        holder_ids = {r["shareholder_id"] for r in page_rows}
        if holder_ids:
            placeholders = ",".join("?" * len(holder_ids))
            holder_names = {
                row["id"]: row["name"]
                for row in conn.execute(
                    f"SELECT id, name FROM shareholders WHERE id IN ({placeholders})",
                    tuple(holder_ids),
                )
            }

        items = []
        for r in page_rows:
            prev = _previous_hold_num(conn, r["stock_code"], r["shareholder_id"], r["end_date"])
            items.append(
                {
                    "stock_code": r["stock_code"],
                    "stock_name": r["stock_name"],
                    "holder_name": holder_names.get(r["shareholder_id"], ""),
                    "hold_num": r["hold_num"],
                    "hold_num_ratio": r["hold_num_ratio"],
                    "change": r["hold_num"] - prev if prev is not None else None,
                    "change_text": r["change_text"],
                    "end_date": r["end_date"],
                }
            )
    return {
        "query": q,
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": items,
    }
