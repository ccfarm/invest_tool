from datetime import datetime, timedelta, timezone

from app import crawler
from app.db import get_stock_crawled_at, set_stock_crawled_at, upsert_stocks


def test_no_record_is_stale():
    assert get_stock_crawled_at("999999") is None
    assert crawler.is_stale("999999") is True


def test_fresh_record_not_stale():
    set_stock_crawled_at("600519")
    assert get_stock_crawled_at("600519") is not None
    assert crawler.is_stale("600519") is False


def test_old_record_stale():
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(timespec="seconds")
    set_stock_crawled_at("600519", at=old)
    assert crawler.is_stale("600519") is True


def test_crawl_stock_skips_when_fresh(monkeypatch):
    set_stock_crawled_at("600519")

    def should_not_call(code):
        raise AssertionError("断点未生效：不应发起网络请求")

    monkeypatch.setattr(crawler, "fetch_stock", should_not_call)
    assert crawler.crawl_stock("600519") == 0


def test_upsert_stocks_idempotent():
    row = {"code": "601398", "name": "工商银行", "market": "SH"}
    assert upsert_stocks([row]) == 1
    assert upsert_stocks([row]) == 0


def test_secucode_mapping():
    assert crawler._secucode("600519") == "600519.SH"
    assert crawler._secucode("000858") == "000858.SZ"
    assert crawler._secucode("300750") == "300750.SZ"
    assert crawler._secucode("920000") == "920000.BJ"
    assert crawler._secucode("830799") == "830799.BJ"
