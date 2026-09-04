import json

import pytest

from app import sector

pytestmark = pytest.mark.no_db


def test_is_strong_requires_ma5_above_ma10_above_ma20():
    assert sector.is_strong([float(i) for i in range(1, 21)]) is True
    assert sector.is_strong([10.0] * 20) is False
    assert sector.is_strong([float(i) for i in range(20, 0, -1)]) is False
    assert sector.is_strong([float(i) for i in range(1, 20)]) is False


def test_fetch_industry_boards_uses_industry_scope(monkeypatch):
    seen = []

    def fake_get(url):
        seen.append(url)
        return json.dumps({"data": {"diff": [
            {"f12": "BK1031", "f14": "半导体"},
            {"f12": None, "f14": "无代码"},
        ]}})

    monkeypatch.setattr(sector, "_get", fake_get)
    assert sector.fetch_industry_boards() == [{"code": "BK1031", "name": "半导体"}]
    assert "m%3A90%2Bt%3A2%2Bf%3A%2150" in seen[0]


def test_ten_day_return_uses_eleven_closes(monkeypatch):
    seen = []

    def fake_closes(secid, limit):
        seen.append((secid, limit))
        return [100.0] + [101.0] * 9 + [110.0]

    monkeypatch.setattr(sector, "fetch_kline_closes", fake_closes)
    result = sector._ten_day_return({"code": "BK1031", "name": "半导体"})
    assert seen == [("90.BK1031", 11)]
    assert result["return_10d"] == pytest.approx(10.0)


def test_screen_sectors_prefilters_by_return_then_sorts_by_ratio(monkeypatch):
    boards = [
        {"code": "BK0001", "name": "甲"},
        {"code": "BK0002", "name": "乙"},
        {"code": "BK0003", "name": "丙"},
    ]
    returns = {"BK0001": 3.0, "BK0002": 9.0, "BK0003": 6.0}
    ratios = {"BK0002": 40.0, "BK0003": 80.0}
    saved = []

    monkeypatch.setattr(sector, "get_last_trade_date", lambda: "2026-09-03")
    monkeypatch.setattr(sector, "fetch_industry_boards", lambda: boards)
    monkeypatch.setattr(
        sector,
        "_ten_day_return",
        lambda board: {**board, "return_10d": returns[board["code"]]},
    )
    monkeypatch.setattr(
        sector,
        "_board_strength",
        lambda board, concurrency: {
            "code": board["code"], "name": board["name"],
            "return_10d": board["return_10d"],
            "strong_count": int(ratios[board["code"]] / 10), "valid_count": 10,
            "strong_ratio": ratios[board["code"]], "url": "https://example.com",
        },
    )
    monkeypatch.setattr(sector, "save_sector_snapshot", lambda day, items: saved.append((day, items)))

    result = sector.screen_sectors(top_n=2, concurrency=1)

    assert [item["code"] for item in result["items"]] == ["BK0003", "BK0002"]
    assert [item["rank"] for item in result["items"]] == [1, 2]
    assert saved[0][0] == "2026-09-03"


def test_refresh_sectors_reuses_same_trade_date(monkeypatch):
    monkeypatch.setattr(sector, "get_last_trade_date", lambda: "2026-09-03")
    monkeypatch.setattr(
        sector,
        "get_sector_snapshot",
        lambda day: {
            "trade_date": day,
            "items": [{"code": f"BK{i:04d}", "valid_count": 10} for i in range(20)],
        },
    )
    monkeypatch.setattr(
        sector,
        "screen_sectors",
        lambda: (_ for _ in ()).throw(AssertionError("不应重复计算")),
    )
    result = sector.refresh_sectors()
    assert result["reused"] is True


def test_refresh_sectors_replaces_invalid_snapshot(monkeypatch):
    monkeypatch.setattr(sector, "get_last_trade_date", lambda: "2026-09-03")
    monkeypatch.setattr(
        sector,
        "get_sector_snapshot",
        lambda day: {"trade_date": day, "items": [{"code": "BK1031", "valid_count": 0}]},
    )
    monkeypatch.setattr(
        sector,
        "screen_sectors",
        lambda: {"trade_date": "2026-09-03", "items": [{"valid_count": 8}]},
    )
    result = sector.refresh_sectors()
    assert result["reused"] is False
    assert result["items"][0]["valid_count"] == 8


def test_scheduled_sectors_waits_for_close(monkeypatch):
    class Morning:
        @classmethod
        def now(cls, tz):
            return cls()

        def weekday(self):
            return 1

        def time(self):
            return sector.time(14, 59)

    monkeypatch.setattr(sector, "datetime", Morning)
    monkeypatch.setattr(
        sector,
        "refresh_sectors",
        lambda: (_ for _ in ()).throw(AssertionError("收盘前不应计算")),
    )
    assert sector.scheduled_sectors()["skipped"] is True
