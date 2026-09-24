import pytest

from app import valuecap


def _stock(code="000001", name="普通股", price=5.0, cap=4_000_000_000.0,
           amount=100_000_000.0, pe=20.0, pb=2.0):
    return {
        "code": code,
        "name": name,
        "price": price,
        "change_pct": 1.2,
        "amount": amount,
        "pe": pe,
        "mktcap": cap,
        "pb": pb,
    }


@pytest.mark.no_db
def test_exclusion_rules():
    assert valuecap.exclusion_reason(_stock(name="*ST风险")) == "风险警示股票"
    assert valuecap.exclusion_reason(_stock(price=1.5)) == "股价不在2—15元"
    assert valuecap.exclusion_reason(_stock(cap=1_000_000_000)) == "市值不在20—100亿元"
    assert valuecap.exclusion_reason(_stock(amount=10_000_000)) == "成交额不足3000万元"
    assert valuecap.exclusion_reason(_stock()) is None


@pytest.mark.no_db
def test_score_is_explainable_and_bounded():
    score, parts = valuecap.score_stock(_stock())
    assert score == round(sum(parts.values()), 2)
    assert 0 <= score <= 100
    assert set(parts) == {
        "low_price", "small_cap", "price_safety", "liquidity", "valuation_quality"
    }


@pytest.mark.no_db
def test_build_ranking_skips_announcement_risk_and_orders(monkeypatch):
    stocks = [
        _stock("000001", price=3.0, cap=3_000_000_000),
        _stock("000002", price=4.0, cap=4_000_000_000),
        _stock("000003", name="ST测试"),
    ]
    monkeypatch.setattr(
        valuecap,
        "check_announcement_risk",
        lambda code: "立案调查" if code == "000001" else None,
    )
    result = valuecap.build_ranking(stocks)
    assert [item["code"] for item in result] == ["000002"]
    assert result[0]["rank"] == 1


@pytest.mark.no_db
def test_refresh_saves_and_reuses_snapshot(monkeypatch):
    stored = {}
    monkeypatch.setattr(valuecap, "get_last_trade_date", lambda: "2026-09-24")
    monkeypatch.setattr(valuecap, "fetch_market_candidates", lambda: [_stock()])
    monkeypatch.setattr(valuecap, "check_announcement_risk", lambda code: None)
    monkeypatch.setattr(valuecap, "get_valuecap_snapshot", lambda date: stored.get(date))
    monkeypatch.setattr(
        valuecap,
        "save_valuecap_snapshot",
        lambda date, items: stored.update({date: {"trade_date": date, "items": items}}),
    )
    first = valuecap.refresh_valuecap(force=True)
    second = valuecap.refresh_valuecap()
    assert first["reused"] is False
    assert second["reused"] is True
    assert stored["2026-09-24"]["items"][0]["code"] == "000001"
