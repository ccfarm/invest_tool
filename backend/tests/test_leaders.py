import pytest

from app import leaders

pytestmark = pytest.mark.no_db


def stock(listed="20200101"):
    return {"code": "600001", "market": 1, "name": "测试", "listing_date": listed}


def bars():
    return [{"date": f"2026-09-{i:02}", "close": 10.0} for i in range(1, 22)] + [
        {"date": "2026-10-14", "close": 20.0}]


def test_month_return_uses_twenty_intervals(monkeypatch):
    monkeypatch.setattr(leaders, "fetch_history", lambda *args: bars())
    assert leaders.evaluate(stock(), "2026-10-14", "strong")["month_change_pct"] == 100


def test_newhigh_listing_age_boundary(monkeypatch):
    monkeypatch.setattr(leaders, "fetch_history", lambda *args: bars())
    assert leaders.evaluate(stock("20231015"), "2026-10-14", "newhigh") is None
    assert leaders.evaluate(stock("20231014"), "2026-10-14", "newhigh")


def test_newhigh_rejects_equal_or_lower_close(monkeypatch):
    history = bars()
    history[0]["close"] = 20
    monkeypatch.setattr(leaders, "fetch_history", lambda *args: history)
    assert leaders.evaluate(stock(), "2026-10-14", "newhigh") is None


def test_newhigh_excludes_prices_outside_five_year_window(monkeypatch):
    history = [{"date": "2021-10-13", "close": 100}] + bars()
    monkeypatch.setattr(leaders, "fetch_history", lambda *args: history)
    assert leaders.evaluate(stock(), "2026-10-14", "newhigh")


def test_rejects_short_history_and_suspended_stock(monkeypatch):
    monkeypatch.setattr(leaders, "fetch_history", lambda *args: bars()[:20])
    assert leaders.evaluate(stock(), "2026-10-14", "strong") is None
    monkeypatch.setattr(leaders, "fetch_history", lambda *args: bars()[:-1])
    assert leaders.evaluate(stock(), "2026-10-14", "strong") is None


def test_strong_ranks_entire_universe_and_keeps_twenty(monkeypatch):
    saved = []
    monkeypatch.setattr(leaders.microcap, "get_last_trade_date", lambda: "2026-10-14")
    monkeypatch.setattr(leaders, "_get_snapshot", lambda *args: None)
    monkeypatch.setattr(leaders, "fetch_universe", lambda: list(range(30)))
    monkeypatch.setattr(leaders, "evaluate", lambda s, *args: {
        "code": str(s), "month_change_pct": s})
    monkeypatch.setattr(leaders, "enrich", lambda item: item)
    monkeypatch.setattr(leaders, "_save_snapshot", lambda *args: saved.append(args))
    result = leaders.refresh_leaders("strong")
    assert [i["month_change_pct"] for i in result["items"]] == list(range(29, 9, -1))
    assert result["items"][-1]["rank"] == 20
    assert len(saved) == 1


def test_same_day_reuses_snapshot(monkeypatch):
    monkeypatch.setattr(leaders.microcap, "get_last_trade_date", lambda: "2026-10-14")
    monkeypatch.setattr(leaders, "_get_snapshot", lambda *args: {"items": []})
    monkeypatch.setattr(leaders, "fetch_universe", lambda: pytest.fail("should reuse"))
    assert leaders.refresh_leaders("newhigh")["reused"]


def test_request_failure_does_not_save_partial_rank(monkeypatch):
    monkeypatch.setattr(leaders.microcap, "get_last_trade_date", lambda: "2026-10-14")
    monkeypatch.setattr(leaders, "_get_snapshot", lambda *args: None)
    monkeypatch.setattr(leaders, "fetch_universe", lambda: [stock()])
    monkeypatch.setattr(leaders, "fetch_history", lambda *args: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(leaders, "_save_snapshot", lambda *args: pytest.fail("partial save"))
    with pytest.raises(OSError):
        leaders.refresh_leaders("strong")
