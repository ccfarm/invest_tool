import json
from datetime import date, timedelta

from app import microcap, trend
from app.db import (
    get_conn,
    get_latest_trend_snapshot,
    get_trend_snapshot,
    save_trend_snapshot,
)


def _rising_closes(n=90, base=10.0, step=0.1):
    """线性上涨序列：MA20 必然逐日上行。"""
    return [base + i * step for i in range(n)]


def _flat_closes(n=90, value=10.0):
    return [value] * n


def _bars(closes):
    start = date(2026, 5, 1)
    return [
        {"day": (start + timedelta(days=i)).isoformat(), "open": str(c), "close": str(c),
         "high": str(c + 0.1), "low": str(c - 0.1)}
        for i, c in enumerate(closes)
    ]


def test_ma20_rising_accepts_uptrend():
    assert trend.is_ma20_rising(_rising_closes(), up_days=10) is True


def test_ma20_rising_rejects_downtrend():
    closes = [100.0 - i * 0.1 for i in range(90)]
    assert trend.is_ma20_rising(closes, up_days=10) is False


def test_ma20_rising_rejects_flat():
    assert trend.is_ma20_rising(_flat_closes(), up_days=10) is False


def test_ma20_rising_rejects_too_short():
    assert trend.is_ma20_rising(_rising_closes(n=29), up_days=10) is False


def test_fetch_market_stocks_with_turnover_filters(monkeypatch):
    payloads = [
        {
            "data": {
                "total": 3,
                "diff": [
                    {"f12": "000003", "f14": "PT金田A", "f2": "-", "f8": 0.0},
                    {"f12": "000005", "f14": "ST星源", "f2": "1.5", "f8": 0.2},
                    {"f12": "601857", "f14": "中国石油", "f2": "8.88", "f8": 0.09},
                ],
            }
        }
    ]
    calls = []

    def fake_get(url):
        calls.append(url)
        return json.dumps(payloads.pop(0))

    monkeypatch.setattr(microcap, "_get", fake_get)
    stocks = trend.fetch_market_stocks_with_turnover()
    assert len(stocks) == 1
    assert stocks[0]["code"] == "601857"
    assert stocks[0]["name"] == "中国石油"
    assert stocks[0]["turnover"] == 0.09
    assert stocks[0]["price"] == 8.88


def _stock(code, name, turnover, price=10.0):
    market = "SH" if code.startswith(("6", "9")) else "SZ"
    return {
        "code": code,
        "name": name,
        "market": market,
        "price": price,
        "turnover": turnover,
    }


def test_screen_trend_selects_lowest_turnover(monkeypatch):
    # 35 只全部通过 MA20，换手率 1~35；第 5 只 MA20 不上行（跳过）
    stocks = [_stock(f"600{100 + i:03d}", f"股{i}", float(i + 1)) for i in range(35)]
    stocks[4]["code"] = "000005"  # 让它返回走平序列

    def fake_kline(symbol="sz000001", **kw):
        if symbol == "sz000005":
            return _bars(_flat_closes())
        return _bars(_rising_closes())

    monkeypatch.setattr(microcap, "fetch_kline", fake_kline)
    monkeypatch.setattr(trend, "fetch_market_stocks_with_turnover", lambda: stocks)
    result = trend.screen_trend(top_n=30, up_days=10)

    assert result["trade_date"] == "2026-07-29"
    assert len(result["items"]) == 30
    assert all(i["rank"] == idx + 1 for idx, i in enumerate(result["items"]))
    assert all(i["turnover"] > 0 for i in result["items"])
    # 换手率升序，且跳过了 000005（换手率 5）
    turnovers = [i["turnover"] for i in result["items"]]
    assert turnovers == sorted(turnovers)
    assert all(i["code"] != "000005" for i in result["items"])
    assert result["items"][0]["code"] == "600100"
    assert result["items"][0]["ma20"] == 17.95


def test_refresh_trend_reuses_same_date(monkeypatch):
    save_trend_snapshot("2026-07-29", [{"rank": 1, "code": "600100", "name": "旧快照"}])
    monkeypatch.setattr(microcap, "fetch_kline", lambda **kw: _bars(_rising_closes()))

    def should_not_screen(*a, **kw):
        raise AssertionError("同交易日不应重新筛选")

    monkeypatch.setattr(trend, "screen_trend", should_not_screen)
    result = trend.refresh_trend()
    assert result["reused"] is True
    assert result["items"][0]["name"] == "旧快照"


def test_trend_snapshot_save_and_query():
    items = [
        {
            "rank": 1,
            "code": "600100",
            "name": "同方股份",
            "price": 12.34,
            "turnover": 0.5,
            "ma20": 11.0,
        }
    ]
    save_trend_snapshot("2026-07-29", items)
    snap = get_trend_snapshot("2026-07-29")
    assert snap["items"] == items
    assert get_latest_trend_snapshot()["trade_date"] == "2026-07-29"


def test_fetch_trend_kline_returns_bars_with_ma20(monkeypatch):
    calls = []

    def fake_kline(symbol="sz000001", **kw):
        calls.append(symbol)
        return _bars(_rising_closes())

    monkeypatch.setattr(microcap, "fetch_kline", fake_kline)
    bars = trend.fetch_trend_kline("000001")
    assert len(bars) == 90
    assert bars[0]["ma20"] is None
    assert bars[-1]["ma20"] is not None
    assert bars[-1]["close"] > bars[0]["close"]
    # 第二次走缓存，不再请求新浪
    trend.fetch_trend_kline("000001")
    assert len(calls) == 1


def test_latest_trend_empty_by_default(client):
    with get_conn() as conn:
        conn.execute("DELETE FROM trend_snapshots")
    resp = client.get("/api/trend/latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trade_date"] is None
    assert body["items"] == []


def test_trend_history_missing_returns_404(client):
    resp = client.get("/api/trend/history", params={"date": "2026-01-01"})
    assert resp.status_code == 404
