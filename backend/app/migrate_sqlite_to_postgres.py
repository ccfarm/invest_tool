"""一次性把旧 SQLite 数据完整迁移到 PostgreSQL。"""
from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path

from .db import DATABASE_URL, SCHEMA, get_conn

TABLES = (
    ("stocks", ("code", "name", "market")),
    ("shareholders", ("id", "name")),
    ("holdings", ("id", "stock_code", "shareholder_id", "hold_num", "hold_num_ratio", "change_text", "end_date", "holder_rank", "updated_at")),
    ("crawl_state", ("stock_code", "last_crawled_at")),
    ("pv_stats", ("date", "count")),
    ("microcap_blacklist", ("code", "name", "reason", "created_at")),
    ("microcap_snapshots", ("id", "trade_date", "created_at", "items")),
    ("trend_snapshots", ("id", "trade_date", "created_at", "items")),
    ("users", ("id", "username", "password_hash", "created_at")),
    ("sessions", ("token_hash", "username", "created_at", "expires_at")),
)


def migrate(source: Path) -> dict[str, int]:
    if not source.is_file():
        raise FileNotFoundError(source)
    sqlite = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    sqlite.row_factory = sqlite3.Row
    counts: dict[str, int] = {}
    with get_conn() as postgres:
        postgres.execute(SCHEMA)
        existing = postgres.execute("SELECT COUNT(*) AS n FROM holdings").fetchone()["n"]
        if existing:
            raise RuntimeError(f"PostgreSQL 已有 {existing} 条 holdings，拒绝重复导入")
        for table, columns in TABLES:
            present = sqlite.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if not present:
                continue
            names = ",".join(columns)
            rows = sqlite.execute(f"SELECT {names} FROM {table}")
            with postgres.cursor().copy(f"COPY {table} ({names}) FROM STDIN") as copy:
                count = 0
                for row in rows:
                    copy.write_row(tuple(row[name] for name in columns))
                    count += 1
            counts[table] = count
            logging.info("迁移 %-24s %d 行", table, count)
        for table in ("shareholders", "holdings", "microcap_snapshots", "trend_snapshots", "users"):
            postgres.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}','id'), COALESCE((SELECT MAX(id) FROM {table}),1), (SELECT COUNT(*)>0 FROM {table}))"
            )
    sqlite.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    counts = migrate(args.source)
    print("迁移完成：" + ", ".join(f"{name}={count}" for name, count in counts.items()))


if __name__ == "__main__":
    main()
