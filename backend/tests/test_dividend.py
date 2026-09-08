from datetime import date, timedelta

import pytest

from app import dividend, microcap

pytestmark = pytest.mark.no_db


def _bars(count=300, start=10.0, step=0.01):
    first = date(2025, 1, 1)
    return [
        {
            "day": (first + timedelta(days=index)).isoformat(),
            "open": str(start + index * step),
            "high": str(start + index * step + 0.1),
            "low": str(start + index * step - 0.1),
            "close": str(start + index * step),
        }
        for index in range(count)
    ]


def test_fiscal_years_uses_five_complete_years():
    assert dividend.fiscal_years("2026-09-08") == [2021, 2022, 2023, 2024, 2025]


def test_continuous_dividend_candidates_requires_every_year(monkeypatch):
    rows = {
        year: [
            {
                "SECURITY_CODE": "600900",
                "SECURITY_NAME_ABBR": "长江电力",
                "DIVIDENT_RATIO": 0.04,
            },
            {
                "SECURITY_CODE": "600001",
                "SECURITY_NAME_ABBR": "缺一年",
                "DIVIDENT_RATIO": 0.08,
            },
        ]
        for year in range(2021, 2026)
    }
    rows[2023] = rows[2023][:1]
    monkeypatch.setattr(dividend, "_fetch_year", lambda year: rows[year])
    result = dividend.continuous_dividend_candidates(list(range(2021, 2026)))
    assert [item["code"] for item in result] == ["600900"]
    assert result[0]["avg_dividend_yield"] == pytest.approx(4.0)


def test_continuous_dividend_candidates_applies_average_yield_floor(monkeypatch):
    monkeypatch.setattr(
        dividend,
        "_fetch_year",
        lambda year: [
            {
                "SECURITY_CODE": "000001",
                "SECURITY_NAME_ABBR": "低股息",
                "DIVIDENT_RATIO": 0.02,
            }
        ],
    )
    assert dividend.continuous_dividend_candidates(list(range(2021, 2026))) == []


def test_evaluate_stock_calculates_requested_metrics(monkeypatch):
    monkeypatch.setattr(microcap, "fetch_kline", lambda **kwargs: _bars())
    result = dividend.evaluate_stock(
        {"code": "600900", "name": "长江电力", "avg_dividend_yield": 4.0}
    )
    assert result["change_day"] > 0
    assert result["change_20d"] > result["change_day"]
    assert result["change_60d"] > result["change_20d"]
    assert result["rsi"] == 100.0
    assert result["rsi_percentile"] == 100.0
    assert result["price_percentile"] == 100.0
    assert result["volatility_60d"] >= 0


def test_percentile_rank():
    assert dividend.percentile_rank([1.0, 2.0, 3.0, 4.0], 2.0) == 50.0
