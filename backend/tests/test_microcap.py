from datetime import datetime, timezone

from app import microcap
from app.db import get_blacklisted_codes, get_microcap_snapshot, save_microcap_snapshot


def _bars(*days):
    return [{"day": d, "close": "1.00"} for d in days]


def test_last_trade_date_after_close(monkeypatch):
    monkeypatch.setattr(microcap, "fetch_kline", lambda **kw: _bars("2026-08-05", "2026-08-06", "2026-08-07"))
    now = datetime(2026, 8, 7, 15, 30, tzinfo=timezone.utc)
    assert microcap.get_last_trade_date(now) == "2026-08-07"


def test_last_trade_date_before_close_uses_previous(monkeypatch):
    monkeypatch.setattr(microcap, "fetch_kline", lambda **kw: _bars("2026-08-05", "2026-08-06", "2026-08-07"))
    now = datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc)
    assert microcap.get_last_trade_date(now) == "2026-08-06"


def _stock(code, name, mktcap, market="SZ"):
    return {"code": code, "name": name, "market": market, "mktcap": mktcap}


def test_screen_microcap(monkeypatch):
    monkeypatch.setattr(microcap, "fetch_kline", lambda **kw: _bars("2026-08-05", "2026-08-06", "2026-08-07"))
    stocks = [_stock("920000", "北交A", 100, "BJ")]
    stocks.append(_stock("000002", "*ST退股", 200))  # 名称排除
    stocks.append(_stock("000003", "风险股", 300))  # 公告风险排除
    # 30 只普通股，市值 1000~3900
    for i in range(30):
        stocks.append(_stock(f"000{100 + i:03d}", f"普通股{i}", 1000 + i * 100))
    monkeypatch.setattr(microcap, "fetch_market_stocks_with_cap", lambda: stocks)
    monkeypatch.setattr(microcap, "check_announcement_risk", lambda code: "连续亏损" if code == "000003" else None)

    result = microcap.screen_microcap(pool_size=100, top_n=20)

    assert result["trade_date"] == "2026-08-07"
    assert len(result["items"]) == 20
    assert all(i["code"] not in {"920000", "000002", "000003"} for i in result["items"])
    assert all(i["code"].startswith("000") for i in result["items"])
    blacklist = get_blacklisted_codes()
    assert "000002" in blacklist and "000003" in blacklist
    assert len(result["blacklisted"]) == 2


def test_refresh_reuses_same_date(monkeypatch):
    monkeypatch.setattr(microcap, "fetch_kline", lambda **kw: _bars("2026-08-05", "2026-08-06", "2026-08-07"))
    save_microcap_snapshot("2026-08-07", [{"rank": 1, "code": "000001", "name": "旧快照", "mktcap_yi": 1.0}])

    def should_not_screen(*a, **kw):
        raise AssertionError("同交易日不应重新筛选")

    monkeypatch.setattr(microcap, "screen_microcap", should_not_screen)
    result = microcap.refresh_microcap()
    assert result["reused"] is True
    assert result["items"][0]["name"] == "旧快照"


def test_snapshot_save_and_query():
    items = [{"rank": 1, "code": "000001", "name": "平安银行", "mktcap_yi": 2000.0}]
    save_microcap_snapshot("2026-08-07", items)
    snap = get_microcap_snapshot("2026-08-07")
    assert snap["items"] == items
    assert microcap.latest_microcap()["trade_date"] == "2026-08-07"


def test_backfill_fills_missing_days(monkeypatch):
    days = [
        "2026-07-24", "2026-07-25", "2026-07-28", "2026-07-29", "2026-07-30",
        "2026-07-31", "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06",
        "2026-08-07",
    ]
    # trade calendar: 最近 K 线（用于判定交易日）
    monkeypatch.setattr(microcap, "fetch_kline", lambda symbol="sz000001", **kw: _bars(*days))
    save_microcap_snapshot("2026-08-07", [{"rank": 1, "code": "000001", "name": "已有", "mktcap_yi": 1.0}])

    # 候选股票：现价 10 元、总市值 100 亿 → 总股本 10 亿股
    stocks = [
        {"code": "300000", "name": "候选A", "market": "SZ", "mktcap": 1e10, "price": 10.0},
        {"code": "000002", "name": "*ST退股", "market": "SZ", "mktcap": 0.5e10, "price": 5.0},
        {"code": "920000", "name": "北交A", "market": "BJ", "mktcap": 0.3e10, "price": 3.0},
    ]
    monkeypatch.setattr(microcap, "fetch_market_stocks_with_cap", lambda: stocks)

    def fake_closes(code, **kw):
        return {d: 1.0 for d in days}  # 历史收盘价统一 1 元

    monkeypatch.setattr(microcap, "fetch_daily_closes", fake_closes)

    result = microcap.backfill_microcap(days=10)

    assert len(result["filled"]) == 9
    assert "2026-08-07" not in result["filled"]
    items = get_microcap_snapshot("2026-07-28")["items"]
    assert items == [{"rank": 1, "board": "创业板", "code": "300000", "name": "候选A", "mktcap_yi": 10.0}]
    # 历史市值 = 当日收盘 1 元 × 总股本 10 亿股 = 10 亿元
    assert items[0]["mktcap_yi"] == 10.0


def test_backfill_no_gap(monkeypatch):
    days = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]
    monkeypatch.setattr(microcap, "fetch_kline", lambda symbol="sz000001", **kw: _bars(*days))
    for d in days:
        save_microcap_snapshot(d, [{"rank": 1, "code": "000001", "name": "已有", "mktcap_yi": 1.0}])

    def should_not_fetch(*a, **kw):
        raise AssertionError("无缺失不应拉取列表")

    monkeypatch.setattr(microcap, "fetch_market_stocks_with_cap", should_not_fetch)
    assert microcap.backfill_microcap(days=5) == {"missing": [], "filled": []}
