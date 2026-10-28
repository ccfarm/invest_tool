from datetime import datetime, timezone

import pytest

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
    monkeypatch.setattr(
        microcap,
        "fetch_daily_closes",
        lambda code, **kw: {f"2026-07-{10 + i:02d}": 10 + i for i in range(21)},
    )
    monkeypatch.setattr(microcap, "fetch_ths_concepts", lambda code: ["机器人", "专精特新"])

    result = microcap.screen_microcap(pool_size=100, top_n=20)

    assert result["trade_date"] == "2026-08-07"
    assert len(result["items"]) == 20
    assert all(i["code"] not in {"920000", "000002", "000003"} for i in result["items"])
    assert all(i["code"].startswith("000") for i in result["items"])
    blacklist = get_blacklisted_codes()
    assert "000002" in blacklist and "000003" in blacklist
    assert len(result["blacklisted"]) == 2
    assert result["items"][0]["month_change_pct"] == 200.0
    assert result["items"][0]["ths_concept_count"] == 2
    assert result["items"][0]["ths_concepts"] == ["机器人", "专精特新"]


@pytest.mark.no_db
def test_fetch_ths_concepts_parses_regular_and_other(monkeypatch):
    page = """
    <td class="gnName" clid="1"> 机器人 </td>
    <td class="gnStockList" tag="其他概念-AI手机">AI手机</td>
    <td class="gnName">机器人</td>
    """
    monkeypatch.setattr(microcap, "_get_ths_concept_page", lambda code: page)

    assert microcap.fetch_ths_concepts("000001") == ["机器人", "AI手机"]


@pytest.mark.no_db
def test_calculate_month_change_uses_20_trading_days():
    closes = {f"2026-08-{i:02d}": float(i) for i in range(1, 22)}

    assert microcap.calculate_month_change(closes, "2026-08-21") == 2000.0
    assert microcap.calculate_month_change(dict(list(closes.items())[:20]), "2026-08-20") is None


def test_refresh_reuses_same_date(monkeypatch):
    monkeypatch.setattr(microcap, "fetch_kline", lambda **kw: _bars("2026-08-05", "2026-08-06", "2026-08-07"))
    save_microcap_snapshot("2026-08-07", [{"rank": 1, "code": "000001", "name": "旧快照", "mktcap_yi": 1.0}])

    def enrich(items, trade_date):
        items[0].update({
            "month_change_pct": 3.5,
            "ths_concept_count": 1,
            "ths_concepts": ["银行"],
        })

    monkeypatch.setattr(microcap, "enrich_microcap_items", enrich)

    def should_not_screen(*a, **kw):
        raise AssertionError("同交易日不应重新筛选")

    monkeypatch.setattr(microcap, "screen_microcap", should_not_screen)
    result = microcap.refresh_microcap()
    assert result["reused"] is True
    assert result["items"][0]["name"] == "旧快照"
    assert result["items"][0]["month_change_pct"] == 3.5


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
    monkeypatch.setattr(microcap, "fetch_ths_concepts", lambda code: ["概念A"])

    result = microcap.backfill_microcap(days=10)

    assert len(result["filled"]) == 9
    assert "2026-08-07" not in result["filled"]
    items = get_microcap_snapshot("2026-07-28")["items"]
    assert items == [{
        "rank": 1,
        "board": "创业板",
        "code": "300000",
        "name": "候选A",
        "mktcap_yi": 10.0,
        "month_change_pct": None,
        "ths_concepts": ["概念A"],
        "ths_concept_count": 1,
    }]
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


@pytest.mark.no_db
@pytest.mark.parametrize(
    ("code", "board"),
    [("000929", "中小板"), ("001001", "中小板"), ("002001", "中小板"),
     ("003001", "中小板"), ("600001", "主板"), ("601001", "主板"),
     ("603001", "主板"), ("605001", "主板"), ("688001", "科创板"),
     ("689001", "科创板"), ("300001", "创业板"), ("301001", "创业板"),
     ("920001", None)],
)
def test_board_code_groups(code, board):
    assert microcap.board_for_code(code) == board


@pytest.mark.no_db
def test_screen_separates_lanzhou_from_shanghai(monkeypatch):
    monkeypatch.setattr(microcap, "fetch_market_stocks_with_cap", lambda: [
        _stock("000929", "兰州黄河", 100),
        _stock("002001", "深市候选", 200),
        _stock("600001", "沪市候选", 300, "SH"),
    ])
    monkeypatch.setattr(microcap, "get_blacklisted_codes", set)
    monkeypatch.setattr(microcap, "check_announcement_risk", lambda code: None)
    items, _ = microcap._screen_items(top_n=1)
    assert [(item["board"], item["code"], item["rank"]) for item in items] == [
        ("中小板", "000929", 1), ("主板", "600001", 1),
    ]


@pytest.mark.no_db
def test_refresh_rebuilds_old_board_snapshot(monkeypatch):
    monkeypatch.setattr(microcap, "get_last_trade_date", lambda: "2026-10-27")
    monkeypatch.setattr(microcap, "get_microcap_snapshot", lambda date: {
        "items": [{"code": "000929", "board": "主板"}],
    })
    monkeypatch.setattr(microcap, "screen_microcap", lambda: {
        "trade_date": "2026-10-27", "items": [], "blacklisted": [],
    })
    monkeypatch.setattr(microcap, "save_microcap_snapshot", lambda *args: None)
    assert microcap.refresh_microcap()["reused"] is False
